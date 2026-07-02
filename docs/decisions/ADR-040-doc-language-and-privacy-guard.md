# ADR-040 — Documentation Language and Private-Reference Guard

- **Status**: Accepted
- **Date**: 2026-07-02
- **Deciders**: Template maintainer (`@DuqueOM`)
- **Supersedes / amends**: none. Extends ADR-031 (Documentation Coherence
  System) with a seventh check.
- **Superseded by**: none
- **Related artifacts**:
  - `scripts/check_doc_coherence.py` — check C7 (`check_doc_language_and_privacy`).
  - `AGENTS.md` — anti-pattern D-37.
  - `agentic/rules/16-doc-coherence.md` — updated check enumeration.
  - `docs/decisions/ADR-037-dual-namespace-retrieval-separation.md`,
    `ADR-028-llm-assist-integration.md` — re-generalized to remove a
    private-repo-specific example (see Consequences).

## 1. Context

An interactive planning session produces documents in whatever language and
level of specificity is fastest for the human in the loop — that is a
feature during planning, not a defect. The failure mode is that some of that
interactive-session material was committed as-is to `docs/audit/` in this
**public** repo without a translation/genericization pass before it
shipped: four documents ended up fully in Spanish, and a private, personal
companion repo ended up named by its slug — in one case as a live clickable
URL pointing at it — across six files in this repo and one in the sibling
`agent-local` repo. That URL 404s for any outside reader since the target
repo is private; this ADR does not repeat the name or the URL for the same
reason C7 (§2) now blocks it everywhere else. Two ADRs
(ADR-037, ADR-028) had gone further: they specified a design ("L-2b
pedagogical RAG") using that private repo as the literal, hard-coded corpus
example, which is also a scoping bug independent of the privacy question —
an ADR for a public, reusable template should describe a pattern any
adopter can apply to *their own* onboarding corpus, not one over-fit to the
author's personal setup.

Neither leak exposed real content — the private repo stayed private, and
the URL 404s for any outside reader — but both are exactly the kind of
"looks unprofessional to anyone who checks closely" defect that undermines
an enterprise-positioning claim the moment someone reads past the surface.
The template's own README states the documentation should read as English,
enterprise-consistent prose throughout; a Spanish planning document
sitting in `docs/audit/` next to English ADRs breaks that claim in the
most visible possible way — a reader doesn't need to dig, they just need to
open one file.

The maintainer asked directly: shouldn't the documentation-coherence system
that already exists (ADR-031, rule 16) have caught this? It should have,
and now does.

## 2. Decision

Add a seventh deterministic check to `scripts/check_doc_coherence.py`
(the existing rule-16/ADR-031 gate, not a new script — this is exactly the
kind of drift that gate already exists to catch, it simply hadn't been
taught to look for language or private-repo references yet):

**C7 — `check_doc_language_and_privacy`**: scans every git-tracked file
under `docs/**/*.md` plus every root-level `*.md` (the repo's actual prose
surface — `agentic/rules/skills/workflows/` and their generated adapter
mirrors are deliberately excluded, see §3) for two independent violations:

1. **Non-English prose** — a curated, whole-word, case-insensitive list of
   Spanish markers (common connectors and `-ción`/`-sión`-suffixed nouns —
   see `_SPANISH_MARKERS` in `scripts/check_doc_coherence.py` for the exact
   list) that essentially never appear in legitimate English technical
   writing.
2. **A forbidden private-repo reference** — a small, extensible denylist
   of repo names that must never be named in this public repo's
   documentation, seeded with the one this ADR describes in §1
   (`_FORBIDDEN_REPO_REFS` in `scripts/check_doc_coherence.py`).

Both failures print a `[C7 doc-language-privacy]` finding with the offending
file path, exactly like the other six checks. This is codified as
anti-pattern **D-37** in `AGENTS.md`.

The two ADRs that hard-coded the private repo as a design example were
re-generalized: "RAG over the author's private companion repo" became "RAG
over the adopter's own long-form onboarding corpus" — a strictly more
reusable design for a public template, not merely a redaction.

## 3. Why a word list, not a character scan

An early draft matched *any* accented character (`á é í ó ú ñ ¿ ¡`). This
repo's own canonical `agentic/` body legitimately cites accented proper
nouns — "Diátaxis" (the documentation-taxonomy framework referenced in rule
16) and "Cramér's V" (a statistics measure referenced in the `eda-analysis`
skill) — so a character scan would have permanently flagged its own
canonical rules as a violation. The check instead matches a curated list of
whole Spanish *words*, and even there the accent must be present exactly:
several common Spanish `-sión`-suffixed nouns spell **exactly** their
English `-sion` counterpart once the accent is stripped (unlike the
`-ción`/`-tion` pattern, which differs in spelling even after the accent is
removed, because English inserts a "t" Spanish never had). An early
implementation made the accent optional per letter and, as a direct
consequence, flagged one of those English words — a word that appears in
nearly every ADR in this repo — as a Spanish violation. That bug was
caught in local testing before
this shipped, not left for CI to teach the hard way.

The scan is also scoped to `docs/**/*.md` + root `*.md` specifically, and
resolved via `git ls-files` rather than a filesystem walk, for two reasons:
it keeps `agentic/`'s legitimate proper nouns out of scope entirely (rather
than allowlisting them one at a time, which does not scale), and it can
never accidentally scan a gitignored, intentionally-private local file
(this repo has one: `AUDIOVISUAL_CONTENT.md`, a personal, Spanish-language,
never-committed production guide — see its own header for why that is
correct and not a second instance of this defect).

