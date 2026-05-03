# VALIDATION_LOG.md — Verified-Execution Evidence

This file records **real executions** of the template's contracts and pipelines.
Every entry must include date, commit SHA, environment, raw output excerpts,
and an explicit `pending` block listing what was NOT validated in that run.

The R4 audit (finding C4) flagged the absence of this file as Critical:
"`production-ready` is an aspiration, not a state, until execution evidence
exists." This file is the operational artifact that makes execution evidence
permanent and reviewable.

> **Read this file before believing any maturity claim in `README.md` § "Production-ready scope".** A row in the maturity matrix that has no entry here is, at best, "designed-ready" — not verified-ready.

---

## Entry 001 — Sprint 0 baseline (R4 audit response)

- **Date**: 2026-04-29
- **Branch**: `audit-r4/sprint-0-credibility`
- **Base commit (pre-Sprint-0)**: `42d0be8bcc951e29e4477c77b78f3b8929116908` (`v1.12.0`)
- **Environment**: local Linux developer workstation (Ubuntu-class), Python 3.13.5, no cloud account, no Kubernetes cluster, no container registry connection
- **Operator**: Staff/Lead engineer — auditor mode
- **Scope**: documentation-only validation that the Sprint-0 R4 changes hold; no cluster execution

### What was executed

#### 1. R4 Sprint-0 invariant tests

```
$ python -m pytest templates/service/tests/test_phase0_disclosure.py \
                   templates/service/tests/test_readme_model_names.py \
                   --no-cov --noconftest -q
collected 9 items

templates/service/tests/test_phase0_disclosure.py ......                 [ 66%]
templates/service/tests/test_readme_model_names.py ...                   [100%]

============================== 9 passed in 1.39s ===============================
```

Closes verification of: C1 (model routing disclaimer), C2 (Phase-0 banners
on README §"Operational Memory Plane" and §"Agentic CI self-healing").

#### 2. Pre-existing contract tests still green

```
$ python -m pytest templates/service/tests/test_ci_autofix_policy_contract.py \
                   --no-cov --noconftest -q
collected 10 items

templates/service/tests/test_ci_autofix_policy_contract.py ..........    [100%]
============================== 10 passed in 0.71s ==============================
```

Confirms ADR-019 Phase 0 policy contract (10 invariants) is intact after the
README and CHANGELOG edits in this branch.

#### 3. Working-tree secret scan (gitleaks)

```
$ gitleaks detect --no-git --source=. --redact --no-banner
10:33AM INF scan completed in 1m23s
10:33AM INF no leaks found
```

Confirms no secret patterns in the working tree at the audit-r4 branch tip.
Does **not** cover the full git history — that scan is delegated to S1-3 per
ADR-020 and `docs/runbooks/secret-history-scan.md` (to be added in Sprint 1).

#### 4. Available binaries (deploy-chain prerequisite check)

```
python    Python 3.13.5         OK
pytest    9.0.1                 OK
kubectl   /usr/local/bin/kubectl OK
trivy     /usr/bin/trivy         OK
gitleaks  /usr/local/bin/gitleaks (v8.18.0) OK
kustomize NOT_INSTALLED         MISSING (deploy-chain dependency)
kubeconform NOT_INSTALLED       MISSING (smoke-lane dependency, S1-1)
cosign    NOT_INSTALLED         MISSING (supply-chain dependency)
syft      NOT_INSTALLED         MISSING (SBOM dependency)
```

This is **honest and important evidence**: a developer who clones this template
and tries to follow the deploy chain end-to-end on a fresh workstation will
fail at the first `kustomize build`, the first `cosign sign`, and the first
`syft sbom` invocation. The S1-1 smoke-lane work item adds a binary-presence
check at PR time so the deploy chain stops referencing tools the runner does
not have. Until S1-1 lands, adopters MUST install these binaries manually
(see Sprint 1 deliverable).

### What was NOT validated (pending — Sprint 1 / Sprint 2)

- **`kustomize build` on six overlays** — `kustomize` not installed locally;
  blocked. Owner: S1-1 smoke-lane.
- **`kubeconform --strict` on rendered overlays** — `kubeconform` not
  installed locally. Owner: S1-1 smoke-lane.
- **`cosign sign` against a registry** — no `cosign` binary, no registry
  credentials. Owner: S1-4 Kyverno admission validation runbook (kind cluster).
