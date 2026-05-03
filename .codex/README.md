# Codex Adapter

This directory wires OpenAI Codex into the canonical agent surfaces
described in `agentic_manifest.yaml`. Codex is treated as an
**adapter** surface: rules + skills + workflows live in `.windsurf/`
and Codex consumes them via thin pointers + a small set of
automations that map naturally to its execution model.

**Authority**: `docs/decisions/ADR-023-agentic-portability-and-context.md`.
**Manifest entry**: `agentic_manifest.yaml#surfaces.codex`.

## What Codex consumes

| Type | Path | Behaviour |
|------|------|-----------|
| Project preamble | `AGENTS.md` | Codex's native preamble convention; already maintained |
| Skills | `.codex/skills/` | Pointer files — each `<id>.md` references `.windsurf/skills/<id>/SKILL.md` |
| Automations | `.codex/automations/` | Codex-specific event/schedule mapping for slash commands |
| MCP config | `.codex/mcp.json` | Adopter copies `.codex/mcp.example.json` and fills credentials |

The pointer pattern is intentional. Duplicating skill bodies into this
directory would multiply the same drift problem ADR-023 solves.

## Sprint-4 minimum scope (4 skills + 3 automations)

The first batch enables the high-ROI flows for an adopter testing
Codex on this template, no more:

**Skills (4)**
- `security-audit` — pre-build/pre-deploy gate; AUTO scan + STOP rotate.
- `rule-audit` — D-01..D-32 compliance scan over a service path.
- `release-checklist` — multi-cloud release checklist; CONSULT mode.
- `debug-ml-inference` — latency / wrong predictions / event-loop blockers.

**Automations (3)**
- `pr-evidence-check` — runs `make mcp-check` + the agentic validator on PR open.
- `nightly-rule-audit` — schedules `rule-audit` against `templates/service/`.
- `release-rehearsal` — chains `release-checklist` (dry-run) before a tag.

Anything beyond this list is **out of scope** for F5 by ADR-023. The
remaining 12 skills and 9 workflows continue to live in `.windsurf/`
and `.cursor/`/`.claude/` as today; they become available to Codex
via additive pointers in subsequent PRs.

## How an adopter onboards Codex

```
# 1. Copy the example MCP config and fill credentials (per surface, never committed)
cp .codex/mcp.example.json .codex/mcp.json
$EDITOR .codex/mcp.json

# 2. Validate the cross-surface contract still holds
python3 scripts/validate_agentic_manifest.py --strict
make mcp-check

# 3. Read the entry point
cat AGENT_CONTEXT.md
```

`mcp.json` is gitignored (see repo `.gitignore`); only the
`mcp.example.json` reference ships in the repo (ADR-023 I-2 pattern
extended to MCP configs).

## Invariants this adapter inherits

- **I-1** — every skill pointer carries `authority:` to either
  `AGENTS.md#<heading>` or an ADR file. The contract test resolves
  these on every PR.
- **I-2** — `.codex/mcp.json` (live) is gitignored. Only
  `.codex/mcp.example.json` is committed.
- **I-3** — no installer entry point. The Codex adapter ships docs
  + pointers + an example config; the adopter triggers MCP setup
  manually from their Codex client.

## Anti-list (deliberately NOT here)

- No skill bodies. Codex reads the canonical Windsurf SKILL.md via
  the pointer and `AGENTS.md` for protocol.
- No rules directory. Rules are universal; Codex consumes them via
  `AGENTS.md` and the rule files referenced from there.
- No live `mcp.json`. Adopter-specific.
- No production-write automations. STOP-class operations stay in
  GitHub Actions per AGENTS.md permissions matrix.
