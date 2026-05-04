# Cost Review Runbook

## Trigger

Use this monthly or when cloud budget alerts fire.

## Procedure

1. Pull cost by environment, cluster, registry, storage bucket, and logging sink.
2. Compare current spend with the monthly budget and last-cycle baseline.
3. Check HPA bounds, node pool sizes, artifact retention, MLflow storage, and log retention.
4. Tag unexpected spend as growth, waste, incident-driven, or unknown.
5. Open corrective tickets for waste and update the budget if growth is approved.

## Exit Criteria

The review closes when variance is explained and every corrective action has a target date.
