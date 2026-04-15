---
description: Execute model retraining with quality gates and safe promotion
whenToUse: When a model needs retraining due to drift, scheduled maintenance, or metric degradation
---

# Model Retraining

## Step 1: Validate Retraining Trigger

Before retraining, confirm the trigger:
- **Drift alert**: PSI ≥ threshold on critical feature (check Prometheus/Grafana)
- **Metric degradation**: Rolling metric below quality gate (check monitoring)
- **Scheduled**: Periodic retraining per policy
- **Manual**: Engineer-initiated (document reason)

## Step 2: Download Fresh Data

```bash
# Download latest production data
gsutil cp gs://{data-bucket}/{service}/production_data_latest.csv data/raw/
# Or from AWS:
aws s3 cp s3://{data-bucket}/{service}/production_data_latest.csv data/raw/
```

## Step 3: Validate Data Before Training

```bash
python -c "
from src.{service}.schemas import ServiceInputSchema
import pandas as pd
import pandera as pa

df = pd.read_csv('data/raw/production_data_latest.csv')
ServiceInputSchema.validate(df)
print(f'Validation passed: {len(df)} rows, {len(df.columns)} columns')
"
```

If validation fails → investigate upstream data changes before proceeding.

## Step 4: Execute Training

```bash
python src/{service}/training/train.py \
  --data data/raw/production_data_latest.csv \
  --experiment "{service}-retraining-$(date +%Y%m%d)" \
  --optuna-trials 50
```

This executes the full pipeline:
1. Load + validate data
2. Feature engineering
3. Train/val/test split (temporal if dates exist)
4. Cross-validation
5. Optuna hyperparameter tuning
6. Evaluate on test set
7. Log to MLflow

## Step 5: Quality Gates (ALL MUST PASS)

```python
gates = {
    "primary_metric >= threshold": new_metrics["primary"] >= MINIMUM_THRESHOLD,
    "no regression > 5%": new_metrics["primary"] >= prod_metrics["primary"] * 0.95,
    "secondary_metric": new_metrics["secondary"] >= SECONDARY_THRESHOLD,
    "fairness DIR >= 0.80": all(new_metrics[f"dir_{attr}"] >= 0.80 for attr in PROTECTED),
    "p95_latency <= 1.2x": new_metrics["p95_ms"] <= prod_metrics["p95_ms"] * 1.20,
}

failed = [name for name, passed in gates.items() if not passed]
```

## Step 6a: ALL PASS → Promote

```bash
# Promote in MLflow Registry
python -c "
import mlflow
client = mlflow.tracking.MlflowClient()
client.transition_model_version_stage('{service}Model', version={V}, stage='Production')
client.transition_model_version_stage('{service}Model', version={V-1}, stage='Archived')
"

# Upload model to GCS/S3
gsutil cp models/model.joblib gs://{model-bucket}/{service}/model.joblib
aws s3 cp models/model.joblib s3://{model-bucket}/{service}/model.joblib

# Rolling restart to pick up new model
kubectl rollout restart deployment/{service}-predictor -n {namespace}
kubectl rollout status deployment/{service}-predictor -n {namespace}
```

## Step 6b: ANY FAIL → Do Not Promote

```bash
# Create GitHub Issue
gh issue create \
  --title "Retraining failed quality gates: {service}" \
  --body "Failed gates: ${failed}\nKeeping current model in production." \
  --label "ml-retraining,quality-gate-failure"
```

## Step 7: Post-Retraining Verification

- [ ] New model version in MLflow Registry = Production
- [ ] Previous model version = Archived
- [ ] Pods restarted and passing health checks
- [ ] `/predict` returning valid predictions
- [ ] Grafana showing new model_version label
- [ ] No new alerts in AlertManager

## Step 8: Update Reference Data

```bash
# Update drift reference to new training data distribution
python src/{service}/monitoring/drift_detection.py --update-reference
gsutil cp data/reference/{service}_reference.csv gs://{data-bucket}/{service}/reference/
```
