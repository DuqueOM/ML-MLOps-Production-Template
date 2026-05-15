# Branch Protection — Canonical Configuration

> **Single source of truth** for the GitHub Rulesets that protect this
> repository. Decision rationale lives in
> [ADR-026](../decisions/ADR-026-branch-protection.md). The applier script
> is `scripts/setup_branch_protection.sh`. If you change anything below,
> open a PR that updates **all three** in the same commit.

---

## Ruleset 1 — `main` branch baseline

| Setting | Value |
|---|---|
| **Ruleset name** | `main-branch-baseline` |
| **Target type** | `branch` |
| **Target pattern** | `main` (exact, not glob) |
| **Enforcement** | `active` |
| **Bypass actors** | `RepositoryRole: admin` (= role, not specific user) |

### Rules

| Rule | State | Configuration |
|---|---|---|
| `deletion` | enabled | — |
| `non_fast_forward` | enabled | — |
| `pull_request` | enabled | `required_approving_review_count: 0`, `dismiss_stale_reviews_on_push: true`, `require_code_owner_review: false`, `require_last_push_approval: false`, `required_review_thread_resolution: true` |
| `required_linear_history` | enabled | — |
| `required_status_checks` | enabled | `strict_required_status_checks_policy: false` (= "Require branches up to date" OFF), checks list below |
| `required_signatures` | disabled | — |

### Required status checks (exactly 6)

| Display name | Workflow file | Always runs on PR? |
|---|---|---|
| `Tests & Coverage / Python 3.11` | `.github/workflows/ci-examples.yml` | ✅ |
| `Tests & Coverage / Python 3.12` | `.github/workflows/ci-examples.yml` | ✅ |
| `Self-audit (gitleaks + tfsec + checkov + trivy fs)` | `.github/workflows/validate-templates.yml` | ✅ |
| `Python Lint + Type Check` | `.github/workflows/validate-templates.yml` | ✅ |
| `Agentic System Validation` | `.github/workflows/validate-templates.yml` | ✅ |
| `Scaffolder End-to-End Test` | `.github/workflows/validate-templates.yml` | ✅ |

> **Critical invariant:** every required check above MUST run on every PR
> to `main` without a `paths:` filter. A path-filtered or
> schedule-only check that is required produces a permanent merge
> deadlock when the relevant files are not touched. See ADR-026 §Context
> point 3.

### Excluded from required (intentional)

| Check | Reason for exclusion |
|---|---|
| `Docs Quality` | Path-filtered to `**/*.md` |
| `Kyverno Admission Smoke` | Path-filtered to `templates/k8s/policies/...` |
| `Golden Path E2E` | `schedule` + `workflow_dispatch` only, not on PR |
| `Golden Path E2E (extended)` | `workflow_run` after Golden Path; not on PR |
| `Policy Tests (D-XX anti-patterns)` | `schedule` + push-to-main, not on PR |
| The other 8 jobs of `validate-templates.yml` | Still must be GREEN to pass the workflow; not gated at SCM layer to keep the required list small and stable |

---

## Ruleset 2 — Tag immutability `v*`

| Setting | Value |
|---|---|
| **Ruleset name** | `tag-immutability-v` |
| **Target type** | `tag` |
| **Target pattern** | `v*` (glob, matches `v0.*`, `v1.*`, …) |
| **Enforcement** | `active` |
| **Bypass actors** | `RepositoryRole: admin` |

### Rules

| Rule | State |
|---|---|
| `deletion` | enabled |
| `non_fast_forward` | enabled |
| `update` | disabled (tags are write-once; recreation is what `non_fast_forward` blocks) |

No required status checks (tags are post-merge; they reference a commit
that already passed Ruleset 1).

---

## How to apply

### Recommended (reproducible)

```bash
# Dry run — prints the JSON payloads that would be sent.
./scripts/setup_branch_protection.sh --dry-run

# Apply (idempotent — safe to re-run).
./scripts/setup_branch_protection.sh
```

The script uses `gh api` and creates or updates both rulesets via the
GitHub Repository Rulesets REST API. Requires `gh auth login` with a
token that has `repo` admin scope.

### Manual (UI, fallback)

GitHub.com → repo → Settings → Rules → Rulesets → New branch ruleset
(and again for tag ruleset). Use the tables above.

---

## Verification checklist

After applying, confirm:

- [ ] `gh api repos/:owner/:repo/rulesets` returns 2 entries with `enforcement: active`
- [ ] An attempt to `git push --force origin main` from a non-admin token is rejected
- [ ] Opening a PR with a deliberately failing required check disables the merge button
- [ ] Opening a PR that touches only `.md` files (no Python/YAML) still shows the 6 required checks as the gate (not "Docs Quality")
- [ ] `git push --force origin v0.15.3` is rejected
- [ ] `git push --delete origin v0.15.0` is rejected

---

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-05-15 | Initial ruleset (ADR-026) | `@DuqueOM` |
