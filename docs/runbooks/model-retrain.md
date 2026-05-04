# Model Retrain Runbook

## Trigger

Use this for scheduled retraining, drift-confirmed retraining, or a quality-gate retry after data refresh.

## Procedure

1. Verify EDA artifacts are current and not blocked by leakage gates.
2. Run `make retrain` or the service training command with the target environment config.
3. Inspect `training_manifest.json`, metrics, fairness slices, and promotion verdict.
4. Promote only if primary, secondary, fairness, and evidence gates pass.
5. Record the model artifact URI, model version, dataset hash, and reviewer in the audit trail.

## Exit Criteria

The retrain is complete when the candidate is either promoted with immutable evidence or rejected with a documented reason.