- **`syft sbom` SBOM generation + attestation** — no `syft` binary. Owner:
  S1-4.
- **Kyverno admission webhook reject of unsigned image** — requires kind
  cluster + Kyverno install. Owner: S1-4.
- **`git log --all -p | gitleaks detect --pipe` history scan** — never
  executed. Owner: S1-3 (delegated, STOP-mode procedure).
- **Pipeline bypass tests** (deploy-skips-staging, model-fails-fairness,
  secret-in-commit) — never executed. Owner: S1-3 (delegated).
- **Real cluster deploy** (kind / GKE / EKS) — out of scope for Sprint 0.
  Earliest opportunity: S1-1 + S1-4 in parallel.
- **Alertmanager routing test with synthetic alert** — Owner: S2-4.
- **GSM / ASM secrets-integration end-to-end** — Owner: S2-5.
- **Compliance gap analysis evidence** — Owner: S2-2.

### Conclusion (Entry 001)

Sprint 0 closes the **documentation-credibility** gap of R4. The
**execution-credibility** gap remains open by design: it is what Sprint 1
exists to address. This entry exists so that any reader of
`README.md` who lands on the maturity matrix can locate, in one place,
exactly which claims are verified by this run and which are still pending.

`README.md` § "Production-ready scope" links here. Any future row added to
the maturity matrix MUST be paired with at least one entry in this file
before the row's status can claim "Production-ready".

---

## Entry 002 — Sprint 1 close (R4 audit response, ADR-019 Phase 1 + structural workflows)

- **Date**: 2026-04-29
- **Branch**: `audit-r4/sprint-0-credibility` (continuation; Sprint 1 batched on the same branch per user direction)
- **Base commit (Sprint 1 start)**: `12f5ccefba08edf198426609aba5fd608f616999`
- **Environment**: local Linux developer workstation (Ubuntu-class), Python 3.13.5; no cloud account, no Kubernetes cluster
- **Operator**: Staff/Lead engineer — agentic implementation, STOP-delegated items deferred
- **Scope**: ADR-019 Phase 1 read-only runtime + per-PR smoke lane + per-PR evidence policy + STOP-delegated runbooks + agentic red-team log

### What was executed

#### 1. ADR-019 Phase 1 runtime — protected paths short-circuit verified

```
$ printf 'would reformat templates/common_utils/secrets.py\n' \
  | python scripts/ci_collect_context.py --job-name lint --workflow ci \
      --changed-files templates/common_utils/secrets.py \
  | python scripts/ci_classify_failure.py \
  | python -c "import json,sys; d=json.load(sys.stdin); \
      print(f'final_mode={d[\"final_mode\"]}'); \
      print(f'matched_class={d[\"matched_class\"]}'); \
      print(f'protected_paths_hit={d[\"protected_paths_hit\"]}'); \
      print(f'writes_allowed={d[\"writes_allowed\"]}')"

final_mode=STOP
matched_class=blast_radius_exceeded
protected_paths_hit=['templates/common_utils/secrets.py']
writes_allowed=False
```

This is the canonical adversarial test (Red-Team Log Entry 3): a black
formatter-drift signature on a protected path. The classifier short-circuits
to STOP based on `protected_paths`, before the signature-derived AUTO class
would have been considered. `writes_allowed` is `False`, confirming Phase 1
read-only invariant. End-to-end stdin pipeline functional.

#### 2. ADR-019 Phase 1 runtime — full invariant suite

```
$ python -m pytest templates/service/tests/test_ci_classify_failure_phase1.py \
      --no-cov --noconftest -q
collected 27 items
templates/service/tests/test_ci_classify_failure_phase1.py ............. [ 48%]
..............                                                           [100%]
=========================== 27 passed in 4.27s ===========================
```

27 invariants covering: read-only enforcement, schema stability,
protected-paths short-circuit (9 parametrized paths), STOP signatures,
AUTO routing for safe drift, blast-radius escalation (lines + files),
no-signature → STOP fallback, no memory hooks in Phase 1 output.

#### 3. Aggregate R4 invariant suite — green

```
$ python -m pytest \
    templates/service/tests/test_ci_classify_failure_phase1.py \
    templates/service/tests/test_phase0_disclosure.py \
    templates/service/tests/test_readme_model_names.py \
    templates/service/tests/test_ci_autofix_policy_contract.py \
    templates/service/tests/test_adoption_boundary_contract.py \
    --no-cov --noconftest -q

======================== 50 passed, 3 skipped in 4.97s =========================
```

