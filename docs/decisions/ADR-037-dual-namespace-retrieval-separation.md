# ADR-037 — Dual-Namespace Retrieval Separation (Operational Memory vs. Pedagogical RAG)

- **Status**: Accepted
- **Date**: 2026-07-01
- **Deciders**: Template maintainer (`@DuqueOM`)
- **Related**: ADR-018 (operational memory plane — the corpus this ADR
  explicitly excludes from pedagogy), ADR-028 (LLM-assist integration, Lane 2
  family), agent-local ADR-008 (retrieval/tier caller isolation),
  `docs/audit/ACTION_PLAN_LLM_AGENT.md` §L-2/§L-2b

## Context

`ACTION_PLAN_LLM_AGENT.md`'s maintenance plane already plans an "L-2 Memory
plane" lane: BM25 retrieval over the template's own **operational** evidence
(`ops/audit.jsonl`, `docs/incidents/`, `VALIDATION_LOG.md`, `releases/*.md`,
drift reports), summarized by agent-local's E4B tier with mandatory
`file:line` citations (§L-2). This lane is governed by ADR-018 (Operational
Memory Plane), which scopes it tightly: structured operational evidence only,
sensitivity-tiered, redacted at ingest, explicitly **not** a general document
indexer ("indexing every doc is out of scope").

A second, distinct need has emerged: newcomers and template adopters need a
way to ask conceptual questions about the template itself — "why does D-01
forbid multiple uvicorn workers," "what does ADR-021's DIR floor mean," "how
does the SHAP `KernelExplainer` wrapper work" — answered from the template's
own **teaching** corpus (long-form onboarding chapters, ADRs read as
pedagogy, `docs/TUTORIAL.md`, `docs/CCDS_MAPPING.md`, glossary), not its
operational history. This is "RAG for pedagogy," and the natural place to run
it is on agent-local's already-planned tier stack — the same mechanism
`ACTION_PLAN_LLM_AGENT.md`'s L-2 already established for operational
retrieval. An adopter may point this at their own internal onboarding/wiki
corpus instead of (or in addition to) the template's own docs — the pattern
is deliberately corpus-agnostic.

The risk: without an explicit boundary, "reuse the memory-plane mechanism for
pedagogy too" is one PR away from becoming "one BM25 index over `ops/` +
`docs/` + the adopter's onboarding corpus," which would:

- Let a pedagogical Q&A surface (plausibly more broadly exposed later — e.g. a
  docs-site widget) surface operational specifics never meant for that
  audience (exact fraud/rate-limit thresholds, incident specifics, internal
  runbook detail) — an operational-to-pedagogical leak.
- Dilute the operational index's precision with teaching prose, degrading the
  L-2 lane's own recall gate (ADR-018 Phase 3's acceptance criterion;
  `ACTION_PLAN_LLM_AGENT.md` §L-2 step 3) — contamination in the other
  direction.
- Put pedagogical content inside ADR-018's Operational Memory Plane at all,
  which is a scope violation of that ADR: its `MemoryUnit` schema has no
  `memory_type` for documentation/teaching content, and its threat model
  (sensitivity tiers, redaction, tenancy) exists to protect operational
  secrets that teaching content does not have and should not need.

This ADR closes that gap before it opens, by making the separation a
structural property instead of a convention.

## Decision

Treat "operational memory" and "pedagogical RAG" as **siblings that share a
serving mechanism and share nothing else**: two disjoint scripts, two disjoint
corpora, two disjoint index objects, one shared stateless tier endpoint
(agent-local ADR-008 establishes why sharing the tier alone is safe).

### 1. Two scripts, never one script with a mode flag

- `scripts/memory_query.py` (existing name, per `ACTION_PLAN_LLM_AGENT.md`
  §L-2) — **operational namespace only**. Hard-coded corpus-root allow-list:
  `ops/audit.jsonl`, `docs/incidents/`, `VALIDATION_LOG.md`, `releases/*.md`,
  drift reports. Consumed exclusively by maintenance-plane lanes (L-1 CI
  self-healing, L-2 itself, L-3 triage, L-4 docs-drift) — never by anything
  customer-facing or publicly exposed.
