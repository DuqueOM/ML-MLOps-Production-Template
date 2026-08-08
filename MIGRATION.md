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

## v0.23.0 → v0.24.0 (2026-08-07)

| Change | Manual action required |
|--------|------------------------|
| **`copier update` now requires `--vcs-ref`** | Use `copier update --vcs-ref=v0.24.0 --trust --defaults`. **A bare `copier update` is destructive**: it resolves to the highest-sorting tag — a frozen `v1.x` audit snapshot — and rewrites your service backwards. Measured: 627 files → 435, 582 deleted, and `.copier-answers.yml` itself removed. |
| **If you already ran a bare `copier update`** | Your service was downgraded and lost its answers file. Recover with `git revert` or `git reset` to the commit before the update — `copier update` requires a clean tree, so that commit exists. If it was already committed and pushed, restore `.copier-answers.yml` from the pre-update commit (`git show <sha>:.copier-answers.yml`) and re-run the update **pinned**. Do not re-scaffold; the answers file is recoverable from history. |

**Tracking**: see `releases/v0.24.0.md` and `CHANGELOG.md` §`[0.24.0]`.

---

## v0.22.0 → v0.23.0 (2026-08-07)

Contains a §1.3 MAJOR-class change shipped as a `v0.x.0` bump per
[`docs/RELEASING.md`](docs/RELEASING.md) §2.1. Treat it as a breaking
release.

| Change | Manual action required |
|--------|------------------------|
| **Scaffold command now requires `--vcs-ref`** | Use `copier copy --vcs-ref=v0.23.0 …`. **Without it Copier serves a frozen `v1.x` audit snapshot from April 2026**, because it resolves an unpinned git source to the highest-sorting tag and `v1.12.0` sorts above every `v0.x` tag. Symptom: 435 files and no `.copier-answers.yml` instead of 626 with one. If you scaffolded before this release, check `test -f .copier-answers.yml` — an absent file means you got the snapshot. |
| **`black`, `isort`, `flake8` pre-commit hooks removed; `ruff-check` + `ruff-format` added** (ADR-044) | Run `pre-commit install --install-hooks`. If you maintain a custom `.pre-commit-config.yaml` overlay, merge the swap in **both** the repo config and the scaffolded service's. Move any custom `[tool.black]` / `[tool.isort]` settings to `[tool.ruff]` — `line-length`, `target-version`, and `known-first-party` map across directly. |
| **`ruff format` output differs from `black`** | Expect a one-time reflow: 55 of 134 files here, 214 insertions / 290 deletions. Apply it as an **isolated commit** that changes nothing else, then register that commit in `.git-blame-ignore-revs` and enable it with `git config blame.ignoreRevsFile .git-blame-ignore-revs`. Verify equivalence by running your test suite before and after and comparing the result exactly. |
| **Ruff now lints directories flake8 skipped** | `flake8`'s `files:` pattern was `^(templates/service/|examples/)`. If your service has code under `scripts/` or a top-level `tests/`, ruff will lint it for the first time. Rule scope is parity-only (`E,W,F,I`), so findings are genuine pre-existing style issues, not new rules. |
| **Generated services gain `docs/decisions/README.md`** | No action. It explains that bare `ADR-NNN` in template-provided files are the *template's* ADRs, not yours, and points upstream for the 33 that are referenced but not vendored. If your reference checker flagged `ADR-027` or similar as missing, this is the resolution. |

**Tracking**: see `releases/v0.23.0.md` and `CHANGELOG.md` §`[0.23.0]`.

---

## v0.21.0 → v0.22.0 (2026-08-07)

| Change | Manual action required |
|--------|------------------------|
| **gitleaks pre-commit pin `v8.21.2` → `v8.30.1`** | Run `pre-commit install --install-hooks` (or just let the next commit rebuild the env). Adopters maintaining a custom `.pre-commit-config.yaml` overlay must merge the bump in **both** the repo config and the scaffolded service's. |
| **`.gitleaks.toml` singular `[allowlist]` table removed** | **Required if you customised `.gitleaks.toml`.** gitleaks >= 8.25 refuses to load a config containing both `[allowlist]` (singular) and `[[allowlists]]` (plural) — it exits with `FTL Failed to load config`. Move every `paths`/`regexes` entry from your singular block into a `[[allowlists]]` table and delete the singular one. Verify with `gitleaks detect --source=. --config=.gitleaks.toml`. |
| **CI installs a pinned gitleaks binary instead of `gitleaks-action`** | No action for adopters using the shipped workflow. If you forked `validate-templates.yml` and kept the action, be aware its bundled version may sit below the 8.25 dialect floor, in which case your CI silently ignores the `[[allowlists]]` tables. `scripts/check_gitleaks_pin.py` now fails the build on that drift — keep the three declaration sites in lockstep. |
| **Scaffolded services now contain `.copier-answers.yml`** | New services: nothing to do — keep the file committed. **Services scaffolded before this release have no update path**; see §"Recovering the update path for a service scaffolded before the fix" below for the full procedure. |
| **`test_phase0_disclosure.py` rewritten** | Only affects adopters who vendored the template's test suite and edited that file. The new version derives its requirement from the ADR Status line instead of hard-coding "Phase 0", and fails rather than skips when it cannot parse one. |