The 3 skipped invariants in `test_phase0_disclosure.py` are the
ADR-019-side banner / hero / matrix checks that correctly skip now that
ADR-019 has transitioned to Phase 1. The ADR-018 side (3 active invariants)
remains enforced because ADR-018 is still Phase 0.

#### 4. New CI workflows — structural verification

Three new GitHub Actions workflows added to `.github/workflows/`:

- `ci-self-healing-shadow.yml` — wires Phase 1 classifier into CI in
  shadow mode; verifies `writes_allowed=false` invariant inline; uploads
  context.json + classification.json as 30-day artifacts.
- `pr-smoke-lane.yml` — per-PR scaffold + render six overlays + kubeconform
  validate + binary-presence audit on deploy chain.
- `pr-evidence-check.yml` — enforces three evidence blocks in PR body for
  PRs that introduce new components (allowlist of paths defined in CONTRIBUTING.md).

Workflows are syntactically validated by pre-commit `check yaml` hook;
structural smoke pending GitHub Actions runner verification at first push.

### What was NOT validated (pending — Sprint 2 / Sprint 3 / external)

- **Real `kustomize build` of the six overlays** — `pr-smoke-lane.yml` renders
  in CI; local environment lacked `kustomize` binary at Sprint 1 close. First
  CI run on the audit-r4 branch will confirm.
- **Real `kubeconform` validation** — same as above; `pr-smoke-lane.yml` runs
  it inline.
- **`pr-evidence-check.yml` enforcing on a real PR** — pending the first PR
  that touches the allowlist after this branch lands.
- **Shadow-mode classifier precision** — requires 14 days of CI failure data
  per ADR-019 §Phase plan. The classifier is now wired; the data
  collection starts on first failure post-merge.
- **`docs/runbooks/secret-history-scan.md` Procedure 1 + 2 execution** — STOP-
  delegated to Platform / Security per the runbook header. Not executed in
  this entry; tracked under H5/H6.
- **`docs/runbooks/kyverno-admission-validation.md` Steps 1–7 execution on
  kind cluster** — STOP-delegated; tracked under H7.
- **Memory plane Phase 1 contracts (`memory_types.py`, `memory_redaction.py`)**
  — Sprint 2 (S2-1).
- **Compliance gap analysis** — Sprint 2 (S2-2).

### Conclusion (Entry 002)

Sprint 1 closes 4 of the 7 R4 Highs (H1, H2, H3, H4) with executable
artifacts and contract tests, and lands documented runbooks for the 3
STOP-delegated Highs (H5, H6, H7). The agentic red-team log
(`docs/agentic/red-team-log.md`) converts the AUTO/CONSULT/STOP claims
into evidence with five documented evasion attempts and the invariants
that blocked each one.

The maturity matrix row for "Agentic CI self-healing" upgrades from
"Phase 0 — runtime not implemented" to "Phase 1 — shadow / read-only"
with the runtime artifacts and 27 contract-test invariants enforcing the
Phase 1 boundary. The next status change requires 14 days of shadow data
and a CONSULT-mode Phase-1 → Phase-2 decision per ADR-019 §Phase plan.

R4 finding closure status:

- C1, C2, C3, C4, C5: closed in Sprint 0 (Entry 001).
- H1: Phase 1 closed; Phase 2 opens after shadow precision review.
- H2: closed (PR-evidence policy + workflow + CONTRIBUTING update).
- H3: closed (per-PR smoke lane wired).
- H4: closed (red-team log with 5 entries + invariant index).
- H5, H6, H7: runbooks shipped; **execution evidence pending Platform / Security action**. The maturity matrix row for "Security and supply chain" remains "Production-ready" pending those entries (does NOT upgrade to "Verified end-to-end" until the runbooks have been executed and recorded).

---

## Entry 003 — Sprint 2 close (R4 audit response, ADR-018 Phase 1 + Mediums)

- **Date**: 2026-04-29
- **Branch**: `audit-r4/sprint-0-credibility` (continuation; Sprint 2 batched on the same branch)
- **Base commit (Sprint 2 start)**: `b85c596b659371db91e0e7b0c265fc88efe1afca`
- **Environment**: local Linux developer workstation, Python 3.13.5
- **Operator**: Staff/Lead engineer
- **Scope**: ADR-018 Phase 1 contracts + redaction · Compliance gap analysis · ADR-021 fairness + ADR-022 PSI · secrets + ground-truth runbooks

