# ADR-013: GitOps Strategy — `kubectl apply` now, ArgoCD when it pays off

## Status

Accepted (current: `kubectl apply` via GitHub Actions; ArgoCD as future trigger)

## Date

2026-04-24

## Context

The template uses `kubectl apply -k k8s/overlays/<env>` driven by GitHub
Actions (ADR-011) across 3 environments × 2 clouds = 6 targets. Each
environment is declarative (Kustomize), auditable (GitHub Deployments
API), and gated (Environment Protection Rules).

The industry is gravitating toward ArgoCD / Flux for declarative GitOps
with continuous reconciliation. The question is: when does the template
switch?

## Options considered

### Option A — Stay on `kubectl apply` (current)

- Pros: zero new infra, well-understood, integrates with Environment
  Protection Rules, 4-minute deploys, CI is the sole pusher.
- Cons: state drift possible (someone applies manually), no drift
  detection, no pull-based reconciliation, no `AppSet` for multi-tenant.

### Option B — ArgoCD per cluster

- Pros: continuous reconciliation, automatic drift detection,
  AppProject RBAC, graphical UI for operators, `AppSet` for many
  services, first-class health checks via Argo Rollouts (already in
  use for canaries).
- Cons: one more control-plane service to operate (ArgoCD itself must
  stay healthy), RBAC model is another source of truth, initial setup
  complexity (App of Apps pattern), bootstrap chicken-and-egg
  (something must install ArgoCD).

### Option C — Flux per cluster

- Pros: smaller footprint than ArgoCD, SOPS native, multi-tenancy via
  namespaces.
- Cons: less-friendly UI for non-platform teams, smaller ecosystem than
  ArgoCD, less adopted in template's target users.

## Decision

**Stay on Option A until one of the revisit triggers fires.** When
triggered, **adopt Option B (ArgoCD)** — not Flux — because:

1. Argo Rollouts is already our canary platform; ArgoCD is the matching
   CD plane with shared mental model.
2. Graphical UI accelerates ops/SRE adoption compared to Flux.
3. `ApplicationSet` directly supports fan-out across environments,
   which matches our dev/staging/prod shape.

## Revisit triggers

Migrate to ArgoCD when **any** of:

- **>5 services** in the template — manual `kubectl apply` per service
  × environment starts to hurt. ArgoCD `ApplicationSet` auto-discovers
  directories.
- **Multi-cluster prod** (e.g., GKE + EKS + on-prem) — ArgoCD manages
  all targets from one control plane; `kubectl apply` would need 3
  parallel credentials.
- **Drift incidents** — if we see ≥2 incidents caused by out-of-band
  `kubectl apply`, the reconciliation loop pays for itself.
- **GitOps-first posture from the org** — some platforms mandate
  ArgoCD for compliance; the template should not stand in the way.

## Migration path (when triggered)

1. Stand up ArgoCD via Helm chart on one dev cluster; bootstrap with
   App-of-Apps pattern reading `k8s/argocd/` directory.
2. Create one `Application` per `(cloud, env, service)` combination;
   initial `syncPolicy: manual` so the team learns the UI before
   automation.
3. Keep `deploy-*.yml` workflows as `ci` — they build/push/sign the
   image; ArgoCD then reconciles to the new digest.
4. Remove the `kubectl apply` step from the workflow; replace with
   `argocd app sync <name>` (or enable `automated: { prune: true }`).
5. Environment Protection Rules become `AppProject.syncWindows`.
6. Document in a new ADR-014 documenting the **actual** migration and
   lessons.

## Consequences of staying on `kubectl apply` (today's posture)

### Positive

- Simple, auditable, uses the primitives every engineer already knows.
- The 3-env chain + protection rules give human review at the points
  that matter.
- No separate control plane to run.

### Negative

- No continuous reconciliation; manual drift survives until the next CI run.
- No UI for operators to see "what is deployed vs. what is in git".
- Some tooling (Argo Rollouts dashboard) assumes ArgoCD presence.

### Mitigations in the current posture

- `rule-audit` skill (v1.8.0) detects drift between committed manifests
  and deployed state via periodic scans.
- Environment Protection Rules prevent silent out-of-band deploys (prod
  is tag-gated + 2 reviewers).
- Lightweight `kubectl diff` in CI would alert on unexpected state —
  feasible but not yet implemented.

## Related

- ADR-005 — Behavior Protocol (the AUTO/CONSULT/STOP discipline
  transfers verbatim to ArgoCD's `syncPolicy`)
- ADR-011 — Environment Promotion Gates (becomes `AppProject.syncWindows`
  post-migration)
- `.windsurf/rules/05-github-actions.md` §Environment Promotion Gates
- `.windsurf/skills/rule-audit/SKILL.md` — drift detection today
