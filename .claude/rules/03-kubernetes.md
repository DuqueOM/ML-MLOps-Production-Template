---
paths:
  - "k8s/**/*.yaml"
  - "**/k8s/**/*.yaml"
  - "templates/k8s/**/*"
---

# Kubernetes Rules

## Serving manifests
- NEVER `uvicorn --workers N` — always 1 worker, HPA handles horizontal scale (D-01)
- HPA uses CPU only — NEVER memory for ML pods (fixed RAM prevents scale-down) (D-02)
- NEVER bake models into Docker images — use Init Container + emptyDir (D-11)
- ALWAYS use Workload Identity (GCP) / IRSA (AWS) — no hardcoded credentials (D-18)
- ALWAYS verify `kubectl config current-context` before applying manifests
- NEVER overwrite existing container image tags — tags are immutable

## Probes and graceful shutdown (D-23, D-25)
- `livenessProbe` → `/health`, `readinessProbe` → `/ready` — MUST differ
- `startupProbe` → `/health` with `failureThreshold: 24` to absorb cold start
- `terminationGracePeriodSeconds` (30s) STRICTLY GREATER than uvicorn
  `--timeout-graceful-shutdown` (20s)

## PodDisruptionBudget (D-27)
- Every Deployment ships a `PodDisruptionBudget` with `minAvailable: 1`
- HPA `minReplicas: 2` — a PDB with `minAvailable: 1` cannot tolerate
  voluntary disruption on a single-replica service

## Pod Security Standards (D-29)
- Pod `securityContext`: `runAsNonRoot: true`, `runAsUser: 65532`,
  `seccompProfile.type: RuntimeDefault`
- Container `securityContext`: `allowPrivilegeEscalation: false`,
  `capabilities.drop: [ALL]`
- Namespace labels: prod `enforce: restricted`; dev/staging
  `enforce: baseline` + `warn/audit: restricted`

## Environment promotion (D-26)
- Deploys chain dev → staging → prod with GitHub Environment Protection
  (1 reviewer at staging, 2 reviewers + wait_timer + tag-only at prod)
- Use the reusable `deploy-common.yml` — single source of truth for
  build/apply/smoke-test (ADR-011)

## Images (D-19, D-30)
- Sign with Cosign keyless OIDC
- Generate CycloneDX SBOM via Syft, attach with `cosign attest --type cyclonedx`
