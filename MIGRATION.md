# MIGRATION.md — Adopter migration guide between releases

This file documents adopter-visible changes between releases of the
ML-MLOps Production Template. Each row covers a `from → to` transition
that touched **scaffolded output**, **wire-level schemas**, **overlay
or namespace names**, **pre-commit hook contract**, or any other
contract listed in [`docs/RELEASING.md`](docs/RELEASING.md) §1.

This file was added in response to R4 audit finding C5: adopters who
scaffolded under `v1.7` had no documented path to `v1.12`. Tags
`v1.0.0`–`v1.12.0` remain immutable; this file is the forward-looking
contract that prevents future versions from breaking adopters silently.

> Releases not listed below introduced **no adopter-visible breaking
> changes** under the §1 contract definition. Skipping them in this
> file is intentional, not an oversight.

---

## v1.11.0 → v1.12.0 (2026-04-29)

| Change | Manual action required |
|--------|------------------------|
| Closed-loop workflow payload schema realignment | If you copied or extended `golden-path-extended.yml`, replace the request body `{feature_1, feature_2, feature_3}` with `{entity_id, feature_a, feature_b, feature_c, slice_values}`. The previous payload returned 422 against the live `/predict` schema. |
| Closed-loop metric fallback label | Update any custom Prometheus query that referenced `requests_total{endpoint="/predict"}` — the counter only carries `status`, not `endpoint`. Use `requests_total{status=~"2xx\|4xx"}` instead. |
| Drift CronJob Python module path (D-32) | Re-scaffold the service or apply the snake-case fix manually. Manifest now uses `src/{service}/monitoring/drift_detection.py` (snake-case). The kebab-case form (`{service-name}`) caused `ModuleNotFoundError` at runtime even though `kubectl apply` succeeded. |
| Pre-commit hook contract (9 → 14 hooks) | Run `scripts/dev-setup.sh` (idempotent) or `make verify-hooks`. Prior installs may not have `pre-push` hooks. Failure to install both stages means the scaffold-smoke pre-push hook silently never runs. |
| New mandatory hooks: `mypy`, `bandit`, `validate-agentic`, `ci-autofix-policy-contract` | Adopters who maintained custom `.pre-commit-config.yaml` overlays must merge the new hooks. The `ci-autofix-policy-contract` hook fires only when policy YAMLs change; the other three fire on every commit. |

**Tracking**: see `releases/v1.12.0.md` and `CHANGELOG.md` §`[1.12.0]` § `### Breaking for adopters`.

---

## v1.10.0 → v1.11.0 (2026-04-28)

| Change | Manual action required |
|--------|------------------------|
| GCP IAM split surface | Run `terraform plan` against your existing GCP project before applying. Per-service identity bindings introduced in `gcp/iam.tf` change the IAM model. Confirm no in-flight workload loses required bindings; coordinate the apply window with workload owners. |
| `templates/config/ci_autofix_policy.yaml` and `model_routing_policy.yaml` introduced | Phase 0 only — no runtime behavior change. To opt into the policy contract test, ensure `pytest templates/service/tests/test_ci_autofix_policy_contract.py` passes locally. No change required for adopters who do not use the autofix lane. |
| 12 new `make` targets in non-agentic on-ramp | Adopters with custom `Makefile` overlays MUST merge the new targets per [`docs/ADOPTION.md`](docs/ADOPTION.md). Conflicts most likely on `scaffold`, `validate`, and `deploy-dev` target names — rename custom targets to avoid collision. |
| New `NOTICE`, `DCO.md`, `CODEOWNERS` files | Apache 2.0 + DCO compliance. If forking, preserve `NOTICE` and reference it in your own `LICENSE` chain. Update `CODEOWNERS` to reflect your team. |

**Tracking**: see `releases/v1.11.0.md` and `CHANGELOG.md` §`[1.11.0]` § `### Breaking for adopters`.

---

## v1.9.0 → v1.10.0 (2026-04-26) — **highest-impact migration in the project's history**

Under [`docs/RELEASING.md`](docs/RELEASING.md) §1.3 this release SHOULD have been
`v2.0.0`. Tag `v1.10.0` is immutable; the changes below are listed in priority
order. Adopters running anything in production from `v1.9.0` or earlier should
plan a maintenance window.

| Change | Manual action required |
|--------|------------------------|
| **Six environment overlays renamed** | `gcp-production` → `gcp-prod`; `aws-production` → `aws-prod`. New: `gcp-dev`, `gcp-staging`, `aws-dev`, `aws-staging`. Update every reference: custom CI workflows, deploy scripts, `kubectl` invocations, ArgoCD `Application` manifests, GitOps repos. **Pre-`v1.10` deploys for dev / staging never worked**: adopters who believed they had dev/staging deploys did not. Verify with `kubectl get ns` after migration. |
| **Cosign signing path now wired** | Prior versions advertised image signing but did NOT install `cosign` in any workflow. Install `cosign` on your CI runners. If you ran Kyverno admission policies in audit mode tolerating unsigned images, plan the move to enforce mode AFTER confirming all images carry signatures. Use the kind-cluster procedure in `docs/runbooks/kyverno-admission-validation.md` (Sprint 1). |
| **Image digest pinning is now mandatory** | `kustomize edit set image <name>=<repo>@<digest>` runs BEFORE every `kubectl apply`. If you deployed by tag (e.g. `:latest`, `:1.0`), switch to digest references. Mutable tags are no longer supported by the deploy chain. Update any external references (Helm charts, manual `kubectl apply` invocations). |
| **Init-container model loading** (D-11) | If you baked model artifacts into your Docker image, migrate to the init-container pattern: artifacts download at runtime into an `emptyDir` volume. Update your image build to remove the artifact bake-in. The new pattern is documented in `docs/runbooks/digest-pin-init-image.md`. |
| **Pod Security Standards labels mandatory** (D-29) | Each overlay carries `pod-security.kubernetes.io/enforce=baseline` for dev/staging and `enforce=restricted` for prod. Adopters with custom namespaces MUST add the labels or admission control rejects the pods. Apply `kubectl label namespace <name> pod-security.kubernetes.io/enforce=<level>` per environment. |
| **CycloneDX SBOM attestation** (D-30) | The deploy chain now generates and attaches an SBOM via Cosign attestation. Install `syft` on CI runners. If you maintain a private registry, ensure it stores OCI artifacts (most modern registries do). |

