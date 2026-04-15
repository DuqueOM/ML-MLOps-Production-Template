---
description: Debug ML inference issues — latency spikes, wrong predictions, event loop blocking
whenToUse: When an ML service has inference errors, high latency, or incorrect predictions
---

# Debug ML Inference

## Step 1: Identify the Symptom

Classify the issue:
- **High latency**: P95 above SLA → likely event loop blocking or resource contention
- **Wrong predictions**: Output doesn't match expectations → model or data issue
- **5xx errors**: Service crashes or timeouts → code or infrastructure issue
- **Score distribution shift**: Model output pattern changed → input drift or model staleness

## Step 2: Check Event Loop Blocking

The #1 cause of ML inference latency in FastAPI is blocking the event loop.

```bash
# Check if predict is wrapped in run_in_executor
grep -r "run_in_executor" {service}/app/
grep -r "sync_predict\|_sync_predict" {service}/app/
```

If `model.predict()` is called directly in an `async def` endpoint → wrap it:
```python
loop = asyncio.get_running_loop()
return await loop.run_in_executor(_inference_executor, partial(_sync_predict, data))
```

## Step 3: Check Worker Count

```bash
# In Dockerfile or deployment YAML
grep -r "workers" {service}/Dockerfile k8s/base/{service}-deployment.yaml
```

If `--workers N` where N > 1 under K8s → change to 1 worker. HPA handles scaling.

## Step 4: Check Model Loading

```bash
# Verify model is loaded at startup, not per-request
grep -r "joblib.load\|pickle.load\|load_model" {service}/app/
```

Model should be loaded ONCE at module level or in a `@app.on_event("startup")` handler.

## Step 5: Check SHAP Performance

If `/predict?explain=true` is slow:
- Verify background data is ≤ 50 samples
- Verify `nsamples` parameter in KernelExplainer (default 2*K+2048 can be excessive)
- SHAP is expected to be slower (seconds) — verify it's opt-in only

## Step 6: Check Resource Limits

```bash
kubectl top pod -l app={service} -n {namespace}
kubectl describe pod {pod-name} -n {namespace} | grep -A5 "Limits\|Requests"
```

If CPU is at limit → HPA should scale. If not scaling → check HPA target and current utilization.

## Step 7: Check Data Validation

```bash
# Look for Pandera SchemaError in logs
kubectl logs -l app={service} -n {namespace} | grep -i "SchemaError\|validation"
```

SchemaError means input data violates the expected schema → upstream data change.

## Quick Reference: ADR Patterns

| Issue | Root Cause | ADR Reference |
|-------|-----------|--------------|
| CPU thrashing | Multi-worker uvicorn | ADR: Single-Worker Pod |
| HPA stuck | Memory-based metric | ADR: CPU-Only HPA |
| Event loop block | Sync predict in async | ADR: Async ThreadPoolExecutor |
| SHAP errors | TreeExplainer on ensemble | ADR: SHAP KernelExplainer |
