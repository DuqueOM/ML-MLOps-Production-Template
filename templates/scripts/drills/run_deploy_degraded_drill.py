"""Deploy-degraded drill (PR-C3 / acceptance #10).

Simulates a production rollout where the candidate model is WORSE than
the current champion, and asserts that the statistical
champion/challenger gate (ADR-008) BLOCKS promotion. This is the
template's last line of defense before a degraded model reaches
production users; a drill that reproduces the block is what proves
the gate still works after every refactor.

What it exercises:

  - Champion: a logistic-regression baseline trained on a separable
    synthetic binary task (deterministic seed → AUC ≈ 0.92).
  - Challenger: a deliberately degraded model trained on the SAME
    features but with shuffled labels (pure noise → AUC ≈ 0.50).
  - Holdout: a fresh sample from the same generative process.
  - Gate: ``{service}.evaluation.champion_challenger.compare_models``
    — the production decision engine.

The expected verdict is ``block``; the drill fails (exit 1) if any
other decision comes back, because that means the gate would let a
worse-than-random model into production.

Usage::

    python -m scripts.drills.run_deploy_degraded_drill
    python -m scripts.drills.run_deploy_degraded_drill --output-dir /tmp/drills

Exit codes::

    0 — drill PASSED (gate blocked the degraded challenger)
    1 — drill FAILED (gate did NOT block — this is a P1 escalation)
    2 — internal error (bootstrap, import failure, missing scipy/sklearn)
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from _drill_common import (  # noqa: E402
    DrillEvidence,
    default_evidence_root,
    make_run_id,
    utcnow_iso,
    write_evidence,
)

logger = logging.getLogger(__name__)

DRILL_NAME = "deploy_degraded"
EXPECTED_VERDICT = "block"

DATA_SEED = 7
LABEL_SHUFFLE_SEED = 11
N_TRAIN = 800
N_HOLDOUT = 600
N_FEATURES = 6


def _import_cc_module():
    repo = Path.cwd()
    src = repo / "src"
    if not src.is_dir():
        raise RuntimeError(f"no src/ directory under {repo}; run drill from service root")
    candidates = [
        d for d in src.iterdir()
        if d.is_dir() and (d / "evaluation" / "champion_challenger.py").is_file()
    ]
    if not candidates:
        raise RuntimeError("no evaluation/champion_challenger.py found under any src/* package")
    pkg = candidates[0].name
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    return importlib.import_module(f"{pkg}.evaluation.champion_challenger"), pkg


def _make_dataset():
    """Deterministic separable binary task. Returns
    ``(X_train, y_train, X_holdout, y_holdout)``.
    """
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(DATA_SEED)
    cols = [f"x{i}" for i in range(N_FEATURES)]

    def _sample(n: int, offset: int):
        # Two well-separated Gaussian blobs along a random direction.
        sub_rng = np.random.default_rng(DATA_SEED + offset)
        direction = rng.normal(size=N_FEATURES)
        direction /= np.linalg.norm(direction)
        y = sub_rng.integers(0, 2, size=n)
        noise = sub_rng.normal(size=(n, N_FEATURES))
        signal = (y[:, None] - 0.5) * 2.0 * direction[None, :] * 1.5
        X = pd.DataFrame(signal + noise, columns=cols)
        return X, y.astype(int)

    X_train, y_train = _sample(N_TRAIN, offset=0)
    X_holdout, y_holdout = _sample(N_HOLDOUT, offset=1000)
    return X_train, y_train, X_holdout, y_holdout


def _train_champion(X, y):
    from sklearn.linear_model import LogisticRegression

    clf = LogisticRegression(max_iter=500, random_state=DATA_SEED)
    clf.fit(X, y)
    return clf


def _train_degraded_challenger(X, y):
    """Same algorithm, but train on SHUFFLED labels — challenger
    learns nothing useful → AUC ≈ 0.50 on a fresh holdout.
    """
    import numpy as np
    from sklearn.linear_model import LogisticRegression

    rng = np.random.default_rng(LABEL_SHUFFLE_SEED)
    y_shuffled = y.copy()
    rng.shuffle(y_shuffled)
    clf = LogisticRegression(max_iter=500, random_state=DATA_SEED + 1)
    clf.fit(X, y_shuffled)
    return clf


def run_drill(output_root: Path) -> int:
    started_at = utcnow_iso()
    run_id = make_run_id()
    artifacts_dir = output_root / DRILL_NAME / run_id / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    try:
        cc_mod, pkg = _import_cc_module()
    except Exception as exc:  # noqa: BLE001
        logger.error("drill bootstrap failed: %s", exc)
        return 2

    try:
        X_train, y_train, X_holdout, y_holdout = _make_dataset()
        champion = _train_champion(X_train, y_train)
        challenger = _train_degraded_challenger(X_train, y_train)
    except Exception as exc:  # noqa: BLE001
        logger.error("drill dataset/model bootstrap failed: %s", exc)
        return 2

    config = cc_mod.ComparisonConfig(
        alpha=0.05,
        n_bootstrap=300,  # smaller than prod default (1000) for a fast drill
        non_inferiority_margin=0.005,
        superiority_margin=0.005,
        random_state=DATA_SEED,
    )

    report = cc_mod.compare_models(
        champion=champion,
        challenger=challenger,
        X_holdout=X_holdout,
        y_holdout=y_holdout,
        config=config,
    )

    cc_report_path = artifacts_dir / "champion_challenger.json"
    cc_report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    decision = report["decision"]["decision"]
    reason = report["decision"]["reason"]
    bootstrap = report["bootstrap"]
    mcnemar = report["mcnemar"]

    passed = (decision == EXPECTED_VERDICT)
    actual_verdict = decision

    observations = [
        f"decision = {decision}",
        f"reason = {reason}",
        f"ΔAUC point estimate = {bootstrap.get('delta_auc_point')}",
        f"ΔAUC 95% CI lower = {bootstrap.get('delta_auc_ci_lower')}",
        f"non-inferiority margin = -{config.non_inferiority_margin}",
        f"McNemar p-value = {mcnemar.get('p_value')}",
        f"holdout size = {report.get('holdout_size')}",
    ]
    if not passed:
        observations.append(
            "ESCALATION: gate did NOT block a model trained on shuffled labels. "
            "The C/C decision logic has regressed; treat as P1 until reproduced "
            "with non-synthetic data."
        )

    evidence = DrillEvidence(
        drill_name=DRILL_NAME,
        run_id=run_id,
        started_at=started_at,
        finished_at=utcnow_iso(),
        expected_verdict=EXPECTED_VERDICT,
        actual_verdict=actual_verdict,
        passed=passed,
        facts={
            "decision": decision,
            "delta_auc_point": bootstrap.get("delta_auc_point"),
            "delta_auc_ci_lower": bootstrap.get("delta_auc_ci_lower"),
            "delta_auc_ci_upper": bootstrap.get("delta_auc_ci_upper"),
            "mcnemar_p_value": mcnemar.get("p_value"),
            "service_package": pkg,
        },
        observations=observations,
        inputs={
            "data_seed": DATA_SEED,
            "label_shuffle_seed": LABEL_SHUFFLE_SEED,
            "n_train": N_TRAIN,
            "n_holdout": N_HOLDOUT,
            "n_features": N_FEATURES,
            "n_bootstrap": config.n_bootstrap,
        },
        artifacts=["artifacts/champion_challenger.json"],
    )
    write_evidence(output_root, evidence)
    logger.info(
        "drill=%s run_id=%s passed=%s actual_verdict=%s",
        DRILL_NAME,
        run_id,
        passed,
        actual_verdict,
    )
    return 0 if passed else 1


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Evidence root (default: $DRILL_EVIDENCE_ROOT or docs/runbooks/drills)",
    )
    args = parser.parse_args()

    output_root = args.output_dir or default_evidence_root()
    output_root.mkdir(parents=True, exist_ok=True)
    return run_drill(output_root)


if __name__ == "__main__":
    sys.exit(main())
