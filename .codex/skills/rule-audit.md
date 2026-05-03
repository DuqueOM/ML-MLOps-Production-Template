# rule-audit (Codex pointer)

**Canonical**: `.windsurf/skills/rule-audit/SKILL.md`
**Authority**: `AGENTS.md#Agent Behavior Protocol`
**Manifest entry**: `agentic_manifest.yaml#skills[id=rule-audit]`

## When to invoke from Codex

- On demand: "audit the fraud-detector service for D-01..D-32
  compliance".
- Scheduled: Codex automation `nightly-rule-audit` runs the skill
  against `templates/service/` once per night and posts a PASS/FAIL
  table to a designated GitHub issue.

## Mode

- AUTO. Pure read-only static analysis. No runtime calls, no MCP
  required for the core scan.

## Codex-specific notes

- No required MCPs for the basic scan. `github` MCP is recommended
  if Codex should also open an issue with findings; the canonical
  skill describes both paths.
- The full anti-pattern table (D-01..D-32) lives in `AGENTS.md` —
  the skill resolves anchors against it; this pointer does not
  duplicate the list.
