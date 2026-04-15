"""Business KPIs derived from model predictions for {ServiceName}.

Translates model metrics into business-meaningful indicators.
Provides functions to compute KPIs from confusion matrix components.

TODO: Replace example KPIs with your actual business metrics.
"""

import logging
from typing import Any

import numpy as np
from sklearn.metrics import confusion_matrix

logger = logging.getLogger(__name__)


def compute_business_kpis(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_prob: np.ndarray,
    cost_fn: float = 100.0,
    cost_fp: float = 10.0,
) -> dict[str, Any]:
    """Compute business KPIs from predictions.

    Args:
        y_true: True labels.
        y_pred: Predicted labels.
        y_prob: Predicted probabilities.
        cost_fn: Business cost of a false negative.
        cost_fp: Business cost of a false positive.

    Returns:
        Dict of business-meaningful KPIs.
    """
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    total = tn + fp + fn + tp

    kpis = {
        # Detection rate — how many positives we catch
        "detection_rate": round(tp / (tp + fn) if (tp + fn) > 0 else 0, 4),
        # False alarm rate — incorrect positive predictions
        "false_alarm_rate": round(fp / (fp + tn) if (fp + tn) > 0 else 0, 4),
        # Precision — reliability of positive predictions
        "precision": round(tp / (tp + fp) if (tp + fp) > 0 else 0, 4),
        # Business cost
        "total_cost": round(fn * cost_fn + fp * cost_fp, 2),
        "cost_per_prediction": round((fn * cost_fn + fp * cost_fp) / total, 4),
        # Volume
        "total_predictions": int(total),
        "positive_predictions": int(tp + fp),
        "negative_predictions": int(tn + fn),
        # Score distribution
        "mean_score": round(float(y_prob.mean()), 4),
        "high_risk_count": int((y_prob >= 0.7).sum()),
        "medium_risk_count": int(((y_prob >= 0.4) & (y_prob < 0.7)).sum()),
        "low_risk_count": int((y_prob < 0.4).sum()),
    }

    logger.info(
        "Business KPIs: detection_rate=%.3f, false_alarm_rate=%.3f, cost=$%.2f",
        kpis["detection_rate"],
        kpis["false_alarm_rate"],
        kpis["total_cost"],
    )

    return kpis