**Tracking**: see `releases/v0.22.0.md` and `CHANGELOG.md` §`[0.22.0]`.

---

## Copier scaffolding migration (ADR-030)

The scaffolder (`templates/scripts/new-service.sh`) is now a thin wrapper
around [Copier](https://copier.readthedocs.io/) instead of manual `cp -r`
+ `sed -i`. This is a structural change to how services are generated.

| Change | Manual action required |
|--------|------------------------|
| **Scaffolding engine changed** | Install `copier` (`pip install copier`). The scaffolder will not work without it. |
| **Placeholder syntax changed** | Old `{ServiceName}`, `{service}`, `{SERVICE}` placeholders are now Copier Jinja tokens: `{@ service_name @}`, `{@ service_slug @}`, etc. If you maintain custom template files, convert them. |
| **`.copier-answers.yml` created in scaffolded services** | Keep this file committed — it tracks the template version and enables `copier update` for pulling future improvements. |
| **Post-generation tasks run automatically** | Copier runs `sync_agentic_adapters.py` + `validate_agentic_manifest.py --strict` after render. If these fail, the scaffold is incomplete. |
| **Upgrading existing services** | Use `copier update` (or the `/scaffold-update` workflow) to pull template improvements into services scaffolded under the new system. Services scaffolded under the old `cp + sed` system need a one-time manual migration: commit a `.copier-answers.yml` with the original template version, then run `copier update`. |

**Tracking**: see `docs/decisions/ADR-030-copier-scaffolding-migration.md`
and `CHANGELOG.md`.

---

## Recovering the update path for a service scaffolded before the fix

**Who this applies to.** Any service generated from this template before
the release that added `templates/service/{@ _copier_conf.answers_file @}`.
Check in one command, from the service root:

```bash
test -f .copier-answers.yml && echo "update path OK" || echo "AFFECTED — no update path"
```

**What went wrong.** The template never shipped an answers-file template, so
`copier copy` produced services with no `.copier-answers.yml` — despite this
file, ADR-003, the `scaffold-update` workflow, and the post-copy message all
stating it exists. Without it `copier update` has no record of which template
revision the service came from, refuses to run, and the service is a fork
with extra steps.

**This is recoverable and does not require regenerating the service.** The
answers file is plain data; the only genuinely unrecoverable part is *which
template revision you generated from*, and that can be reconstructed.

### Step 1 — establish the originating template revision

In order of reliability:

1. **The scaffold commit date.** Find the first commit in the service repo
   (`git log --reverse --format='%H %ad' | head -1`), then pick the template
   tag that was current on that date (`git -C <template-clone> tag --sort=creatordate`
   with `git log -1 --format=%ad <tag>`).
2. **A `_commit` recorded elsewhere** — some services captured the template
   version in their own README or CHANGELOG at scaffold time.
3. **Fallback**: the oldest template tag whose scaffold output still matches
   your service's file layout.

Precision matters less than being *earlier than or equal to* the true
revision. Naming a revision newer than the real one makes `copier update`
skip changes you never received; naming an older one produces extra diff
hunks you can review and discard.

### Step 2 — write the answers file by hand

At the service root, create `.copier-answers.yml`. Every question you
answered at scaffold time must appear, plus `_src_path` and `_commit`:

```yaml
# This file is AUTOGENERATED by Copier — do not edit by hand.
_commit: v0.21.0                       # from Step 1
_src_path: gh:DuqueOM/ml-service-template
service_slug: demand_forecast          # your real answers below
gh_org: your-org
gh_repo: demand-forecast
profile: local
```

The authoritative question list is `copier.yml` in the template (every
top-level key not starting with `_`). Omitting one makes `copier update`
re-prompt for it, which is harmless.

### Step 3 — commit it, then dry-run the update

```bash
git add .copier-answers.yml && git commit -m "chore: restore copier update path"
```

`copier update` performs a three-way merge against a working tree it
expects to be clean, so commit first and run the update on a branch:

```bash
git switch -c chore/copier-update
copier update --pretend --trust
```

`--pretend` shows what would change without writing. Expect a larger diff
than a normal update: you are replaying every template improvement since
Step 1's revision in one pass. Review it before dropping `--pretend`.

### Step 4 — verify the path is live

```bash
grep '^_commit:' .copier-answers.yml
```

After a real (non-`--pretend`) update this must show the revision you
updated *to*. If it still shows the Step 1 value, the update did not apply.

> **Do not skip Step 3's branch.** The first update after a long gap is the
> one most likely to conflict with local modifications, and it is the worst
> possible moment to be merging into a dirty tree.

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
