# Changelog

All notable changes to the ML-MLOps Production Template are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

> **Versioning policy is now governed by [`docs/RELEASING.md`](docs/RELEASING.md).** Adopter migration guidance lives in [`MIGRATION.md`](MIGRATION.md). Verified-execution evidence lives in [`VALIDATION_LOG.md`](VALIDATION_LOG.md). Tags `v1.0.0`–`v1.12.0` remain immutable historical audit snapshots. The active public line is now `v0.x` hardening; `v1.0.0` is reserved for the first real cloud E2E validation across GKE and EKS.

---

## [Unreleased]

### Fixed — AUDIT R10 (documentation language + private-reference leak)

- **Four `docs/audit/*.md` files translated from Spanish to English**
  (`ACTION_PLAN_LLM_AGENT.md`, `ARCH_REVIEW_LLM_AGENT.md`,
  `AUDIT_R8_STAFF_LEAD.md`, `ACTION_PLAN_R9_ENTERPRISE_BENCHMARK.md`, plus
  the small `ACTION_PLAN_ADR028.md` stub and 38 bilingual section titles in
  `feedback-may-2026-triage.md`): this repo's documentation is English-only
  everywhere else; these were leftover interactive-session artifacts.
- **A private, personal companion repo de-referenced by name from 6
  files** in this repo (`docs/audit/{ACTION_PLAN_LLM_AGENT,
  ACTION_PLAN_R9_ENTERPRISE_BENCHMARK,AUDIT_R8_STAFF_LEAD}.md`,
  `docs/decisions/{ADR-028,ADR-037}.md`, `CHANGELOG.md`) and one in the
  sibling `agent-local` repo (`docs/decisions/ADR-008-*.md`) — one instance
  was a live clickable URL pointing at it, which 404s for any public
  reader since that repo is private. `ADR-037` and `ADR-028`
  were re-generalized (not just redacted): the "L-2b pedagogical RAG"
  design now describes "the adopter's own long-form onboarding corpus"
  rather than a hard-coded reference to the author's private repo — a
  strictly more reusable design for a public template.
- **A pre-existing D-36 rollout gap**: `CLAUDE.md`'s compact anti-pattern
  table (root and vendored `templates/service/CLAUDE.md`) had never
  actually gained a D-36 row when D-36 shipped (R9 Wave A) — it still
  ended at D-35 and claimed "35 invariants." Backfilled alongside this
  round's D-37.
- **Stale `Windsurf` references** in currently-live docs (`QUICK_START.md`,
  `README.md` badge + 2 prose mentions, `docs/ide-parity-audit.md`,
  `docs/agentic/runtime-monitoring-companion.md`,
  `docs/runbooks/mcp-config-hygiene.md`,
  `templates/config/mcp_registry.yaml`): the template's agentic surface
  moved to Devin/Cursor/Claude Code/Codex a while ago; these had not been
  updated to match and one (`ide-parity-audit.md`) still described the
  pre-ADR-027 architecture where the canonical source was literally named
  "Windsurf" instead of the current vendor-neutral `agentic/`.

### Added — AUDIT R10 (documentation coherence hardening)

- **`check_doc_coherence.py` C7 + anti-pattern D-37 + ADR-040**: a new
  deterministic check — `check_doc_language_and_privacy` — scans every
  git-tracked `docs/**/*.md` and root `*.md` file for non-English prose
  (a curated Spanish word list, accent required — an early draft made the
  accent optional and flagged the English word "decision" repo-wide,
  caught in local testing) and for a private-repo denylist (seeded with the
  repo named above, see ADR-040). This is the gate that should have caught
  the R10 finding above and now will, going forward. Vendored into
  `templates/service/scripts/check_doc_coherence.py`; adapters
  (`.devin/.claude/.cursor/.codex`) resynced via
  `sync_agentic_adapters.py`.

### Added — AUDIT R9 Wave A (enterprise benchmark remediation)

- **OpenSSF Scorecard** (`.github/workflows/scorecard.yml`, R9-01): weekly +
  on-push supply-chain scoring, published and SARIF-uploaded to the Security
  tab — makes the template's existing signing/SBOM/branch-protection posture
  independently verifiable instead of just claimed.
- **All GitHub Actions pinned by commit SHA** (R9-02): every third-party
  action across all 13 workflow files now resolves to an immutable SHA
  (`uses: owner/action@<sha> # vX.Y.Z`), resolved live against the GitHub
  API. Closes the tag-mutability supply-chain gap Scorecard's
  Pinned-Dependencies check flags (the class of exposure behind the 2025
  tj-actions incident). `dependabot.yml` already tracks the
  `github-actions` ecosystem, so SHA bumps keep flowing as PRs.
