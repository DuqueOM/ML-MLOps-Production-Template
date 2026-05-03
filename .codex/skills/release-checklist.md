# release-checklist (Codex pointer)

**Canonical**: `.windsurf/skills/release-checklist/SKILL.md`
**Authority**: `AGENTS.md#Agent Behavior Protocol`
**Manifest entry**: `agentic_manifest.yaml#skills[id=release-checklist]`

## When to invoke from Codex

- Before tagging a release. Codex automation
  `release-rehearsal` runs the dry-run path nightly on the default
  branch so failures surface before a human triggers the actual
  release workflow.
- On demand: "run the release checklist for fraud-detector v0.7.0".

## Mode

- CONSULT. The skill is informational + dry-run by default; any
  promotion step is delegated to GitHub Actions per
  `AGENTS.md#Agent Permissions Matrix`. Codex never runs
  `terraform apply` or `kubectl apply` against staging or production.

## Codex-specific notes

- Required MCPs (per `mcp_registry.yaml`): `github`, `kubectl`,
  `terraform`. Without them, Codex degrades to the documentation
  path of the canonical skill (still useful, less complete).
- The canonical SKILL.md owns the actual checklist (image signing,
  SBOM presence, Kyverno admission, drift baseline, runbook freshness).
  This pointer only describes the Codex-side ergonomics.
