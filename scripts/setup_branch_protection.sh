#!/usr/bin/env bash
# =============================================================================
# scripts/setup_branch_protection.sh — apply GitHub Rulesets idempotently.
#
# This is the EXECUTABLE half of ADR-026. The HUMAN-REVIEWABLE half lives in
# `docs/governance/branch-protection.md` (canonical config table) and
# `docs/decisions/ADR-026-branch-protection.md` (rationale).
#
# What this script does:
#   1. Validates `gh` is authenticated with sufficient scope.
#   2. Resolves the current repo from `gh repo view --json nameWithOwner`.
#   3. Builds two ruleset payloads (main-branch-baseline + tag-immutability-v).
#   4. Creates them if absent, updates them if present (idempotent).
#
# What this script does NOT do:
#   - It does not modify any other repo settings (merge button, default
#     branch, environments). That is out of ADR-026 scope.
#   - It does not run on a schedule. Re-run manually after editing
#     `docs/governance/branch-protection.md`.
#
# Usage:
#   ./scripts/setup_branch_protection.sh                  # apply (default)
#   ./scripts/setup_branch_protection.sh --dry-run        # print payloads only
#   ./scripts/setup_branch_protection.sh --check          # exit 0 if both rulesets exist & match enforcement=active
#
# Requires:
#   - gh >= 2.40 (rulesets API support)
#   - jq
#   - a token with `repo` admin scope (gh auth login --scopes 'repo,admin:repo_hook')
# =============================================================================

set -euo pipefail

DRY_RUN=0
CHECK_ONLY=0
case "${1:-}" in
    --dry-run) DRY_RUN=1 ;;
    --check)   CHECK_ONLY=1 ;;
    "")        ;;
    *) echo "Usage: $0 [--dry-run|--check]" >&2; exit 2 ;;
esac

# ---- preconditions ---------------------------------------------------------

command -v gh >/dev/null 2>&1 || {
    echo "::error::gh CLI not found. Install: https://cli.github.com/" >&2
    exit 1
}

# jq is OPTIONAL — used only for pretty-printing payloads during --dry-run.
# `gh api --jq` uses gh's embedded jq library and does NOT need the external
# binary, so the apply/check paths work even without it. We pick a pretty-
# printer at startup: jq if present, otherwise python3 -m json.tool, otherwise
# cat. All three are read-only formatters; correctness is identical.
if command -v jq >/dev/null 2>&1; then
    PRETTY="jq ."
elif command -v python3 >/dev/null 2>&1; then
    PRETTY="python3 -m json.tool"
else
    PRETTY="cat"
fi

if ! gh auth status >/dev/null 2>&1; then
    echo "::error::gh is not authenticated. Run: gh auth login" >&2
    exit 1
fi

REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
if [[ -z "${REPO}" ]]; then
    echo "::error::Could not resolve current repo. Run from inside a clone." >&2
    exit 1
fi

echo "[setup-branch-protection] target repo = ${REPO}"

# ---- ruleset payloads ------------------------------------------------------
# These payloads MUST stay in sync with docs/governance/branch-protection.md.
# If you change anything here, update the doc in the same PR.

read -r -d '' MAIN_RULESET_JSON <<'JSON' || true
{
  "name": "main-branch-baseline",
  "target": "branch",
  "enforcement": "active",
  "bypass_actors": [
    {
      "actor_id": 5,
      "actor_type": "RepositoryRole",
      "bypass_mode": "always"
    }
  ],
  "conditions": {
    "ref_name": {
      "include": ["refs/heads/main"],
      "exclude": []
    }
  },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "required_linear_history" },
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": true,
        "required_reviewers": [],
        "require_extra_approval_for_unattributed_changes": true,
        "allowed_merge_methods": ["squash", "rebase"]
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": false,
        "required_status_checks": [
          { "context": "Tests & Coverage / Python 3.11" },
          { "context": "Tests & Coverage / Python 3.12" },
          { "context": "Self-audit (secrets + IaC + supply chain)" },
          { "context": "Python Lint + Type Check" },
          { "context": "Agentic System Validation" },
          { "context": "Scaffolder End-to-End Test" }
        ]
      }
    }
  ]
}
JSON

read -r -d '' TAGS_RULESET_JSON <<'JSON' || true
{
  "name": "tag-immutability-v",
  "target": "tag",
  "enforcement": "active",
  "bypass_actors": [
    {
      "actor_id": 5,
      "actor_type": "RepositoryRole",
      "bypass_mode": "always"
    }
  ],
  "conditions": {
    "ref_name": {
      "include": ["refs/tags/v*"],
      "exclude": []
    }
  },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" }
  ]
}
JSON