- `scripts/pedagogy_query.py` (new) — **pedagogical namespace only**.
  Hard-coded corpus-root allow-list: `docs/decisions/ADR-*.md` (prose only —
  context/decision/consequences read as teaching material, never as an
  operational log), `docs/TUTORIAL.md`, `docs/CCDS_MAPPING.md`, glossary
  files, plus — optionally, per adopter — their own long-form onboarding/wiki
  corpus root, added to the allow-list explicitly rather than discovered.
  Consumed by a documentation/onboarding assistant surface (CLI first; a
  docs-site widget is a possible later consumer) — explicitly never wired
  into L-1..L-4 or into agent-local's customer-facing `tienda` use-case.

Two scripts, not a `--namespace` flag on one, because a flag can default
wrong or be forgotten at a call site; two separate entry points cannot be
silently misrouted — the caller has to name the wrong script on purpose. This
mirrors the plan's own precedent for "when scope diverges, split the file,
don't overload it with a mode" (`ACTION_PLAN_ADR028.md` was absorbed into
`ACTION_PLAN_LLM_AGENT.md` rather than mode-flagged into it).

### 2. Disjoint corpus roots, asserted, not just documented

A CI-enforced check (`tests/test_retrieval_namespace_isolation.py`, new — same
family as the `check_*_drift.py` deterministic gates) asserts, at minimum:

- The operational allow-list and the pedagogical allow-list have empty path
  intersection.
- Neither allow-list resolves (via glob) to any file under the other's
  exclusive roots (`ops/`, `docs/incidents/`, `VALIDATION_LOG.md`,
  `releases/` excluded from pedagogy; any adopter-provided pedagogical
  corpus root excluded from operational).
- Both allow-lists are hard-coded module constants in their respective
  scripts — never a request parameter, config value, or environment variable
  that a caller could override to point either script at the other's corpus.

### 3. Separate index objects (never a shared corpus/vector store)

Each script builds and owns its own `BM25Index`-equivalent in-process — no
shared index object, no shared file handle, no shared database table between
the two namespaces. This is the same principle agent-local's own
`core/retrieval.py` already applies at the use-case boundary (one `BM25Index`
per use-case); here it is applied at the script boundary, since neither
namespace lives inside agent-local's process (agent-local ADR-008).

### 4. Shared-nothing except the stateless tier endpoint

Both scripts may call the same agent-local E4B endpoint
(`http://127.0.0.1:8091/v1/chat/completions`) for summarization. This is the
one deliberate exception, and it is safe specifically because the tier is
stateless per request (agent-local ADR-008) — it retains no corpus, no
memory, no cross-request linkage that could leak retrieval context from one
namespace into the other's answer. Sharing the tier is a hardware-cost
decision (one resident model, not two), not a separation compromise.

### 5. Mandatory, namespace-scoped citation validation (the runtime backstop)

Both namespaces already require "a response without a citation is discarded"
(§L-2). This ADR extends it: **a citation must resolve to a path inside its
own namespace's allow-list, or the answer is discarded and an integrity event
is logged.** A pedagogical answer citing `ops/audit.jsonl:142` is not just
wrong, it is a defect — fail closed, do not serve it, log it loudly. This
turns "we designed it to be separate" into "we verify at query time that it
stayed separate," which is the falsifiable form of the guarantee this ADR
exists to make.

### 6. Namespace-tagged telemetry

Every query from either script emits a log line carrying
`{"namespace": "operational"|"pedagogical", "query", "citations", "trace_id",
...}` (the same OTel-aligned naming convention agent-local's own telemetry
already uses, agent-local ADR-005). This is what makes the separation
auditable after the fact, not just correct by construction at write time:
`grep namespace ops/*.jsonl` should always partition cleanly.

### 7. Content-governance rule (the data-level firewall, not just the code one)

- The pedagogical corpus curation process (whoever/whatever selects which
  onboarding chapters and ADR sections get indexed) MUST NEVER pull from
  `ops/`, `VALIDATION_LOG.md`, `releases/`, or `docs/incidents/`.
- The operational corpus MUST NEVER pull from the pedagogical corpus's
  teaching prose.