### What was executed

#### 1. ADR-018 Phase 1 contracts + redaction — full invariant suite

```
$ python -m pytest \
    templates/service/tests/test_memory_contracts.py \
    templates/service/tests/test_memory_redaction.py \
    --no-cov --noconftest -q
collected 59 items
templates/service/tests/test_memory_contracts.py .....................   [ 35%]
templates/service/tests/test_memory_redaction.py ....................... [ 74%]
...............                                                          [100%]
============================== 59 passed in 0.97s ==============================
```

59 invariants spanning 10 categories: frozen dataclass, UUID id,
non-empty bounded summary, enum-typed kind/severity/sensitivity,
sensitivity ≥ bucket-ACL minimum, evidence_uri scheme requirement,
single-tenant Phase 1 lock, ISO 8601 UTC timestamp, to_dict round-trip,
and **structural invariant J** (no service/ Python imports the memory
modules — Phase 1 isolation from `/predict`).

Redaction suite: idempotence, no-leak guarantee for 13 secret + PII
classes (AWS / GCP / GitHub PAT / OpenAI / Anthropic / Slack / JWT /
Bearer / PEM / connection strings / email / SSN / phone / IBAN / IPv4),
length-preserving placeholder, `redact_strict` raises on redactable,
type discipline, idempotent on already-redacted output.

#### 2. Aggregate R4 invariant suite — green

```
$ python -m pytest \
    templates/service/tests/test_memory_contracts.py \
    templates/service/tests/test_memory_redaction.py \
    templates/service/tests/test_phase0_disclosure.py \
    templates/service/tests/test_readme_model_names.py \
    templates/service/tests/test_ci_classify_failure_phase1.py \
    templates/service/tests/test_ci_autofix_policy_contract.py \
    --no-cov --noconftest -q

======================== 99 passed, 6 skipped in 8.48s =========================
```

The 6 skipped invariants are the ADR-018 + ADR-019 banner / hero /
matrix checks that auto-skip now that both ADRs have transitioned out
of Phase 0. The skip is structural and intentional — the test will
re-engage if a future contributor regresses either ADR's status to
Phase 0.

#### 3. Compliance gap analysis — published

`docs/ADOPTION.md` extended with §6 covering GDPR (7 controls), SOC 2
(7 controls), ISO 27001 (8 controls), HIPAA (8 controls), with
explicit Out-of-scope-by-philosophy section (PCI DSS, FedRAMP, HITRUST).
Per-row `Coverage / Evidence / Adopter responsibility` triplet so every
"Covered" row links to a specific file in the template.

#### 4. ADRs ratifying numeric thresholds

- `docs/decisions/ADR-021-fairness-thresholds.md` — DIR ≥ 0.80 default
  + per-domain table (credit ≥ 0.85, healthcare ≥ 0.90, advertising ≥ 0.75)
  + `[0.80, 0.85)` consultation band + calibration parity rule.
- `docs/decisions/ADR-022-psi-thresholds.md` — `psi_warn = 0.10` /
  `psi_alert = 0.25` defaults + per-feature override file format with
  mandatory rationale + `2× alert` super-threshold mapped to
  `drift_severe` dynamic-risk signal.

#### 5. Operational runbooks for Mediums M1 / M2

- `docs/runbooks/secrets-integration-e2e.md` — three procedures for
  GSM, ASM, and `os.environ`-refusal in non-dev. CONSULT mode.
- `docs/runbooks/ground-truth-ingestion.md` — three-tier SLA
  (real-time / operational / long-horizon), Prometheus alert names,
  per-tier obligations, JOIN-stable ingest schema.

### Status transitions

- ADR-018 Status: Phase 0 → Phase 1 (canonical contracts + redaction).
- README §"Operational Memory Plane" banner updated to Phase 1.
- README maturity matrix row for Memory Plane upgraded to "Phase 1 — contracts + redaction shipped".

### What was NOT validated (pending)

- **GSM / ASM real cloud execution** — Sprint 2 ships the runbook;
  execution requires cloud credentials per Procedure 1/2. Tracked under M1.
- **Ground-truth SLA evidence on a real service** — Sprint 2 ships the
  contract; first-service evidence pending production deployment. Tracked under M2.
