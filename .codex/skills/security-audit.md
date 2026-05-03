# security-audit (Codex pointer)

**Canonical**: `.windsurf/skills/security-audit/SKILL.md`
**Authority**: `AGENTS.md#Agent Behavior Protocol`
**Manifest entry**: `agentic_manifest.yaml#skills[id=security-audit]`

## When to invoke from Codex

Before every build or deploy. Codex's automation
`pr-evidence-check` triggers the `scan` sub-mode automatically on
PR open; humans invoke `block_build` and `rotate_secret` manually.

## Modes

- `scan` — AUTO. Read-only secret/IAM/image scan.
- `block_build` — AUTO. Blocking the pipeline on critical findings
  is always authorized.
- `rotate_secret` — STOP. Never rotate from this skill — chain to
  `secret-breach-response` (and the `/secret-breach` workflow), which
  requires human approval per AGENTS.md permissions matrix.

## Codex-specific notes

- The MCPs `github` (CI status) and `kubectl` (cluster scan) listed
  as `required_for: [security-audit]` in `mcp_registry.yaml` must
  be configured in `.codex/mcp.json` before the skill executes.
- The skill's full procedure (gitleaks, trivy, cosign verify, Kyverno
  policy verification, IRSA/WI binding inspection) is in the
  canonical SKILL.md — do not duplicate here.