## 4. What this check does NOT do

- It does not translate anything — it only reports. Fixing a finding is a
  normal edit (or, for a large document, a delegated translation pass);
  there is no auto-fix mode, the same way C1–C6 do not auto-fix.
- It does not lint prose *style* or grammar (a Vale-style lane is a future,
  separately-numbered check per ADR-031's Revisit When — this check is
  binary: English-only word list absent, forbidden reference absent).
- It does not scan code comments, YAML, or non-`.md` files. A future
  extension could, but the actual incident was entirely markdown prose;
  scope grows when a real gap is found, not speculatively.

## 5. Consequences

**Positive**

- The exact failure mode that triggered this ADR — Spanish prose and a
  private-repo reference reaching a public repo's `docs/` — now fails CI
  deterministically instead of depending on a human happening to notice.
- Re-generalizing ADR-037/ADR-028's pedagogical-RAG design away from a
  hard-coded private repo makes that design *more* correct for a public,
  reusable template, not just more private.
- Consistent with the existing ADR-031 architecture: one more check
  function in the same file, same `list[str]` contract, same
  `[doc-coherence]` print prefix, same vendoring story into
  `templates/service/`.

**Negative / costs**

- The Spanish-marker word list requires occasional maintenance (a
  legitimate future addition to `docs/` prose could theoretically collide
  with a listed word; the accent-required design in §3 makes this unlikely
  but not impossible).
- Scanning every `docs/**/*.md` file on every CI run adds a small,
  constant-time cost to an already-cheap gate (regex over markdown text,
  no external calls).

## 6. Revisit triggers

- A second private/personal companion repo is ever referenced from either
  public repo → add its name to `_FORBIDDEN_REPO_REFS` (the tuple is
  deliberately a simple, append-only list, not a config file, until there
  are enough entries to justify one).
- The word-list approach produces a real false positive on legitimate
  English prose → prefer narrowing the specific word (e.g. requiring more
  surrounding context) over disabling the check; a silent regression here
  is exactly the failure this ADR closes.
- Prose-level style/grammar consistency becomes a recurring problem →
  a Vale lane, numbered check **C8** per ADR-031's Revisit When (not C7 —
  that number is now taken).

## 7. Related

- ADR-031 — Documentation Coherence System (the gate this ADR extends).
- ADR-037 — Dual-Namespace Retrieval Separation (re-generalized as part of
  this remediation).
- ADR-028 — LLM-Assist Integration (same re-generalization, Lane 2b).
- `AGENTS.md` D-37.