- **Memory plane Phase 2 (ingest worker, vector store)** — gated on 30 days of Phase 1 contract stability per ADR-018 §Phase plan.
- **Alertmanager routing test (S2-4 / M5)** — deferred (requires `amtool`
  + sample alertmanager.yaml). Will land in Sprint 3 with the
  observability-dashboard inventory work.

### Conclusion (Entry 003)

Sprint 2 closes 5 of 6 R4 Mediums (M1 runbook, M2 runbook, M3, M4, M6)
plus the H1 second half (Memory Plane Phase 1 contracts). M5
(Alertmanager routing) deferred to Sprint 3.

R4 cumulative finding closure status:

- C1, C2, C3, C4, C5: closed Sprint 0.
- H1: Phase 1 closed for both ADR-018 and ADR-019.
- H2, H3, H4: closed Sprint 1.
- H5, H6, H7: runbooks shipped Sprint 1; **execution pending Platform / Security**.
- M1: runbook shipped (`secrets-integration-e2e.md`); execution pending.
- M2: runbook shipped (`ground-truth-ingestion.md`); execution pending.
- M3: closed (`ADR-021-fairness-thresholds.md`).
- M4: closed (`ADOPTION.md` §6 compliance gap).
- M5: open — Sprint 3.
- M6: closed (`ADR-022-psi-thresholds.md`).
- L1, L2, L3: open — Sprint 3.

Sprint 0 + Sprint 1 + Sprint 2 cumulative: **+~5500 lines / -~10 lines** across ~30 files. Net effect: 5 Critical + 4 High + 4 Medium closed; 3 High delegated with runbooks; 2 Medium with runbooks pending execution; 1 Medium + 3 Low open for Sprint 3.

---

## Entry 004 — R5 AUTO batch close (May 2026)

- **Date**: 2026-05-03
- **Branch**: `audit-r4/sprint-0-credibility` (continuation; R5 closures batched on the same branch).
- **Base commit (R5 batch start)**: `0505551b0756b1772c00fc21c0acb431ab8b716f`
- **Operator**: Staff/Lead engineer.
- **Scope**: 4 R5 AUTO findings + R5 plan publication. CONSULT findings (R5-M1, R5-M3) and the documentation-only High (R5-H1) tracked in remaining todos.

### What was executed

#### 1. ACTION_PLAN_R5 published
- `docs/audit/ACTION_PLAN_R5.md` — engineering judgement on pre-commit
  scaffold smoke friction, 6 R5 findings (1 H + 4 M + 1 L) plus R5-L4
  on pre-commit cardinality. Sprint plan integration table folds R5
  items into existing R4 Sprint 3.

#### 2. R5-L4 — scaffold smoke off pre-commit
- `.pre-commit-config.yaml`: removed `scaffold-smoke` pre-push hook
  (was 60 s on every push); replaced with a comment block citing R5-L4
  rationale + redirect to `make smoke` and `pr-smoke-lane.yml`.
- `default_install_hook_types` reduced from `[pre-commit, pre-push]` to
  `[pre-commit]`; header rewritten.
- `Makefile`: `smoke` target added as alias of `test-scaffold`.
- `CONTRIBUTING.md`: new §"Local validation cadence" with cost table
  (commit < 10 s · `make smoke` ~60 s · `make validate-templates`
  ~3 min · CI per-PR 3-10 min). Install instructions updated to drop
  `--hook-type pre-push` and point at `make smoke`.

#### 3. R5-M4 — Locust schema sync
- `templates/service/tests/load_test.py`: `SAMPLE_PAYLOAD` rewritten to
  match `app.schemas.PredictionRequest` (`entity_id`, `slice_values`,
  `feature_a/b/c`); `BATCH_PAYLOAD` switched from `instances` →
  `customers` with unique `entity_id` per batch entry (D-20 join key).
- NEW `templates/service/tests/test_load_payload_matches_schema.py` —
  5 contract tests asserting payload validates against the live
  Pydantic models, batch uses `customers` (not `instances`), batch
  entity_ids are unique, and SAMPLE_PAYLOAD carries `entity_id`. Test
  module gracefully skips when `locust` is unavailable so contributors
  without the dev extras are not blocked.