- The ban is symmetric; the risk is not. Operational-into-pedagogical is the
  higher-severity direction (pedagogical content may eventually reach a
  broader, more public audience — e.g. a docs-site widget — where an
  operational leak becomes a disclosure, not just an internal mix-up). The
  controls above are ordered accordingly: the citation-path validator (§5) is
  the hard backstop specifically because curation-time discipline (this
  section) is a process control, and process controls fail silently.

## Explicit non-goal: this is not a Phase of ADR-018

The Operational Memory Plane (ADR-018) is scoped to structured operational
evidence with a real threat model (leaked CI tokens, secret redaction,
sensitivity tiers, tenancy). Pedagogical/teaching content has none of that
risk profile and none of that schema (`MemoryUnit.memory_type` has no
"documentation" value, deliberately — ADR-018 "indexing every doc is out of
scope"). The pedagogical namespace is therefore **not** a phase, addendum, or
extension of ADR-018; it is this ADR's own, much lighter, BM25-first
mechanism, kept structurally apart from ADR-018's eventual Postgres+pgvector
path (Phase 3) exactly as it is kept apart from ADR-018's Phase 1/2
file-based precursor. If ADR-018 ever grows a `memory_type` that could
plausibly include documentation, that is a decision for ADR-018 to make
explicitly — not a default this ADR creates by proximity.

## Consequences

**Positive**

- The pedagogical RAG idea becomes buildable without ever risking the
  operational memory-plane's threat model or diluting its recall.
- The separation is falsifiable (citation-path check, CI
  allow-list-disjointness test, namespace-tagged telemetry) rather than a
  promise living only in a docstring.
- Reuses agent-local's existing stateless-tier property (ADR-008) instead of
  paying for a second resident model — a real hardware-budget win on the
  fixed 8GB VRAM ceiling (`ACTION_PLAN_LLM_AGENT.md` §0).
- Gives the frontier-comparison "pedagogy/onboarding" gap (`README.md` "How
  this compares" table) a concrete, safely-scoped answer.

**Negative / costs**

- Two scripts and two corpus-curation processes to maintain instead of one.
- A new CI check (`test_retrieval_namespace_isolation.py`) to keep green.
- `scripts/pedagogy_query.py` and its corpus curation are net-new work, gated
  behind the same "P2 INTEGRATION" timeline as `scripts/memory_query.py` —
  neither script exists yet as of this ADR; both are specified, not shipped.

## Acceptance gate (before either script ships)

- `tests/test_retrieval_namespace_isolation.py` green: disjoint allow-lists,
  no cross-resolution.
- A citation-path validator unit test: a citation outside the caller's
  namespace allow-list is rejected and logged, never served.
- Both scripts' telemetry lines carry `namespace` and validate against a
  closed two-value enum.
- The pedagogical corpus and the agent-local platform docs describe the
  separation for a human reader, not only in code — see Related.

## Revisit triggers

- A third retrieval namespace is proposed (e.g. a customer-support knowledge
  base) → this ADR's pattern (disjoint script, disjoint corpus, shared
  stateless tier, namespace-tagged telemetry) is the template to replicate,
  not a two-namespace special case to extend ad hoc.
- The citation-path validator ever needs to be relaxed for a namespace (e.g.
  to let a pedagogical answer cross-link to an operational runbook on a
  maintainer-only surface) → that is a new, explicit, narrower ADR — never a
  silent loosening of this one.
- agent-local grows an in-process `usecases/pedagogy/` use-case instead of the
  external-script approach → reconcile with agent-local ADR-008's own revisit
  triggers; the corpus-root and citation-validation discipline specified here
  still applies, just relocated.

## Related

- ADR-018 — Operational Memory Plane (the corpus and threat model this ADR
  does not extend)
- ADR-028 — LLM-Assist Integration (Lane 2 family; this ADR's L-2b sibling
  lane)
- agent-local ADR-008 — Retrieval/tier caller isolation (the stateless-tier
  justification this ADR relies on)
- `docs/audit/ACTION_PLAN_LLM_AGENT.md` §L-2 / §L-2b — the executable plan
  this ADR canonicalizes
