# Incident Response Runbook

## Severity

P1 and P2 incidents are STOP-class. P3 and P4 may be CONSULT unless customer impact escalates.

## Procedure

1. Declare incident owner, scribe, severity, impacted environment, and start time.
2. Freeze risky deploys and capture current deployment id, image digest, and model version.
3. Triage health, readiness, latency, error-rate, prediction-log, and drift signals.
4. Choose mitigation: rollback, scale, disable optional logging, rotate secret, or block traffic.
5. Publish updates on the agreed cadence and keep all commands in the incident log.

## Exit Criteria

The incident closes after mitigation is verified, customer impact is recorded, and a follow-up action list exists.