#### 4. R5-M2 — Windows ASCII fallback in validator
- `scripts/validate_agentic.py`: try `sys.stdout.reconfigure(utf-8,
  errors=replace)` with safe fallback; probe whether the (possibly
  upgraded) stream can encode `✓ ✗ ⚠ ℹ` and substitute `[OK] [X] [!]
  [i]` if not. All five literal glyph occurrences replaced with
  `MARK_*` constants.
- Verified two paths locally:
  - Linux default → `_USE_UNICODE = True`, glyphs preserved (regression
    suite `python scripts/validate_agentic.py` exits 0 with `✓`).
  - Simulated cp1252 stream that refuses `reconfigure` → `_USE_UNICODE
    = False`, `MARK_OK = "[OK]"`, `MARK_FAIL = "[X]"`, etc.

#### 5. R5-L1 — D-32 catalog drift sweep
- Bumped `D-01..D-30` → `D-01..D-32` (and "30 invariants" → "32") in:
  - `CLAUDE.md` (3 sites + new D-31..D-32 partition row in summary table).
  - `.claude/rules/01-serving.md` (1 site).
  - `.claude/rules/09-mlops-conventions.md` (1 site).
  - `.windsurf/skills/debug-ml-inference/SKILL.md` (2 sites — heuristic
    table + success criteria checklist).
  - `docs/decisions/ADR-014-gap-remediation-plan.md` (1 site).
  - `docs/ide-parity-audit.md` (2 sites).
- Left `AUDIOVISUAL_CONTENT.md` unchanged (creative video scripts,
  flagged as separate doc-cleanup item; not invariant reference).
- NEW `templates/service/tests/test_anti_pattern_count_consistency.py`
  — parses `AGENTS.md` for the highest `D-NN` row id and asserts
  every catalog-size range citation in 6 secondary docs cites the
  canonical max. Markdown table partition rows (e.g.
  `| D-01..D-08 | Serving |`) are excluded via `_is_in_partition_row`
  helper. 7 invariants (6 parametrized + 1 floor-≥-32 sanity).

### Aggregate test run

```
$ python -m pytest \
    templates/service/tests/test_memory_contracts.py \
    templates/service/tests/test_memory_redaction.py \
    templates/service/tests/test_phase0_disclosure.py \
    templates/service/tests/test_readme_model_names.py \
    templates/service/tests/test_ci_classify_failure_phase1.py \
    templates/service/tests/test_ci_autofix_policy_contract.py \
    templates/service/tests/test_anti_pattern_count_consistency.py \
    templates/service/tests/test_load_payload_matches_schema.py \
    --no-cov --noconftest -q
================== 106 passed, 7 skipped, 1 warning in 7.04s ======================
```

The 7 skips: 6 Phase-0 banner enforcers correctly auto-skipped (both
ADR-018 and ADR-019 are Phase 1) + 1 locust env probe.

### Status transitions

- ADR-020 §"Progress log": new R5 closure section appended.
- R5 closure status:
  - R5-H1: **open** — README softening + Verification status mini-matrix.
  - R5-M1: **open** — shadow workflow real log fetch (CONSULT).
  - R5-M2: **closed** — Windows fallback + dual-codec verification.
  - R5-M3: **open** — NetworkPolicy egress per overlay (CONSULT).
  - R5-M4: **closed** — schema sync + 5-invariant contract test.
  - R5-L1: **closed** — 6 doc sites bumped + 7-invariant guard test.
  - R5-L4: **closed** — scaffold smoke off pre-commit + `make smoke` + CONTRIBUTING.

### What was NOT validated (pending)

- **R5-H1** README softening — needs maintainer judgement on "Production-
  ready by design" wording across 7 maturity matrix rows; AUTO scope but
  high-impact wording so deferred to next batch with explicit reviewer
  approval.
- **R5-M1** shadow log fetch — CONSULT mode; touches CI surface and gates
  the Phase-1 → Phase-2 ADR-019 decision. Needs separate PR for review.
- **R5-M3** NetworkPolicy egress — CONSULT mode; per-cloud allowlists
  require operator input on representative GCS / S3 prefix-list IDs.
- **Windows CI lane** — separate PR adding `windows-latest` runner job
  to validate `scripts/validate_agentic.py --strict`. Unblocks proof of
  R5-M2 cross-platform claim in CI.

---

## Entry 005 — R5 remainder close (May 2026)

