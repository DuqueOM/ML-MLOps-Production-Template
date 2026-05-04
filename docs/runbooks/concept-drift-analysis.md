# Concept Drift Analysis Runbook

## Trigger

Use this when feature drift is weak but model performance drops after labels arrive.

## Procedure

1. Confirm label freshness and join quality before interpreting performance.
2. Compare current and baseline performance globally and by slice.
3. Review calibration and threshold behavior; do not assume retraining is always required.
4. Segment by business period, channel, geography, and model version.
5. Recommend threshold adjustment, retraining, feature change, or more label collection.

## Exit Criteria

Concept drift is confirmed only when label-backed performance change persists after data-quality checks pass.
