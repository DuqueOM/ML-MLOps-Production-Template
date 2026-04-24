---
paths:
  - "**/app/*.py"
  - "**/api/*.py"
---

# ML Serving Rules

## Invariants
- NEVER call `model.predict()` directly in async endpoint — blocks event loop (D-03)
- ALWAYS use `asyncio.run_in_executor(ThreadPoolExecutor, partial(_sync_predict, ...))` (D-03)
- ALWAYS use `KernelExplainer` for SHAP with ensemble/pipeline models, never TreeExplainer (D-04)
- ALWAYS compute SHAP in ORIGINAL feature space via `predict_proba_wrapper` (D-04)
- ALWAYS build the SHAP explainer ONCE during warm-up and cache on app state (D-24)
- ALWAYS run `warm_up_model()` in FastAPI `lifespan` BEFORE flipping `_warmed_up=True` (D-23)
- NEVER `uvicorn --workers N` — 1 worker, HPA provides horizontal scale (D-01)
- NEVER bake models into Docker — use Init Container + emptyDir (D-11)
- Model loaded ONCE at startup (lifespan handler), never per-request

## Probes (D-23)
- `/health` — liveness: returns 200 while event loop is alive
- `/ready` — readiness: returns 503 until warm-up completes; HPA-safe gate
- Must be DIFFERENT paths — sharing one recreates the cold-start traffic spike

## Graceful Shutdown (D-25)
- `terminationGracePeriodSeconds` (pod) STRICTLY GREATER than uvicorn
  `--timeout-graceful-shutdown` (e.g., 30 vs 20)

## API Contracts (D-28)
- Public schemas in `app/schemas.py` — single source of truth
- `tests/contract/openapi.snapshot.json` is COMMITTED
- Any schema change requires `python scripts/refresh_contract.py` AND
  a bump of `app.version` (semver). CI rejects a snapshot change alone.

## FastAPI Conventions
- `/predict` — main inference, `/predict?explain=true` — SHAP (opt-in)
- `/health` + `/ready` — probes, `/metrics` — Prometheus
- Mandatory metrics: `{service}_predictions_total`,
  `{service}_request_duration_seconds`,
  `{service}_prediction_score_bucket` (histogram for C/C),
  `prediction_log_total` + `prediction_log_errors_total` (D-22)
- Optional: `{service}_input_out_of_range_total{feature,direction}` (C4)

See `AGENTS.md` for anti-pattern table D-01 to D-30 and both Behavior
Protocols (static mapping + ADR-010 dynamic escalation).
