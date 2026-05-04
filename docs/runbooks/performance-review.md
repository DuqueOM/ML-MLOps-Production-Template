# Performance Review Runbook

## Trigger

Use this monthly, after retraining, or when sliced model-quality alerts fire.

## Procedure

1. Pull global and sliced metrics for ROC-AUC, F1, calibration, latency, and prediction-log errors.
2. Compare against `configs/quality_gates.yaml` and the previous accepted model.
3. Identify slices below gate and whether sample size is large enough to act.
4. Decide continue, retrain, rollback, or gather more labels.
5. Store the review summary with model version, dataset window, and owner.

## Exit Criteria

The review is complete when every failing or watchlisted slice has an owner and next action.
