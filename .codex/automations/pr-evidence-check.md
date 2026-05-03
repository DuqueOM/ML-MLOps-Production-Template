# pr-evidence-check (Codex automation)

**Authority**: `docs/decisions/ADR-020-r4-audit-remediation.md` §S1-2
(evidence policy for new components).

## Trigger

Pull-request `opened` or `synchronize` against `main`.

## What it does

1. Runs `python3 scripts/validate_agentic_manifest.py --strict`.
2. Runs `make mcp-check`.
3. Runs `python3 scripts/validate_agentic.py`.
4. If the PR introduces a new component (per ADR-020 §S1-2 heuristic
   on diff scope), verifies the PR body contains the three required
   evidence headers:
   - `### Evidence — Schema / Contract Test`
   - `### Evidence — Real Execution Output`
   - `### Evidence — CI Run Link`
5. Posts a structured comment on the PR with the four results.
   Comment is updated in place on subsequent pushes (same
   `<!-- codex:pr-evidence-check -->` marker).

## Mode

- AUTO for the read-only checks (steps 1–3).
- AUTO for the body-format check (step 4) — pattern matching only.
- AUTO for posting the comment (step 5) — `github` MCP, scoped to
  `pulls:write` for the repository.

The automation never approves or merges the PR. Human reviewers
remain the gate.

## Failure handling

- Any of steps 1–3 failing → comment marked `blocking`, exit 1.
- Step 4 failing → comment marked `advisory`, exit 1 (matches the
  current `evidence-check` workflow behaviour).
- Step 5 failing (e.g. `github` MCP unreachable) → exit 0 with a
  warning. The local checks still ran; comment posting is
  best-effort.

## Why a Codex automation and not a GitHub Action?

This automation is a **complement**, not a replacement. The
authoritative gate is `.github/workflows/evidence-check.yml` running
in CI. The Codex automation runs the same checks earlier (during
review) so reviewers see issues before the runners even start.
Removing the GitHub Action would violate AGENTS.md permissions
matrix (CI is the only path to merge gating).