# Note on the three pull_request parameters added 2026-09-04: GitHub fills
# any parameter a payload omits with its own default and stores the result.
# `allowed_merge_methods`, `require_extra_approval_for_unattributed_changes`
# and `required_reviewers` were all being set that way, which meant the
# deployed ruleset carried settings that docs/governance/branch-protection.md
# — the declared single source of truth — never mentioned. They are now
# declared explicitly so the applier is deterministic and a future change to
# GitHub's defaults cannot silently move the contract.
#
# `allowed_merge_methods` deliberately excludes "merge": a merge commit
# cannot satisfy the `required_linear_history` rule above, so offering the
# button only to reject the merge afterwards is a worse failure mode than
# not offering it. Squash is this repo's normal path; rebase stays available.
#
# `require_extra_approval_for_unattributed_changes` is kept at GitHub's
# default of true. It interacts with `required_approving_review_count: 0`:
# a PR carrying commits GitHub cannot attribute to an account still needs
# one approval, even though the baseline requires none. On a solo-maintained
# repo the admin bypass actor below is the break-glass path.
#
# Note on actor_id=5: in GitHub's RepositoryRole actor_type, the built-in
# role ids are 1=Read, 2=Triage, 3=Write, 4=Maintain, 5=Admin. We bypass at
# the Admin level only — Admin is the minimum that can already mutate the
# rulesets via repo settings, so granting bypass is no privilege escalation.
# Maintain (id=4) is too permissive for break-glass on a governance-bearing
# repo; an attacker with Maintain could push to main without admin oversight.
# If your fork's threat model differs, change the actor_id here and document
# the change in ADR-026 §"Bypass actors".

# ---- helpers ---------------------------------------------------------------

# Print payload for inspection (dry-run or for the audit log).
print_payload() {
    local name="$1" payload="$2"
    echo "----- payload: ${name} -----"
    echo "${payload}" | ${PRETTY}
    echo "----- end ${name} -----"
}

# Look up an existing ruleset id by name. Echoes the id or empty string.
find_ruleset_id() {
    local name="$1"
    gh api "repos/${REPO}/rulesets" --jq \
        ".[] | select(.name == \"${name}\") | .id" 2>/dev/null || true
}

# Create or update one ruleset. Idempotent.
apply_ruleset() {
    local name="$1" payload="$2"

    local existing_id
    existing_id="$(find_ruleset_id "${name}")"

    if [[ -n "${existing_id}" ]]; then
        echo "[apply] updating existing ruleset '${name}' (id=${existing_id})"
        if (( DRY_RUN )); then
            print_payload "${name} (PUT)" "${payload}"
            return 0
        fi
        echo "${payload}" | gh api \
            --method PUT \
            "repos/${REPO}/rulesets/${existing_id}" \
            --input - >/dev/null
        echo "[apply] OK — '${name}' updated"
    else
        echo "[apply] creating new ruleset '${name}'"
        if (( DRY_RUN )); then
            print_payload "${name} (POST)" "${payload}"
            return 0
        fi
        echo "${payload}" | gh api \
            --method POST \
            "repos/${REPO}/rulesets" \
            --input - >/dev/null
        echo "[apply] OK — '${name}' created"
    fi
}

# --check mode: return 0 only if both rulesets exist and are active.
check_state() {
    local missing=0
    for name in "main-branch-baseline" "tag-immutability-v"; do
        local id
        id="$(find_ruleset_id "${name}")"
        if [[ -z "${id}" ]]; then
            echo "::error::ruleset '${name}' is missing"
            missing=1
            continue
        fi
        local enforcement
        enforcement="$(gh api "repos/${REPO}/rulesets/${id}" --jq .enforcement)"
        if [[ "${enforcement}" != "active" ]]; then
            echo "::error::ruleset '${name}' (id=${id}) is enforcement=${enforcement}, expected active"
            missing=1
            continue
        fi
        echo "[check] OK — '${name}' (id=${id}, enforcement=active)"
    done
    return "${missing}"
}

# ---- main ------------------------------------------------------------------

if (( CHECK_ONLY )); then
    check_state
    exit $?
fi

apply_ruleset "main-branch-baseline" "${MAIN_RULESET_JSON}"
apply_ruleset "tag-immutability-v"   "${TAGS_RULESET_JSON}"

if (( DRY_RUN )); then
    echo
    echo "[dry-run] no changes were applied. Drop --dry-run to execute."
    exit 0
fi

echo
echo "[setup-branch-protection] DONE. Verify with:"
echo "    $0 --check"
echo "    gh api repos/${REPO}/rulesets --jq '.[] | {id, name, enforcement, target}'"
