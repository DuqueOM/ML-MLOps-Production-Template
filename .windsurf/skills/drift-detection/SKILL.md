---
description: Run and interpret PSI-based drift detection for an ML service
whenToUse: When checking data drift, interpreting PSI scores, or configuring drift thresholds
---

# Drift Detection

## Step 1: Understand the Drift Metric

**PSI (Population Stability Index)** with quantile-based bins:
```
PSI < 0.10:  No significant change → no action
0.10 ≤ PSI < 0.20: Moderate change → monitor closely
PSI ≥ 0.20:  Significant change → action required
```

ALWAYS use quantile-based bins (not uniform):
```python
breakpoints = np.percentile(reference, np.linspace(0, 100, bins + 1))
```

Uniform bins can produce empty bins at extremes → PSI dominated by epsilon noise.

## Step 2: Run Drift Detection Manually

```bash
python src/{service}/monitoring/drift_detection.py \
  --reference data/reference/{service}_reference.csv \
  --current data/production/{service}_latest.csv \
  --output drift_report.json
```

## Step 3: Interpret Results

For each feature, review:
```json
{
  "feature_name": "age",
  "psi": 0.15,
  "status": "warning",
  "reference_mean": 45.2,
  "current_mean": 48.1,
  "bins_detail": [...]
}
```

### Common Root Causes

| Pattern | Likely Cause | Action |
|---------|-------------|--------|
| Single feature PSI high | Upstream data change | Investigate ETL pipeline |
| All features PSI high | Data source change | Full retraining |
| Temporal features PSI high | Seasonal pattern | Use YoY comparison |
| Categorical OOV rate up | New categories in production | Update schema + retrain |

## Step 4: Configure Thresholds

Each feature needs per-feature thresholds with domain reasoning:
```python
THRESHOLDS = {
    "stable_feature": {"warning": 0.10, "alert": 0.20},
    "volatile_feature": {"warning": 0.15, "alert": 0.30},  # Higher natural variance
    "categorical_feature": {"warning": 0.10, "alert": 0.20},
}
```

For temporal data (e.g., time series, seasonal patterns):
- Standard PSI will flag EVERY seasonal change as drift
- Use Year-over-Year comparison instead

## Step 5: Push Metrics to Prometheus

```python
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

registry = CollectorRegistry()
psi_gauge = Gauge('service_psi_score', 'PSI per feature', ['feature'], registry=registry)

for feature, psi in results.items():
    psi_gauge.labels(feature=feature).set(psi)

push_to_gateway('pushgateway:9091', job='drift-detection', registry=registry)
```

## Step 6: Verify CronJob Health

```bash
# Check CronJob status
kubectl get cronjob drift-detection -n {namespace}

# Check last job
kubectl get jobs -l app=drift-detection -n {namespace} --sort-by=.metadata.creationTimestamp

# Check heartbeat
curl -s 'http://prometheus:9090/api/v1/query?query=drift_detection_last_run_timestamp'
```

## Trigger Retraining

If PSI exceeds alert threshold on critical features:
```bash
gh workflow run retrain-{service}.yml -f reason="PSI drift: {feature}={psi_value}"
```

Chain to `/retrain` workflow for the full retraining process.
