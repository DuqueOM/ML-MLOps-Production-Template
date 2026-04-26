# Release Checklist — {ServiceName}

Use this checklist before every production release. Copy to an issue or PR description.

---

## Pre-Release

- [ ] All quality gates pass (primary metric, secondary metric, fairness DIR >= 0.80)
- [ ] No data leakage detected (suspiciously high metrics investigated; D-06)
- [ ] SHAP values computed in original feature space (D-04, D-24)
- [ ] Coverage >= 90% lines, >= 80% branches
- [ ] All anti-patterns checked (**D-01 through D-30** — see AGENTS.md Anti-Pattern Table)
- [ ] ADR created for any non-trivial decisions
- [ ] CHANGELOG.md updated with release notes
- [ ] Version bumped in pyproject.toml / requirements.txt

## Model Artifacts

- [ ] Model trained on latest validated dataset
- [ ] Model artifact uploaded to GCS/S3 (not baked into Docker image)
- [ ] Model metadata (metrics, hash, training date) recorded in MLflow
- [ ] SHA256 integrity hash matches between training and serving
- [ ] `promote_model.sh` quality gates passed

## Docker

- [ ] Multi-stage build, non-root USER
- [ ] HEALTHCHECK instruction present
- [ ] No model artifacts in image — init container pattern (D-11)
- [ ] Single uvicorn worker (D-01); horizontal scale via HPA, never `--workers N`
- [ ] Image tagged with immutable version (never overwrite)
- [ ] Trivy scan passes (no critical/high CVEs; D-19)
- [ ] Image signed with Cosign keyless (D-19)
- [ ] SBOM generated (Syft) and attached as attestation (D-30)

## Kubernetes

- [ ] `kubectl config current-context` verified (correct cluster)
- [ ] HPA uses CPU-only metric, never memory (D-02)
- [ ] Init container downloads correct model version (D-11)
- [ ] NetworkPolicy applied
- [ ] RBAC (Role + RoleBinding) applied
- [ ] ServiceAccount with Workload Identity (GCP) / IRSA (AWS) configured (D-18)
- [ ] Resource requests/limits set appropriately
- [ ] Liveness probe on `/health`, readiness probe on `/ready` — split (D-23)
- [ ] `terminationGracePeriodSeconds` strictly greater than `--timeout-graceful-shutdown` (D-25)
- [ ] `PodDisruptionBudget` shipped, `minAvailable: 1`, HPA `minReplicas >= 2` (D-27)
- [ ] Pod Security Standards `restricted` profile applied to namespace (D-29)
- [ ] Kyverno admission policy verifying Cosign signature applies in prod ns

## Infrastructure

- [ ] Terraform state is remote (GCS for GCP, S3+DynamoDB for AWS)
- [ ] No secrets in tfvars or repository
- [ ] `terraform plan` shows expected changes only
- [ ] tfsec + Checkov pass

## CI/CD

- [ ] CI pipeline green (lint + test + build + scan + sign + SBOM; D-19, D-30)
- [ ] OpenAPI snapshot test passes — no unintended schema break (D-28)
- [ ] Deploy workflow uses `dev → staging → prod` chain via `deploy-common.yml` (D-26, ADR-011)
- [ ] Production env requires 2 reviewers + `wait_timer: 5` + protected_tags (ADR-011)
- [ ] No static cloud creds; OIDC/WIF (GCP) or IAM Identity Provider (AWS) only (D-17, D-18)
- [ ] Smoke test passes after deployment
- [ ] Rollback plan documented (link to `/rollback` workflow)

## Monitoring

- [ ] Prometheus alerts configured (P1-P4)
- [ ] Drift detection CronJob running
- [ ] Drift heartbeat alert active (fires if CronJob missing > 48h)
- [ ] Grafana dashboard deployed
- [ ] `/health` and `/metrics` endpoints responding

## Post-Release

- [ ] Smoke test in production environment
- [ ] Drift detection baseline updated if data distribution changed
- [ ] GitHub Release published with notes from CHANGELOG
- [ ] Team notified of release

---

## Multi-Cloud Verification

### GCP (GKE)

- [ ] Artifact Registry image pushed
- [ ] Workload Identity binding verified
- [ ] GCS model bucket accessible from pod
- [ ] `kubectl apply -k k8s/overlays/gcp-prod/` (CI digest-pin step replaces newTag with @sha256)

### AWS (EKS)

- [ ] ECR image pushed
- [ ] IRSA role binding verified
- [ ] S3 model bucket accessible from pod
- [ ] `kubectl apply -k k8s/overlays/aws-prod/` (CI digest-pin step replaces newTag with @sha256)
