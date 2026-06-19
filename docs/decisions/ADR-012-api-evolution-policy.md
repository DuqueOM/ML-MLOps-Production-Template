# ADR-012 — API Evolution Policy (reserved number, withdrawn)

- **Status**: Withdrawn (number retired, never a standalone decision)
- **Date**: reserved 2026 · formally tombstoned 2026-06-10 (`v0.18.0`)
- **Deciders**: Template maintainer (`@DuqueOM`)

## Why this file exists

ADR numbers are **immutable identifiers** — referenced from commits, PRs,
code comments, runbooks and other ADRs. They are never renumbered and never
recycled. When a planned ADR is dropped, the professional record is a
**tombstone**, not a silent gap: a reader (or interviewer) who notices `012`
missing should find a one-paragraph explanation here, not a mystery that
looks like an oversight.

## What ADR-012 was reserved for

Number 012 was reserved early for a standalone **"API evolution policy"** ADR
(versioning, breaking-change discipline, deprecation). That dedicated ADR was
**never written**, because the policy was instead encoded where it is actually
enforced:

- **`agentic/rules/04a-python-serving.md` / `rules/14-api-contracts.md`** — the
  contract rules: `openapi.snapshot.json`, `refresh_contract.py`, mandatory
  major bump + `/v2/` mount on field rename, no validator narrowing without a
  major bump, CHANGELOG `### API Contract` section.
- **Anti-pattern `D-28`** (AGENTS.md) — API contract semver enforcement.

Since the concern is fully covered by an executable rule + a tracked
anti-pattern, a separate ADR would only duplicate them. The number is
therefore **retired**, not reassigned.

## Consequences

- The numbering runs `ADR-001 … ADR-028` with `012` as a documented,
  intentional gap. **27 active decisions across 28 numbered slots.**
- This number will **not** be reused for any future decision; new ADRs
  continue from the highest number.

## Related

- `agentic/rules/14-api-contracts.md` — where the policy lives.
- AGENTS.md anti-pattern `D-28` — API contract semver.
- ADR-014 / ADR-028 — neighbouring accepted decisions.