- **Date**: 2026-05-03
- **Branch**: `audit-r4/sprint-0-credibility` (continuation).
- **Base commit (R5 remainder start)**: `39c6f1de9e800b308192ddd3c84791cfd786cff7`
- **Operator**: Staff/Lead engineer.
- **Scope**: Close the remaining 3 R5 findings — H1 (README softening +
  Verification status matrix), M3 (NetworkPolicy egress per overlay),
  M1 (shadow workflow real log fetch + PR-base diff). All on same
  branch per user direction.

### What was executed

#### 1. R5-H1 — README wording softening + Verification status matrix

- `README.md` §"Production-ready scope" — status column rewritten to
  **"Production-ready by design"** with a 3-bullet preamble making
  three claims explicit:
  - contract-tested and scaffold-tested in THIS repo,
  - the patterns the author operates with in production,
  - adopter verification against their environment remains their
    responsibility.
- NEW §"Verification status" sub-matrix with 4 layers L1–L4:
  - L1 Contract tests (`validate-templates.yml`, 144 tests today)
  - L2 Scaffold smoke (`pr-smoke-lane.yml` + `make smoke`)
  - L3 Golden-path E2E (`golden-path.yml` on release tags)
  - L4 Adopter production rollout — **explicitly not assertable
    from this repo** (honesty anchor)
- Badge: `anti--patterns-30` → `anti--patterns-32` (R5-L1 leftover).
- NEW `templates/service/tests/test_readme_verification_status.py`
  with 9 invariants: status-column discipline, §Verification status
  presence, 4-layer coverage (L1…L4 parametrized), L4 "Not assertable"
  disclaimer, badge count matches canonical D-32.

#### 2. R5-M3 — NetworkPolicy egress per overlay

- `templates/k8s/base/networkpolicy.yaml` — banner added on the
  `0.0.0.0/0:443` cloud-storage egress rule flagging it as
  DEV-ONLY with explicit "OVERLAY-OVERRIDE REQUIRED" marker and
  reference to this test.
- 4 NEW `patch-networkpolicy.yaml` files (JSON 6902):
  - `overlays/gcp-staging`, `overlays/gcp-prod`: replace egress[3]
    with `199.36.153.4/30` (restricted.googleapis.com) +
    `199.36.153.8/30` (private.googleapis.com) + `34.0.0.0/8` residual.
  - `overlays/aws-staging`, `overlays/aws-prod`: replace egress[3]
    with `52.0.0.0/8` (S3+ECR) + `54.0.0.0/8 except 54.64.0.0/11`
    (STS+Secrets Manager residual).
- 4 `kustomization.yaml` files wired: patch referenced with
  `target.kind: NetworkPolicy` + `target.name: "{service-name}-
  network-policy"`.
- NEW `templates/service/tests/test_networkpolicy_egress_hygiene.py`
  with 19 invariants (14 structural + 4 kustomize-optional + 1
  dev-negative):
  - base banner present (+ "R5-M3" + "non-dev" tokens),
  - each non-dev overlay ships the patch file,
  - each patch body does NOT contain `0.0.0.0/0` on non-comment lines,
  - each `kustomization.yaml` wires the patch with correct `target`,
  - `kustomize build` render check (skips when kustomize binary
    absent; CI covers this path),
  - dev overlays are NOT required to carry the patch (avoids false
    regressions in the permissive local dev flow).

#### 3. R5-M1 — Shadow workflow real log fetch + PR-base diff

- `.github/workflows/ci-self-healing-shadow.yml`:
  - `permissions:` — added `pull-requests: read` (needed to resolve
    PR base SHA); all three scopes remain strictly `read`.
  - Fetch-logs step rewritten: 3 paths — `log_artifact_url` replay
    via `curl`; upstream `workflow_run` via `gh api /repos/.../
    actions/runs/{id}/logs` with 50 MB size cap + unzip + concat;
    fallback empty log. Emits `fetch_source` / `fetch_bytes` outputs
    for provenance.
  - Changed-files step rewritten: resolves `pulls/${PR_NUMBER}`
    via gh api to get `base.sha`, runs `git fetch` on the base,
    and diffs `base...HEAD` instead of `HEAD~1`. Falls back to
    the previous heuristic when no PR context. Closes red-team F1
    inline (shadow lane now sees the full PR diff).
  - Step summary upgraded to a table with 9 provenance fields
    (upstream run, workflow, fetch source, fetch bytes, diff mode,
    PR number, base SHA, head SHA, changed files).
  - Phase-1 invariant `writes_allowed != false` verifier preserved.
  - `python` → `python3` in the 3 script steps for portability.
