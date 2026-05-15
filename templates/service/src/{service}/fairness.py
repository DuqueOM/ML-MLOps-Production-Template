"""Fairness and bias audit module for {ServiceName}.

Computes group-level fairness metrics across protected attributes to detect
disparate impact and equal opportunity violations. Produces a structured
report suitable for CI/CD quality gates.

Key metrics:
- Disparate Impact Ratio (DIR) — 4/5 rule: must be >= 0.80
- Equal Opportunity Difference — TPR gap between groups
- Demographic Parity Difference — positive rate gap

Usage:
    report = run_fairness_audit(
        y_true, y_pred, sensitive_df,
        y_prob=probabilities,
        output_path="results/fairness.json",
    )
    if not report["_summary"]["overall_pass"]:
        raise ValueError("Fairness check FAILED")

TODO: Set PROTECTED_ATTRIBUTES to your domain-specific sensitive features.
TODO: Adjust thresholds if your domain requires stricter/looser bounds.

Choosing Protected Attributes:
    Protected attributes depend on your domain and jurisdiction:
    - Finance (lending): race, sex, age, national_origin (ECOA/Reg B)
    - Healthcare: race, sex, age, disability_status (ACA Section 1557)
    - Employment: race, sex, age, religion, disability (Title VII / ADA)
    - Insurance: varies by state — some prohibit gender, credit score
    - General (GDPR Art. 9): racial/ethnic origin, political opinions,
      religion, trade union, genetic/biometric data, health, sex life

    If you don't have explicit protected attributes in your dataset:
    1. Check if proxy variables exist (zip code → race, name → gender)
    2. Document the absence and the reason in your model card
    3. Consider using fairlearn or AIF360 for proxy detection

Threshold Guidance:
    - DIR >= 0.80 is the US "4/5 rule" (EEOC). It's a starting point, not universal.
    - EU AI Act (2024) may require stricter thresholds for high-risk systems.
    - Some domains need DIR >= 0.90 (healthcare) or accept DIR >= 0.70 (marketing).
    - Document your chosen threshold and rationale in an ADR.

Limitations of DIR:
    - DIR is a group-level metric — it can miss individual-level discrimination.
    - Small subgroups (<30 samples) produce unreliable DIR values.
    - DIR doesn't capture intersectional fairness (e.g., Black women vs White men).
    - A passing DIR doesn't guarantee fairness — combine with Equal Opportunity,
      Calibration, and qualitative review.
    - Consider using fairlearn.MetricFrame for more comprehensive audits.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

logger = logging.getLogger(__name__)

# Thresholds per the 4/5 (80%) rule
DISPARATE_IMPACT_THRESHOLD = 0.80
EQUAL_OPPORTUNITY_THRESHOLD = 0.80
CALIBRATION_PARITY_THRESHOLD = 0.05
DIR_CONSULTATION_UPPER = 0.85


def calibration_error(y_true: np.ndarray, y_prob: np.ndarray, *, n_bins: int = 10) -> float:
    """Mean absolute calibration error over equal-width probability bins."""
    y_true = np.asarray(y_true)
    y_prob = np.asarray(y_prob)
    if len(y_true) == 0:
        return 0.0

    bins = np.linspace(0.0, 1.0, n_bins + 1)
    # Keep probability == 1.0 in the final bin.
    bin_ids = np.clip(np.digitize(y_prob, bins, right=False) - 1, 0, n_bins - 1)
    weighted_error = 0.0
    for bin_id in range(n_bins):
        mask = bin_ids == bin_id
        if not mask.any():
            continue
        weighted_error += float(mask.mean()) * abs(float(y_prob[mask].mean()) - float(y_true[mask].mean()))
    return weighted_error


def compute_group_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_prob: Optional[np.ndarray] = None,
) -> Dict[str, float]:
    """Compute classification metrics for a single demographic group."""
    n = len(y_true)
    if n == 0:
        return {}

    metrics: Dict[str, float] = {
        "n_samples": n,
        "positive_rate": float(y_pred.mean()),
        "base_rate": float(y_true.mean()),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "true_positive_rate": float(recall_score(y_true, y_pred, zero_division=0)),
        "false_positive_rate": float(np.sum((y_pred == 1) & (y_true == 0)) / max(np.sum(y_true == 0), 1)),
    }

    if y_prob is not None and len(np.unique(y_true)) > 1:
        metrics["auc"] = float(roc_auc_score(y_true, y_prob))
        metrics["calibration_error"] = float(calibration_error(y_true, y_prob))

    return metrics


def compute_fairness_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    sensitive_features: pd.DataFrame,
    y_prob: Optional[np.ndarray] = None,
    disparate_impact_threshold: float = DISPARATE_IMPACT_THRESHOLD,
    equal_opportunity_threshold: float = EQUAL_OPPORTUNITY_THRESHOLD,
    calibration_parity_threshold: float = CALIBRATION_PARITY_THRESHOLD,
    consultation_upper: float = DIR_CONSULTATION_UPPER,
) -> Dict[str, Any]:
    """Compute fairness metrics across all protected attribute columns.

    For each attribute computes:
    - Per-group classification metrics
    - Disparate Impact Ratio (positive_rate_min / positive_rate_max)
    - Equal Opportunity Difference (TPR gap)
    - Demographic Parity Difference (positive_rate gap)
    """
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    if y_prob is not None:
        y_prob = np.asarray(y_prob)

    report: Dict[str, Any] = {}

    for attr in sensitive_features.columns:
        groups = sensitive_features[attr].unique()
        group_metrics: Dict[str, Any] = {}

        for group in sorted(groups):
            mask = sensitive_features[attr].values == group
            gm = compute_group_metrics(
                y_true[mask],
                y_pred[mask],
                y_prob[mask] if y_prob is not None else None,
            )
            group_metrics[str(group)] = gm

        # Cross-group fairness indicators
        positive_rates = [gm["positive_rate"] for gm in group_metrics.values() if gm.get("positive_rate") is not None]
        tpr_values = [
            gm["true_positive_rate"] for gm in group_metrics.values() if gm.get("true_positive_rate") is not None
        ]
        fpr_values = [
            gm["false_positive_rate"] for gm in group_metrics.values() if gm.get("false_positive_rate") is not None
        ]
        calibration_errors = [
            gm["calibration_error"] for gm in group_metrics.values() if gm.get("calibration_error") is not None
        ]

        fairness_indicators: Dict[str, Any] = {}

        if positive_rates and max(positive_rates) > 0:
            di_ratio = min(positive_rates) / max(positive_rates)
            fairness_indicators["disparate_impact_ratio"] = round(di_ratio, 4)
            fairness_indicators["disparate_impact_pass"] = di_ratio >= disparate_impact_threshold
            fairness_indicators["consultation_required"] = disparate_impact_threshold <= di_ratio < consultation_upper

        if tpr_values:
            eo_diff = max(tpr_values) - min(tpr_values)
            fairness_indicators["equal_opportunity_difference"] = round(eo_diff, 4)
            fairness_indicators["equal_opportunity_pass"] = 1.0 - eo_diff >= equal_opportunity_threshold

        if positive_rates:
            dp_diff = max(positive_rates) - min(positive_rates)
            fairness_indicators["demographic_parity_difference"] = round(dp_diff, 4)

        if fpr_values:
            fairness_indicators["equalized_odds_fpr_gap"] = round(max(fpr_values) - min(fpr_values), 4)

        if calibration_errors:
            calibration_gap = max(calibration_errors) - min(calibration_errors)
            fairness_indicators["calibration_parity_difference"] = round(calibration_gap, 4)
            fairness_indicators["calibration_parity_pass"] = calibration_gap <= calibration_parity_threshold

        report[attr] = {"groups": group_metrics, "fairness": fairness_indicators}

    return report


def compute_intersectional_fairness(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    sensitive_features: pd.DataFrame,
    y_prob: Optional[np.ndarray] = None,
    min_samples_per_cell: int = 30,
    disparate_impact_threshold: float = DISPARATE_IMPACT_THRESHOLD,
    consultation_upper: float = DIR_CONSULTATION_UPPER,
) -> Dict[str, Any]:
    """Compute DIR across all 2-way combinations of protected attributes (C6).

    Per-attribute DIR can pass while specific COMBINATIONS (e.g., Black
    women) fail — a well-documented blind spot of univariate fairness
    audits. This function enumerates every unordered pair of protected
    attribute columns and computes a DIR for the joint distribution.

    Args:
        min_samples_per_cell: groups with fewer samples are marked
            ``insufficient_data`` rather than reported (avoids noisy DIRs
            from tiny cells, per the module's Limitations note).

    Returns a nested dict:
        {
          "(attr_a, attr_b)": {
            "groups": { "(value_a, value_b)": { "positive_rate": ..., "n_samples": ... } },
            "fairness": { "disparate_impact_ratio": ..., "disparate_impact_pass": True/False }
          }
        }
    """
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    if y_prob is not None:
        y_prob = np.asarray(y_prob)

    columns = list(sensitive_features.columns)
    report: Dict[str, Any] = {}

    for i, attr_a in enumerate(columns):
        for attr_b in columns[i + 1 :]:
            key = f"({attr_a}, {attr_b})"
            group_metrics: Dict[str, Any] = {}

            joint = sensitive_features[[attr_a, attr_b]].astype(str).agg(" | ".join, axis=1)
            for group in sorted(joint.unique()):
                mask = joint.values == group
                if mask.sum() < min_samples_per_cell:
                    group_metrics[str(group)] = {
                        "n_samples": int(mask.sum()),
                        "status": "insufficient_data",
                    }
                    continue
                gm = compute_group_metrics(
                    y_true[mask],
                    y_pred[mask],
                    y_prob[mask] if y_prob is not None else None,
                )
                group_metrics[str(group)] = gm

            positive_rates = [
                gm["positive_rate"]
                for gm in group_metrics.values()
                if isinstance(gm, dict) and gm.get("positive_rate") is not None
            ]
            fairness_indicators: Dict[str, Any] = {}
            if positive_rates and max(positive_rates) > 0:
                di_ratio = min(positive_rates) / max(positive_rates)
                fairness_indicators["disparate_impact_ratio"] = round(di_ratio, 4)
                fairness_indicators["disparate_impact_pass"] = di_ratio >= disparate_impact_threshold
                fairness_indicators["consultation_required"] = (
                    disparate_impact_threshold <= di_ratio < consultation_upper
                )
                fairness_indicators["n_groups_evaluated"] = len(positive_rates)

            report[key] = {"groups": group_metrics, "fairness": fairness_indicators}

    return report


def run_fairness_audit(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    sensitive_features: pd.DataFrame,
    y_prob: Optional[np.ndarray] = None,
    output_path: Optional[str | Path] = None,
    intersectional: bool = False,
    min_intersectional_samples: int = 30,
    disparate_impact_threshold: float = DISPARATE_IMPACT_THRESHOLD,
    equal_opportunity_threshold: float = EQUAL_OPPORTUNITY_THRESHOLD,
    calibration_parity_threshold: float = CALIBRATION_PARITY_THRESHOLD,
    consultation_upper: float = DIR_CONSULTATION_UPPER,
) -> Dict[str, Any]:
    """Run a complete fairness audit and optionally save JSON report.

    Args:
        intersectional: if True, also evaluate every 2-way combination
            of protected attributes (C6 — catches subgroup-only bias).
        min_intersectional_samples: cells smaller than this are reported
            as insufficient_data; prevents noisy DIRs from tiny groups.

    Returns the full report including a _summary with overall_pass flag.
    """
    report = compute_fairness_metrics(
        y_true,
        y_pred,
        sensitive_features,
        y_prob,
        disparate_impact_threshold=disparate_impact_threshold,
        equal_opportunity_threshold=equal_opportunity_threshold,
        calibration_parity_threshold=calibration_parity_threshold,
        consultation_upper=consultation_upper,
    )
    intersectional_report: Dict[str, Any] = {}
    if intersectional and len(sensitive_features.columns) >= 2:
        intersectional_report = compute_intersectional_fairness(
            y_true,
            y_pred,
            sensitive_features,
            y_prob,
            min_samples_per_cell=min_intersectional_samples,
            disparate_impact_threshold=disparate_impact_threshold,
            consultation_upper=consultation_upper,
        )
        report["_intersectional"] = intersectional_report

    # Summary: check all fairness gates
    all_pass = True
    consultation_required = False
    summary: List[str] = []

    for attr, data in report.items():
        if attr.startswith("_"):
            continue
        fi = data.get("fairness", {})
        di_pass = fi.get("disparate_impact_pass", True)
        eo_pass = fi.get("equal_opportunity_pass", True)
        calibration_pass = fi.get("calibration_parity_pass", True)

        if not di_pass:
            all_pass = False
            summary.append(f"{attr}: FAIL DI ({fi['disparate_impact_ratio']:.3f} < {disparate_impact_threshold})")
        if fi.get("consultation_required", False):
            consultation_required = True
            summary.append(f"{attr}: CONSULT DI margin ({fi['disparate_impact_ratio']:.3f})")
        if not eo_pass:
            all_pass = False
            summary.append(f"{attr}: FAIL equal opportunity (gap={fi['equal_opportunity_difference']:.3f})")
        if not calibration_pass:
            all_pass = False
            summary.append(f"{attr}: FAIL calibration parity (gap={fi['calibration_parity_difference']:.3f})")

    # Intersectional issues — separate summary so operators see the delta
    for combo, data in intersectional_report.items():
        fi = data.get("fairness", {})
        if fi.get("disparate_impact_pass") is False:
            all_pass = False
            summary.append(f"intersectional {combo}: FAIL DI ({fi['disparate_impact_ratio']:.3f})")
        if fi.get("consultation_required", False):
            consultation_required = True
            summary.append(f"intersectional {combo}: CONSULT DI margin ({fi['disparate_impact_ratio']:.3f})")

    report["_summary"] = {
        "overall_pass": all_pass,
        "consultation_required": consultation_required,
        "issues": summary if summary else ["No fairness violations detected"],
        "intersectional_evaluated": bool(intersectional_report),
        "thresholds": {
            "disparate_impact": disparate_impact_threshold,
            "equal_opportunity": equal_opportunity_threshold,
            "calibration_parity_gap": calibration_parity_threshold,
            "consultation_upper": consultation_upper,
        },
    }

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        logger.info("Fairness report saved to %s", output_path)

    return report
