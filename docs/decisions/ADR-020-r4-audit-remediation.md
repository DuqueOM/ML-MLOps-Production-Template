# ADR-020: External Audit R4 — Remediation Plan (master)

- **Status:** Accepted
- **Date:** 2026-04-29
- **Supersedes:** none (extends ADR-016 closure)
- **Related:** ADR-014 (gap remediation), ADR-015 (productization roadmap), ADR-016 (R2 remediation), ADR-018 (Memory Plane), ADR-019 (CI Self-Healing)
- **Authors:** Staff/Lead, AI staff engineer

## Context

A fourth-round external audit (R4), conducted post-`v1.12.0` (which closed R3),
surfaced 20 findings — 5 Critical, 7 High, 6 Medium, 3 Low — spanning credibility,
release discipline, execution evidence, runtime implementation gaps, and
governance evidence.

The R4 audit's central thesis is sharp and correct:

> The template's intellectual core is mature. The gap is between
> intellectual maturity and **verified-execution maturity**.

R3 found bugs of the form "the YAML looks right; it was never executed against
reality." R4 generalizes that finding into a release-discipline diagnosis and
asks for two structural changes: **(1) every component change requires execution
evidence**, and **(2) capabilities that are not implemented must say so on the
README at the section heading, not in a footnote.**

Beyond the runtime credibility gaps, R4 also asks the project to ship the runtime
Phase 1 of ADR-018 (Operational Memory Plane) and ADR-019 (Agentic CI
Self-Healing), which until now had been deferred behind explicit Phase 0 status.

## Decision

Adopt a **four-sprint plan** governed by this ADR with the following structure:

| Sprint | Focus | Mode mix |
|--------|-------|----------|
| 0 (days 1–7) | Credibility — close all 5 Criticals via documentation + policy + assertion tests; **no cloud runtime change** | AUTO + 1 CONSULT |
| 1 (days 8–14) | Execution hardening — per-PR smoke lane, PR-evidence policy, red-team log, ADR-019 Phase 1 read-only | AUTO + CONSULT + 2 STOP-delegated |
| 2 (days 15–21) | Memory Plane Phase 1 contracts + Mediums | AUTO + 1 CONSULT |
| 3 (days 22–28) | Lows + closure + Phase-1→Phase-2 gate | AUTO + CONSULT |

The full per-finding plan with severity scoring, owners, files touched, and
acceptance criteria lives in
[`docs/audit/ACTION_PLAN_R4.md`](../audit/ACTION_PLAN_R4.md). This ADR ratifies
the structure; the plan document is the operational artifact.

### Hard rules ratified by this ADR

1. **No retroactive re-tagging.** Existing `v1.x` tags remain immutable. Versioning
   discipline is reset forward via `docs/RELEASING.md`. The next breaking
   change in scaffolded output goes to `v2.0.0`, not `v1.13.0`.
2. **Phase-0 banners are non-negotiable.** Any capability that ships policy + tests
   but no runtime MUST carry a Phase-0 banner at the README section heading.
   Removing the banner without the corresponding ADR transitioning Phase
   status is blocked by `tests/test_phase0_disclosure.py`.
3. **Anticipated model names ≠ verified model names.** The README's model
   routing section labels names as cadence-anticipated until vendor verification
   is recorded with a `verified_at` field that links to a dashboard reference.
4. **Execution evidence is mandatory for new components.** `pr-evidence-check.yml`
   (Sprint 1) blocks PRs that introduce new template components without
   schema/contract test, real execution output, and CI run link.
5. **STOP-delegated actions never run inside the agent loop.** Three R4 items
   (gitleaks history scan, Kyverno admission validation against a real cluster,
   any prod IaC mutation) are documented but only Platform / Security can
   execute them, with audit trail.

## Consequences

### Positive

- The "production-ready" claim becomes defensible because every dimension is
  either backed by a `VALIDATION_LOG.md` entry, a contract test, or a STOP-mode
  delegation note. No more silent gaps.
- The Phase-0 / Phase-1 distinction is enforced by tests, not prose. Adopters
  who skim the README cannot mistakenly believe the runtime exists.
- The release discipline shift toward `v2.0.0` for the next breaking change
  recovers semver credibility without requiring a destructive re-tag.

### Negative / cost

- Sprint 1's smoke lane and PR-evidence workflow add CI minutes per PR. Bounded
  to ~6 minutes overhead based on sister-project measurements. Acceptable.
- Phase 1 runtime for ADR-019 ships in shadow only — no value extracted from
  it for ~14 days while data accumulates. This is the correct phasing per
  ADR-019 §"Why split policy from runtime"; we accept the calendar cost.
- Three STOP-delegated items (S1-3, S1-4) cannot close inside this ADR's
  4-sprint window unless Platform / Security capacity is allocated. Their
  evidence may land in `VALIDATION_LOG.md` after the calendar deadline.
  This is honest scope, not a hidden gap.

### Neutral

- ADR-018 and ADR-019 transition from "Phase 0 — runtime deferred" to
  "Phase 1 in shadow" — the deferral is no longer total.

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC-1 | All 5 Criticals (C1–C5) closed in Sprint 0 PR `audit-r4/sprint-0-credibility` |
| AC-2 | `tests/test_readme_model_names.py` and `tests/test_phase0_disclosure.py` green on `main` |
| AC-3 | `docs/RELEASING.md`, `MIGRATION.md`, `VALIDATION_LOG.md` exist and are linked from `README.md` and `CHANGELOG.md` |
| AC-4 | Sprint 1 ships smoke lane + PR-evidence policy + red-team log + ADR-019 Phase 1 read-only |
| AC-5 | Sprint 2 ships ADR-018 Phase 1 contracts (`memory_types.py`, `memory_redaction.py`) with green tests, plus Compliance gap analysis in `ADOPTION.md` |
| AC-6 | Phase-1 → Phase-2 transition gate decision is documented as a CONSULT operation with shadow-mode evidence linked |
| AC-7 | This ADR is updated at sprint boundaries with a `## Progress log` section listing closed findings and evidence |

## Revisit triggers

- A Critical finding from R4 is found to be only partially closed → re-open this ADR, escalate severity.
- ADR-019 Phase 1 shadow data shows classifier precision below the threshold defined at S1-6 acceptance → Phase 2 deferred indefinitely; this ADR documents the pause.
- A new external audit (R5) lands during Sprint 0–3 → fold its findings into this ADR's progress log rather than opening a parallel ADR; sequence by severity.

## Progress log

_To be updated at the close of each sprint with closed-finding evidence._

- **Sprint 0 (in progress, opened 2026-04-29)**: branch `audit-r4/sprint-0-credibility` opened; ACTION_PLAN_R4 + ADR-020 ratified.