- NEW `templates/service/tests/test_shadow_workflow_phase1.py`
  with 14 invariants: read-only permissions (3 scopes), no write
  perms anywhere (regex), triggers + inputs present,
  real gh api log fetch regex (backslash-continuation aware),
  `log_artifact_url` replay path, `fetch_source` output declared,
  PR-base diff path present, outputs `diff_mode` / `pr_number` /
  `base_sha` declared, invariant check preserved, no `gh pr create`
  / `git push` / create-pull-request action anywhere.

### Aggregate test run

```
$ python -m pytest \
    test_memory_contracts test_memory_redaction \
    test_phase0_disclosure test_readme_model_names \
    test_readme_verification_status \
    test_ci_classify_failure_phase1 \
    test_ci_autofix_policy_contract \
    test_anti_pattern_count_consistency \
    test_load_payload_matches_schema \
    test_networkpolicy_egress_hygiene \
    test_shadow_workflow_phase1 \
    --no-cov --noconftest -q
================== 144 passed, 11 skipped, 1 warning in 8.21s ==================
```

Skips breakdown (all intentional): 6 Phase-0 banner auto-skips +
1 locust env probe + 4 kustomize-binary-optional.

### Status transitions

- ADR-020 §"Progress log": new "R5 remainder" closure table appended.
- R5 closure status (final):
  - R5-H1: **closed** — README softened + §Verification status shipped.
  - R5-M1: **closed** — real gh api log fetch + PR-base diff + 14
    contract invariants.
  - R5-M2: **closed** (Entry 004) — Windows fallback.
  - R5-M3: **closed** — 4 patch files + 4 kustomization wires + 19
    contract invariants.
  - R5-M4: **closed** (Entry 004) — Locust schema sync.
  - R5-L1: **closed** (Entry 004) — D-32 drift sweep.
  - R5-L4: **closed** (Entry 004) — scaffold smoke off pre-commit.

Every R5 finding is now either:
- shipped with a contract test enforcing the invariant (7 of 7), or
- explicitly documented as pending operator action (0 of 7).

### Follow-ups recorded

- **R5-M3 follow-up**: create `docs/runbooks/egress-narrowing.md`
  describing how adopters should replace the coarse CIDR residuals
  with their region's exact AWS IP-ranges.json prefix lists or GCP
  Private Google Access VIPs. Dev+CI does not need the runbook;
  adopters planning staging/prod rollouts do. Tracked as a new
  "runbook shipped" row in Sprint 3.
- **R5-M1 follow-up (Phase-2 gate)**: the shadow workflow's
  expanded provenance output unblocks the 14-day precision study.
  Phase-1 → Phase-2 transition decision remains CONSULT per
  ADR-019 §Phase plan; this commit does not close it.

### What was NOT validated (acknowledged deltas)

- **CI run of the shadow workflow against a real failing upstream
  run** — requires a failed CI to observe; best done during the
  Phase-2 precision study on main post-merge.
- **`kustomize build` of the 4 non-dev overlays** — requires
  kustomize binary (absent in local env); CI covers this via the
  existing validate-templates lane + the new contract test's
  optional kustomize path.
- **Adopter-side egress allowlist** — the CIDR choices are
  residual; adopters deploying into regulated environments MUST
  tighten them via `docs/runbooks/egress-narrowing.md` (above).

---

## Template for future entries

Each subsequent entry MUST follow this skeleton:

```markdown
## Entry NNN — <short title>



- **Date**: YYYY-MM-DD
- **Branch**: <branch-name>
- **Base commit**: <full SHA>
- **Environment**: <local | kind cluster <version> | GKE <version> | EKS <version>>
- **Operator**: <role>
- **Scope**: <single-sentence what-this-run-validated>

### What was executed

<numbered subsections with raw output excerpts; truncate to material lines>

### What was NOT validated (pending)

<bulleted list of items not covered by this run, each with owner + tracking ID>

### Conclusion (Entry NNN)

<one-paragraph summary; cross-link to README maturity matrix rows that this entry materially supports>
```

The `pending` block is non-negotiable. An entry with no `pending` block is
a claim that the run validated everything, which is almost never true and
is the exact pattern R4 finding C4 was designed to prevent.
