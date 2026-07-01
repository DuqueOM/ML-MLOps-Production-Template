# ADR-036 — Batch-Only Deployment Topology

- **Status**: Accepted
- **Date**: 2026-07-01
- **Deciders**: Template maintainer (`@DuqueOM`)
- **Related**: R7 Staff/Lead audit (`docs/audit/AUDIT_R7_STAFF_LEAD.md` §3,
  audience "batch-only pipelines"), `agentic/skills/batch-inference/SKILL.md`
  (ADR-006 prediction logger, rule 02-kubernetes), ADR-001 (scope boundaries)

## Context

The R7 audit's audience-fit review found the template correctly scopes
*itself* out for "batch-only pipelines" (`README.md`'s non-claims list) —
but flagged that the underlying capability was already 90% present and
worth exposing as a real on-ramp rather than leaving it as a scope
exclusion. Two existing pieces already do the hard work:

1. The `batch-inference` skill scaffolds `src/<service>/batch.py` (shares
   `predictor.predict_batch()` with the live API — no training/serving
   *or* training/batch skew) and a `k8s/base/cronjob-batch.yaml`, but only
   as something an agent generates **on demand, alongside** the live
   Deployment/Service/HPA stack. It answers "I have a live API and *also*
   want nightly scoring."
2. Nothing answers "I will **never** run the live API — my team only needs
   scheduled batch scoring" without still deploying (and paying for) a
   Deployment, Service, HPA, and PodDisruptionBudget that serve zero
   traffic.

## Decision

Ship a **batch-only Kustomize overlay** —
`templates/service/k8s/overlays/batch-only/` — that composes a
deployment topology with **no online-serving resources at all**:

- Includes the **full** `../../base` and deletes the online-serving-only
  resources (`deployment.yaml`, `service.yaml`, `hpa.yaml`, `pdb.yaml`,
  both `AnalysisTemplate`s, the performance/drift `CronJob`s and their
  `PrometheusRule`s, the online-shaped `NetworkPolicy`) via
  `$patch: delete`, **one resource per file** under `delete/`.
  Cherry-picking individual sibling files (e.g.
  `../../base/serviceaccount.yaml`) was tried first and rejected: Kustomize's
  load restrictor forbids referencing a file outside the including
  kustomization's own directory tree — only whole kustomization
  directories may be included cross-tree. Separately, the bundled
  kustomize/kyaml version (`kustomize/v5.4.2`, `kyaml v0.17.1`) panics
  with a nil-pointer dereference when a single `patches: - path:` entry
  points at a **multi-document** strategic-merge file; verified locally
  with `kubectl kustomize` (one document per file is the reproducibly
  stable path — see `k8s/overlays/batch-only/delete/*.yaml`).
- Ships a working `cronjob-batch.yaml` directly (the same shape the
  `batch-inference` skill would otherwise generate), so a batch-only
  adopter gets a runnable example without invoking an agent.
- Ships its own PSS-labeled `namespace.yaml` (defaults straight to
  `restricted` — no `baseline` on-ramp needed, since nothing here is
  internet-facing) and a dedicated `networkpolicy-batch.yaml`: the
  base `NetworkPolicy`'s `podSelector` targets `app:
  "{@ service_kebab @}"`, which would **not** match this overlay's
  `app: "{@ service_kebab @}-batch"` pod label, silently leaving the
  batch pod covered only by the namespace-wide deny-all baseline (no
  DNS, no cloud-storage egress — the init containers would hang). The
  dedicated policy selects the batch pod correctly and grants only the
  egress a scheduled job needs (DNS, MLflow, and a cloud-storage rule
  the adopter fills in) — no ingress rules, since a `CronJob` pod never
  listens on a port.
- Reuses the **same predictor image** as the online path — batch and
  live serving are never separate builds. No new anti-pattern is needed:
  this is a Kustomize composition choice, not a new invariant.

## Scope

**In scope**: one new overlay directory, one ADR, `docs/ADOPTION.md` and
`agentic/skills/batch-inference/SKILL.md` cross-references.

**Out of scope** (deliberately, per the Engineering Calibration
Principle): a `batch` × `{gcp,aws}` × `{dev,staging,prod}` cross-product of
overlays. A 2–3-model team adopting a batch-only topology does not need
six additional overlay variants; the single cloud-agnostic
`batch-only/` overlay documents in-line how to add a cloud-specific image
patch (mirroring the pattern in `gcp-dev/kustomization.yaml`) if an
adopter needs one. Drift/performance CronJobs (`cronjob-drift.yaml`,
`cronjob-performance.yaml`) are not included by default — a batch-only
service still benefits from data drift monitoring, but wiring it is an
adopter decision (the overlay's README documents how), not a default, to
keep the on-ramp's first `kustomize build` minimal and readable.

## Consequences

**Positive**: a batch-only adopter can `kustomize build
k8s/overlays/batch-only/` and get a runnable, PSS-compliant, RBAC-scoped
manifest set with zero always-on compute for an API nobody calls —
directly closing the R7 audience-fit gap without diluting the template's
identity (still K8s-opinionated, still governed).

**Negative**: a second CronJob-authoring surface exists
(`batch-inference` skill's on-demand generation vs. this shipped static
example). Mitigated: the skill's docs now point to this overlay as the
starting point to *copy and adapt*, rather than generating from scratch,
for the batch-only case specifically.

**Neutral**: this does not change the template's non-claims list — batch
pipelines are still explicitly out of scope as a *primary* identity; this
overlay is an on-ramp for teams that need *only* that slice of the
template, not a pivot toward becoming a general orchestration platform.

## Revisit Triggers

- An adopter needs the `batch-only` overlay across more than one cloud
  simultaneously → add cloud-specific patches following the existing
  `gcp-dev`/`aws-dev` pattern, not a new abstraction.
- Drift monitoring is requested as a default for batch-only adopters →
  add `cronjob-drift.yaml` to the overlay's resource list in the same PR
  that adds the request, not speculatively now.

## Related

- `docs/decisions/ADR-001-template-scope-boundaries.md` — non-claims list
- `agentic/skills/batch-inference/SKILL.md` — the on-demand, hybrid path
- `agentic/rules/02-kubernetes.md` — CronJob + PSS conventions
- `docs/audit/AUDIT_R7_STAFF_LEAD.md` §3 — the audience-fit finding this closes
