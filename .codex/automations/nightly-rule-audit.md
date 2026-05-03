# nightly-rule-audit (Codex automation)

**Authority**: `AGENTS.md#Critical Patterns — DO NOT VIOLATE`
**Skill**: `.codex/skills/rule-audit.md` →
`.windsurf/skills/rule-audit/SKILL.md`

## Trigger

Cron: every weekday 02:00 UTC (off-hours per the default
`MLOPS_ON_HOURS_UTC=08-18`).

## What it does

1. Runs `rule-audit` against `templates/service/` and `templates/k8s/`.
2. Aggregates findings into a Markdown table grouped by
   D-01..D-32 anti-pattern code.
3. If a previous open issue tagged `audit:rule-audit` exists,
   updates its body. Otherwise opens a new issue with the same tag.
4. Failures with severity `STOP` (per AGENTS.md mode mapping) are
   pinned to the top of the issue body and copied to the
   `#mlops-alerts` label for human triage.

## Mode

- AUTO for the scan and the issue-update path.
- AUTO for opening a new issue (additive).
- Never auto-closes an issue. Closing is a human action.

## Why this is in Codex and not GitHub Actions

Codex's automation engine is intentionally narrower than GitHub
Actions: it runs from the contributor's editor environment, against
the local checkout, with the contributor's own MCP credentials. That
makes it a useful fast-feedback loop **before** changes land in the
repo. The CI version (`.github/workflows/agentic-validation.yml`)
remains the authoritative gate.

## Failure handling

- Scan fails → automation reports the rule-audit script error
  verbatim in the issue, no findings table.
- `github` MCP unreachable → automation logs locally, exits 0.
  Next run will catch up.
