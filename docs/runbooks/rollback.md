# Rollback Runbook

## Trigger

Use this when deploy smoke, SLO burn, champion/challenger, or operator review blocks a release.

## Procedure

1. Identify the last healthy deployment id and image digest from `ops/audit.jsonl`.
2. Abort active canary or rollout if one is running.
3. Run `make rollback REV=<revision>` or `kubectl rollout undo deployment/<service>-predictor`.
4. Wait for rollout status and run `/ready`, `/predict`, and metrics smoke checks.
5. Record the rollback reason, previous digest, restored digest, and approver.

## Exit Criteria

The rollback is complete when service readiness, prediction, and error-rate checks are green for the restored revision.
