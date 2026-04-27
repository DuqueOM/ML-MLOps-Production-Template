"""Drift drill (PR-C3 / acceptance #10).

Exercises the drift-detection code path end-to-end against synthetic
deterministic inputs:

  1. Build a synthetic baseline (1000 rows, 3 numeric features, fixed seed).
  2. Synthesise the canonical ``baseline_distributions.parquet`` using
     the same long-form schema the EDA pipeline emits — this is the
     PR-B2 artifact contract the production drift CronJob consumes.
  3. Build a "production" frame with a deliberate +3σ shift on
     ``feature_a`` while leaving ``feature_b`` and ``feature_c`` alone.
  4. Call ``{service}.monitoring.drift_detection.detect_drift`` with
     ``--eda-baseline`` mode. This is the SAME function the production
     CronJob runs.
  5. Assert PSI on the shifted feature crosses the alert threshold,
     PSI on the untouched features stays below warning.
  6. Write an evidence bundle to ``docs/runbooks/drills/drift/<run-id>/``.

The drill is reproducible: same seeds → same PSI values → same verdict.
That property is what makes the test contract auditable.

Usage::

    python -m scripts.drills.run_drift_drill
    python -m scripts.drills.run_drift_drill --output-dir /tmp/drills

Exit codes::

    0 — drill PASSED (drift detected as expected)
    1 — drill FAILED (drift not detected, or untouched feature alerted)
    2 — internal error (synthetic generation, import failure)
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

# Make sibling _drill_common importable when invoked as a script.
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

DRILL_NAME = "drift"
EXPECTED_VERDICT = "alert_on_feature_a"

BASELINE_SEED = 4242
DRIFTED_SEED = 9999
N_ROWS_BASELINE = 1000
N_ROWS_CURRENT = 800
SHIFT_SIGMA = 3.0  # mean shift on feature_a, in std-units


def _import_drift_module():
    """Resolve the rendered service package and import its
    ``monitoring.drift_detection`` submodule.

    The template ships the module at
    ``src/{service}/monitoring/drift_detection.py`` where ``{service}``
    is replaced by ``new-service.sh``. The drill is invoked from the
    SCAFFOLDED service so we discover the package by walking ``src/``.
    """
    repo = Path.cwd()
    src = repo / "src"
    if not src.is_dir():
        raise RuntimeError(f"no src/ directory under {repo}; run drill from service root")
    candidates = [d for d in src.iterdir() if d.is_dir() and (d / "monitoring" / "drift_detection.py").is_file()]
    if not candidates:
        raise RuntimeError("no monitoring/drift_detection.py found under any src/* package")
    pkg = candidates[0].name
    # ``src/`` so ``{pkg}.monitoring.drift_detection`` resolves; ``cwd``
    # so ``common_utils`` (a sibling of ``src/`` in the scaffolded
    # layout) resolves; honour any extra ``DRILL_PYTHONPATH`` injected
    # by the contract test when it runs in the template repo (where
    # ``common_utils`` lives at ``../common_utils``).
    for p in (str(src), str(repo), os.getenv("DRILL_PYTHONPATH", "")):
        if p and p not in sys.path:
            sys.path.insert(0, p)
    return importlib.import_module(f"{pkg}.monitoring.drift_detection"), pkg


def _build_baseline_and_artifacts(tmp_dir: Path) -> tuple[Path, Path]:
    """Return ``(baseline_csv, eda_baseline_dir)``."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(BASELINE_SEED)
    df = pd.DataFrame(
        {
            "feature_a": rng.normal(0.0, 1.0, N_ROWS_BASELINE),
            "feature_b": rng.normal(5.0, 2.0, N_ROWS_BASELINE),
            "feature_c": rng.normal(-2.0, 0.5, N_ROWS_BASELINE),
        }
    )
    baseline_csv = tmp_dir / "baseline.csv"
    df.to_csv(baseline_csv, index=False)

    # Synthesise the canonical EDA baseline_distributions.parquet using
    # the long-form schema documented in common_utils/eda_artifacts.py.
    rows: list[dict[str, Any]] = []
    for col in df.columns:
        edges = np.unique(np.quantile(df[col], np.linspace(0, 1, 11)))
        for i, edge in enumerate(edges):
            rows.append({"feature": col, "kind": "numeric_bin_edge", "key": str(i), "value": float(edge)})
        rows.append({"feature": col, "kind": "numeric_stat", "key": "mean", "value": float(df[col].mean())})
        rows.append({"feature": col, "kind": "numeric_stat", "key": "std", "value": float(df[col].std())})

    # Import the artifact contract to get the canonical filename and
    # version. The drill MUST use the live contract — hard-coding the
    # filename here would let the contract drift away from the drill.
    common_utils = importlib.import_module("common_utils.eda_artifacts")
    out_df = pd.DataFrame(rows)
    out_df["eda_artifact_version"] = common_utils.ARTIFACT_VERSION

    eda_dir = tmp_dir / "eda_artifacts"
    eda_dir.mkdir(exist_ok=True)
    out_df.to_parquet(eda_dir / common_utils.BASELINE_DISTRIBUTIONS_FILENAME, index=False)
    return baseline_csv, eda_dir


