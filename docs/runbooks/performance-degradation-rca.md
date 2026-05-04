# Performance Degradation RCA Runbook

## Trigger

Use this when latency, error rate, throughput, or resource saturation regresses.

## Procedure

1. Establish the regression window and compare it to deploys, retrains, traffic shifts, and data changes.
2. Check pod restarts, HPA events, CPU, memory, cold-starts, model artifact size, and SHAP/explanation usage.
3. Compare p50, p95, and p99 latency by endpoint and slice.
4. Test mitigation: scale, disable optional explanation, rollback image, or rollback model.
5. Record root cause confidence and prevention work.

## Exit Criteria

RCA is complete when the primary cause has evidence, the mitigation is verified, and prevention has an owner.