**Tracking**: see `releases/v1.10.0.md` and `CHANGELOG.md` §`[1.10.0]` § `### Breaking for adopters`. Owner for assistance: ML Platform via `audit-r4` issue label.

---

## v1.8.1 → v1.9.0 (2026-04-24)

No adopter-visible breaking changes. Batch inference, devcontainer, secret-rotation
runbook, and DORA scaffolding are additive.

---

## v1.8.0 → v1.8.1 (2026-04-24)

| Change | Manual action required |
|--------|------------------------|
| Pod Security Standards (D-29) introduced as policy YAML (pre-overlay rename of v1.10) | At v1.8.1 PSS labels were templates; not enforced until v1.10. No immediate migration; v1.9 → v1.10 row above subsumes this work. |
| `deployment.yaml` adds pod-level and container-level `securityContext` (`runAsNonRoot: true`, `capabilities.drop: [ALL]`, `seccompProfile: RuntimeDefault`) | If your image runs as root, switch the base image or set a non-root user. Inspect `Dockerfile` for `USER` directive. |
| SBOM attestation introduced (D-30) | Pre-cursor to v1.10 enforcement. Adopters can opt in by installing `syft` on CI runners. |

---

## v1.7.1 → v1.8.0 (2026-04-24)

No adopter-visible breaking changes (per the v1.8.0 release-note `No breaking
runtime changes` declaration). Typed agent handoffs, `AuditLog`, and OpenAPI
contract versioning are additive. Existing services continue to function.

---

## v1.7.0 → v1.7.1 (2026-04-24)

| Change | Manual action required |
|--------|------------------------|
| Model warm-up + readiness gating (D-23, D-24) | If you maintained custom `livenessProbe` / `readinessProbe` / `startupProbe` definitions, replace them with the split-probes pattern. Pre-`v1.7.1` deploys had a 300–800 ms cold-inference window during which pods received traffic before SHAP was ready. |
| PodDisruptionBudget + Rego v1 policies (D-27) | Apply the new `pdb.yaml` from `templates/k8s/base/`. Adopters who maintained custom PDBs should reconcile minimum-replicas assumptions (default minimum is 1 for dev, 2 for staging, 3 for prod). |
| Champion/Challenger in Argo Rollouts (G-02b) | Adopters using stock `Deployment` are unaffected. If you opt into Argo Rollouts, follow `docs/runbooks/` (no specific migration; this is opt-in). |
| Environment promotion gates dev → staging → prod (D-26, ADR-011) | Wire `templates/cicd/deploy-common.yml` into your existing CI. Pre-`v1.7.1` deploys could skip staging; the new gate refuses prod deploys without staging success. |

---

## v1.6.0 → v1.7.0 (2026-04-23)

| Change | Manual action required |
|--------|------------------------|
| **Closed-loop monitoring introduced**: prediction logger, ground-truth ingestion, sliced performance, champion/challenger | This is a feature addition, not a contract break, but adopters using the template before v1.7.0 had **no** closed-loop monitoring at all. Wire the new `prediction_logger` into `fastapi_app.py` and choose a backend (parquet, BigQuery, SQLite, stdout) via `PREDICTION_LOG_BACKEND`. |
| `PredictionEvent` dataclass requires `prediction_id` and `entity_id` (D-20) | If you log predictions through any custom path, add both fields. The dataclass refuses construction otherwise. |
| Daily ground-truth CronJob requires user implementation | The CronJob skeleton ships in `monitoring/ground_truth.py`; the adopter implements the `fetch_ground_truth(entity_ids)` function for their domain. |

---

## v1.0.0–v1.5.x → v1.6.0

These releases predate the closed-loop monitoring foundation and the Pandera
schema discipline. Adopters running services from these versions should plan
a complete migration to at least v1.10.0 rather than incrementally upgrading,
because most subsequent contract changes assume v1.7.0+ closed-loop infrastructure
is in place.

If incremental upgrade is required, sequence:

1. v1.6.0 → v1.7.0 (closed loop)
2. v1.7.0 → v1.7.1 (probes + PDB + env gates)
3. v1.7.1 → v1.8.x (typed handoffs)
4. v1.8.x → v1.10.0 (overlays + Cosign + digest + init container — **this row alone is what `docs/RELEASING.md` calls a MAJOR**)
5. v1.10.0 → v1.12.0 (per the rows above)

---

## Compatibility commitments going forward

Per [`docs/RELEASING.md`](docs/RELEASING.md):

- The next breaking change in scaffolded output bumps to **v2.0.0**, not v1.13.0.
- Every MAJOR release adds a row to this file in the SAME PR that introduces
  the breaking change. The release is not mergeable without the migration row.
- PATCH releases (`v1.12.1`, `v1.12.2`, …) carry a `### Patch — no migration` line in
  this file as a positive confirmation that no migration is required.

This file is reviewed alongside CODEOWNERS for every release.
