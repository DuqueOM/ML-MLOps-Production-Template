"""PSI drift detection demo.

Demonstrates:
- Quantile-based PSI calculation (NOT uniform bins)
- Simulated drift detection on perturbed data
- Exit codes for CronJob integration (0=ok, 1=warning, 2=alert)

Run:
    python train.py        # Generate reference data
    python drift_check.py  # Run drift check with synthetic drift
"""

from __future__ import annotations

import json
import logging
import sys

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

PSI_BINS = 10
PSI_EPSILON = 1e-8
WARNING_THRESHOLD = 0.10
ALERT_THRESHOLD = 0.20


def calculate_psi(
    reference: np.ndarray,
    current: np.ndarray,
    bins: int = PSI_BINS,
    epsilon: float = PSI_EPSILON,
) -> float:
    """PSI with quantile-based bins (NOT uniform).

    Why quantiles: uniform bins can have empty bins at extremes
    → PSI dominated by epsilon, not real drift.
    Quantiles guarantee each bin has observations in the reference.
    """
    breakpoints = np.percentile(reference, np.linspace(0, 100, bins + 1))
    breakpoints[0] = -np.inf
    breakpoints[-1] = np.inf

    ref_counts, _ = np.histogram(reference, bins=breakpoints)
    cur_counts, _ = np.histogram(current, bins=breakpoints)

    ref_pct = np.maximum(ref_counts / len(reference), epsilon)
    cur_pct = np.maximum(cur_counts / len(current), epsilon)

    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def main() -> int:
    ref_df = pd.read_csv("artifacts/reference.csv")
    logger.info("Reference data loaded: %d rows, %d features", *ref_df.shape)

    # Simulate production data with drift in 'amount' and 'distance_from_home'
    rng = np.random.RandomState(99)
    current_df = ref_df.copy()
    current_df["amount"] = current_df["amount"] * 1.5 + rng.normal(0, 50, len(current_df))
    current_df["distance_from_home"] = current_df["distance_from_home"] * 2.0
    logger.info("Simulated drifted production data")

    results = {}
    alerts, warnings = [], []

    for col in ref_df.select_dtypes(include=[np.number]).columns:
        ref_vals = ref_df[col].dropna().values
        cur_vals = current_df[col].dropna().values
        psi = calculate_psi(ref_vals, cur_vals)

        if psi >= ALERT_THRESHOLD:
            status = "ALERT"
            alerts.append(col)
        elif psi >= WARNING_THRESHOLD:
            status = "WARNING"
            warnings.append(col)
        else:
            status = "OK"

        results[col] = {"psi": round(psi, 4), "status": status}
        logger.info("  %-25s PSI=%.4f  %s", col, psi, status)

    print("\n" + json.dumps({"alerts": alerts, "warnings": warnings, "all_features": results}, indent=2))

    if alerts:
        logger.warning("EXIT 2: Alert-level drift in %s", alerts)
        return 2
    elif warnings:
        logger.info("EXIT 1: Warning-level drift in %s", warnings)
        return 1
    else:
        logger.info("EXIT 0: No drift")
        return 0


if __name__ == "__main__":
    sys.exit(main())
