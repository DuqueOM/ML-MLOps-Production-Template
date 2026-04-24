# Incident 2026-04-24 — MCP config plaintext credentials

**Severity**: P2 (exposure, no confirmed compromise)
**Status**: Remediation IN PROGRESS — awaiting user rotation
**Owner**: @DuqueOM
**Agent**: Windsurf Cascade
**Workflow**: `/secret-breach`

## Detection

Cascade read `~/.codeium/windsurf/mcp_config.json` to add the
`mcp-prometheus` entry declared in AGENTS.md but missing from the user's
setup. The `cat` output surfaced **three literal credentials** embedded
as `args` / `headers` / `env` values:

| # | Provider | Token prefix | Location in config |
|---|----------|--------------|--------------------|
| 1 | GitHub (fine-grained PAT) | `github_pat_11BUDJJFQ0...` | `mcpServers.github.headers.Authorization` |
| 2 | Pinecone API | `pcsk_5rCLLx_...` | `mcpServers.pinecone-mcp-server.env.PINECONE_API_KEY` |
| 3 | Supabase access token | `sbp_20fc1075...` | `mcpServers.supabase-mcp-server.args` (`--access-token`) |

## Blast radius

Git history scan on `template_MLOps`, `ML-MLOps-Portfolio`, and `DuqueOM`
repos: **CLEAN**. Tokens never committed.

Exposure surface:
- Local file `~/.codeium/windsurf/mcp_config.json` (readable by user + any
  process running as `duque_om`)
- Conversation context of the agent session that read the file
- No evidence of external exposure

## Classification

Matches invariant **D-17** (hardcoded credentials) and **D-18** (static
credentials instead of env-var delegation). Pre-existing configuration —
not introduced by this session.

## Remediation (in progress)

- [x] Backup original config → `~/.codeium/windsurf/mcp_config.json.bak-prometheus`
- [x] Create `~/.secrets.env` (chmod 600) with empty placeholders
- [x] Add auto-source line to `~/.zshrc`
- [x] Rewrite `mcp_config.json` to reference `${GITHUB_PERSONAL_ACCESS_TOKEN}`,
      `${PINECONE_API_KEY}`, `${SUPABASE_ACCESS_TOKEN}` (no literals)
- [ ] **USER**: revoke token #1 on GitHub Settings → Developer Settings → PATs
- [ ] **USER**: revoke token #2 on Pinecone dashboard → API Keys
- [ ] **USER**: revoke token #3 on Supabase dashboard → Account → Access Tokens
- [ ] **USER**: generate new tokens with least-privilege scopes
- [ ] **USER**: paste new tokens into `~/.secrets.env`
- [ ] **USER**: `source ~/.secrets.env && restart Windsurf` to verify MCPs work
- [ ] **USER**: delete the backup file `~/.codeium/windsurf/mcp_config.json.bak-prometheus`
      after verifying new tokens work (contains the old literals)
- [ ] **USER**: audit GitHub PAT activity for last 90 days (Settings → Security log)

## Root cause

No automated pre-commit / pre-write hook validated that MCP config writes
did not contain token literals. Historically the Windsurf MCP setup
documentation allowed inline tokens for convenience, which conflicts with
our own D-17/D-18 invariants once the project adopted them.

## Corrective actions (post-rotation)

1. **Template**: add `scripts/check_mcp_config.py` that scans a supplied
   `mcp_config.json` for `github_pat_`, `pcsk_`, `sbp_`, `AKIA`, `AIza`,
   `ghp_` patterns and fails if found. Run in `make bootstrap`.
2. **AGENTS.md**: § MCP Integrations — add explicit D-17 callout with
   the env-var reference pattern.
3. **Runbook**: `docs/runbooks/mcp-config-hygiene.md` (TODO) with the
   end-to-end secure setup.

## Related

- `.windsurf/skills/secret-breach-response/SKILL.md`
- `.windsurf/workflows/secret-breach.md`
- `docs/runbooks/secret-rotation.md`
- Invariants D-17, D-18
- MEMORY[12-security-secrets.md] (user-provided, always-on)
