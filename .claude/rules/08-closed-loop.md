---
paths:
  - "**/prediction_logger.py"
  - "**/ground_truth.py"
  - "**/performance_monitor.py"
  - "**/champion_challenger.py"
  - "**/monitoring/**/*.py"
  - "**/app/fastapi_app.py"
  - "**/app/main.py"
  - "**/app/schemas.py"
  - "**/configs/slices.yaml"
  - "**/configs/ground_truth_source.yaml"
  - "**/configs/champion_challenger.yaml"
  - "**/k8s/base/cronjob-performance.yaml"
  - "**/k8s/base/performance-prometheusrule.yaml"
description: Closed-loop monitoring invariants (D-20/D-21/D-22) — prediction logging, ground truth, sliced performance, champion/challenger
---

# Closed-Loop Monitoring (ADR-006 / ADR-007 / ADR-008)

Parity with `.windsurf/rules/13-closed-loop-monitoring.md` and
`.cursor/rules/08-closed-loop.mdc`. Full rationale in AGENTS.md.

## Invariants

**D-20** — Every prediction MUST log `prediction_id` (UUID) + `entity_id`
(stable business key) + `model_version`. `PredictionRequest.entity_id` is
required. `PredictionResponse.prediction_id` is returned to the client.

**D-21** — `log_prediction()` is fire-and-forget: buffers and flushes in a
background task via `run_in_executor(None, ...)`. NEVER awaits backend I/O
on the handler path. Buffer drains on FastAPI shutdown.

**D-22** — Logging failures are swallowed and counted via
`prediction_log_errors_total`. They NEVER propagate to the HTTP response.
Alert on error-rate, not on 5xx.

## Slicing (ADR-007)

- `slice_values` dict keys MUST match `configs/slices.yaml`.
- Unbounded free-text slices FORBIDDEN (Prometheus cardinality).
- Sample size below `min_samples_per_slice` → `insufficient_data` (no false alerts).

## Ground truth (ADR-006)

- `fetch_labels_from_source()` is a user-implemented stub. CSV is dev-only.
- JOIN causality: `label_ts >= prediction_ts`.
- Idempotent partition writes (daily year=/month=/day=).

## Champion/Challenger (ADR-008)

- STOP-class operation. Only via CI workflow step-summary.
- Both McNemar p-value AND bootstrap ΔAUC CI must agree.
- Tri-state decision: promote / keep / block. Margin changes require ADR.

## Agent behavior by file

| File | Mode |
|------|------|
| `app/fastapi_app.py`, `app/main.py` | AUTO (preserve D-21/D-22) |
| `prediction_logger.py` | CONSULT |
| `champion_challenger.py` + its config | STOP (governance) |

See AGENTS.md for full Anti-Patterns D-01 → D-22.