- **`docs/COMPLIANCE_MAPPING.md` + ADR-038** (R9-03): maps existing template
  artifacts (quality gates, fairness DIR gate, drift monitoring, audit
  trail, human-in-the-loop promotion, signed supply chain) to NIST AI RMF,
  ISO/IEC 42001, and EU AI Act Arts. 9–15 control questions — explicitly
  NOT a certification claim (see the document's own non-claims section).
  Includes a verified Digital Omnibus timeline note (Annex III high-risk
  obligations move 2026-08-02 → 2027-12-02).
- **Portability & escape-hatches matrix** in `docs/ADOPTION.md` §4 (R9-04):
  a per-dimension swap table (cloud, tracking/registry, serving backend,
  model framework, data validation, drift tooling, scaffolding engine, IaC,
  agentic host) stating exactly what changes and what stays fixed.
- **CI-green verification agentic gate** (R9-05, ADR-039): new skill
  `ci-green-verify` (AUTO to check, STOP to override red/missing — verbs
  separated on purpose, mirroring GitHub branch-protection's own
  view-vs-bypass split) + `/ci-green` workflow + anti-pattern **D-36**.
  Wired as a hard precondition into `agentic/workflows/release.md` step 1
  (was a non-blocking `gh run list`) and into `deploy-gke`/`deploy-aws`
  before `staging`/`prod` (Step 0, `dev` exempt). Surface counts: skills
  20→21, workflows 16→17, anti-patterns D-01..D-35→D-01..D-36 — cascaded
  through `AGENTS.md`, both `CLAUDE.md` files, `llms.txt`, `README.md`, and
  `templates/config/agentic_manifest.yaml`; `sync_agentic_adapters.py` +
  `validate_agentic_manifest.py --strict` + `validate_agentic.py` all green.

### Fixed

- **AUDIT R8-05 — root `pytest -q` collects again** (`pyproject.toml`):
  the three sibling test packages all named `tests`
  (`templates/service/{tests,eda/tests,monitoring/tests}`) collided in
  `sys.modules` under pytest's default `prepend` import mode and aborted
  collection from the repo root. Fixed with `--import-mode=importlib` in the
  root `addopts` (verified: zero cross-test `from tests…` imports exist, so
  importlib is safe). A new **"Root suite collects" guard step** in
  `template-context-tests.yml` runs `pytest --collect-only -q` from the root
  so this supported dev flow can never break without CI signal again.
  Second layer, exposed by CI run 28552562658: invocations with paths under
  `templates/service/` resolve rootdir to the SERVICE `pyproject.toml`, so
  the flag is set there too — and it ships to scaffolded services, which
  carry the same three-sibling `tests` layout.
- **Alertmanager routing contract revived** —
  (`templates/service/monitoring/tests/test_alertmanager_routing.py`): the
  module anchored its config paths at `parents[3]` from before the Copier
  Stage-2a relocation, resolving to a nonexistent `templates/templates/…` —
  it had been **uncollectable (dead) since the move**, masked by the R8-05
  collision. Paths are now file-relative (`parents[1]`, correct in template
  context AND in a scaffolded service), the local amtool unpack is
  discovered by ancestor walk with an `X_OK` guard (a non-executable unpack
  means *skip*, never *fail*), and the module is now executed in CI: the
  template-context lane runs `monitoring/tests` + `eda/tests` explicitly.
  All 14 tests pass locally including the 6 amtool-authoritative ones.
- **AUDIT R8-08 — async tests execute from the root env**
  (`pyproject.toml`): `asyncio_mode = "auto"` + `pytest-asyncio` in the
  template-context lane install; previously a root run without the plugin
  collected `@pytest.mark.asyncio` tests as unknown-marked no-ops.
  Full root suite after all fixes: **963 passed, 0 failed**
  (`pytest -q -p no:locust -m "not scaffold_context"`).

### Added

- **AUDIT R8 — Staff/Lead dual-repo audit (template + agent-local)**
  (`docs/audit/AUDIT_R8_STAFF_LEAD.md`): first audit round covering
  `agent-local` as a full audit subject alongside this template. Verdicts:
  template 9.1/10 (no new architecture/security/supply-chain findings; two
  local-DX findings — root `pytest -q` collection collision between three
  sibling `tests` packages, and missing `pytest-asyncio` in the root env),
  agent-local 7.9/10 (12 findings, worst: synchronous multi-LLM loop inside
  an `async def` endpoint — the D-24 class — plus exception-detail leak,
  discarded `reflect()` output, and a triple version drift with no coherence
  gate). Includes a governance-parity matrix (every discipline that traveled
  to agent-local without its gate has a live finding), per-dimension scoring
  for both repos, structural knowledge-graph verification of D-24 across all
  10 `.predict*` call sites, and a prioritized P0/P1/P2 action plan.
- **ADR-037 — Dual-namespace retrieval separation (operational memory vs.
  pedagogical RAG)**
  (`docs/decisions/ADR-037-dual-namespace-retrieval-separation.md`):
  canonicalizes a new `L-2b` maintenance-plane lane in
  `docs/audit/ACTION_PLAN_LLM_AGENT.md` — a pedagogical/onboarding RAG over
  the adopter's own long-form documentation + ADR prose, built as a
  namespace-disjoint sibling of the existing `L-2` operational memory plane
  (ADR-018), never the same index or script. Two disjoint scripts (`scripts/memory_query.py` vs. the new
  `scripts/pedagogy_query.py`), two hard-coded disjoint corpus-root
  allow-lists, two independent `BM25Index` objects, one shared *stateless*
  agent-local tier endpoint (justified by agent-local's new ADR-008), and a
  citation-path validator that discards (and logs) any answer whose citation
  resolves outside its own namespace. Both scripts are specified, not yet
  shipped — gated behind the same "P2 INTEGRATION" timeline as the rest of
  the memory-plane lane.
- **ADR-036 — Batch-only deployment topology**
  (`docs/decisions/ADR-036-batch-only-deployment-topology.md`): a new
  `templates/service/k8s/overlays/batch-only/` Kustomize overlay for
  adopters who never run the live `/predict` API — only scheduled batch
  scoring. Includes the full `../../base` and removes the online-serving
  resources (Deployment, Service, HPA, PDB, both `AnalysisTemplate`s,
  performance/drift `CronJob`s + their `PrometheusRule`s, the
  online-shaped `NetworkPolicy`) via one-resource-per-file
  `$patch: delete` — a multi-document patch file panics the bundled
  kustomize/kyaml version (verified locally); ships a working
  `cronjob-batch.yaml` and a dedicated `networkpolicy-batch.yaml` (the
  base policy's `podSelector` would not match the batch pod's label,
  silently leaving it with no egress at all).
- **`docs/EXPORTING.md`**: the Vertex AI / SageMaker "export surface"
  documentation promised by `README.md`'s non-claims list — what travels
  (the signed container image, API/data contracts, quality evidence) vs.
  what doesn't (K8s manifests, Terraform, Kyverno policies), with worked
  `gcloud ai models upload` and SageMaker Model Package registration steps
  for the *same* image this template's CI already builds and signs.
- `agentic/skills/batch-inference/SKILL.md`: cross-references the new
  `batch-only` overlay for adopters who need scheduled scoring with no
  live API at all (previously the skill only covered adding batch
  scoring *alongside* an existing online Deployment).
- `docs/ADOPTION.md`: two new maturity-matrix rows (batch-only topology,
  export surface); corrected a pre-existing citation (`/onboard` was
  attributed to ADR-035 — it is ADR-029 Wave 3).

---

## [v0.20.0] — 2026-07-01

### Added

- **ADR-033 — Local-first stack profiles**
  (`docs/decisions/ADR-033-local-first-stack-profiles.md`): a `local`
  profile that requires no Docker, K8s, Terraform, or cloud credentials,
  enabling a laptop-only inner loop. Stack profiles are selectable at
  scaffold time via Copier `profile` question and switchable post-scaffold
  via `/stack-switch` workflow.
- **ADR-034 — CCDS-aligned generated layout**
  (`docs/decisions/ADR-034-ccds-aligned-generated-layout.md`):
  documentation-only mapping from the template's production directory
  layout to the Cookiecutter Data Science (CCDS) vocabulary. No directory
  rename — the mapping lives in `templates/service/docs/CCDS_MAPPING.md`.
- **ADR-035 — uv adoption + Copier index publication**
  (`docs/decisions/ADR-035-uv-adoption-copier-index.md`): `uv sync` as
  a first-class install option alongside pip (requirements.txt retained
  as compatibility export). Template is indexable via
  `copier copy https://github.com/DuqueOM/ML-MLOps-Production-Template.git`.
- **D-35 — `local` stack profile accepts cloud credentials or targets a
  cluster**: Anti-pattern forbidding cloud credentials in the `local`
  profile. Enforced by `tests/contract/test_d35_local_profile_no_cloud_deps.py`.
- **Stack profile configs**: `templates/config/stack-profiles/local.yaml`,
  `staging.yaml`, `production.yaml` with `requires.*` and `deploy.enabled`
  flags.
- **Makefile `local-loop` + `switch-profile` targets**: local training →
  serving → drift check loop; profile switching with validation.
- **`stack-switch` skill + `/stack-switch` workflow** (CONSULT mode):
  switch a scaffolded service between stack profiles.
- **`template-onboard` skill + `/onboard` workflow** (AUTO mode):
  interviews the adopter and emits a validated `*_context.local.yaml`
  (gitignored, no secrets).
- **`docs/TUTORIAL.md`**: narrated "from notebook to production" arc
  covering 8 anti-patterns tied to concrete failures each prevents.
- **`templates/service/docs/CCDS_MAPPING.md`**: CCDS → production layout
  mapping table for recognizability.
- **Makefile `install-uv` target**: `uv sync` as faster alternative to
  `pip install -r requirements.txt` (ADR-035).
- **`docs/ADOPTION.md` "Scaffolding & local-first" maturity matrix section**:
  7 new capability rows (Copier scaffolding, copier update, local-first
  profile, stack switching, CCDS mapping, adopter context, uv sync).
- **`docs/PROGRESSION.md` Stage 2 updated**: `copier copy` as primary
  scaffolding command, `uv sync` as recommended install option.

### Changed

- Anti-pattern count: 34 → 35 (D-35 added).
- Agentic surface counts: 19 skills → 20, 15 workflows → 16
  (`template-onboard` + `/onboard` added).
- README comparison table: "Entry friction" lowered from "higher" to
  "medium (local-first profile, `copier copy`)"; "Pedagogy / learning
  arc" updated from "roadmap" to "narrated tutorial + anti-pattern
  walk-through".
- README quick-start: `copier copy` as primary, `new-service.sh` as
  fallback. TUTORIAL.md linked from README and QUICK_START.
- QUICK_START Track B: `copier copy` as primary scaffolding command.
- CONTRIBUTING: `uv sync` option documented; `pyproject.toml` noted as
  source of truth for dependencies.
- `templates/config/agentic_manifest.yaml`: `template-onboard` skill
  (AUTO) and `onboard` workflow (AUTO) added.

### Fixed

- **Documentation coherence drift**: README anti-pattern badge 34→35;
  llms.txt range D-01 to D-34 → D-01 to D-35; CLAUDE.md surface counts
  18 skills / 14 workflows → 20 skills / 16 workflows; AGENT_CONTEXT.md
  D-01..D-34 → D-01..D-35; rule-audit and debug-ml-inference skill
  descriptions updated from D-01..D-34 to D-01..D-35 in canonical and
  generated surfaces.

### Added

- **Documentation Coherence System (rule 16 + ADR-031)**: a single-source-of-truth
  contract for facts restated across documents, enforced like every other
  invariant — a deterministic gate plus an agentic surface that fixes drift.
  - `scripts/check_doc_coherence.py` — blocking gate (sibling of the
    `check_*_drift.py` family): version SSoT, `llms.txt` version, anti-pattern
    count, agentic surface counts, ADR traceability/no-silent-gaps.
  - `agentic/rules/16-doc-coherence.md` (SSoT register + cascade map),
    `agentic/skills/doc-coherence/` (the agent that applies the cascade with
    CONSULT/STOP boundaries), `agentic/workflows/doc-coherence.md` (`/doc-coherence`).
  - CI job `doc-coherence-gate` in `validate-templates.yml` (blocking, seeded green).
- **ADR-031 — Documentation Coherence System**
  (`docs/decisions/ADR-031-documentation-coherence-system.md`): records why the
  contract is composed in-repo (no single external tool spans cross-document
  coherence) and based on Keep a Changelog, towncrier/changesets,
  release-please, MADR/Log4brains, Vale, and Diátaxis patterns.

### Fixed

- **Documentation coherence drift (audit R7, `docs/audit/AUDIT_R7_STAFF_LEAD.md`)**:
  `VERSION` 0.18.0 → 0.19.0 to match the latest released CHANGELOG heading;
  rewrote a `llms.txt` frozen in the v1.3.0 era (advertised "12 anti-patterns",
  "5 rules", "8 skills") to current reality (D-34, 17 rules, 18 skills, 14
  workflows, v0.19.0); corrected both `CLAUDE.md` files ("32 invariants" → 34,
  added the D-33/D-34 partition row, surface counts 15/16/12 → 17/18/14);
  `Dockerfile` header comment "Python 3.11 slim" → 3.13 to match its base image.
- **Python 3.13 CI coverage (audit R7 F-4)**: `ci-examples.yml` test matrix
  extended `["3.11", "3.12"]` → `["3.11", "3.12", "3.13"]` so the runtime the
  Docker image ships (3.13-slim-bookworm) is actually exercised in CI.

### Added (R7 follow-up)

- **ADR-032 — BentoML as an Optional Alternative Serving Backend** (Proposed)
  (`docs/decisions/ADR-032-bentoml-alternative-serving-backend.md`): records
  the invariant contract (D-01/D-02/D-11/D-23/D-25/D-04) any future BentoML
  backend must satisfy; no code shipped — documentation-only seam per the R7
  audit recommendation ("evaluate, don't mandate").
- **README §"How this compares"**: added a Kubeflow column (full-platform
  reference point) and a "Tools we compose with, not against" subsection
  covering BentoML (→ ADR-032) and Evidently report artifacts.

### Fixed — Wave 2–4 implementation audit (this pass)

An independent Staff/Lead review verified every file the Wave 2–4 ADRs
(033/034/035) claimed to ship, ran the full validator + test suite, and
exercised a real `copier copy` render end-to-end (scaffold → `make deploy`
blocked on `local` → `make onboard` → `make switch-profile PROFILE=staging` →
`make deploy` proceeds). The following defects were found and fixed:

- **Broken `/onboard` schema validation (functional bug)**: `template-onboard`
  SKILL.md / `/onboard` workflow validated their adopter-infra YAML
  (`cloud_provider`, `container_registry`, `mlflow_tracking_uri`, …) against
  `context.schema.json` — the ADR-023 company/project risk-context schema,
  which requires `{version, company}` or `{version, project, kpis}` with
  `additionalProperties: false`. Validation would have failed on every
  invocation. Fixed by adding a dedicated `config/adopter_context.schema.json`
  (+ `config/adopter_context.example.yaml`) and repointing the skill/workflow
  at it. Verified end-to-end against a real scaffold.
- **Missing `templates/service/.gitignore` (never existed, pre-dates Waves
  2-4)**: a scaffolded service had no `.gitignore` at all — `.terraform/`,
  `*.tfstate*`, secrets, model artifacts, and `mlruns/` were all committable,
  and the `/onboard` precondition check (`grep "_context.local.yaml"
  .gitignore`) would always fail. Added a full `.gitignore` (Python, testing,
  venvs, ML artifacts with `.gitkeep`-preserved data dirs, Terraform state,
  secrets, and the ADR-023/029 `*_context.local.yaml` pattern).
- **Unenforced ADR-033 invariant**: ADR-033 §2.5 states the `local` profile's
  `deploy` must be **blocked**, but `make deploy` had no guard. Added a check
  reading `configs/profiles/active_profile.yaml` that refuses to proceed
  when the active profile is `local`. Verified: blocks on `local`, proceeds
  on `staging`.
- **`make deploy` / `scripts/deploy.sh` CLI contract mismatch** (pre-existing,
  surfaced by the end-to-end verification): the Makefile called `deploy.sh`
  with positional args; `deploy.sh` only accepts `--service/--version/--cloud`
  flags. Fixed the Makefile invocation; added `VERSION`/`CLOUD` variables.
- **Missing non-agentic on-ramp for two new workflows**: `/onboard` and
  `/stack-switch` had no `make` target registered (PR-R2-12 violation,
  caught by `test_adoption_boundary_contract.py`). Added `make onboard`,
  mapped `/stack-switch` → the pre-existing `make switch-profile`, and
  documented both in `docs/ADOPTION.md`.
- **Vendored-runtime drift (7 files)**: `stack-switch`/`template-onboard`
  skills and the `onboard`/`stack-switch` workflows were added to canonical
  `agentic/` but never propagated into `templates/service/agentic/`
  (`scripts/check_vendored_runtime_drift.py` was red). Re-synced.
- **Stale anti-pattern range citations left over from the D-35 bump**: the
  weaker-model wave updated most but not all citations when D-35 was added.
  Fixed: `docs/decisions/ADR-014-gap-remediation-plan.md` (`D-01..D-34` →
  `D-01..D-35`, caught by `test_anti_pattern_count_consistency.py`);
  `agentic/skills/rule-audit/SKILL.md` heading (same file already said D-35
  twice elsewhere); `templates/service/docs/ADOPTION.md` (3 instances);
  `docs/TUTORIAL.md` (cited a non-existent test name
  `test_d32_drift_cronjob_module_exists` → corrected to
  `test_d32_drift_cronjob_python_path`); `README.md` D-35 row (cited a
  non-existent path `tests/contract/test_d35_local_profile_no_cloud_deps.py`
  → corrected to the real
  `tests/policy/test_anti_patterns.py::test_d35_local_profile_no_cloud_deps`).
- **Stale ADR-count claims**: `llms.txt` and `docs/ADOPTION.md` /
  `templates/service/docs/ADOPTION.md` said "17 ADRs" / "30 ADR files
  (ADR-001 → ADR-031)"; the repo now has 35 (`ADR-001` → `ADR-035`, `012`
  tombstoned). Corrected all four call-sites.
- **`new-service.sh` had no `--profile` passthrough** despite ADR-033's own
  acceptance criterion ("scaffold with `--profile local`"). Added a 5th
  optional positional arg, validated against `local|staging|prod`, forwarded
  to Copier as `--data profile=$PROFILE`.
- **`new-service.sh` didn't create `.gitkeep` for `data/validated/` or
  `reports/`** even though it created the directories. Fixed.

### Known follow-ons

- `templates/service/docs/ADOPTION.md` is a hand-maintained near-copy of
  `docs/ADOPTION.md` and had drifted in more ways than the citations fixed
  above (it is missing the `doc-coherence` rows this release adds to the
  root copy). Not currently a registered vendored pair, so
  `check_vendored_runtime_drift.py` does not catch this class of drift.
  Tracked for a future pass: either register it as a vendored pair or
  formally scope it as an independent, service-specific document.
- The on-ramps recommended by the R7 audit for batch-only pipelines and a
  Vertex AI / SageMaker "export surface" doc are not part of this release
  (out of scope for the Wave 2–4 verification pass); still open.
- `check_doc_coherence.py` validates anti-pattern counts and agentic surface
  counts but not free-text "N ADRs" claims (the class of drift found in
  `llms.txt`/`ADOPTION.md` this pass) — a candidate C6 check, deferred to
  avoid rushing a repo-wide regex against historical/point-in-time documents
  (CHANGELOG, VALIDATION_LOG, past `ACTION_PLAN_*` audits) that must NOT be
  "corrected".

---

## [v0.19.0] — 2026-06-30

### Added

- **Copier scaffolding migration (Wave 1)**: Replaced manual `cp -r` + `sed`
  scaffolding with [Copier](https://copier.readthedocs.io/) using custom Jinja2
  delimiters `{@ @}` to avoid conflicts with Python f-strings and shell
  variables. `templates/scripts/new-service.sh` is now a thin wrapper around
  `copier copy`. All template files use `{@ service_slug @}`, `{@ service_name @}`,
  `{@ service_kebab @}`, `{@ SERVICE_NAME @}` tokens instead of legacy
  `{service}`, `{ServiceName}`, `{SERVICE}` placeholders.
- **D-33 — Manual file copying or sed-based placeholder substitution in the
  scaffolder**: Anti-pattern forbidding `cp -r` + `sed -i` in favor of
  `copier copy`.
- **D-34 — Unquoted Jinja tokens in YAML lists**: Anti-pattern requiring all
  `{@ @}` tokens in YAML list items to be quoted (`- "{@ service_name @}"`)
  because unquoted `- {@ service_name @}` is invalid YAML.
- **ADR-029 — Agentic Adoption Contract & Interoperability Strategy**
  (`docs/decisions/ADR-029-agentic-adoption-contract.md`): ratifies the
  five-condition gate that routes all industry-adoption improvements (Copier,
  local-first stack profiles, recognizable layout, tutorial) *through* the
  vendor-neutral canonical agentic store (ADR-027) instead of around it.
- **README §"How this compares"**: honest positioning table vs Made With ML,
  Cookiecutter Data Science, and ZenML, with explicit "borrow ideas, never fork"
  framing and a link to the adoption tracker.
- **`docs/audit/ACTION_PLAN_ADAPTABILITY.md`**: living, enterprise-grade tracker
  for the adaptability program (Waves 0–4), including a license/provenance
  guardrail (§1.1) confirming the repo's Apache-2.0 license is unaffected.

### Fixed

- **Copier Jinja2 token handling in tests**: Dynamically construct `{@ @}`
  strings in Python test files to prevent Jinja2 from parsing them as template
  expressions during Copier render. Updated `_normalise_metric_name` in
  `test_metrics_contract.py` to handle Copier tokens in PromQL expressions.
  Updated `test_red_team_regression.py` paths to match new
  `templates/service/` prefixed protected_paths in `ci_autofix_policy.yaml`.
- **tfsec archival workaround**: Pinned tfsec to v1.28.14 (last working release)
  in `.github/workflows/validate-templates.yml` after aquasecurity archived the
  project and `/releases/latest` began returning 404. Long-term migration to
  `trivy config` (tfsec's official successor) tracked in TODO comment.
- **CI/CD template drift**: Synchronized GitHub Actions versions in `templates/cicd/`
  with `.github/workflows/` to resolve drift gate failures on Dependabot PRs:
  - `actions/checkout` v4 → v7 (13 references across 8 template files)
  - `codecov/codecov-action` v4 → v7 (1 reference in `ci.yml`)
  - `bridgecrewio/checkov-action` v12.3105.0 → v12.3107.0 (1 reference in `ci-infra.yml`)
- **Link checker**: Ignore `../SECURITY.md` relative link (returns 400 from
  GitHub link checker).

### Changed

- **Dependency updates** (Dependabot PRs #39, #40, #41):
  - `actions/checkout` v4 → v7
  - `codecov/codecov-action` v4 → v7
  - `bridgecrewio/checkov-action` v12.3105.0 → v12.3107.0

---

## [0.18.0] - 2026-06-10

R6 audit closure ([`docs/audit/ACTION_PLAN_R6.md`](docs/audit/ACTION_PLAN_R6.md)).
Full release notes: [`releases/v0.18.0.md`](releases/v0.18.0.md).

### Added

- **Template-context CI lane** `.github/workflows/template-context-tests.yml` —
  runs the full `templates/service/tests` suite (`-m "not scaffold_context"`)
  on every push/PR; previously NO lane executed it and 8 contract tests were
  silently red on `main` (R6 S0-2). `scaffold_context` marker registered in
  `templates/service/pyproject.toml`.
- **MCP registry**: `docker` (CONSULT — local daemon inspection/builds, never
  registry pushes) and `postgres` (CONSULT — read-only closed-loop SQL) in
  `templates/config/mcp_registry.yaml`; `docs/agentic/mcp-portability.md`
  re-rendered; placeholder-only `.mcp.json.example` for Claude Code project
  scope (live `.mcp.json` gitignored).
- **Surface-loadability validation** in `validate_agentic_manifest.py`:
  claude skill pointers must parse as SKILL.md frontmatter with a non-empty
  description (R6 S2-1).
- **ADR-028 (Accepted)** — LLM-assist integration for maintenance/Day-2 ops;
  accepted as written, including its recommendation *against* fine-tuning
  dedicated models at this scale. Local-model plane realized in the sibling
  repo `agent-local`; unified plan in `docs/audit/ACTION_PLAN_LLM_AGENT.md`.
- `releases/README.md` — explains legacy `v1.x` vs active `v0.x` lines and
  the re-reserved `v1.0.0` L4 gate (R6 S1-3).
- Autouse `os.environ` snapshot/restore fixture in service-test conftest
  (R6 S1-2).

### Changed

- **`.claude/skills/` layout**: flat `<id>.md` pointers → `<id>/SKILL.md`
  directories with frontmatter so Claude Code actually discovers the 16
  skills (R6 S0-1); rendered by `sync_agentic_adapters.py`, validated by
  manifest strict mode; AGENTS.md parity matrix updated.
- `rule-audit` skill: catalogue and frontmatter extended D-27 → D-32
  (R6 S0-3); anti-pattern count consistency test now covers skill bodies.
- AGENTS.md §MCP Integrations: stale `~/.codeium/windsurf/` setup path
  replaced with the per-surface config table (R6 S1-1); docker/postgres rows
  added to the recommended-MCP table.
- `test_networkpolicy_egress_hygiene.py` aligned with the May-2026
  default-deny base contract (every overlay patches egress; dev permissive
  by design); base `networkpolicy.yaml` carries the `OVERLAY-OVERRIDE
  REQUIRED` banner.
- CLAUDE.md: rule count corrected to 15; releases pointer updated (R6 S1-4).

### Fixed

- `docs/observability/dashboards-inventory.md` now lists
  `dashboard-dora.json` (+ panels section) — inventory contract test green.
- `## Known follow-ons` sections backfilled into `releases/v0.16.0.md` and
  `releases/v0.16.1.md`.
- `test_k8s_name_vocabulary.py` no longer false-positives on
  `src/{service}/…` Python module paths in K8s manifests (D-32 vocabulary).
- **Locust/gevent deadlock isolated**: importing locust monkey-patches
  ssl/socket and deadlocks anyio `TestClient` lifespans sharing the process
  (observed as a 55-min hang idle in `gevent/hub.py`, 0 CPU). Crucially the
  patch fires at pytest COLLECTION time, so `-m` deselection is NOT enough —
  exclusion happens at collection: `load_test.py` and
  `test_load_payload_matches_schema.py` are `collect_ignore`d (the latter
  re-enabled via `RUN_LOCUST_PARITY=1` in its own pytest invocation in CI,
  new `locust_parity` marker), and the lane runs `-p no:locust`.
- **`app/main.py` import-order fragility**: `from app.fastapi_app import
  load_model_artifacts` froze the binding at import order, so patches on
  `app.fastapi_app` silently missed `main.py` — `/model/reload` failed only
  when another module imported `app.main` first during collection. `main.py`
  now resolves `load_model_artifacts` / `warm_up_model` / prediction-logger
  hooks through the module at call time (behavior-identical in production).
- **Dual-layout `common_utils` shim** in service-test conftest: in the
  template repo `common_utils` lives at `templates/common_utils` (not on
  the rootdir pythonpath), which collection-errored 52 tests; the shim adds
  `templates/` to `sys.path` only when the package is not already importable
  (scaffolded services keep their vendored copy).

---

## [0.17.0] - 2026-06-08

Vendor-neutral agentic surface (ADR-027) plus the Dependabot GitHub Actions
bumps that landed on `main` after the untagged `0.16.2` working entry. The
agentic refactor is the headline change: it removes the last vendor name
(`.windsurf/`) from the canonical layer so the template survives IDE rebrands
without touching rule/skill/workflow bodies.

### Added

- **`ADR-027` — Vendor-Neutral Canonical Agentic Surface** (`Status: Accepted`).
  Establishes `agentic/{rules,skills,workflows}/` as the single human-authored
  canonical body store and demotes every IDE directory to a *generated*
  surface. Amends `ADR-023` invariant I-4 (canonical source is now `agentic/`,
  not `.windsurf/`).
- **`.devin/` mirror-surface** — a generated, byte-identical copy of
  `agentic/` bodies, because Devin Desktop ingests directory bodies and cannot
  follow pointers. CI enforces byte-parity via
  `scripts/sync_agentic_adapters.py --check`.
- **`.devin_context.md`** context pointer for the Devin surface.
- **Mirror/pointer surface model** in `scripts/validate_agentic_manifest.py`:
  `canonical` (`agentic/`), `mirror` (`.devin/`, full bodies + byte-parity),
  and `pointer` (`.cursor/`, `.claude/`, `.codex/`, thin pointers).

### Changed

- **Canonical agentic store moved `.windsurf/` → `agentic/`** via `git mv`
  (15 rules, 16 skills, 12 workflows). `AGENTS.md` remains the sole behavior
  authority; `agentic/` is the body store; `templates/config/agentic_manifest.yaml`
  is the cross-surface index. This is an **internal/governance** surface — it
  does NOT change the output of `templates/scripts/new-service.sh`, so it is a
  MINOR per `docs/RELEASING.md` §1.2 (new Accepted ADR + backward-compatible
  surface), not a MAJOR.
- **`.cursor/`, `.claude/`, `.codex/`** regenerated as thin pointer-surfaces;
  `.windsurf/` and `.windsurf_context.md` dropped.
- Propagated the canonical-path rename across `surface_capabilities.yaml`,
  `mcp_registry.yaml`, `AGENTS.md`, `.pre-commit-config.yaml`,
  `.github/CODEOWNERS`, `validate-templates.yml`, contract tests, docs, and
  in-code comments.
- **Bump `docker/setup-buildx-action` from `v3` to `v4`** (#29) in
  `.github/workflows/`.
- **Bump `azure/setup-kubectl` from `v4` to `v5`** (#32) in the golden-path
  workflows. Runtime-only action (not mirrored in `templates/cicd/`), so the
  CI/CD Template Drift Gate (ADR-026) is unaffected.
- **Bump `bridgecrewio/checkov-action` from `v12.3102.0` to `v12.3105.0`**
  (#33) in `.github/workflows/validate-templates.yml` **and** mirrored into
  `templates/cicd/ci-infra.yml` to satisfy the drift gate.
- **Bump `gitleaks/gitleaks-action` from `v2` to `v3`** (#34) in
  `.github/workflows/validate-templates.yml` **and** mirrored into
  `templates/cicd/ci.yml`. v3 is a Node 20 → Node 24 runtime migration with no
  input/output/behavior change; `v2` stops working once GitHub removes Node 20
  (2026-09-16), so this keeps scaffolded services on a supported action.

### Fixed

- **Broken relative link in `.github/ISSUE_TEMPLATE/feature_request.md`** —
  `../AGENTS.md` resolved to `.github/AGENTS.md`; corrected to
  `../../AGENTS.md`. Pre-existing bug surfaced by the Link Check once the file
  was edited in this release.

### Known follow-ons

- **`codex/fastapi-template-hardening`** is a separate WIP initiative branched
  from `0.15.2` that still references `.windsurf/` and conflicts on
  `CHANGELOG.md`/`VERSION`. It must be rebased onto post-ADR-027 `main` (with
  the `.windsurf/` → `agentic/` rename applied) before it can ship; it is NOT
  included in this release.
- The untagged `0.16.2` working entry (cosign `v4.1.2` pin + Kyverno schema
  fix + `azure/setup-helm v5`) is retained below for the audit trail; its
  content is already on `main` and is therefore included under the `v0.17.0`
  tag history.

## [0.16.2] - 2026-05-25

CI hardening pass to unblock the open Dependabot PRs (#28
`sigstore/cosign-installer 3.7.0→4.1.2`, #30 `azure/setup-helm 4→5`)
and to fix a latent bug in the supply-chain policy. Three independent
fixes shipped together because all three were blocking the same CI
matrix:

### Changed

- **Bump `sigstore/cosign-installer` from `v3.7.0` to `v4.1.2`** in
  `templates/cicd/{ci,deploy-aws,deploy-gcp,retrain-service}.yml` and
  `.github/workflows/golden-path.yml`. This satisfies the CI/CD
  Template Drift Gate (ADR-026) for the runtime bump landing via
  Dependabot in `.github/workflows/`.
- **Pin `cosign-release: v2.4.0`** on the `templates/cicd/ci.yml`
  installer step. The other workflows were already pinned. Without an
  explicit pin, cosign-installer v4 installs Cosign **v3** by default,
  which is a breaking CLI change (renamed flags, mandatory tlog
  inclusion proofs, OCI registry default changes). The Cosign v2→v3
  migration is deferred to a dedicated ADR; this release adopts only
  the installer's security/maintenance patches.

### Fixed

- **Kyverno image-verification policy schema bug**
  (`templates/k8s/policies/kyverno-image-verification.yaml`).
  Replaced the single `subjectRegExp:` entry with three explicit
  `subject:` entries (one per trusted signing workflow:
  `ci.yml`, `deploy-gcp.yml`, `deploy-aws.yml`). The `subjectRegExp`
  field is rejected by the Kyverno CRD shipped in chart 3.2.6 (strict
  decoding error: `unknown field`), which broke the
  `Kyverno Admission Smoke / Reject :latest in production namespace`
  job on every PR. The new form preserves the exact trust set, is
  Kyverno-version-forward-compatible (uses only documented fields),
  and Kyverno OR's `entries` within a single attestor so semantics
  are identical.

### Why these landed together

`Kyverno Admission Smoke` was failing on `main` before the Dependabot
bumps arrived, so every Dependabot PR inherited a red required check
unrelated to its diff. Bumping `cosign-installer` in templates without
the explicit Cosign release pin would also have broken adopters'
deploy pipelines silently the first time they regenerated from the
scaffolder. Shipping the three fixes in one merge keeps the audit
trail tight: one PR, one CHANGELOG entry, and Dependabot's open PRs
auto-rebase onto a clean `main`.

## [0.16.1] - 2026-05-15

CI/CD template drift gate. Closes a Dependabot blindspot: the
`github-actions` ecosystem only scans `.github/workflows/`, so action
references in `templates/cicd/*.yml` (the scaffolder inputs copied
verbatim into adopter services) age silently after every Dependabot
bump that lands in runtime. This release adds an enforcement script,
fixes the four drifts that already existed, and wires the gate into
`validate-templates.yml`.

### Added

- `scripts/check_cicd_template_drift.py` — fails when any GitHub
  Action used in both `.github/workflows/` and `templates/cicd/`
  has a version in templates that is not present in runtime
- `cicd-template-drift` job in `.github/workflows/validate-templates.yml`
  (runs on every PR; not in required-checks list per ADR-026, same
  posture as `common-utils-drift`)
- `docs/governance/cicd-templates-drift.md` — full rationale,
  enforcement scope, what it does NOT cover, revisit triggers

### Changed

- `templates/cicd/*.yml` — bumped four lagging action references
  to match runtime (`actions/upload-artifact` v4→v7,
  `aquasecurity/tfsec-action` v1.0.0→v1.0.3,
  `bridgecrewio/checkov-action` v12.2752.0→v12.3102.0,
  `sigstore/cosign-installer` floating `v3` → pinned `v3.7.0`)
  across 6 template files

## [0.16.0] - 2026-05-15

SCM governance feature release. Adds branch-protection and tag-immutability
enforcement at the Git-server layer via GitHub Repository Rulesets, with a
canonical configuration doc, ADR with rejected options + revisit triggers,
and an idempotent `gh api` applier wired into three Make targets. No changes
to scaffolded service surface, K8s identifiers, prediction schema, or any
existing template contract — opt-in capability per the CONSULT-class entry
in `AGENTS.md`. Full notes: `releases/v0.16.0.md`.

### Added

- ADR-026 — Branch Protection & Tag Immutability via GitHub Rulesets
  (`docs/decisions/ADR-026-branch-protection.md`)
- Canonical SCM governance config table (`docs/governance/branch-protection.md`)
- Idempotent applier `scripts/setup_branch_protection.sh` with `--dry-run`
  and `--check` modes; no hard `jq` dependency (`jq` → `python3 -m json.tool`
  → `cat` fallback at startup)
- Make targets `setup-github-preview`, `setup-github`, `setup-github-check`
- `AGENTS.md` operations matrix: 2 rows for branch-protection apply/modify
- `scripts/bootstrap.sh` Next Steps step 4 surfaces SCM protection
- `QUICK_START.md` "Protect your fork" section
- `README.md` references ADR-026 in Release-and-operate

### Changed

- `docs/ADOPTION.md` CC7.2 SOC 2 row points at the real enforcement
  artifacts (ADR-026 + `make setup-github`), no longer the prior
  aspirational "branch protection" string
- `scripts/verify_enterprise_adoption.py` tracking constants bumped
  to `RELEASE = "0.15.3"` + new `RELEASE_DATE` constant; still passes

## [0.15.3] - 2026-05-15

ML/Data Scientist template hardening release. This patch aligns the
training path with the EDA and fairness contracts the template already
advertised, without changing the `/predict` API surface or scaffolded
directory layout.

### Changed

- `train.py` now fails closed when
  `quality_gates.require_eda_artifacts=true` unless the full canonical
  EDA packet is present and loadable: `eda_summary.json`,
  `schema_ranges.json`, `baseline_distributions.parquet`,
  `feature_catalog.yaml`, and `leakage_report.json`.
- Training fairness now runs at the same optimal decision threshold
  selected during evaluation, writes `fairness.json`, fails closed for
  missing configured protected attributes, and blocks automatic quality
  gate pass-through when DIR is in the ADR-021 consultation band
  `[0.80, 0.85)`.
- The canonical EDA rule, skill, workflow, README, and ADR references
  now use `baseline_distributions.parquet` and `feature_catalog.yaml`
  as the source-of-truth names. Legacy names remain documented only as
  transition outputs.

### Added

- `templates/service/tests/test_training_fairness_gate.py` — contract
  tests for operational-threshold fairness, missing protected
  attributes, and the DIR consultation band.
- Additional EDA gate coverage proving a partial canonical artifact
  packet fails when EDA artifacts are required.

### Known follow-ons

- Generate service-specific `FeatureEngineer` skeletons from
  `feature_catalog.yaml` once at least one adopter-provided catalog is
  available as a concrete fixture.
- Extend `fairness.json` promotion evidence into model-card rendering
  so subgroup findings are copied automatically into service docs.

---

## [0.15.2] - 2026-05-06

FastAPI template contract hardening release. This does not add a second
serving framework or a parallel API template; it makes the existing
FastAPI scaffold more explicit, easier to review, and harder to drift.

### Added

- `docs/FASTAPI_TEMPLATE_CONTRACT.md` — concise contract for the
  scaffolded serving layer: required endpoints, non-negotiable
  invariants, customization order, and reviewer evidence.
- `templates/service/tests/test_fastapi_template_contract.py` —
  structural contract tests for OpenAPI surface, async
  `run_in_executor` usage, train/inference feature parity,
  readiness gating, auth/admin guards, observability hooks, and
  restricted modelless startup.

### Changed

- `.windsurf/rules/04a-python-serving.md` now treats the generated
  FastAPI scaffold as a first-class contract and documents the current
  `app/main.py` + `app/fastapi_app.py` split.
- Agentic guidance for `new-service`, `debug-ml-inference`, cloud
  deploy smoke tests, `/load-test`, and `/incident` now uses the
  schema-valid scaffold payload and checks `/ready` alongside
  `/health`.
- `scripts/test_scaffold.sh` now includes
  `tests/test_fastapi_template_contract.py` in the full
  `SCAFFOLD_SMOKE=1` pytest chain.
- `README.md` and `QUICK_START.md` now point adopters to the FastAPI
  contract and make the scaffolded serving surface explicit.
- `releases/v0.14.0.md` now uses the canonical
  `## Known follow-ons (scoped, not regressions)` heading, preserving
  release-note consistency.

---

## [0.15.1] - 2026-05-04

Patch release that closes 3 of the 5 pending items from the v0.15.0
audit-remediation entry (VALIDATION_LOG.md Entry 007).

### Added

- `scripts/check_baselines_expiry.py` — enforces that every entry in
  `.security-baselines/{tfsec.yml,checkov.yml,.trivyignore}` carries an
  `# expiry: YYYY-MM-DD` annotation AND that no entry is past due.
  Wired into `validate-templates.yml` as the `security-baseline-expiry`
  job. Closes the v0.15.0 pending item "baseline drift over time".
- `model-verifier` init container in `templates/k8s/base/deployment.yaml`:
  cosign keyless `verify-blob` of `model.joblib` against the workflow
  identity used by `retrain-service.yml`. Two modes:
  `MODEL_SIGNATURE_VERIFY=warn` (base default) and `=true|enforce`
  (production overlays). Closes the v0.15.0 pending item "cosign
  verification at deploy time".

### Changed

- `scripts/test_scaffold.sh` (`SCAFFOLD_SMOKE=1` path) now runs
  `tests/integration/` against the freshly-scaffolded service.
  `test_train_serve_drift_e2e.py` ships in CI. Closes the v0.15.0
  pending item "E2E integration test not executed in CI".
- `templates/k8s/overlays/{gcp,aws}-prod/patch-deployment.yaml`:
  `model-downloader` now also fetches `model.joblib.sig` and `.pem`;
  `model-verifier` patched to `MODEL_SIGNATURE_VERIFY=true` (enforce).
  Production pods that find a missing or tampered model fail at init
  rather than serving an unsigned model.
- `docs/runbooks/deploy-gke.md`: new "Model signature verification
  (init container)" section with the verifier commands, modes, and
  failure-path triage that chains to `secret-breach.md` on
  `no matching signatures`.

### Pending after v0.15.1

- L4 real-cluster execution (gates `v1.0.0`).
- OpenTelemetry tracing under load (adopter-side; opt-in middleware
  ships with the template).

---

## [0.15.0] - 2026-05-04

May 2026 enterprise-audit remediation release. Closes **4 critical,
9 high, 8 medium, and 2 low** findings from the Staff-level audit.
Template posture tightens from "Production-ready by design" to
**"Designed-ready (L1+L2+L3)"** with an honest L4 gap disclosure.

### Added

- `.security-baselines/` directory with `tfsec.yml`, `checkov.yml`,
  `.trivyignore`, and `README.md`. Baselines enforce the flip from
  `soft_fail: true` to hard-fail for supply-chain scans (HIGH-1).
- `templates/common_utils/tracing.py` — opt-in OpenTelemetry FastAPI
  middleware, wired from `app/main.py`; no-op + warning log when OTel
  packages are not installed (MED-6).
- `templates/service/constraints.txt` — optional pip-compile lockfile
  contract for adopters requiring bit-identical builds (MED-5).
- `templates/service/tests/integration/test_train_serve_drift_e2e.py`
  — real end-to-end integration test (LogisticRegression + FastAPI
  TestClient + real PSI) covering the train → serve → drift chain
  without mocks (MED-1).
- Drift `CronJob` init-containers that fetch `reference.csv` and
  `latest.csv` from the cloud bucket into a shared `emptyDir` before
  the detector runs (CRIT-3).
- Cosign blob signing of `model.joblib` + companion `.sig`/`.pem`
  publication to the model bucket in `retrain-service.yml`;
  verification command documented (HIGH-8).
- `Emit audit entry` step on every retrain run (success/failure/halt),
  with model SHA256, archive stamp, and C/C decision in the audit
  entry (HIGH-7).
- PSS-restricted `securityContext`, workload-pool `tolerations`, and
  per-container resource limits on `cronjob-drift.yaml` (CRIT-2).
- `{ORG}/{REPO}` placeholder substitution in `new-service.sh`
  (resolves from CLI args → env vars → `git remote get-url origin`
  → explicit warning) so Kyverno `subjectRegExp` policies render
  with a real GitHub identity, not a literal placeholder (MED-10).
- Maintainership disclosure in `.github/CODEOWNERS`, plus aligned
  notes in `deploy-gcp.yml` and `deploy-aws.yml` on the
  "2 reviewers" production gate being aspirational with a single
  CODEOWNER (HIGH-2).
- Dev overlay NetworkPolicy patch files (`gcp-dev/patch-networkpolicy.yaml`,
  `aws-dev/patch-networkpolicy.yaml`) so the base NetworkPolicy can
  default-deny public egress without breaking dev scaffolding (MED-11).

### Changed

- `templates/k8s/base/kustomization.yaml` now includes
  `slo-prometheusrule.yaml` in `resources:` — previously shipped under
  `base/` but never rendered. SLO burn-rate alerts now ship with every
  scaffolded service (CRIT-1).
- `templates/k8s/base/argo-rollout.yaml` rewritten with full security
  parity to `deployment.yaml`: PSS-restricted pod + container
  `securityContext`, workload-pool tolerations, `DEPLOYMENT_ID` via
  Downward API, `SERVICE_METRIC_PREFIX`, symbolic `cloud-cli-image`
  init container (no more literal `google/cloud-sdk:slim`), probes
  split. The file remains OPT-IN (not in base kustomization) so it
  does not collide with the Deployment — header documents the
  enablement patch (CRIT-4).
- `templates/k8s/base/networkpolicy.yaml` default-deny egress: the
  permissive `0.0.0.0/0` fallback moved from base into the dev
  overlays. Staging/prod overlays now APPEND their narrow CIDR rule
  (previously replaced index 3 which no longer exists). Contract
  test updated (MED-11).
- `.github/workflows/validate-templates.yml`: tfsec, checkov, trivy
  flipped from `soft_fail: true` to hard-fail with baseline config
  files (HIGH-1).
- `templates/service/app/fastapi_app.py`:
  - `ThreadPoolExecutor` size now derived from `INFERENCE_CPU_LIMIT`
    and `os.cpu_count()` with explicit override via
    `INFERENCE_THREADPOOL_WORKERS`; sizing logged at startup
    (MED-2).
  - `ALLOW_MODELLESS_STARTUP=true` is REFUSED in `staging`,
    `production`, and any non-dev `ENVIRONMENT`. Misconfigured
    deploys fail fast instead of serving a synthetic model to real
    traffic (HIGH-6).
  - `/metrics` endpoint carries explicit documentation about its
    NetworkPolicy-based access control (MED-4).
- `templates/service/app/main.py`: `/model/info` protected by
  `verify_api_key` so model type/path/version are not publicly
  fingerprintable when `API_AUTH_ENABLED=true` (MED-3).
- `templates/common_utils/risk_context.py`: Prometheus query now
  requires scheme validation (http/https only), optional Bearer auth
  via `PROMETHEUS_BEARER_TOKEN`, optional custom CA bundle via
  `PROMETHEUS_CA_BUNDLE`, and explicit opt-in for
  `PROMETHEUS_INSECURE_SKIP_VERIFY` (refused outside dev/local)
  (HIGH-9).
- `templates/service/pyproject.toml` version bumped from `1.0.0` down
  to `0.1.0` to match the `v0.x` template posture; scaffolded
  services own their own version (MED-8).
- `examples/minimal/serve.py` now implements the canonical warm-up +
  `/ready` gating pattern (D-23) with CPU-aware ThreadPool sizing,
  aligning the example with the full template (MED-9).
- README "Production-ready by design" wording replaced with "Designed-
  ready (L1+L2+L3)" across the maturity matrix. Numeric self-rating
  table removed. Memory Plane and CI self-healing demoted from hero
  capabilities to "Roadmap — Phase 1 contracts only" (HIGH-3/4/5).

### Security

- Baselines in `.security-baselines/` document accepted findings with
  rationale + expiry. Every exception is reviewable in a PR; the path
  to zero-baseline is explicit.
- Model artifacts now carry a cosign signature chain verifiable via
  Rekor; bucket compromise no longer silently substitutes a model.
- Dynamic-risk protocol queries Prometheus over authenticated TLS;
  an attacker cannot downgrade the agent's risk posture by
  misconfiguring the signal source (the fallthrough always escalates,
  never relaxes).

### Fixed

- Drift detection `CronJob` no longer crash-loops in PSS-restricted
  namespaces — missing `securityContext` caused admission rejection,
  the `DriftDetectionHeartbeatMissing` alert fired forever, and
  operators chased a phantom "drift pipeline broken" incident instead
  of the real "the manifest was always broken" cause (CRIT-2/3).
- Staging/prod NetworkPolicy patches no longer reference the removed
  index `/spec/egress/3`; they now APPEND their narrow rule using
  `op: add /spec/egress/-`.
- Deploy workflow comments no longer imply a 2-reviewer gate that
  the single-CODEOWNER setup cannot actually satisfy (HIGH-2).

### Documentation

- `README.md` §"Production-ready scope" completely rewritten with
  the L1/L2/L3/L4 layer matrix and an honest L4-gap disclosure.
- `README.md` §"Recent hardening" replaces the numeric self-rating
  with per-release, file-level evidence against the most recent
  audit.
- Runbooks expanded: `docs/runbooks/rollback.md`,
  `docs/runbooks/deploy-gke.md`, `docs/runbooks/deploy-aws.md`,
  `docs/runbooks/secret-breach.md` — each now includes trigger
  criteria, pre-flight, procedure, verification table, audit + comms,
  exit criteria, failure paths, and anti-patterns (LOW-5).
- `docs/decisions/ADR-024-audit-may-2026-remediation.md` — ADR
  recording the 23-finding remediation, the move from
  "Production-ready by design" to "Designed-ready", and the
  baseline-to-zero roadmap.
- `VALIDATION_LOG.md` Entry 005 records the per-file evidence for
  every CRIT/HIGH fix in this release.

---

## [0.14.0] - 2026-05-03

Enterprise adoption remediation release. This closes the highest-impact
gaps from the Staff-level audit without changing the template's public
positioning: production-ready by design, pre-GA until real cloud L4
evidence is captured.

### Added

- Runbooks referenced by the non-agentic adoption guide and scaffolded
  Makefile: drift detection, model retrain, release checklist, rollback,
  incident response, performance review, cost review, secret breach,
  inference debugging, performance RCA, concept drift analysis, and
  GKE/AWS deploy procedures.
- Enterprise adoption verifier in `scripts/verify_enterprise_adoption.py`
  covering runbook links, release documentation, scaffolded CI/CD layout,
  and train/inference parity contract text.

### Changed

- Generated CI now treats the scaffolded service as a single-service repo
  rooted at `app/`, `src/`, `requirements.txt`, and `Dockerfile`.
- GCP/AWS deploy workflows now build from repo root and publish
  `{service-name}-predictor` images, matching the Kustomize overlay
  vocabulary and digest-pinning reusable workflow.
- Python packaging now discovers packages under `src/`; pytest also gets
  `pythonpath = [".", "src"]` for scaffolded test ergonomics.
- Template pre-commit versions now match the root quality chain.
- README now records the post-remediation score delta and explicitly keeps
  the L4 cloud rollout caveat.

### Fixed

- First scaffold CI no longer points at a non-existent `${ServiceName}/`
  subdirectory.
- Deploy image names no longer mix PascalCase service names with
  kebab-case Kubernetes image names.
- API inference now loads the training `FeatureEngineer` and applies
  `transform_inference()` before prediction unless an operator explicitly
  opts out with `FEATURE_ENGINEERING_REQUIRED=false`.
- The skipped train/inference feature parity test is now an executable
  contract in scaffolded services.
- D-01..D-32 documentation references are reconciled in README,
  adoption docs, and policy workflow summaries.

### Known follow-ons

- Real GKE/EKS cloud golden-path execution remains the release gate for
  future `v1.0.0`.
- Adopter-specific egress allowlists and cloud credentials still require
  environment-local validation.

## [0.13.0] - 2026-05-03

Pre-GA hardening release. This release deliberately moves the public
signal back to a `v0.x` channel while preserving historical `v1.x` tags.
The template remains production-oriented, but GA enterprise readiness is
reserved for the first verified cloud golden path.

### Added

- `scripts/sync_agentic_adapters.py` renders Cursor, Claude, and Codex
  as thin manifest-driven adapter pointers instead of hand-maintained
  rule/skill/workflow forks.
- Codex parity now covers the full canonical set: 15 rule files, 16
  skills, and 12 workflows through `.codex/{rules,skills,workflows}/`.
- `make agentic-sync` and targeted CI verification now check adapter
  drift with `scripts/sync_agentic_adapters.py --check`.
- Root Day-2 operations runbook index in `docs/runbooks/day-2-operations.md`.
- Strict CI verifier scripts for YAML, workflows, and targeted policy
  gates used by the autofix policy.

### Changed

- Agentic manifest surfaces now include `codex` for all canonical rules,
  skills, and workflows.
- `AGENTS.md`, `docs/ide-parity-audit.md`, `.codex/README.md`, and
  ADR-023 now describe the enterprise adapter pattern: `AGENTS.md` as
  authority, `.windsurf/` as canonical body store, YAML as index, and
  generated pointers as IDE adapters.
- Golden-path workflows are stricter: scaffold smoke must fail on
  skipped install/test/snapshot paths, and deploy smoke requires real
  `/health`, `/ready`, `/predict`, and metrics evidence.
- Quality gates can require EDA artifacts before training/promotion.
- GCP/AWS infra defaults were tightened around private endpoints,
  node OAuth scopes, state-lock naming, artifact IAM, and bucket-scoped
  runtime identities.
- Codex MCP example includes the optional Playwright MCP entry.

### Fixed

- Missing CI autofix verifier commands are now real scripts.
- `mcp_doctor.py` validates workflow MCP capabilities, not only skills.
- `AGENT_CONTEXT.md` stale training path and ADR references were corrected.

### Known follow-ons

- Terraform MCP uses Docker; this workstation could not pull
  `hashicorp/terraform-mcp-server:latest` because the Docker daemon was
  not running.
- Real cloud GKE/EKS E2E validation remains the release gate for
  future `v1.0.0`.

---

## [1.12.0] - 2026-04-29

Closes 4 external-audit Round-3 findings and hardens pre-commit as the first filter. Root cause of the R3 findings: contributor clones shipped without actually installing git hooks, so black / flake8 drift, a closed-loop workflow with a payload that didn't match the live schema, and a kebab-vs-snake path bug in the drift CronJob all reached CI as the last line of defense. This release makes the first filter non-optional.

### Breaking for adopters (post-R4 audit re-classification)

Under the versioning policy ratified in `docs/RELEASING.md` (introduced post-tag in response to R4 finding C3), the following items in this release WOULD have required a MAJOR bump. Tag `v1.12.0` is immutable; this block documents the contract change so adopters can migrate explicitly. See `MIGRATION.md` for the `v1.11 → v1.12` row.

- **Closed-loop schema realignment** (HIGH-1, PR-R2-9): the `golden-path-extended.yml` workflow now POSTs `entity_id` + `feature_a/b/c` + `slice_values` to `/predict`, replacing the previous `feature_1/2/3` payload that returned 422 against the live schema. Adopters who copied or extended that workflow MUST update their payload to the canonical schema. Metric fallback also changed from `requests_total{endpoint="/predict"}` to `requests_total{status=~"2xx|4xx"}` because the counter only carries a `status` label.
- **Drift CronJob Python path** (HIGH-2, D-32): scaffolded manifest now uses `src/{service}/monitoring/drift_detection.py` (snake) instead of `src/{service-name}/...` (kebab). Adopters whose CronJob applied cleanly but exploded with `ModuleNotFoundError` at runtime must redeploy after re-scaffolding or apply the snake-case path manually.
- **Pre-commit hook contract**: hook count went 9 → 14 with `default_install_hook_types: [pre-commit, pre-push]`. Adopters who maintained custom `.pre-commit-config.yaml` overlays MUST run `pre-commit install --overwrite` (now wrapped in `scripts/dev-setup.sh` and `make verify-hooks`).

### HIGH — closed (pre-commit + audit R3)

- **HIGH-1 (PR-R2-9)** Stage 1 of `golden-path-extended.yml` was posting `feature_1/2/3` against a live schema that required `entity_id` + `feature_a/b/c` — every "valid" request was 422'd. The metric fallback `requests_total{endpoint="/predict"}` matched NOTHING because the counter only has a `status` label (see `fastapi_app.py:176`). Fixed: payload uses the canonical schema fields including `slice_values`; fallback awk pattern matches against `status="2xx|4xx"` which actually exists. NEW `test_closed_loop_workflow_contract.py` (3 tests) parses both sides and fails LOUD if workflow and schema drift.
- **HIGH-2 (D-32)** Drift `CronJob` referenced `src/{service-name}/monitoring/drift_detection.py` (kebab) but the scaffolder renames `src/{service}` → `src/<snake_slug>`. Manifest applied cleanly, then exploded at runtime with `ModuleNotFoundError: fraud-detector is not a valid Python package name`. Fixed: manifest now uses `{service}` (snake). NEW **D-32** entry in `AGENTS.md` formalizes the rule with inline rationale. NEW `test_d32_drift_cronjob_python_path` regression test (placeholder leak guard + snake-case check + on-disk directory existence + `drift_detection.py` existence).

### Pre-commit as mandatory first filter

Discovered this clone had ZERO hooks in `.git/hooks/` — which is why this session shipped 5 commits with black drift and F541 caught ONLY by CI. The fix makes hooks non-optional.

- `default_install_hook_types: [pre-commit, pre-push]` in `.pre-commit-config.yaml` so a single `pre-commit install` covers both stages (previously `--hook-type pre-push` had to be passed separately and almost nobody did — the scaffold-smoke pre-push hook silently never ran).
- NEW `scripts/dev-setup.sh` — idempotent bootstrap: installs pre-commit if missing, validates config, installs both stages with `--overwrite`, verifies hooks actually landed in `.git/hooks/`, runs `pre-commit run --all-files` as sanity check. Fails LOUD with the fix command.
- NEW `make verify-hooks` target — fails non-zero if either hook is missing or doesn't reference the pre-commit framework.
- NEW hooks (ported from the portfolio): **mypy 1.13** narrowed to `common_utils/` + `examples/` + `scripts/` (template service territory is placeholder land and explodes mypy), **bandit 1.7.10** with `-ll -i` threshold.
- NEW LOCAL hooks: **validate-agentic** (runs `scripts/validate_agentic.py --strict` when AGENTS.md or agent runtime config changes) and **ci-autofix-policy-contract** (runs the 10-invariant contract test from ADR-019 when policy YAMLs change). These are the project's OWN gates; contributors no longer wait for CI to discover drift.

Result: **14 hooks** (was 9), all 14 green on `main`.

### LOW — release hygiene

- `releases/v.1.11.0.md` → `releases/v1.11.0.md` (`git mv` preserves history). The previous filename broke alphabetical sorting between v1.10 and v1.11.

### MEDIUM — catalog reconciliation

- README said "30 production anti-patterns" while AGENTS table ended at D-31 and code/tests already referenced D-32 without a canonical definition. Fixed: `D-01..D-32` across `README.md`, `AGENTS.md` (4 callsites reconciled), and D-32 formalized in the anti-pattern table.

### CI hardening

- **CI parity for local hooks**: the two new local hooks need pytest/pyyaml/jsonschema in the lint lane. Added to the `python-quality` job so CI matches the same set of hooks as local pre-commit.
- **ci-autofix-policy-contract** uses `--noconftest --rootdir=.` so pytest doesn't pick up the service's numpy-heavy conftest (unnecessary for a self-contained contract test). Fast + self-contained is the whole point.
- **mypy fix** in `risk_context.py:301`: removed a redundant `ctx: RiskContext` annotation that re-declared a cache-unpacked variable. `[no-redef]` was the only mypy error blocking the new hook from going green on the existing tree.
- **bandit fix** in `risk_context.py:215`: explicit `# nosec B310` on the Prometheus urlopen with a 3-line comment explaining the URL comes from deployment config, not request input.

### Known follow-ons (scoped, not regressions)

- MEDIUM legacy-service migration guide for adopters that need to temporarily set `require_eda_artifacts=false`.
- MEDIUM Windows CI matrix for `validate_agentic.py` (new lane; script currently works on Linux/WSL/macOS).
- MEDIUM NetworkPolicy egress allowlist by cloud (per-overlay work).
- MEDIUM `load_test.py` schema sync to `feature_a/b/c` (low-risk but clean review as separate PR).
- ADR-018/019 runtime implementation remains staged: Phase 1 shadow/read-only capabilities are shipped; write-enabled runtime remains deferred pending shadow precision evidence.

---

## [1.11.0] - 2026-04-28

Closes the ADR-016 external-audit R2 remediation backlog (7-day, 30-day, and 90-day windows all materially shipped) and lays the policy foundation for two new agent capabilities (Operational Memory Plane, Agentic CI Self-Healing). Also closes the OSS-packaging gap (NOTICE, DCO, CODEOWNERS) and tightens cloud parity through an additional 33 contract tests.

### Breaking for adopters (post-R4 audit re-classification)

Under the versioning policy in `docs/RELEASING.md`, the following items in this release WOULD have required a MAJOR bump. Tag `v1.11.0` is immutable; this block documents the contract change explicitly.

- **GCP IAM split surface**: `gcp/iam.tf` introduced per-service identity bindings that change the IAM model. Adopters with existing GCP deployments must apply the `terraform plan` carefully and confirm no privilege downgrade for in-flight workloads.
- **`templates/config/ci_autofix_policy.yaml` and `model_routing_policy.yaml` introduced**: these become the canonical source of truth for autofix routing. Adopters who previously relied on undocumented defaults must opt in by enabling the (Phase 0) policy contract tests; no runtime behavior change yet.
- **New `make` targets in non-agentic on-ramp**: 12 targets added (`scaffold`, `validate`, `deploy-dev`, etc.). Adopters who maintained custom Makefiles must merge the new targets per `docs/ADOPTION.md`.

### ADR-016 R2 remediation — closed

- **PR-R2-1..R2-5** (7-day window): shipped earlier in 1.10.0.
- **PR-R2-6** AWS parity: storage, registry, IAM, secrets, logging — shipped.
- **PR-R2-7** Quality-gate config externalized per service — shipped.
- **PR-R2-8** EDA artifacts as machine-readable contract — shipped (delivered as part of PR-B2 stages 1–2).
- **PR-R2-9 Stage 1** Closed-loop verification — NEW `.github/workflows/golden-path-extended.yml` that re-scaffolds + deploys + posts 100 valid + 5 invalid `/predict` requests + asserts the prediction-log counter increments. Triggers on `workflow_run` after the base Golden Path E2E succeeds, plus weekly schedule and on-demand. PR-R2-9b (alert firing via Prometheus + Pushgateway) is the explicit follow-on.
- **PR-R2-10** Reproducible drift + degraded-deploy drills — shipped.
- **PR-R2-11** D-01..D-31 anti-patterns as policy tests over scaffolded output — NEW `templates/service/tests/policy/` (13 tests) + dedicated weekly workflow. The suite scaffolds a fresh service per session and asserts AGENTS.md invariants hold on the rendered output. Surfaces a documentation drift in `aws/iam.tf` on first run; fixed in same PR.
- **PR-R2-12** Adoption-boundary doc + non-agentic on-ramp — NEW `docs/ADOPTION.md` (maturity matrix per cloud × environment + non-claims list) + 12 new `make` targets so teams can adopt the template without inheriting the agentic surface + `test_adoption_boundary_contract.py` (7 tests) enforcing parity workflow ↔ make target ↔ doc.

### Cloud parity (AWS ↔ GCP)

- **GCP gets** secrets.tf, logging.tf, kms.tf at the live layer with bootstrap-tier KMS key separation. Mirrors the AWS surface introduced in 1.10.0.
- **NEW** `test_terraform_cloud_parity.py` (14 tests) enforces semantic parity: same secret-store usage, logging retention, budget alert wiring, CMEK across both clouds.
- **GCP IAM** parity rationale documented inline in `gcp/iam.tf`: GCP doesn't need an `iam-roles-split.tf` equivalent because per-service identities don't exist on GCP — Workload Identity bindings per-secret/per-bucket already partition responsibilities.
- **Cluster defaults** (PR-A3): private endpoint configurable and secure by default, system/workload node pool split with taint, deny-default `NetworkPolicy`. Enforced by `test_cluster_defaults_contract.py`.
- **Bootstrap split**: state bucket, KMS, registry tiers separated from live layer per ADR. Enforced by `test_terraform_bootstrap_contract.py` (~7 tests).

### NEW agent capabilities (Phase 0 only — runtime deferred)

- **ADR-018 Operational Memory Plane** ratifies a typed retrieval layer over existing evidence (audit.jsonl, drift reports, postmortems, security findings) that feeds new dynamic risk signals to `risk_context.py`. Hard boundaries codified: NOT in `/predict` path, NOT authoritative, NOT a policy mutator (memory hits can only ESCALATE prudence, never demote STOP). Phase plan with 7 phases; either phase auto-withdraws if the next phase doesn't ship in 30 days.
- **ADR-019 Agentic CI Self-Healing** ratifies the policy contract for bounded autofix on CI failures. Ships TWO governance YAMLs (`templates/config/ci_autofix_policy.yaml`, `templates/config/model_routing_policy.yaml`) + ONE contract test (10 invariants) + the canonical failure-class table (12 classes mapped AUTO/CONSULT/STOP). Runtime scripts deferred — policy first, scripts second.

### Model routing recommendation

- New README §"Recommended baseline (verified 2026-04)" subsection adds a provider × tier table mirroring `model_routing_policy.yaml` plus three pre-tuned profiles. Includes an explicit honesty caveat: vendor model names rotate every 6–12 months; the `verified_at` field declares when the catalog was last reconciled; the contract test enforces structure (preview never lands on protected branches), not specific identities.

### OSS packaging

- **NEW** `NOTICE` (Apache-2.0 attribution).
- **NEW** `DCO.md` (explicit DCO policy — already used in commits but undocumented).
- **NEW** `.github/CODEOWNERS` routes review for protected areas (AGENTS.md, agent runtime config, ADRs, CICD/k8s/infra/scripts, common_utils, service template, monitoring, governance files).
- Existing `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md` retained — already detailed and aligned.

### CI hardening

- **CI tfsec fix**: replaced unsupported Terraform `check` block with `terraform_data` + `lifecycle.precondition` for AWS subnet validation (tfsec v1.28.x parser limitation).
- **Policy-tests workflow numpy isolation**: added `--rootdir` + `--confcutdir` so the policy suite doesn't trigger the parent ML conftest's numerics imports. Workflow stays cheap (~30s install vs ~5min full ML stack).
- **black drift fix**: 5 test files reformatted; local + CI now agree.
- **F541 fix**: removed an f-prefix on a string with no placeholders.

### Test count

Contract tests: **76 PASS** (14 parity, 7 bootstrap, 11 cluster defaults, 7 adoption boundary, 10 CI policy, 18 day-2 artifacts, 9 IAM least-privilege).
Policy tests over scaffolded output: **13 PASS + 3 SKIP** (~4 min wall-clock per run).

### Known follow-ons (scoped, not regressions)

- **PR-R2-9b** alert-firing via Prometheus + Pushgateway (Stage 2 of PR-R2-9).
- **ADR-018 Phases 1–6** (canonical contracts, ingestion, storage/retrieval, integration, shadow→advisory→guarded-gate→enforced, hardening).
- **ADR-019 Phases 1–6** (context collection, classification, verifier helpers, workflow scaffold, AUTO enablement per failure class, CONSULT lane).

---

## [1.10.0] - 2026-04-26

Closes a 15-finding template audit. The audit caught a class of bugs
where the template LOOKED finished — green CI, scaffolder passes —
but the deploy chain, supply-chain trust chain, and governance gates
had silent gaps a real production user would discover only at the
worst time. This release is mostly fixes; there is little new
surface area but the existing surface now does what the docs say.

### Breaking for adopters (post-R4 audit re-classification)

Under the versioning policy in `docs/RELEASING.md`, this release SHOULD have been `v2.0.0` rather than `v1.10.0`. The R4 audit (finding C3) explicitly flagged it. Tag `v1.10.0` is immutable; this block makes the contract change visible. See `MIGRATION.md` for the `v1.9 → v1.10` row, which is the highest-impact migration in the project's history.

- **Six environment overlays renamed**: `gcp-production` → `gcp-prod`; `aws-production` → `aws-prod`; new `gcp-dev`, `gcp-staging`, `aws-dev`, `aws-staging` introduced. Adopters MUST update every reference in custom CI, deploy scripts, and `kubectl` invocations. Pre-`v1.10` deploys for dev/staging never worked; adopters who thought they had dev deploys did not.
- **Cosign signing path now wired end-to-end**: prior versions advertised image signing but did NOT install `cosign` in any workflow. From `v1.10.0` onward, every prod build signs and attests; adopters with existing Kyverno admission policies in audit mode must move to enforce mode AFTER confirming all images carry signatures and SBOMs.
- **Image digest pinning is now mandatory**: `kustomize edit set image <name>=<repo>@<digest>` runs BEFORE every `kubectl apply`. Adopters who deployed by tag (e.g. `:latest`, `:1.0`) MUST switch to digest references; mutable tags are no longer supported by the deploy chain.
- **Init-container model loading**: `templates/k8s/base/deployment.yaml` introduces an init-container with an `emptyDir` volume to download model artifacts at runtime. Adopters who baked artifacts into images (D-11) MUST migrate to the init pattern.
- **Pod Security Standards labels mandatory**: each overlay now carries the correct PSS labels (`enforce=baseline` for dev/staging, `enforce=restricted` for prod). Adopters with custom namespaces MUST add the labels or admission control will reject the pods.

### Critical fixes

- **Six environment overlays** (`templates/k8s/overlays/`):
  `gcp-{dev,staging,prod}` and `aws-{dev,staging,prod}`. The
  deploy workflows referenced these names; the repo only shipped
  two misnamed dirs (`gcp-production`, `aws-production`). Every
  dev/staging deploy was broken. Each overlay carries its own
  `namespace.yaml` with PSS labels (D-29: `enforce=baseline` for
  dev/staging with `warn/audit=restricted`; `enforce=restricted`
  for prod) and env-tier resources (1×100m for dev, 1×250m for
  staging, 2×500m for prod).
- **Image digest pinning end-to-end**:
  `deploy-{gcp,aws}.yml` build job captures `sha256:...` via
  `docker buildx imagetools inspect` and emits a JSON map.
  `deploy-common.yml` consumes it and runs `kustomize edit set
  image <name>=<repo>@<digest>` BEFORE `kubectl apply`. Cosign
  signs and attests by digest. The Kyverno digest gate that was
  installed in v1.6.0 finally has compliant manifests to admit.
- **Root pytest stops crashing on Prometheus metric placeholders**:
  `templates/service/app/fastapi_app.py` previously declared
  `Counter("{service}_predictions_total", ...)`. `prometheus_client`
  rejects metric names containing `{` / `}`, so root-level coverage
  collection produced 11 errors before any test ran. Metrics now
  use `f"{os.getenv('SERVICE_METRIC_PREFIX', 'ml_service')}_..."`;
  `deployment.yaml` sets the env var to the scaffolded service name
  so production metrics are unchanged.

### High fixes

- **`common_utils/__init__.py` lazy re-exports** so
  `from common_utils.agent_context import AuditLog` works on a
  CI runner without joblib installed. The audit step in
  `deploy-common.yml` (introduced v1.8.0) was failing to write
  evidence on lightweight runners — the "obligatory" audit trail
  was actually fragile.
- **`AWS_ROLE_ARN` declared in `deploy-common.yml`'s
  `workflow_call.secrets`**. The reusable workflow read
  `secrets.AWS_ROLE_ARN` while declaring `secrets: {}` — invalid
  contract that blocked AWS callers at validation time.
- **Cosign installed in `deploy-{gcp,aws}.yml`**. The build job
  ran `cosign sign` and `cosign attest` without ever installing
  cosign on `ubuntu-latest`. Signing and attestation never worked
  before this release.
- **Pod Security Standards namespace labels** included in every
  overlay (was a separate file in `templates/k8s/policies/` that
  no overlay consumed). D-29 is now actually enforced.
- **`SecurityAuditResult` blocks HIGH findings**, not just
  CRITICAL. The dataclass derived `passed` from `trivy_critical
  == 0` only — a service with 5 HIGH and 0 CRITICAL passed the
  gate even though the `security-audit` skill said both block.
  The dataclass and the policy doc are now consistent.
- **Per-env Terraform state**. Backends are partial config:
  `backend "gcs" {}` / `backend "s3" {}` with `backend-configs/
  {env}.hcl` files passed at init time. Three envs × two clouds
  = six bucket/lock-table pairs, fully isolated. New runbook
  `docs/runbooks/terraform-state-bootstrap.md` documents the
  bootstrap.
- **Drift detection + retraining pipelines operationalized**.
  Workflows previously had `# TODO: Configure data download`
  + `echo "TODO: Upload model"` placeholders. Now use
  parametrized `{DATA,MODEL}_BUCKET_KIND` env vars to pick
  `gcs` vs `s3` and FAIL loudly on missing config instead of
  succeeding with a no-op. Champion/Challenger has a real
  champion to compare against; promotion uploads two copies
  (current + timestamped archive) per cloud.

### Medium fixes

- **`Makefile validate-tf` paths corrected** from
  `templates/infra/{gcp,aws}` to
  `templates/infra/terraform/{gcp,aws}`. `terraform init` now
  uses `-backend=false` so validate works without backend buckets.
- **`ci-examples.yml` installs `pyarrow` and `pytest-asyncio`**.
  Tests that exercised Parquet (prediction logger) or async
  client paths errored at import time and pytest counted them
  as "errors" not "failures" — green-yellow signal that hid
  missing coverage.
- **`docs/environment-promotion.md` purged of `GCP_SA_KEY`**
  references. The deploy chain has been WIF-only since v1.6.0;
  the doc was telling new contributors to provision a static
  service account key in defiance of D-18.
- **Demo fairness threshold documented as exception**, not a
  contradiction. `examples/minimal/train.py` keeps
  `FAIRNESS_THRESHOLD = 0.70` (synthetic data is too small to
  reliably hit 0.80 on a 1600-sample fold) but now has an 8-line
  comment explaining the policy baseline is 0.80 and only this
  demo runs laxer.
- **Smoke test runs in the right namespace**. `kubectl run smoke...`
  no longer lands in `default` and call services via FQDN
  (`<svc>-service.<ns>.svc.cluster.local`). With the new
  `{service}-{env}` overlay namespaces, the previous short-DNS
  form would always have failed.

### New runbooks

- `docs/runbooks/aws-irsa-setup.md` — AWS counterpart to
  the existing GCP WIF runbook. Covers GitHub OIDC trust + IRSA
  pod identity. Symmetric setup steps; cross-linked from
  AGENTS.md and environment-promotion.md.
- `docs/runbooks/terraform-state-bootstrap.md` — per-env state
  bucket bootstrap for GCP and AWS. Required reading before the
  first `terraform init` of any env.

### Verification

```bash
# All 6 overlays render
for o in gcp-dev gcp-staging gcp-prod aws-dev aws-staging aws-prod; do
  kustomize build templates/k8s/overlays/$o > /dev/null && echo "✓ $o"
done

# Cosign installed in BOTH deploy workflows
grep -c sigstore/cosign-installer templates/cicd/deploy-{gcp,aws}.yml

# Digest pinning step present
grep -c 'kustomize edit set image' templates/cicd/deploy-common.yml

# Test that previously crashed now passes
PYTHONPATH=templates/service python -c "from app import fastapi_app; print('ok')"

# Audit record runs without ML deps
PYTHONPATH=templates python -c "from common_utils.agent_context import AuditLog; print('ok')"

# Validator stays green strict
python scripts/validate_agentic.py --strict
```

### Total commits

9d8894e → b8708b6 (5 fix commits + this changelog entry)

---

## [1.9.0] - 2026-04-24

### Added

- **Batch inference skill** — `.windsurf/skills/batch-inference/SKILL.md`
  scaffolds CronJob-based scoring that reuses the exact same
  `predictor.predict_batch()` function and Pandera schema as the live
  API; includes PSS restricted container, `concurrencyPolicy: Forbid`,
  and `activeDeadlineSeconds` hard cap
- **ADR-013 — GitOps strategy** — codifies the current
  `kubectl apply` posture and the four revisit triggers for
  migrating to ArgoCD
- **DORA metrics exporter** — `templates/scripts/dora_metrics.py`
  aggregates deployment_frequency, lead_time_for_changes,
  change_failure_rate, and mttr from the GitHub REST API +
  `ops/audit.jsonl`. Writes `ops/dora/{YYYY-MM}-metrics.json`.
  Graceful degradation without `GITHUB_TOKEN`. 9 unit tests
- **Devcontainer** — `.devcontainer/devcontainer.json` +
  `post-create.sh` give contributors a reproducible environment
  matching the CI runner (Python 3.11 bookworm + docker-in-docker +
  kubectl/helm + terraform + cosign + conftest + syft + gitleaks)
- **Secret rotation runbook** — `docs/runbooks/secret-rotation.md`
  covers SCHEDULED rotation (complement to `secret-breach-response`
  which handles emergencies): per-credential cadence table, STOP per
  env, 7-day soak on OLD version, quarterly calendar

### Scope note

v1.9.0 was planned as a 10-item roadmap. Delivered the 5 highest-
impact items; deferred D2 (GPU), D5 (more reusable GHA), D6
(Terraform tests), D8 (template repo publish) to future releases.

### Total test count

- Unit tests: **127 passing** (was 118 in v1.8.1)

---

## [1.8.1] - 2026-04-24

### Added

- **Pod Security Standards** (D-29) — `templates/k8s/policies/pod-security-standards.yaml`
  with Namespace definitions per environment; base `deployment.yaml`
  now ships pod + container `securityContext` compatible with PSS
  `restricted` (`runAsNonRoot`, `capabilities.drop: [ALL]`,
  `seccompProfile: RuntimeDefault`). Rule 02 §Pod Security Standards
- **SBOM attestation** (D-30) — `deploy-gcp.yml` + `deploy-aws.yml`
  generate a CycloneDX SBOM via Syft and attach it as a Cosign
  attestation. Full SLSA L3 provenance via `slsa-github-generator`
  documented as ROADMAP template block
- **ThreadPoolExecutor sizing** — `docs/threadpool-sizing.md` operator
  guide + `templates/service/scripts/benchmark_executor.py` executable
  sweep script (writes `ops/benchmarks/{ts}-executor.json`)
- **Input quality** — `common_utils/input_quality.py` opt-in checker
  against training-time `[p01, p99]` quantiles. Emits
  `{service}_input_out_of_range_total` labels without blocking the
  request. 14 unit tests
- **Closed-loop Grafana dashboard** —
  `templates/monitoring/grafana/dashboard-closed-loop.json` (10 panels:
  SLO availability + burn, per-version AUC, sliced-AUC heatmap, C/C
  error rate, score-distribution p50, logger errors, input-quality
  flags, monitor heartbeat, PSI top 10)
- **Intersectional fairness** — `fairness.py::compute_intersectional_fairness()`
  evaluates all 2-way combinations of protected attributes. New
  parameters on `run_fairness_audit(intersectional=False,
  min_intersectional_samples=30)`. 4 unit tests
- **Anti-patterns D-29, D-30** in AGENTS.md

### Changed

- `templates/k8s/base/deployment.yaml` — pod/container securityContext;
  init container resource requests/limits
- `templates/cicd/deploy-gcp.yml` + `deploy-aws.yml` — SBOM generation
  and attestation steps
- `templates/service/src/{service}/fairness.py` —
  `run_fairness_audit(intersectional=..., min_intersectional_samples=...)`
  parameters; `_summary.intersectional_evaluated` flag; `_intersectional`
  report block
- `.windsurf/rules/02-kubernetes.md` — new Pod Security Standards section

### Total test count

- Unit tests: **118 passing** (was 100 in v1.8.0)

---

## [1.8.0] - 2026-04-24

### Added

- **AuditLog** — thread-safe append-only JSONL writer in
  `common_utils/agent_context.py` for `ops/audit.jsonl`. Integrates with
  `RiskContext` via `record_operation()` to automatically persist the
  five ADR-010 signals plus `base_mode` whenever dynamic escalation
  changed the operation's mode
- **AuditEntry hardening** — now validates `result ∈ {success, failure,
  halted}` and requires an `approver` for CONSULT/STOP success entries
  (human-accountability invariant)
- **Skill `rule-audit`** — READ-ONLY automated compliance scanner
  against AGENTS.md anti-patterns D-01..D-28. Per-invariant query,
  evidence-backed findings, `--subset` scoping, AuditLog integration
- **Skill `performance-degradation-rca`** — multi-stream RCA
  correlating sliced metrics, drift, deploys, upstream data, and
  logger health. Produces R1..R5 root-cause classification and
  `docs/incidents/{date}-{service}.md` blameless RCA template
- **Rule 14 `14-api-contracts.md`** — API contract versioning policy:
  committed `openapi.snapshot.json`, semver table for schema evolution,
  CI guard enforcing version bump alongside snapshot changes
- **`templates/service/tests/contract/`** — scaffolded contract-test
  layout: `test_openapi_snapshot.py` (3 tests) + `openapi.snapshot.json`
  (regenerated via `scripts/refresh_contract.py`)
- **`templates/service/scripts/refresh_contract.py`** — operator
  regeneration script (executable)
- **Anti-pattern D-28** in AGENTS.md — breaking API change without
  version bump + snapshot update
- **25 unit tests** in `test_agent_context.py` covering every typed
  handoff + AuditLog semantics

### Changed

- `common_utils/agent_context.py`: `AuditEntry` gains `risk_signals:
  list[str]` and `base_mode: AgentMode | None` fields (omitted from
  JSONL when None)

### Total test count

- Unit tests: **100 passing** (was 75 in v1.7.1)

---

## [1.7.1] - 2026-04-24

### Added

- **Model warm-up** (`warm_up_model` in `fastapi_app.py`) forces a dummy
  predict and builds the SHAP `KernelExplainer` once during lifespan,
  before `_warmed_up=True`. Cached on app state (D-24)
- **Probe split** — `livenessProbe: /health` (always 200 while alive),
  `readinessProbe: /ready` (503 until warmed), `startupProbe: /health`
  with `failureThreshold: 24` to absorb cold start (D-23)
- **Graceful shutdown** — `terminationGracePeriodSeconds: 30` coordinated
  with uvicorn `--timeout-graceful-shutdown=20` (D-25)
- **PodDisruptionBudget** (`k8s/base/pdb.yaml`) with `minAvailable: 1`
  and HPA `minReplicas: 2` (D-27)
- **Champion/Challenger Argo Rollouts** — two AnalysisTemplates:
  `{service}-cc-online` (4 proxy metrics during canary, auto-rollback)
  and `{service}-cc-post-deploy` (3 business metrics from performance_monitor,
  human-gated rollback). Closes G-02b
- **Rollback skill + /rollback workflow** — STOP-class emergency revert
  procedure: Argo Rollouts abort+undo, MLflow registry revert, alert
  silencing, audit issue. Closes G-05
- **Environment promotion chain** — dev→staging→prod with GitHub
  Environment Protection Rules. Reusable `deploy-common.yml` workflow;
  `deploy-gcp.yml` and `deploy-aws.yml` rewritten as 4-job chains.
  `docs/environment-promotion.md` operator setup guide (ADR-011, D-26)
- **Dynamic Behavior Protocol** — `common_utils/risk_context.py` with
  19 unit tests. Reads `mcp-prometheus` for 5 live signals
  (incident_active, drift_severe, error_budget_exhausted, off_hours,
  recent_rollback); escalates AUTO→CONSULT or CONSULT→STOP per
  ADR-010. Fallback to `ops/*.json` files keeps template usable
  without the MCP
- **mcp-prometheus promoted to CORE MCP** in AGENTS.md §MCP Integrations
- **ADR-010** — Dynamic Behavior Protocol via mcp-prometheus
- **ADR-011** — Environment Promotion Gates (dev→staging→prod)
- **Anti-patterns D-23..D-27** added to AGENTS.md table with corrective
  actions

### Changed

- `templates/tests/infra/policies/kubernetes.rego` converted from Rego
  v0 (legacy `deny[msg] { }`) to Rego v1 (`deny contains msg if { }`).
  Pre-existing technical debt — current versions of conftest reject the
  old syntax. Content preserved; only syntax updated.
- `.windsurf/rules/01-mlops-conventions.md` — invariants list grows to
  6 (adds warm-up/probe-split); new Dynamic Behavior Protocol section
- `.windsurf/rules/02-kubernetes.md` — new sections for probe split,
  graceful shutdown, PodDisruptionBudget
- `.windsurf/rules/05-github-actions.md` — Environment Promotion Gates
  (D-26) and Reusable Workflows sections
- HPA `minReplicas: 1 → 2` (required for PDB `minAvailable: 1` to be
  non-trivially effective)
- Rollout's canary `analysis.templates` references the new
  `{service}-cc-online` template in dedicated file (previously inline)

### Fixed

- `templates/tests/infra/policies/kubernetes.rego` now parses with
  current conftest/OPA (Rego v1 strict mode)
- Argo Rollout canary no longer serves traffic to pods that have passed
  `/health` but have not finished warming their SHAP explainer

### Total test count

- Unit tests: **75 passing** (was 56 in v1.7.0)

---

## [1.7.0] - 2026-04-23

### Added

#### Closed-Loop Monitoring — Ground Truth + Sliced Performance + Champion/Challenger

Closes the largest remaining gap in the template: concept drift went silent
because the system only tracked feature distributions (PSI). This release
wires predictions to their eventual ground-truth labels, computes sliced
performance metrics, and gates promotion on statistical superiority.

See **ADR-006** (closed-loop monitoring), **ADR-007** (sliced analysis),
**ADR-008** (champion/challenger), and **ADR-009** (retraining orchestration
triggers) for the full rationale.

**Prediction logger (ADR-006):**
- `templates/common_utils/prediction_logger.py` — async buffered logger with
  4 pluggable backends (parquet, BigQuery, SQLite, stdout) via
  `PREDICTION_LOG_BACKEND` env var
- `PredictionEvent` frozen dataclass validates `prediction_id`,
  `entity_id`, and `model_version` at construction (invariant D-20)
- Fire-and-forget semantics: handler never blocks on log I/O (D-21)
- Failure-tolerant: flush errors swallowed + counted via
  `prediction_log_errors_total` (D-22)
- Integrated into `fastapi_app.py` and `main.py` lifespan; gracefully
  degrades if backend fails to start

**Ground truth ingestion (ADR-006):**
- `templates/service/src/{service}/monitoring/ground_truth.py` — daily
  CronJob with user-implemented `fetch_labels_from_source()` contract
- Ships CSV stub for local dev + documented examples for BigQuery, Postgres
- Writes idempotent daily parquet partitions (`year=/month=/day=`)
- `configs/ground_truth_source.yaml` — declarative source config

**Sliced performance monitor (ADR-007):**
- `templates/service/src/{service}/monitoring/performance_monitor.py` —
  JOINs predictions with labels on `entity_id` with causality constraint
  (`label_ts >= prediction_ts`), computes AUC/F1/precision/recall/Brier
  globally AND per slice
- Baseline comparison for concept drift (`auc_drop_warning/alert`)
- Tri-state status: `ok` / `warning` / `alert` / `insufficient_data`
- Prometheus Pushgateway metrics with labels
  `{slice_name, slice_value, metric}` for Grafana filtering
- `configs/slices.yaml` — bounded-cardinality slice declarations
  (country, channel, model_version, score_bucket examples)

**K8s manifests:**
- `k8s/base/cronjob-performance.yaml` — two CronJobs:
  - `{service}-ground-truth-ingester` at 03:00 UTC
  - `{service}-performance-monitor` at 04:00 UTC
- `k8s/base/performance-prometheusrule.yaml` — 5 alerts:
  - `GlobalAUCBelowAlert` (concept drift)
  - `SlicedAUCBelowAlert` (subpopulation degradation)
  - `F1BelowAlert` (threshold calibration)
  - `PerformanceMonitorStale` (heartbeat)
  - `PredictionLogErrorsHigh` (D-22 degradation visibility)

**Champion/Challenger statistical gate (ADR-008):**
- `templates/service/src/{service}/evaluation/champion_challenger.py` —
  McNemar exact binomial test + bootstrap ΔAUC 95% CI combined into
  tri-state decision (promote / keep / block)
- `configs/champion_challenger.yaml` — alpha, n_bootstrap,
  non_inferiority_margin, superiority_margin
- `cicd/retrain-service.yml` — new C/C gate between quality gates and
  promotion; posts decision to Actions step summary; opens issue on
  keep/block
- Exit codes: 0 (promote) / 1 (keep) / 2 (block)

**Anti-patterns (D-20, D-21, D-22):**
- D-20 — prediction log events without `prediction_id` / `entity_id`
- D-21 — prediction logging blocking the async inference event loop
- D-22 — logging backend failure propagating to the HTTP response
- Added to `AGENTS.md` anti-pattern table (now D-01 → D-22)

**Agentic system:**
- `.windsurf/rules/13-closed-loop-monitoring.md` — invariants + slicing /
  ground-truth / C/C contracts + agent behavior by file (AUTO/CONSULT/STOP)
- `.windsurf/skills/concept-drift-analysis/` — new skill with RCA decision
  tree (global vs sliced, drift vs labels vs noise)
- `.windsurf/skills/drift-detection/` — extended to cover BOTH data drift
  (PSI) AND concept drift (sliced performance)
- `.windsurf/skills/model-retrain/` — new Step 5.5 for C/C statistical gate
- `.windsurf/workflows/performance-review.md` — monthly review workflow
  with multi-window metric collection + degrading-slice detection

**IDE parity:**
- `.cursor/rules/08-closed-loop.mdc` — parity with Windsurf rule 13
- `.claude/rules/08-closed-loop.md` — parity with Windsurf rule 13

**ADRs:**
- `docs/decisions/ADR-006-closed-loop-monitoring.md`
- `docs/decisions/ADR-007-sliced-performance-analysis.md`
- `docs/decisions/ADR-008-champion-challenger-statistical-gate.md`
- `docs/decisions/ADR-009-retraining-orchestration-triggers.md` —
  documents measurable triggers for migrating retraining beyond GHA;
  explicitly rejects premature Argo Workflows adoption

**Tests (50 total passing, 25 new):**
- `templates/tests/unit/test_prediction_logger.py` — 20 tests covering
  `PredictionEvent` invariants, 3 backends, D-21/D-22 contract
- `templates/tests/unit/test_ground_truth.py` — 6 tests for LabelRecord
  invariants and CSV stub
- `templates/tests/unit/test_performance_monitor.py` — 14 tests for
  metrics, slicing, thresholds, full pipeline with sliced subpopulations
- `templates/tests/unit/test_champion_challenger.py` — 10 tests for
  McNemar, bootstrap CI, decide() logic, end-to-end sklearn comparison

**Schema changes (BREAKING for services on v1.6.x):**
- `PredictionRequest.entity_id` is now REQUIRED (`min_length=1`)
- `PredictionResponse.prediction_id` is now REQUIRED (UUID hex)
- Optional: `PredictionRequest.slice_values: dict[str, str]` for sliced
  monitoring

**Dependencies:**
- `pyarrow ~=18.0` — parquet backend for prediction_logger
- `pyyaml ~=6.0` — config loaders

**Scope respected:**
- No Argo Workflows (ADR-009 documents triggers; GHA remains default)
- No Bytewax / streaming (parquet batch covers target audience)
- No ClickHouse default (parquet is default; BigQuery optional; ClickHouse
  mentioned as future trigger at >100M predictions/day)
- No Istio shadow mode (ADR-008 future-work section)
- ADR-001 scope honored throughout

---

## [1.6.0] - 2026-04-23

### Added

#### Agent Behavior Protocol + Supply Chain Security

Closes two latent gaps: agents now know **when to pause and ask**, and the supply
chain has first-class controls (Cosign signing + SBOM + admission policy). See
**ADR-005** for full rationale.

**Agent Behavior Protocol (3 modes):**
- `AGENTS.md` — new **Agent Behavior Protocol** section with AUTO / CONSULT / STOP modes
- **Operation → Mode mapping table** (21 operations, canonical)
- **Escalation triggers** — automatic STOP even from AUTO/CONSULT (marginal fairness,
  drift PSI > 2× threshold, cost > 1.2× budget, credential detected, etc.)
- Structured mode transition signal format for handoffs

**Authorization checkpoints in skills:**
- `.windsurf/skills/deploy-gke/SKILL.md` — `authorization_mode` frontmatter + protocol section (dev=AUTO, staging=CONSULT, prod=STOP)
- `.windsurf/skills/deploy-aws/SKILL.md` — same pattern
- `.windsurf/skills/model-retrain/SKILL.md` — train=AUTO, to_staging=CONSULT, to_production=STOP + automatic STOP on D-06 / marginal fairness / regression > 5%

**New Layer 2 agent: Agent-SecurityAuditor**
- Runs **before** Agent-DockerBuilder and Agent-K8sBuilder
- Blocks pipeline on findings (never silent)
- Chains to `/secret-breach` on secret leaks

**Agent Permissions Matrix** — capability boundaries per agent × environment.
"Blocked" entries cannot be bypassed by human insistence.

**Agent Handoff Schema** — typed dataclass contracts replacing ad-hoc dicts:
- `templates/common_utils/agent_context.py` — `AgentMode`, `Environment`,
  `EDAHandoff`, `TrainingArtifact`, `BuildArtifact`, `SecurityAuditResult`,
  `DeploymentRequest`, `AuditEntry`
- All `frozen=True`, validate invariants at construction (fail-fast)
- `DeploymentRequest` refuses to construct if `env=production` + `audit.passed=False`

**Audit Trail Protocol:**
- Every agentic operation → `ops/audit.jsonl` (append-only)
- Mirrored to GitHub Actions step summary
- CONSULT/STOP operations additionally open a GitHub issue tagged `audit`
- Failures open an issue tagged `audit` + `incident`

#### Supply Chain Security (SLSA L2 components)

**New anti-patterns D-17 / D-18 / D-19:**
- D-17: Hardcoded credentials / direct `os.environ` for secrets in prod
- D-18: Static AWS keys or GCP JSON keys in production
- D-19: Unsigned images or missing SBOM in production

**`.windsurf/rules/12-security-secrets.md` (NEW, `always_on`):**
- Non-negotiable invariants D-17/D-18/D-19
- Pre-commit gitleaks + credential-pattern grep
- Python module guidance: `common_utils.secrets.get_secret`, never log values
- K8s: `envFrom.secretRef`, IRSA/WI annotations, image digests in staging/prod
- Terraform: secret manager data sources, no literals
- Environment separation table (local / ci / staging / prod)
- Explicitly documents what it does NOT cover (Vault, SLSA L3+, compliance — per ADR-001)

**`templates/common_utils/secrets.py` (NEW):**
- Cloud-native secret loader with environment-aware resolution
- Backends: dotenv (local), `os.environ` (CI), AWS Secrets Manager, GCP Secret Manager
- **Refuses to fall through to `os.environ` in staging/production** (D-18)
- Never logs secret values (D-17)

**`templates/cicd/ci.yml` updates:**
- New `security-audit` job: gitleaks + credential-pattern grep + IRSA/WI enforcement
- `build` job renamed to "Build, Sign & Attest":
  - Syft SBOM generation (CycloneDX + SPDX) with 90-day retention
  - Cosign keyless signing via GitHub OIDC (commented until registry wired)
  - `cosign attest` for SBOM as CycloneDX attestation
  - `permissions.id-token: write` for keyless signing
  - Build provenance summary in GHA step summary

**`templates/k8s/policies/kyverno-image-verification.yaml` (NEW):**
- ClusterPolicy `verify-image-signatures` — reject unsigned images in
  `environment=production` namespaces
- Keyless Cosign: GitHub OIDC identity + Rekor transparency log
- Requires CycloneDX SBOM attestation (max 90 days old)
- Companion ClusterPolicy `require-image-digest` — forbids tag-only refs in staging/prod

**Incident response:**
- `.windsurf/skills/security-audit/SKILL.md` (NEW) — pre-build/pre-deploy scans
- `.windsurf/skills/secret-breach-response/SKILL.md` (NEW) — 7-phase playbook
  (halt → classify → revoke → audit → rotate → clean history → notify → post-mortem)
- `.windsurf/workflows/secret-breach.md` (NEW, `/secret-breach` slash command)

**Documentation:**
- `docs/decisions/ADR-005-agent-behavior-and-security.md` (NEW)
  - Why 3 modes (not binary)
  - Why keyless Cosign (not keypair)
  - Why Kyverno (not OPA Gatekeeper)
  - Why refuse `os.environ` in prod
  - Why not Vault (ADR-001 deferred)
  - Why JSONL audit log (not GitHub issues per op)
  - Why dataclasses (not JSON Schema)
  - 4 alternatives considered + rejected
  - Revisit triggers

### Changed

- `AGENTS.md`: new sections (Behavior Protocol, Handoff Schema, Audit Trail, Permissions Matrix)
- Agent list in Layer 2 now includes Agent-SecurityAuditor
- Skills inventory adds `security-audit`, `secret-breach-response`
- Workflow inventory adds `/secret-breach`
- Cross-references table adds: pre-build/pre-deploy, secret-leak-detected

### Smoke tests

- Handoff dataclasses enforce invariants at construction:
  - `TrainingArtifact.requires_consult()` returns True for marginal fairness (0.80–0.85) or metric > 0.99
  - `SecurityAuditResult` raises `ValueError` if `passed` flag disagrees with component fields
  - `DeploymentRequest` raises `ValueError` on production + failed audit

### The consultative gap is now closed

```
Before:  Agent executes all the way to kubectl apply — human sees only results.
After:   Agent emits [AGENT MODE: CONSULT] before staging apply, [AGENT MODE: STOP]
         before production apply, presents plan, waits for explicit approval.
```

### The supply chain gap is now closed

```
Before:  Trivy scan → push → deploy (no signature, no SBOM, no admission gate)
After:   Trivy + Gitleaks → SBOM (CycloneDX + SPDX) → Cosign sign (keyless OIDC)
         → Cosign attest SBOM → push → Kyverno admission verifies at cluster entry
```

---

## [1.5.0] - 2026-04-23

### Added

#### EDA Phase Integration (closes data-to-training gap)

The template now has a first-class Exploratory Data Analysis phase that connects
raw data → trained model through 6 structured phases with 4 agentic invariants.

**Agentic configuration:**
- **`AGENTS.md`**: new Agent-EDAProfiler (Layer 2); anti-patterns D-13 through D-16;
  updated skill/workflow inventories with `eda-analysis` and `/eda`
- **`.windsurf/rules/11-data-eda.md`**: enforces snake_case, sandbox isolation,
  baseline persistence, structural layout. Glob: `**/eda/**`, `**/notebooks/**/*.ipynb`
- **`.windsurf/skills/eda-analysis/SKILL.md`**: 6-phase procedure with hard gate on
  phase 4 (leakage detection) — chains to `/incident` on block
- **`.windsurf/workflows/eda.md`**: `/eda` slash command; chains to `/new-service`
  on pass or `/incident` on leakage block

**Template module `templates/eda/`:**
- **`eda_pipeline.py`** (500 lines): scriptable pipeline
  - Phase 0: ingest + snake_case normalization (D-13 sandbox check)
  - Phase 1: structural profile → `01_dtypes_map.json`
  - Phase 2: univariate + **`02_baseline_distributions.pkl`** (D-15) with
    quantile bins for PSI compatibility (D-08)
  - Phase 3: correlations + feature ranking
  - Phase 4: leakage detection HARD GATE (exit 1 if `BLOCKED_FEATURES` non-empty)
  - Phase 5: feature proposals with rationale (D-16)
  - Phase 6: `schema_proposal.py` with observed ranges (D-14) + summary markdown
- **`notebook_template.ipynb`**: interactive companion (13 cells, one per phase)
- **`requirements.txt`**: lightweight mode (~50MB, pandas + scipy + pandera)
- **`requirements-heavy.txt`**: opt-in ydata-profiling + plotly (~500MB)
- **`README.md`**: conventions, phase artifacts reference, drift loop diagram

**Anti-patterns D-13 to D-16:**
- D-13: EDA on production data without sandbox
- D-14: Pandera schema without observed ranges from EDA
- D-15: Baseline distributions not persisted (silently breaks drift detection)
- D-16: Feature engineering without documented rationale

**Integration:**
- `new-service.sh` now copies `eda/` to scaffolded services + creates
  `reports/`, `artifacts/`, `notebooks/` subdirs
- Updated scaffolder next-steps walk users through EDA before `schemas.py`/`features.py`
- `test_scaffold.sh` validates 5 new `eda/` paths exist in scaffolded output
- `make eda-validate` target (syntax + `py_compile`); chained into `make validate-templates`

**Documentation:**
- **`docs/decisions/ADR-004-eda-phase-integration.md`**: documents the design,
  rationale for 6 phases (not fewer), hard gate on leakage, lightweight vs heavy
  modes, and why `schemas.py` is never auto-overwritten

**Validation:**
Tested end-to-end against `examples/minimal` fraud data (400 rows × 6 cols): all
6 phases pass in <1s, `baseline_distributions.pkl` produced with quantile bins,
leakage gate correctly PASSED, 3 transforms proposed each with rationale.

**The drift detection loop now closes:**
```
EDA phase 2 → 02_baseline_distributions.pkl (DVC-tracked)
           → Drift CronJob (production, consumes the pkl)
           → PSI per feature using quantile bins (D-08)
           → Alert if PSI > threshold → /drift-check → /retrain
```

---

## [1.4.0] - 2026-04-19

### Added

#### One-Command Bootstrap
- **`scripts/bootstrap.sh`** — Detects OS (Linux/macOS/WSL), verifies required tools (Python 3.11+, Docker, kubectl, terraform, git, make), installs Python dependencies, configures MCPs interactively, installs pre-commit hooks, and validates by running the minimal example end-to-end. Idempotent; supports `--skip-mcp`, `--skip-demo`, `--check-only`.
- **`scripts/_lib/detect_os.sh`** — OS detection helper
- **`scripts/_lib/install_deps.sh`** — Python + system dependency installer
- **`scripts/_lib/configure_mcp.sh`** — Interactive MCP configuration (github, git, kubectl-mcp-server, terraform-mcp-server)
- **Makefile targets**: `make bootstrap`, `make bootstrap-check`

#### Agentic System Validator
- **`scripts/validate_agentic.py`** — Validates `.windsurf/` structure:
  - Rule frontmatter (`trigger`, `description`, `globs`)
  - Glob patterns match real files (catches dead rules)
  - Skill `SKILL.md` contracts (`name`, `description`, `allowed-tools`)
  - Workflow frontmatter
  - AGENTS.md cross-references (no orphan skills/workflows)
- **CI job**: `agentic-system` in `validate-templates.yml` runs on every PR
- **Makefile target**: `make validate-agentic` (chained into `make validate-templates`)

#### Governance Module (opt-in)
- **`templates/governance/README.md`** — When/how to enable approval gates
- **`templates/governance/ROLES.md`** — ML Engineer / Tech Lead / Platform Engineer responsibilities
- **`templates/governance/github-environments.yml`** — GitHub Environments configuration reference (staging + production with `required_reviewers` and 24h soak)
- **`templates/governance/promote-with-approval.yml`** — GitHub Actions workflow for Staging → Production promotion with MLflow stage transitions and audit tags
- **`templates/governance/promote_to_stage.sh`** — CLI for MLflow Model Registry stage transitions with audit trail
- **`docs/decisions/ADR-002-model-promotion-governance.md`** — Documents why governance is opt-in, why GitHub Environments + MLflow stages over custom infrastructure, and how it respects ADR-001

#### Scaffolder End-to-End Test
- **`scripts/test_scaffold.sh`** — Runs `new-service.sh` in an isolated temp dir and validates:
  - Zero remaining `{ServiceName}`/`{service}`/`{SERVICE}` placeholders
  - All critical files and directories present
  - `src/{service}/` renamed correctly to `src/<slug>/`
  - All generated Python files parse (syntax check)
  - Both Kustomize overlays render (GCP + AWS)
  - `pytest` can collect scaffolded tests
- **CI job**: `scaffold-e2e` in `validate-templates.yml` runs on every PR
- **Makefile target**: `make test-scaffold` (also chained into `make validate-templates`)

#### Feast Integration Pattern
- **`docs/decisions/ADR-003-feast-integration-pattern.md`** — Documents the pattern for
  integrating Feast without modifying the core template. Uses external feature repo
  approach; service becomes a Feast client. Preserves Pandera validation (solves a
  different problem). Migration checklist (4 phases) and invariants maintained.

### Changed

#### Makefile (root)
- `validate-templates` now includes `validate-agentic` and `test-scaffold` steps
- Added `bootstrap`, `bootstrap-check`, `validate-agentic`, `test-scaffold` as first-class targets

---

## [1.3.0] - 2026-04-16

### Added

#### Standalone Documentation (root)
- **`QUICK_START.md`** — 10-minute setup guide: Option A (example demo), Option B (scaffold service), Option C (full MLflow stack)
- **`RUNBOOK.md`** — Template operations reference: scaffolding, validation, MLflow, contributing, release process
- **`LICENSE`** — MIT License (was referenced in README but file was missing)
- **`docker-compose.yml`** — Local dev stack: example fraud detection API + MLflow (one command: `docker compose up`)
- **`releases/`** — GitHub Release notes directory: `v1.0.0.md`, `v1.1.0.md`, `v1.2.0.md` ready to publish

#### DVC Templates (new)
- **`templates/service/dvc.yaml`** — DVC pipeline with 4 stages: validate → featurize → train → evaluate
- **`templates/service/.dvc/config`** — DVC remote configuration template for GCS/S3 storage

#### Infrastructure (from portfolio)
- **`templates/infra/docker-compose.mlflow.yml`** — Production-like MLflow stack: PostgreSQL + MinIO (S3-compatible) + MLflow server with health checks

#### Documentation Templates (new)
- **`templates/docs/CHECKLIST_RELEASE.md`** — Pre-deployment release checklist: quality gates, Docker, K8s, infra, monitoring, multi-cloud
- **`templates/docs/mkdocs.yml`** — MkDocs Material configuration template with navigation, plugins, theme, and docstring support

#### Integration Test Templates (new)
- **`templates/tests/integration/conftest.py`** — Service health wait fixture, auto-skip if unavailable
- **`templates/tests/integration/test_service_integration.py`** — Full service validation: health, predictions, SHAP, latency SLA, metrics, model info

#### Enterprise K8s & Security (new)
- **`templates/tests/infra/policies/kubernetes.rego`** — OPA/Conftest policies (ported from portfolio): non-root, resource limits, health probes, no :latest, namespace, HPA scaleDown + ML-specific D-01/D-02 enforcement
- **`templates/k8s/base/slo-prometheusrule.yaml`** — SLO/SLA definitions as PrometheusRule:
  - Availability SLI (99.5% non-5xx), Latency SLI (95% < 500ms)
  - Error budget recording rules (30-day window)
  - Multi-window burn rate alerts: P1 (14.4x/1h), P2 (6x/6h), P3 (budget < 25%)

#### Service Template Additions
- **`templates/service/codecov.yml`** — Codecov configuration template with per-service coverage flags

#### Example Improvements
- **`examples/minimal/Dockerfile`** — Docker image for the fraud detection example (used by root docker-compose.yml)

#### Architecture Decision Records
- **`docs/decisions/ADR-001-template-scope-boundaries.md`** — Documents why LLM/GenAI, multi-tenancy, Vault, feature store, data contracts, SOC2/GDPR, and audit logs are deferred. Includes revisit triggers and Engineering Calibration rationale.

#### CI: End-to-End Example Proof
- **`validate-templates.yml`** — New `example-e2e` job: install → train → verify artifacts → start server → run tests → drift check → verify quality gates. Proves the template works in CI, not just locally.

### Changed

#### README — Major Restructure
- **Concise hook at top** — Problem statement + differentiator in 3 lines, replacing verbose intro
- **Quick Navigation** — Replaced bullet list with 3-column table (Getting Started | Architecture | Development)
- **Quick Start** — Removed manual `sed -i` commands, now uses `new-service.sh` exclusively (fixes inconsistency with CHANGELOG v1.1.0)
- **"Try It in 5 Minutes"** — Added `make demo-minimal` one-liner and Docker Compose alternative
- **Repository Structure** — Updated tree with all new files: QUICK_START.md, RUNBOOK.md, LICENSE, docker-compose.yml, releases/, DVC, integration tests, SLO, mkdocs, checklist, MLflow compose
- **Templates Detail** — Added sections for DVC, integration tests, SLO, MLflow, release checklist, MkDocs
- **MkDocs section** — Now references `templates/docs/mkdocs.yml` template instead of just the portfolio
- Added links to QUICK_START.md and RUNBOOK.md at top of README

#### AGENTS.md
- Updated Template System tree with DVC, pyproject.toml, integration tests, SLO, MLflow compose, mkdocs, checklist

#### CLAUDE.md
- Updated File Structure with all new files and directories

#### `new-service.sh`
- Added DVC template copying step
- Added integration test template copying
- Added `data/validated/`, `data/processed/`, `reports/` to standard directories

#### Fairness Module
- **`templates/service/src/{service}/fairness.py`** — Added domain guidance: protected attribute selection by industry (Finance, Healthcare, Employment, GDPR), threshold customization, DIR limitations, proxy detection references

#### common_utils Distribution Strategy
- **`templates/common_utils/__init__.py`** — Documented the copy-in pattern, trade-offs, and PyPI graduation path (>5 services)

#### README: Claude Code & Cursor Rules
- **Agentic System section** — Added dedicated subsections for `.claude/rules/` (5 rules, `paths:` triggers) and `.cursor/rules/` (5 MDC rules, `globs:` triggers) with per-file tables

#### RUNBOOK: Secret Management
- **`RUNBOOK.md`** — Added Secret Management section: GCP/AWS Secrets Manager commands, anti-pattern D-10 guidance

### Notes

#### Claude-code-main Assessment
- Evaluated `/home/duque_om/projects/Claude-code-main` — TypeScript CLI rebuild of Claude Code, **no reusable content** for this MLOps template

#### Enterprise Gap Assessment
- **Already present**: RBAC (`rbac.yaml`), NetworkPolicy, Workload Identity/IRSA, SHAP `/predict?explain=true`, JSONFormatter, Prometheus/Grafana (9 panels), Pandera (3 validation points), Makefile x2, MLflow+DVC, Codecov badge (dynamic), `make demo-minimal`
- **Added in v1.3.0**: SLO/SLA PrometheusRule, ADR-001, e2e CI job, fairness domain guidance, Claude/Cursor docs
- **Deferred by design** (ADR-001): LLM/GenAI, multi-tenancy, HashiCorp Vault, feature store, SOC2/GDPR — documented with revisit triggers

---

## [1.2.0] - 2026-04-15

### Added

#### Developer Experience (root DX files)
- **`Makefile`** (root) — Contributor entry point with template-specific targets:
  - `make validate-templates` — lint + K8s validation in one command
  - `make lint-all` / `make format-all` — operate on all Python across `templates/` and `examples/`
  - `make demo-minimal` — run fraud detection example end-to-end (install → train → test → drift)
  - `make test-examples` — regression tests for examples/
  - `make new-service NAME=X SLUG=y` — scaffold wrapper around `new-service.sh`
- **`.pre-commit-config.yaml`** (root) — Contributor hooks: black, isort, flake8, `pre-commit-hooks` (yaml, merge conflicts, large files), gitleaks
- **`.gitleaks.toml`** (root) — Secret detection config shared between root and `templates/`, with allowlists for template placeholder tokens (`{ServiceName}`, `{service}`)

#### Multi-IDE Cursor Parity
- **`.cursor/rules/02-kubernetes.mdc`** — K8s rules: 1 worker, CPU HPA, init container pattern with code example
- **`.cursor/rules/03-python-serving.mdc`** — Serving rules: async inference, SHAP KernelExplainer, Prometheus metrics
- **`.cursor/rules/04-python-training.mdc`** — Training rules: pipeline sequence, quality gate table, required tests
- **`.cursor/rules/05-docker.mdc`** — Docker rules: multi-stage, non-root USER, HEALTHCHECK, no model artifacts

#### GitHub Releases
- **v1.0.0** — tag pushed to remote (was created locally, not published)
- **v1.1.0** — annotated tag created and pushed with full release notes

### Changed

#### CI Template (`templates/cicd/ci.yml`)
- Added **Python 3.12 matrix** — test job now runs `["3.11", "3.12"]` in parallel
- Added **Codecov integration** — uploads `coverage.xml` on `3.11` run via `codecov/codecov-action@v4`
- Coverage report format changed from `term-missing` only → `xml` + `term-missing`

#### README
- Added **Release badge** with dynamic version from GitHub Releases
- Updated **Python badge** to `3.11 | 3.12`
- Added **Codecov badge**
- Updated `.cursor/rules/` entry to reflect 5 MDC rules (was 1)
- Updated repo tree with root DX files (`Makefile`, `.pre-commit-config.yaml`, `.gitleaks.toml`)

#### AGENTS.md / CLAUDE.md / .cursor/rules/
- Updated Multi-IDE Support section in AGENTS.md to show all 5 cursor rules

---

## [1.1.0] - 2026-04-15

### Added

#### Working Example (`examples/minimal/`)
- **Fraud detection service** — fully functional end-to-end demo (train → serve → predict → test → drift)
- `train.py` — synthetic data generation, Pandera validation, sklearn pipeline, quality gates
- `serve.py` — FastAPI with async inference (ThreadPoolExecutor), SHAP KernelExplainer, Prometheus metrics
- `test_service.py` — regression tests: data leakage, SHAP consistency, latency SLA, fairness DIR
- `drift_check.py` — PSI drift detection with quantile bins and exit codes (0/1/2)

#### Scaffolding
- **`new-service.sh`** — automated scaffolding script: copies templates, replaces placeholders ({ServiceName}, {service}, {SERVICE}), creates directory structure

#### Monitoring
- **`alertmanager-rules.yaml`** — production AlertManager rules with P1–P4 severity:
  - Service down + error rate spike (P1)
  - Inference latency degradation (P2)
  - **Drift heartbeat missing** (P2) — fires if CronJob hasn't run in 48h
  - PSI drift alert/warning (P3)
  - CPU approaching limit + pod restarts (P4)

### Changed

#### drift_detection.py — Production CronJob Integration
- Added **exit codes** (0=ok, 1=warning, 2=alert) for K8s CronJob integration
- Added **GitHub Issue creation** on alert-level drift via GitHub API
- Added **reference data update** with timestamped backups
- Added proper `main()` function with `sys.exit()` for clean process control

#### test_explainer.py — Self-Contained SHAP Tests
- Replaced stub tests with **runnable, self-contained regression tests**
- Tests use synthetic data + simple pipeline (no service dependency)
- Covers: all-zero SHAP detection, consistency property, original feature space, background representativeness, latency SLA

#### Kustomize Structure
- Moved manifests to `k8s/base/` (standard Kustomize pattern)
- Fixed `commonLabels` (deprecated) → `labels` with pairs syntax
- Fixed `patchesStrategicMerge` (deprecated) → `patches` in overlays
- Replaced `kubeval` (abandoned) with `kubeconform` in CI

#### README
- Added **"Try It in 5 Minutes"** section with copy-paste commands
- Added **"What's Different From Other Templates"** comparison table
- Updated Quick Start to use `new-service.sh` scaffolding script
- Updated repo structure tree with all new files

#### Agentic System Improvements
- **Split `04-python-ml.md`** into `04a-python-serving.md` (app/) and `04b-python-training.md` (training/) — reduces unnecessary context loading
- **Added `10-examples.md`** — prevents production rules from firing in `examples/` directory
- **Added `.claude/rules/`** — 5 context-aware rules with `paths:` frontmatter for Claude Code IDE
- **AGENTS.md** — added Session Initialization Protocol, How to Invoke Skills, Multi-IDE Support sections
- **01-mlops-conventions.md** — slimmed from 75 to 43 lines, references `AGENTS.md` for detail
- **CLAUDE.md** — comprehensive rewrite: session protocol, full anti-pattern table, key commands
- **`.cursor/rules/`** — enhanced with session protocol, full D-01→D-12 table, key commands
- **Skill `new-service`** — now invokes `new-service.sh`, verifies zero remaining placeholders
- **Skill `debug-ml-inference`** — added D-01→D-12 anti-pattern checklist as Step 1
- **Skill `drift-detection`** — added PSI interpretation table with exit codes, special cases for time series/NLP/categorical
- **Workflow `/new-service`** — uses `new-service.sh` with manual fallback
- **Workflow `/incident`** — added Step 0: severity classification decision tree (P1–P4)
- **Workflow `/retrain`** — added explicit quality gate table with typical thresholds and verification script
- **Workflow `/cost-review`** — added PromQL queries for CPU/memory/throughput/HPA utilization

### Fixed
- black formatting: reformatted `test_explainer.py` and `drift_detection.py`
- flake8 F401: removed unused imports across 7 files
- flake8 E501/F841: fixed long lines and unused variable in cli.py
- Kustomize cycle error: restructured to standard `base/` + `overlays/` layout

---

## [1.0.0] - 2026-04-15

### Added

#### Agentic System
- **AGENTS.md** - Root-level agent architecture with 3-layer design (Orchestrator, 11 Specialist Agents, 4 Maintenance Agents), 12 anti-pattern detectors (D-01 to D-12), and Engineering Calibration Principle
- **10 context-aware rules** (`.windsurf/rules/`) - Behavioral constraints for K8s, Terraform, Python serving/training (split), CI/CD, Docker, docs, data validation, monitoring, examples
- **8 operational skills** (`.windsurf/skills/`) - Structured frontmatter with `allowed-tools`, `when_to_use`, `argument-hint`, per-step `Success criteria`
- **8 slash-command workflows** (`.windsurf/workflows/`) - `/release`, `/retrain`, `/load-test`, `/new-adr`, `/incident`, `/drift-check`, `/new-service`, `/cost-review`

#### Service Template (`templates/service/`)
- FastAPI app with async inference via ThreadPoolExecutor
- SHAP KernelExplainer integration with consistency checks
- Prometheus metrics (counter, histogram, summary)
- Pandera DataFrameModel for training, API, and drift validation
- Optuna hyperparameter tuning with configurable trials
- Quality gates (primary metric, secondary metric, fairness DIR >= 0.80)
- MLflow experiment tracking and model registry integration
- Comprehensive pytest tests (leakage, quality gates, API, SHAP, latency SLA)
- Locust load test template (100 concurrent users, < 1% error rate)
- Multi-stage Dockerfile with non-root USER and HEALTHCHECK

#### Common Utils (`templates/common_utils/`)
- `seed.py` - Reproducibility across Python, NumPy, PyTorch, TensorFlow
- `logging.py` - JSON formatter (production K8s) + colored human-readable (dev)
- `model_persistence.py` - joblib save/load with SHA256 integrity validation
- `telemetry.py` - OpenTelemetry tracing with graceful no-op fallback

#### Kubernetes (`templates/k8s/`)
- Deployment with init container for model download from GCS/S3
- CPU-only HPA (never memory for ML pods)
- Kustomize base + GCP-production and AWS-production overlays
- Argo Rollouts canary deployment with Prometheus-based AnalysisTemplate
- ServiceAccount with Workload Identity (GCP) and IRSA (AWS) annotations

#### Infrastructure (`templates/infra/`)
- Terraform GCP: GKE cluster, Workload Identity, GCS buckets, Artifact Registry
- Terraform AWS: EKS cluster, OIDC for IRSA, managed node group, IAM roles

#### CI/CD (`templates/cicd/`)
- CI: flake8 + black + isort + mypy, pytest (90% coverage), Docker build + Trivy
- Infrastructure CI: terraform validate + tfsec + Checkov + kubeval
- Deploy GCP/AWS: tag-triggered with cluster verification and smoke tests
- Drift Detection: daily scheduled + manual trigger, auto-creates GitHub issue
- Retraining: manual trigger with data validation, quality gates, artifact upload

#### Scripts (`templates/scripts/`)
- `deploy.sh` - Build, push, deploy with kubectl context verification and tag immutability
- `promote_model.sh` - Quality gates (metric, fairness, leakage, integrity) before promotion
- `health_check.sh` - Pod status + /health and /model/info endpoint checks

#### Developer Experience
- `docker-compose.demo.yml` - Demo stack with MLflow + Pushgateway + optional monitoring
- `Makefile` - Standard targets: train, test, serve, build, deploy, health-check, demo
- `.pre-commit-config.yaml` - black, isort, flake8, mypy, bandit, gitleaks
- `.gitleaks.toml` - Secret detection configuration
- `.env.example` - Environment variable documentation

#### Documentation Templates
- ADR template with Context, Options, Decision, Rationale, Consequences, Revisit When
- Runbook template with P1-P4 severity procedures
- Service README template with measured data slots
- Model card template for ML transparency
- Dependency analysis template for conflict documentation

#### Monitoring Templates
- Prometheus alerts: error rate, service down, drift heartbeat, latency, resources
- Grafana dashboard: request rate, latency percentiles, PSI scores, HPA, CPU/memory

#### Open Source Maturity
- `SECURITY.md` - Vulnerability reporting policy and security measures
- `CONTRIBUTING.md` - Contribution guidelines with Engineering Calibration awareness
- `CODE_OF_CONDUCT.md` - Contributor Covenant v2.0
- `.github/ISSUE_TEMPLATE/` - Bug report and feature request templates
- `.github/pull_request_template.md` - PR checklist with anti-pattern verification
- `.github/dependabot.yml` - Automated dependency updates
- `.gitattributes` - Git LFS for model artifacts, line ending normalization
- CI workflow `validate-templates.yml` - Validates K8s, Terraform, and Python templates

---

*This template was extracted from [ML-MLOps-Portfolio](https://github.com/DuqueOM/ML-MLOps-Portfolio), a production portfolio with 3 live ML services.*
