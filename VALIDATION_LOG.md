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
