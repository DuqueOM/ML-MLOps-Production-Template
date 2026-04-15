---
trigger: glob
globs: ["**/*.py"]
description: Python ML conventions — async inference, SHAP wrappers, training pipelines
---

# Python ML Rules

## Async Inference (MANDATORY)

`sklearn.predict()` and most ML frameworks are synchronous — they block asyncio's event loop.

ALWAYS use `asyncio.run_in_executor()`:
```python
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import asyncio

_inference_executor = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="ml-infer"
)

def _sync_predict(input_dict: dict, explain: bool) -> dict:
    """CPU-bound — runs in thread pool, does not block event loop."""
    df = pd.DataFrame([input_dict])
    prob = float(model_pipeline.predict_proba(df)[:, 1][0])
    # ... build response
    return response

@app.post("/predict")
async def predict(input_data: InputSchema, explain: bool = False):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _inference_executor,
        partial(_sync_predict, input_data.model_dump(), explain)
    )
```

Why this works: sklearn, XGBoost, LightGBM release the GIL during C extensions → real parallelism with threads.

## SHAP KernelExplainer (MANDATORY for complex models)

NEVER use `TreeExplainer` with StackingClassifier, pipelines, or complex ensembles.

ALWAYS use `KernelExplainer` with a `predict_proba_wrapper`:
```python
def predict_proba_wrapper(X_array: np.ndarray) -> np.ndarray:
    """SHAP in ORIGINAL feature space, not transformed space."""
    X_df = pd.DataFrame(X_array, columns=original_feature_names)
    return pipeline.predict_proba(X_df)[:, 1]

explainer = shap.KernelExplainer(
    model=predict_proba_wrapper,
    data=X_background.values[:50],  # 50 samples: precision/speed balance
)
```

ALWAYS verify the consistency property:
```
base_value + sum(shap_values) ≈ predict_proba(input)  (tolerance < 0.001)
```

## Training Pipeline Structure

Every trainer MUST follow this sequence:
1. `load_data()` + Pandera validation
2. `engineer_features()`
3. `split_train_val_test()` — no temporal leakage if dates exist
4. `cross_validate()`
5. `evaluate()` with optimal threshold search
6. `fairness_check()` — DIR >= 0.80 per protected attribute
7. `save_artifacts()` with SHA256 checksum
8. `log_to_mlflow()` — parameters, metrics, artifacts, tags
9. `quality_gates()` — must ALL pass before promotion

## Quality Gates

```python
def should_promote(new_metrics: dict, current_prod_metrics: dict) -> bool:
    return all([
        new_metrics["primary_metric"] >= current_prod_metrics["primary_metric"] * 0.95,
        new_metrics["primary_metric"] >= MINIMUM_THRESHOLD,
        new_metrics["secondary_metric"] >= SECONDARY_THRESHOLD,
        new_metrics["p95_latency_ms"] <= current_prod_metrics["p95_latency_ms"] * 1.20,
        new_metrics["dir_attribute"] >= 0.80,  # Fairness
    ])
```

## FastAPI Conventions

- `/predict` — main inference endpoint
- `/predict?explain=true` — SHAP explanation (opt-in)
- `/health` — liveness + readiness
- `/metrics` — Prometheus metrics

## Prometheus Metrics (MANDATORY per service)

```python
from prometheus_client import Counter, Histogram, Gauge

predictions_total = Counter('{service}_predictions_total', '...', ['risk_level', 'model_version'])
prediction_latency = Histogram('{service}_prediction_latency_seconds', '...', ['endpoint'])
prediction_score_distribution = Histogram('{service}_prediction_score', '...')
psi_score_per_feature = Gauge('{service}_psi_score', '...', ['feature'])
```

## Type Hints

Required on all public functions. Use Pydantic for config and API schemas:
```python
from pydantic import BaseModel, Field

class PredictionRequest(BaseModel):
    feature_a: float = Field(..., ge=0, le=100, description="Feature A value")
    feature_b: str = Field(..., description="Category")
```

## Testing Requirements

- `test_no_data_leakage()` — primary metric below suspicion threshold
- `test_shap_values_not_all_zero()` — SHAP returning zeros is a known failure
- `test_shap_consistency()` — base_value + sum = prediction
- `test_feature_space_is_original()` — SHAP in original, not transformed space
- `test_model_meets_quality_gate()` — metric above production threshold
- `test_inference_latency()` — within SLA
- `test_fairness_disparate_impact()` — DIR >= 0.80
