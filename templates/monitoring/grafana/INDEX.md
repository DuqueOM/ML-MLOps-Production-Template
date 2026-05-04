# Grafana dashboard inventory

Centralized inventory of every Grafana dashboard the template ships.
External-feedback gap 6.4 (May 2026 triage): dashboards existed but
were not centrally registered, making completeness invisible to
adopters. This file is the **source of truth**: every shipped
dashboard MUST appear here with audience, panel summary, source data,
and the runbook that consumes it.

| Dashboard | File | Audience | Source data | Runbook |
|-----------|------|----------|-------------|---------|
| ML service overview | `dashboard-template.json` | On-call SRE / ML engineer | Prometheus `<service>_*` metrics emitted by FastAPI app | `docs/runbooks/incident.md` |
| Closed-loop monitoring | `dashboard-closed-loop.json` | ML engineer / data scientist | Prediction logger + drift CronJob output | `docs/runbooks/closed-loop-sla.md`, `docs/decisions/ADR-008-champion-challenger.md` |
| DORA delivery metrics | `dashboard-dora.json` | Engineering manager / Staff+ | `dora_*` Prometheus series (see Pipeline below) | `/performance-review` workflow |

## Pipeline contract per dashboard

### `dashboard-template.json`

Direct: FastAPI app emits Prometheus counters / histograms via
`prometheus_client`. No additional plumbing required. Variables
`{ServiceName}` and `{service}` are substituted by `new-service.sh`
at scaffold time.

### `dashboard-closed-loop.json`

The dashboard reads metrics that the prediction logger (D-21/D-22)
and drift CronJob (CRIT-2/3) write to Prometheus directly. SLO
burn-rate panels reference the rules in `slo-prometheusrule.yaml`
(CRIT-1).

### `dashboard-dora.json`

`scripts/dora_metrics.py` writes JSON to `ops/dora/{YYYY-MM}-metrics.json`.
It does NOT emit Prometheus metrics itself — the design is
intentionally deployment-agnostic.

To populate the dashboard, the adopter MUST add a small companion
job (CronJob or GitHub Action) that:

1. Runs `python scripts/dora_metrics.py --output /tmp/dora.json`.
2. Translates each JSON field to a Prometheus push-gateway POST
   under the metric names referenced by the dashboard:
   - `dora_deploy_frequency_per_week`
   - `dora_lead_time_hours_p50`
   - `dora_change_failure_rate_percent`
   - `dora_mttr_minutes_p50`
   - `dora_deploys_total`
   - `dora_rollbacks_total`
3. Tags each series with `service="<scaffolded slug>"`.

A reference CronJob is intentionally NOT shipped with the template
(every adopter's Pushgateway endpoint, auth, and retention policy
differ). The contract is fully documented here so the wiring is
mechanical.

## Adding a new dashboard

1. Drop the JSON into this directory with the file name
   `dashboard-<topic>.json`.
2. Add a row to the table above with audience + source data + runbook.
3. Reference the dashboard from at least one runbook so it has a
   user, not just a producer.
4. If the dashboard relies on a series the template does not yet
   emit, document the wiring under "Pipeline contract per dashboard"
   above — same level of detail as the DORA section.

The CI gate enforces that this INDEX.md mentions every JSON file
present in this directory (see
`.github/workflows/validate-templates.yml::dashboard-inventory`
job — added in PR-1 of the May 2026 feedback triage).
