# Observability — Grafana Dashboards Inventory

- **Authority**: R4 audit finding L2; ACTION_PLAN_R4 §7.
- **Scope**: a single index of every Grafana dashboard the template
  ships, with title, purpose, panels, and the Prometheus metrics /
  recording rules each dashboard depends on.
- **Owner**: Platform Engineering.

Adopters consume dashboards by pointing Grafana at the JSON files
under `templates/monitoring/grafana/`. Every `{service}` placeholder
is substituted at scaffold time by `templates/scripts/new-service.sh`;
`{ServiceName}` becomes the Pascal-case variant in the title.

This document is regenerated (manually) whenever a new dashboard is
added. The contract test
[`test_dashboards_inventory.py`](../../templates/service/tests/test_dashboards_inventory.py)
fails if a JSON dashboard exists under `templates/monitoring/grafana/`
without a row in the table below, or if a listed dashboard references
a file that no longer exists.

---

## Dashboards shipped

| File | Title | Primary use | Tags |
|------|-------|-------------|------|
| [`dashboard-template.json`](../../templates/monitoring/grafana/dashboard-template.json) | `{ServiceName} — ML Service Dashboard` | Day-to-day operations view: request rate, error rate, latency, drift, capacity. This is the first dashboard to open when a P1/P2 alert fires. | `ml-service`, `{service}` |
| [`dashboard-closed-loop.json`](../../templates/monitoring/grafana/dashboard-closed-loop.json) | `{ServiceName} — Closed-Loop & SLO Dashboard` | Long-horizon health: SLO burn, champion/challenger, sliced AUC, prediction-logger error rate, PSI heatmap. Reviewed in the monthly performance review (see `/performance-review`). | `ml-service`, `{service}`, `closed-loop`, `slo` |

---

## `dashboard-template.json` — panels

Ten panels, ordered top-to-bottom as they render:

| # | Type | Title | Purpose |
|---|------|-------|---------|
| 1 | `timeseries` | Request Rate | Per-replica + aggregate `{service}_requests_total` rate. |
| 2 | `timeseries` | Error Rate (%) | Ratio of 5xx responses over total; ties to the P1 error-rate alert. |
| 3 | `timeseries` | Prediction Latency (Percentiles) | P50 / P95 / P99 of `{service}_request_duration_seconds`; ties to P2 latency alert. |
| 4 | `histogram` | Prediction Score Distribution | Shape check — narrowing = model collapse; widening = drift. |
| 5 | `timeseries` | PSI Drift Score (per feature) | Per-feature PSI from the drift CronJob. Ties to the drift alerts. |
| 6 | `piechart` | Predictions by Risk Level | Business-side view of score-bucket distribution. |
| 7 | `stat` | Model Version | Single-value panel showing the currently-served `model_version` label. |
| 8 | `timeseries` | Pod CPU Usage | `container_cpu_usage_seconds_total` per replica. |
| 9 | `timeseries` | Pod Memory Usage | `container_memory_working_set_bytes`. ML pods have fixed memory; watch for leaks. |
| 10 | `timeseries` | HPA Replicas | `kube_horizontalpodautoscaler_status_current_replicas` — validates CPU-based scaling is actually triggering. |

**Prometheus dependencies**:

- Service metrics: `{service}_requests_total`, `{service}_request_duration_seconds_bucket`, `{service}_prediction_score`, `{service}_psi_score`.
- Kubernetes metrics: `container_cpu_usage_seconds_total`, `container_memory_working_set_bytes`, `kube_horizontalpodautoscaler_status_current_replicas`.

---

## `dashboard-closed-loop.json` — panels

Ten panels covering the slower feedback loop. Consumed by the
`/performance-review` workflow and the drift incident playbook.

| # | Type | Title | Purpose |
|---|------|-------|---------|
| 1 | `stat` | SLO — Availability (30-day) | 30-day rolling SLO; displays against target (default 99.5%). |
| 2 | `timeseries` | SLO Error Budget Burn (14d) | 14-day error budget burn; ties to the dynamic risk signal `error_budget_exhausted` (ADR-010). |
| 3 | `timeseries` | Global AUC (per model_version) | Ground-truth-backed performance over time, stratified by version. |
| 4 | `heatmap` | Sliced AUC heatmap (worst slices) | Per-slice AUC — catches silent concept drift that the global number hides. Inputs to `performance-degradation-rca`. |
| 5 | `timeseries` | Champion vs Challenger — error rate | Shadow-traffic comparison during model promotion. Ties to `/release`. |
| 6 | `timeseries` | Score distribution — p50 per version | Median score per version over time; distribution shift is a leading indicator of drift. |
| 7 | `timeseries` | Prediction logger — error rate (D-22) | Health of the async prediction logging pipeline (D-22 enforces it must run at < 1% error). |
| 8 | `timeseries` | Input quality flags (C4) | Schema-validation failures emitted by Pandera at the API boundary (C4 closure signal). |
| 9 | `stat` | `performance_monitor` heartbeat | Last-run timestamp of the performance monitor CronJob. Stale → silent concept drift. |
| 10 | `bargauge` | PSI per feature (drift) | Current PSI per feature against the reference window. Input to the drift alert routing. |

**Prometheus dependencies**:

- Recording rules: `slo:availability:ratio_30d`, `slo:error_budget:burn_14d`.
- Service metrics: `{service}_auc_global`, `{service}_auc_slice`, `{service}_prediction_score`, `{service}_psi_score`, `{service}_prediction_logger_errors_total`, `{service}_input_quality_flags_total`.
- Heartbeat: `performance_monitor_last_run_timestamp`.

---

## How dashboards are used operationally

| Incident class | Open first | Then |
|----------------|-----------|------|
| P1 service-down, error-rate, pod-restart | `dashboard-template.json` → panels 1, 2, 8–10 | Cross-check `dashboard-closed-loop.json` panel 7 (prediction logger) for async-side errors |
| P2 latency | `dashboard-template.json` → panel 3 | Prometheus query builder for per-endpoint breakdown |
| P2 drift-heartbeat-missing | `dashboard-closed-loop.json` → panels 9, 10 | `kubectl describe cronjob` |
| P3 PSI drift alert | `dashboard-template.json` → panel 5; `dashboard-closed-loop.json` → panel 10 | Run `/drift-check <service>` |
| Monthly performance review | `dashboard-closed-loop.json` → panels 1, 3, 4, 8 | [`performance-review` workflow](../../.windsurf/workflows/performance-review.md) |

---

## Adding a new dashboard

1. Place the JSON under `templates/monitoring/grafana/`.
2. Append a row to the "Dashboards shipped" table above (file, title, purpose, tags).
3. Add a per-dashboard "panels" subsection documenting each panel's type, title, and purpose. Keep it terse — the canonical source is the JSON.
4. Run `python -m pytest templates/service/tests/test_dashboards_inventory.py` to confirm the contract test still passes.
5. Open a PR. The PR evidence policy (ADR-020 §S1-2) applies because the dashboard file lives in the allow-listed `templates/monitoring/` surface.

---

## References

- ACTION_PLAN_R4 §R4 findings table (`L2`)
- `templates/monitoring/alertmanager-rules.yaml` — alerts these dashboards complement
- `docs/decisions/ADR-022-psi-thresholds.md` — PSI numbers surfaced in panel 5 / panel 10
