# release-rehearsal (Codex automation)

**Authority**: `AGENTS.md#Operation → Mode mapping`
**Skill**: `.codex/skills/release-checklist.md` →
`.windsurf/skills/release-checklist/SKILL.md`

## Trigger

Cron: 23:00 UTC daily on the default branch.

## What it does

1. Runs `release-checklist` in **dry-run** mode against the current
   `main` branch HEAD.
2. Verifies presence of: signed images for the most recent release
   tag, SBOM artefacts, ADR for any non-trivial code added since the
   last release, drift baselines refreshed within 30 days.
3. Posts a single-line status to the `#mlops-releases` label-issue:
   `READY` / `BLOCKED — <reason>` with a link to the latest
   `release-checklist` run output.

## Mode

- CONSULT. The skill itself is CONSULT-class (`AGENTS.md§Operation
  → Mode mapping`). The automation runs the **dry-run** path only,
  which is AUTO. Any actual promotion remains gated by the
  `/release` workflow + GitHub Actions environment approvals.

## Why a rehearsal?

Production releases are STOP. Discovering at 09:00 on a release day
that an ADR is missing or an image is unsigned converts a STOP into
a 4-hour emergency. Rehearsing nightly catches the gaps while the
fix path is still AUTO/CONSULT.

## Failure handling

- Any check fails → status `BLOCKED` with the failing check named.
  Issue body lists the most recent 5 failures so trends are
  visible without log surfing.
- All checks pass → status `READY`. Comment auto-collapses if the
  next run is also `READY` (avoids issue noise).
