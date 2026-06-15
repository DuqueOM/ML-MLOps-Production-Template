# ADR-028 — LLM-Assist Integration for Template Maintenance and Day-2 Operations

- **Status**: Proposed (R6 audit follow-up — requires maintainer acceptance)
- **Date**: 2026-06-09
- **Deciders**: Template maintainer (`@DuqueOM`)
- **Related**: ADR-001 (scope boundaries), ADR-010 (dynamic behavior),
  ADR-018 (memory plane), ADR-019 (CI self-healing),
  `templates/config/model_routing_policy.yaml`, README §Model routing policy.

## 1. Context

The template already treats agent behavior as an engineering surface:
AUTO/CONSULT/STOP modes, typed handoffs, audit trail, a four-tier model
routing policy, and two Phase-1 capabilities (operational memory,
CI self-healing) that are contracts-only today. The open question this
ADR answers: **should the template integrate LLMs more deeply — and
should it fine-tune dedicated models — to support repo maintenance and
the operation of deployed services?**

Two boundaries are fixed by prior ADRs and stay fixed:

1. **No LLM in the `/predict` path.** ADR-001 keeps LLM serving out of
   template scope; the inference surface remains classical tabular ML.
2. **LLM autonomy never weakens policy.** Escalation-only discipline
   (ADR-010): a model may raise caution, never approve a risky action.

## 2. Decision (proposed)

Integrate LLMs as **bounded operators on the maintenance plane**, in
four phased lanes that reuse existing contracts. Do **NOT** fine-tune
dedicated models at this scale (see §4).

### Lane 1 — CI self-healing Phase 2 (highest leverage, gated)

Open the ADR-019 patch worker behind CONSULT once the 14-day shadow
window produces classifier precision data. Routing per
`model_routing_policy.yaml` (patch-worker tier; never escalation-tier
in AUTO). Entry criterion: schedule the shadow measurement window NOW —
the phase gate has no start date, which makes it indefinite by default.

### Lane 2 — Memory plane Phase 2 (retrieval, file-based first)

Implement ADR-018 ingest + retrieval over the artifacts that already
exist (`ops/audit.jsonl`, `docs/incidents/`, `VALIDATION_LOG.md`,
release notes, drift reports). Start file-based + embeddings-free
(BM25/grep-class retrieval) to prove the recall surface before paying
for a vector store. LLM summarization sits on top, read-only.

### Lane 3 — Drift / incident triage summarizer

A read-only lane that joins Prometheus signals (via the `prometheus`
MCP), prediction-log slices, and deploy history into a draft RCA
report (`templates/config/report_schema.json` shape) attached to the
incident issue. Human owns the conclusion; the LLM owns the gathering.
This operationalizes what `performance-degradation-rca` documents as a
manual skill today.

### Lane 4 — Docs-drift updater (Agent-DocUpdater, operationalized)

Weekly lane that diffs code-visible facts against the doc surface
(counts in CLAUDE.md, inventory tables, runbook references — exactly
the R6 S1-4 class of drift) and opens a CONSULT PR. The R6 audit found
four instances of this drift class; it is the cheapest recurring win.

## 3. Eval harness before autonomy (precondition for every lane)

Extend `docs/agentic/red-team-log.md` into executable scenario evals in
CI: given scenario X (prod apply request, quality-gate override, secret
in diff), the agent MUST refuse / escalate per the Behavior Protocol.
A lane may not graduate from CONSULT to AUTO without a regression eval
covering its failure modes. This is the agentic analogue of the
template's own quality-gate philosophy (D-12).

## 4. Fine-tuning stance: NO (revisit triggers below)

Rejected for now, on Engineering Calibration grounds:

- **Volume**: the repo generates hundreds, not millions, of labeled
  maintenance events; below any fine-tuning payoff threshold.
- **Churn**: vendor catalogs rotate every 6–12 months (the
  `verified_at` discipline exists precisely because of this); a tuned
  model is a depreciating asset on that clock.
- **Alternative**: routing + structured prompts + retrieval (Lane 2)
  captures most of the gain at near-zero marginal cost.

Revisit when ANY of: (a) >10k classified CI-failure events with ground
truth, (b) measured router precision below the ADR-019 gate despite
prompt iteration, (c) inference cost of the default lanes dominating
the maintenance budget.

## 5. Consequences

- Positive: closes the gap between the template's agentic *design* and
  agentic *runtime*; every lane lands on surfaces that already have
  contract tests and audit trails.
- Negative: adds recurring LLM spend (bounded by routing tiers) and an
  eval-maintenance burden; Lane 1 carries real risk and stays CONSULT
  until evals + shadow data justify AUTO.
- Out of scope, unchanged: LLM serving in the template's data plane,
  multi-tenant agent platforms, autonomous prod mutations (STOP).

## 6. Implementation — the `agent-local` sibling repository

The **local-model tiers** of this routing policy (the router/reasoner/assistant/
verifier loop on llama.cpp) are implemented in a separate, reusable repository:
[`agent-local`](https://github.com/DuqueOM/agent-local) (Apache-2.0). It is kept
deliberately separate from this template (agent-local ADR-001: different product,
lifecycle and audience).

- The day-2 lanes above (CI self-healing, memory plane, drift triage, docs-drift)
  run on `agent-local`'s tier stack, registered **below** the cheapest cloud tier
  in `templates/config/model_routing_policy.yaml` (escalation-only discipline of
  ADR-010 is unchanged: a local model may signal, never approve).
- When `agent-local` needs cloud infra, it **reuses** this template's Terraform
  modules and Kustomize overlays (agent-local ADR-002), not a rewrite.
- The unified execution plan for both planes is
  [`docs/audit/ACTION_PLAN_LLM_AGENT.md`](../audit/ACTION_PLAN_LLM_AGENT.md); the
  local-model architecture decisions are `agent-local/docs/decisions/ADR-001..005`.
