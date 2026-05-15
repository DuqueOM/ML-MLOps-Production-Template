# CI/CD Templates Drift Gate

**Status**: Active enforcement (v0.16.1+)
**Enforcement**: `scripts/check_cicd_template_drift.py` + `cicd-template-drift` job in `.github/workflows/validate-templates.yml`
**Related**: ADR-025 (`common_utils` distribution), ADR-026 (branch protection)

## What this gate enforces

For every GitHub Action `X` that appears in BOTH `.github/workflows/`
(the runtime workflows of the template repo itself) and `templates/cicd/`
(the scaffolder inputs copied verbatim into adopter services), the set of
versions used in `templates/cicd/` must be a subset of the set of versions
used in `.github/workflows/`.

If templates use any version not present in runtime, the gate fails the
PR with a structured diff.

## Why this gate exists

Dependabot's `github-actions` ecosystem scans `.github/workflows/`
relative to the configured `directory:` in `.github/dependabot.yml`. It
does not — and cannot trivially — scan `templates/cicd/*.yml` because
those files are scaffolder inputs, not executable workflows of the
template repo.

The blast radius is concrete:

```
1. Dependabot opens PR: actions/upload-artifact v4 -> v7 in .github/workflows/
2. PR is merged. Runtime workflows are now on v7.
3. templates/cicd/ still references v4 (Dependabot never saw those files).
4. An adopter runs `make new-service` today.
5. The new service is scaffolded with v4 references.
6. The adopter's own Dependabot opens the SAME bumps the template
   already merged, multiplying maintenance cost across every fork.
```

Without this gate, the divergence is invisible until an adopter notices
their scaffolded service has stale CI references — by which point the
contract has already shipped.

## What this gate does NOT enforce

- Action versions in `templates/cicd/` that are NOT also used in
  `.github/workflows/`. Some template-only actions exist by design
  (`google-github-actions/auth`, `aws-actions/configure-aws-credentials`,
  `infracost/actions/setup`) because the template repo doesn't deploy
  to a real cloud but adopters do. Those have no parallel reference to
  compare against.
- Whether a shared action SHOULD be used in both places. That's an
  architecture decision, not a drift question.
- SHA-pinned versus tag-pinned references. Tag drift was the immediate
  blindspot and what this gate catches; SHA pinning is a separate
  hardening that would live in its own governance doc.

## How drift is fixed

When the gate fails, it prints the action, the runtime versions, and
the template versions. The fix is mechanical: bump the offending
references in `templates/cicd/*.yml` to a version already used in
`.github/workflows/`. The script's error message includes the exact
versions to remove.

For intentional divergence (e.g., a template needs an older version
for backward compat with a specific runner), add an exception inside
`scripts/check_cicd_template_drift.py` with an inline comment linking
to the ADR or governance doc that justifies the deviation.

## Required check posture

This gate runs on every PR but is **not** in the required-status-checks
list codified by ADR-026 (`docs/governance/branch-protection.md`).
That list is intentionally minimal — six always-on checks that protect
the core invariants. Adding `cicd-template-drift` to required would
require:

1. PR amending `docs/governance/branch-protection.md` to extend the
   required-checks list to seven entries.
2. Update to ADR-026 §Revisit triggers documenting why the seventh
   slot is justified.
3. Re-running `make setup-github` to push the updated ruleset.

Until that consensus exists, the gate enforces via merge friction (a
red check is visible to reviewers) rather than via hard server-side
block. This matches the posture of `common-utils-drift` (ADR-025).

## Why a script and not a yaml-only check

The check could in principle be expressed inline as a `grep`-and-diff
shell snippet. The script form was chosen for three reasons:

1. **Clear failure messages.** The drift report prints the exact
   action, the version sets on each side, and the template-only
   versions to remove. A `grep` pipe would print line numbers without
   semantic context.
2. **Future extensibility.** When SHA-pinning is added (separate
   governance work), the script can grow a `--require-sha` mode
   without changing the workflow yaml.
3. **Reusability.** Adopters can add the same check to their own forks
   if they fork-and-modify `templates/cicd/`, by reusing the script.

## Operational cost

Empty repo state (no shared actions): `O(0)` work — the script returns
0 immediately. Typical state (5–15 shared actions across 8 templates +
11 runtime workflows): `O(20ms)` on a CI runner, dominated by Python
startup. Negligible in CI budget terms.

## Revisit triggers

This gate becomes obsolete (and removable) when Dependabot grows
support for scanning arbitrary template directories under
`github-actions` ecosystem, OR when `templates/cicd/` is replaced by a
generation step that derives templates from `.github/workflows/` at
scaffold time. Neither is on the immediate roadmap; the gate is the
correct calibration today.