def _build_drifted_current(tmp_dir: Path) -> Path:
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(DRIFTED_SEED)
    df = pd.DataFrame(
        {
            "feature_a": rng.normal(SHIFT_SIGMA, 1.0, N_ROWS_CURRENT),  # shifted
            "feature_b": rng.normal(5.0, 2.0, N_ROWS_CURRENT),
            "feature_c": rng.normal(-2.0, 0.5, N_ROWS_CURRENT),
        }
    )
    out = tmp_dir / "current_drifted.csv"
    df.to_csv(out, index=False)
    return out


def run_drill(output_root: Path, work_dir: Path) -> int:
    started_at = utcnow_iso()
    run_id = make_run_id()
    artifacts_dir = output_root / DRILL_NAME / run_id / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    try:
        drift_mod, pkg = _import_drift_module()
    except Exception as exc:  # noqa: BLE001
        logger.error("drill bootstrap failed: %s", exc)
        return 2

    baseline_csv, eda_dir = _build_baseline_and_artifacts(work_dir)
    current_csv = _build_drifted_current(work_dir)

    # The synthetic frames don't match the templated ServiceInputSchema
    # (which is service-specific), so bypass schema validation. Schema
    # validation is exercised by its own contract test (PR-R2-4).
    report = drift_mod.detect_drift(
        reference_path=None,
        current_path=str(current_csv),
        eda_baseline_dir=str(eda_dir),
        skip_schema=True,
    )

    # Persist the drift report next to the evidence so the auditor can
    # reproduce the verdict without re-running anything.
    drift_report_path = artifacts_dir / "drift_report.json"
    drift_report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    summary = report["summary"]
    features = report["features"]
    psi_a = features.get("feature_a", {}).get("psi")
    psi_b = features.get("feature_b", {}).get("psi")
    psi_c = features.get("feature_c", {}).get("psi")

    expected_alerts = {"feature_a"}
    actual_alerts = set(summary.get("alerts", []))

    # Verdict: drift CORRECTLY detected on feature_a, untouched
    # features did NOT alert. Both halves matter — a noisy detector
    # that alerts on everything is just as broken as one that alerts
    # on nothing.
    drift_correct = "feature_a" in actual_alerts
    no_false_positive = (actual_alerts - expected_alerts) == set()
    passed = bool(drift_correct and no_false_positive)
    actual_verdict = (
        "alert_on_feature_a" if (drift_correct and no_false_positive)
        else "drift_missed" if not drift_correct
        else f"false_positive_on:{sorted(actual_alerts - expected_alerts)}"
    )

    observations = [
        f"PSI feature_a = {psi_a} (alert threshold = {drift_mod.DEFAULT_ALERT})",
        f"PSI feature_b = {psi_b} (untouched)",
        f"PSI feature_c = {psi_c} (untouched)",
        f"baseline_source = {summary['baseline_source']} (expected eda_parquet)",
        f"requires_action = {summary['requires_action']}",
        f"alerts = {sorted(actual_alerts)}",
    ]

    evidence = DrillEvidence(
        drill_name=DRILL_NAME,
        run_id=run_id,
        started_at=started_at,
        finished_at=utcnow_iso(),
        expected_verdict=EXPECTED_VERDICT,
        actual_verdict=actual_verdict,
        passed=passed,
        facts={
            "psi_feature_a": psi_a,
            "psi_feature_b": psi_b,
            "psi_feature_c": psi_c,
            "alert_threshold": drift_mod.DEFAULT_ALERT,
            "warning_threshold": drift_mod.DEFAULT_WARNING,
            "baseline_source": summary["baseline_source"],
            "service_package": pkg,
        },
        observations=observations,
        inputs={
            "baseline_seed": BASELINE_SEED,
            "drifted_seed": DRIFTED_SEED,
            "n_rows_baseline": N_ROWS_BASELINE,
            "n_rows_current": N_ROWS_CURRENT,
            "shift_sigma": SHIFT_SIGMA,
        },
        artifacts=["artifacts/drift_report.json"],
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
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="Scratch dir for synthetic CSVs and parquet (default: tempfile)",
    )
    args = parser.parse_args()

    output_root = args.output_dir or default_evidence_root()
    output_root.mkdir(parents=True, exist_ok=True)

    if args.work_dir:
        args.work_dir.mkdir(parents=True, exist_ok=True)
        return run_drill(output_root, args.work_dir)

    import tempfile

    with tempfile.TemporaryDirectory(prefix="drift-drill-") as tmp:
        return run_drill(output_root, Path(tmp))


if __name__ == "__main__":
    sys.exit(main())
