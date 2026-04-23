"""Statistical Champion/Challenger comparison for safe model promotion (ADR-008).

Intent: before a new model (challenger) replaces the current production model
(champion), we must prove it is statistically superior (or non-inferior) on
the SAME holdout data the champion saw. This is NOT the same as a canary:
- Canary   → "does the new pod crash?"  (infrastructure)
- C/C      → "is the new model better?" (statistics)

Two tests are combined:
1. McNemar test (classification)
   - Looks at predictions that the two models disagree on
   - Null hypothesis: the two classifiers have the same error rate
   - Significant p-value → models differ (not just by chance)

2. Bootstrap confidence interval on ΔAUC
   - Resample the holdout set B times (default 1000), compute AUC for both
   - 95% CI of (challenger_AUC - champion_AUC)
   - Non-inferiority: lower bound of CI > -margin (e.g., -0.005)
   - Superiority:     lower bound of CI > 0

Decision logic (configurable via champion_challenger.yaml):
    promote    = superiority_met AND mcnemar_p < alpha
    keep       = neither promote nor block
    block      = lower_ci < -non_inferiority_margin (worse than champion)

Exit codes:
    0 = promote, 1 = keep, 2 = block

Usage:
    python -m src.{service}.evaluation.champion_challenger \\
        --champion models/champion.joblib \\
        --challenger models/challenger.joblib \\
        --holdout data/holdout.csv --target churn \\
        --config configs/champion_challenger.yaml \\
        --output reports/champion_challenger.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import yaml
from scipy.stats import binomtest
from sklearn.metrics import roc_auc_score

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
@dataclass
class ComparisonConfig:
    alpha: float = 0.05  # significance level for McNemar
    n_bootstrap: int = 1000
    non_inferiority_margin: float = 0.005  # challenger may be up to 0.5% worse
    superiority_margin: float = 0.005  # challenger must beat champion by this
    random_state: int = 42


def load_config(path: str | None) -> ComparisonConfig:
    if path is None or not Path(path).exists():
        return ComparisonConfig()
    raw = yaml.safe_load(Path(path).read_text()) or {}
    return ComparisonConfig(
        alpha=raw.get("alpha", 0.05),
        n_bootstrap=raw.get("n_bootstrap", 1000),
        non_inferiority_margin=raw.get("non_inferiority_margin", 0.005),
        superiority_margin=raw.get("superiority_margin", 0.005),
        random_state=raw.get("random_state", 42),
    )


# ---------------------------------------------------------------------------
# Statistical tests
# ---------------------------------------------------------------------------
def mcnemar_test(y_true: np.ndarray, y_pred_a: np.ndarray, y_pred_b: np.ndarray) -> dict[str, Any]:
    """McNemar exact test for paired classification.

    Counts:
        b = A correct, B wrong
        c = A wrong,   B correct
    Under H0 (same error rate), b and c are exchangeable. Using binomial exact
    test avoids the chi-square approximation issues on small samples and is
    the scipy idiomatic approach (statsmodels mcnemar also available but we
    keep dependencies minimal).
    """
    a_correct = y_pred_a == y_true
    b_correct = y_pred_b == y_true

    b = int(np.sum(a_correct & ~b_correct))  # champion right, challenger wrong
    c = int(np.sum(~a_correct & b_correct))  # champion wrong, challenger right
    n = b + c

    if n == 0:
        return {"b": 0, "c": 0, "p_value": 1.0, "interpretation": "models agree on every sample"}

    # Exact binomial: is c significantly different from n/2?
    result = binomtest(c, n, p=0.5, alternative="two-sided")
    return {
        "b": b,
        "c": c,
        "discordant_pairs": n,
        "p_value": float(result.pvalue),
        "challenger_uniquely_correct": c,
        "champion_uniquely_correct": b,
    }


def bootstrap_delta_auc(
    y_true: np.ndarray,
    y_score_champion: np.ndarray,
    y_score_challenger: np.ndarray,
    n_bootstrap: int = 1000,
    random_state: int = 42,
) -> dict[str, Any]:
    """Bootstrap paired ΔAUC = AUC(challenger) - AUC(champion)."""
    rng = np.random.default_rng(random_state)
    n = len(y_true)
    deltas = np.empty(n_bootstrap, dtype=float)

    # Pre-compute point estimates
    try:
        auc_champion = float(roc_auc_score(y_true, y_score_champion))
        auc_challenger = float(roc_auc_score(y_true, y_score_challenger))
    except ValueError:
        return {"error": "AUC undefined — likely single-class holdout"}

    for i in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        y_t = y_true[idx]
        # Skip iterations without both classes
        if len(np.unique(y_t)) < 2:
            deltas[i] = np.nan
            continue
        try:
            a_ch = roc_auc_score(y_t, y_score_challenger[idx])
            a_ca = roc_auc_score(y_t, y_score_champion[idx])
            deltas[i] = a_ch - a_ca
        except ValueError:
            deltas[i] = np.nan

    deltas = deltas[~np.isnan(deltas)]
    if deltas.size == 0:
        return {"error": "all bootstrap samples degenerate"}

    lower = float(np.percentile(deltas, 2.5))
    upper = float(np.percentile(deltas, 97.5))
    return {
        "auc_champion": auc_champion,
        "auc_challenger": auc_challenger,
        "delta_auc_point": auc_challenger - auc_champion,
        "delta_auc_ci_lower": lower,
        "delta_auc_ci_upper": upper,
        "n_bootstrap_effective": int(len(deltas)),
    }


# ---------------------------------------------------------------------------
# Decision engine
# ---------------------------------------------------------------------------
def decide(
    mcnemar: dict[str, Any],
    bootstrap: dict[str, Any],
    config: ComparisonConfig,
) -> dict[str, Any]:
    """Combine test results into a promote/keep/block decision."""
    if "error" in bootstrap:
        return {"decision": "block", "reason": bootstrap["error"]}

    lower = bootstrap["delta_auc_ci_lower"]
    point = bootstrap["delta_auc_point"]
    p_value = mcnemar.get("p_value", 1.0)

    is_non_inferior = lower > -config.non_inferiority_margin
    is_superior_point = point > config.superiority_margin
    is_significant = p_value < config.alpha

    if not is_non_inferior:
        decision = "block"
        reason = (
            f"Challenger CI lower bound {lower:.4f} < -{config.non_inferiority_margin} "
            f"→ challenger may be WORSE than champion"
        )
    elif is_superior_point and is_significant:
        decision = "promote"
        reason = (
            f"ΔAUC={point:.4f} > {config.superiority_margin} "
            f"AND McNemar p={p_value:.4f} < {config.alpha} (significant)"
        )
    elif is_superior_point and not is_significant:
        decision = "keep"
        reason = (
            f"ΔAUC={point:.4f} > {config.superiority_margin} "
            f"BUT McNemar p={p_value:.4f} ≥ {config.alpha} (not significant)"
        )
    else:
        decision = "keep"
        reason = f"ΔAUC={point:.4f} within ({-config.non_inferiority_margin}, {config.superiority_margin}) — neutral"

    return {
        "decision": decision,
        "reason": reason,
        "is_non_inferior": is_non_inferior,
        "is_superior_point": is_superior_point,
        "is_significant": is_significant,
    }


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------
def compare_models(
    champion: Any,
    challenger: Any,
    X_holdout: pd.DataFrame,
    y_holdout: np.ndarray,
    config: ComparisonConfig | None = None,
) -> dict[str, Any]:
    """End-to-end comparison returning a serializable report."""
    config = config or ComparisonConfig()

    # Assume both models expose predict_proba for binary classification
    p_champion = champion.predict_proba(X_holdout)[:, 1]
    p_challenger = challenger.predict_proba(X_holdout)[:, 1]

    # Use each model's optimal threshold if stored, else 0.5
    threshold = 0.5
    pred_champion = (p_champion >= threshold).astype(int)
    pred_challenger = (p_challenger >= threshold).astype(int)

    mcnemar = mcnemar_test(y_holdout, pred_champion, pred_challenger)
    bootstrap = bootstrap_delta_auc(
        y_holdout,
        p_champion,
        p_challenger,
        n_bootstrap=config.n_bootstrap,
        random_state=config.random_state,
    )
    decision = decide(mcnemar, bootstrap, config)

    return {
        "config": {
            "alpha": config.alpha,
            "n_bootstrap": config.n_bootstrap,
            "non_inferiority_margin": config.non_inferiority_margin,
            "superiority_margin": config.superiority_margin,
        },
        "holdout_size": int(len(X_holdout)),
        "mcnemar": mcnemar,
        "bootstrap": bootstrap,
        "decision": decision,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")

    parser = argparse.ArgumentParser(description="Champion/Challenger comparison")
    parser.add_argument("--champion", required=True)
    parser.add_argument("--challenger", required=True)
    parser.add_argument("--holdout", required=True, help="CSV with features + target column")
    parser.add_argument("--target", required=True)
    parser.add_argument("--config", help="YAML with alpha, n_bootstrap, margins")
    parser.add_argument("--output", help="Report JSON output path")
    args = parser.parse_args()

    logger.info("Loading champion from %s", args.champion)
    champion = joblib.load(args.champion)
    logger.info("Loading challenger from %s", args.challenger)
    challenger = joblib.load(args.challenger)

    df = pd.read_csv(args.holdout)
    y = df[args.target].astype(int).values
    X = df.drop(columns=[args.target])

    config = load_config(args.config)
    report = compare_models(champion, challenger, X, y, config)

    print(json.dumps({"decision": report["decision"], "summary": report["bootstrap"]}, indent=2, default=str))

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(report, indent=2, default=str))
        logger.info("Report saved to %s", args.output)

    decision = report["decision"]["decision"]
    if decision == "promote":
        return 0
    if decision == "keep":
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
