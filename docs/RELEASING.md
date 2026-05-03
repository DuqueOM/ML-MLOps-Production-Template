# Releasing — versioning policy and adopter contract

This document defines the project's semantic versioning contract and the
release workflow. It is the canonical answer to "is this change a PATCH,
a MINOR, or a MAJOR?" Every release MUST cite this document in its commit
trailer or in the release-note header.

- **Audit context**: this policy was introduced in response to R4 finding
  C3 — twelve minor bumps in fourteen days, with several closing blocker
  bugs that should have been PATCH or MAJOR. See
  [`docs/audit/ACTION_PLAN_R4.md`](audit/ACTION_PLAN_R4.md) §S0-3 and
  [`ADR-020`](decisions/ADR-020-r4-audit-remediation.md).
- **Authority**: this document, plus the `Keep a Changelog` and SemVer 2.0
  conventions referenced from `CHANGELOG.md`.

---

## 1. The contract

The version number applies to **scaffolded service output, public template
contracts, and adopter-visible operating procedures** — not to every commit.
Internal refactors that do not change scaffolded output are PATCH.

We version the **adopter surface**, not the template's internal code.

### 1.1 PATCH bump (e.g. `1.12.0 → 1.12.1`)

A PATCH release fixes a defect WITHOUT changing any of the following:

- The output of `templates/scripts/new-service.sh` (file list, file
  contents at template-rendered boundaries, default flag values).
- The shape of any contract under `templates/service/tests/contract/`.
- The names of overlays, namespaces, ServiceAccounts, or other
  cluster-bound identifiers in `templates/k8s/overlays/`.
- The name or signature of any callable in `templates/common_utils/`
  that is documented as part of the adopter API surface.
- The name, severity, or routing of any Prometheus alert in the
  scaffolded `monitoring/` output.
- The name or required hooks of any `make` target documented in
  `docs/ADOPTION.md` § non-agentic on-ramp.
- The name of any pre-commit hook stage or its declared inputs.
- The name of any ADR or its acceptance criteria.

PATCH is also the right level for documentation typo fixes that do not
change adopter-facing instructions.

### 1.2 MINOR bump (e.g. `1.12.0 → 1.13.0`)

A MINOR release introduces a backward-compatible feature: a new template
file, a new optional flag, a new ADR with `Status: Proposed` or
`Status: Accepted`, a new contract test, or a new ADR-recognized
component. MINOR releases MAY add a column to a maturity matrix or
toggle a capability from `Phase 0` to `Phase 1` if and only if the
existing Phase 0 contract remains intact and any banner referenced in
`tests/test_phase0_disclosure.py` is updated alongside the test.

A MINOR release MUST NOT close a defect that breaks scaffolded output
or any contract listed under §1.1; that is either a PATCH (if the fix
preserves all contracts) or a MAJOR (if the fix has to break a
contract).

### 1.3 MAJOR bump (e.g. `1.12.0 → 2.0.0`)

A MAJOR release is required for **any** of the following:

- A change in scaffolded file names, paths, or required directory
  layout (e.g. renaming an overlay, splitting `gcp-prod` into
  `gcp-prod-primary` + `gcp-prod-failover`).
- A change in any schema field that the scaffolded service exposes on
  the wire (`/predict` request or response, prediction-log JSONL,
  ground-truth ingestion contract).
- A change in any pre-commit hook contract (rename, removal, or
  required-input change). Adding a new hook is MINOR; removing or
  renaming one is MAJOR.
- Any breaking change in the public API surface of
  `templates/common_utils/` documented modules.
- Removing or renaming an ADR-recognized `make` target.
- Removing or renaming any operation in the AGENTS.md AUTO/CONSULT/STOP
  matrix.
- Removing or renaming any contract test that adopters extend.

When a MAJOR is unavoidable, the release MUST ship a `MIGRATION.md`
section covering every adopter-visible change with the manual action
required and a code example or `sed` command where applicable. Adopters
who scaffolded under the previous major MUST be able to follow the
migration sequentially without inferring undocumented changes.

### 1.4 Why this matters (post-R4 lesson)

The pattern this policy explicitly forbids: a fix that closes a blocker
bug shipping under MINOR because it added a new file. **The number of
new files added is irrelevant to the semver bump.** What matters is
whether the change touches an adopter contract.

Examples from the R3 / R4 audit window that were misclassified:

- Cosign install added in `v1.10.0` (was MINOR, should have been MAJOR
  because the scaffolded deploy path silently changed: prior versions
  could not actually sign images).
- Overlay rename in `v1.10.0` (was MINOR, should have been MAJOR by
  the rule in §1.3 first bullet).
- Closed-loop schema realignment in `v1.12.0` (was MINOR, should have
  been MAJOR because the workflow's request payload changed shape).

The discipline is forward-looking: existing tags `v1.0.0` through
`v1.12.0` remain immutable. The next breaking change will go to
`v2.0.0`.

---

## 2. Re-anchoring at `v1.12.0`

Per ADR-020 §"Hard rules", `v1.12.0` is the **GA hardening anchor**.
Existing tags are not re-numbered. The release line resumes from
`v1.12.0` with this policy in force.

The next release that touches any item in §1.3 — even by a single
character — bumps to `v2.0.0`. The next release that adds a feature
without breaking anything bumps to `v1.13.0`. PATCHes (`v1.12.1`,
`v1.12.2`, …) are reserved for defects that do not touch any contract
in §1.1.

---

## 3. Release checklist

Every release MUST satisfy the following before tagging:

- [ ] CHANGELOG entry exists under the new version with the correct
      bump level per §1.
- [ ] If MAJOR: a `## [vX.0.0] - YYYY-MM-DD` section in CHANGELOG includes
      a `### Breaking for adopters` block with one row per change,
      mapped to a manual action; AND `MIGRATION.md` has a corresponding
      `from → to` entry.
- [ ] If MINOR: the `### Added` / `### Changed` blocks in CHANGELOG do
      NOT include any change that would force a MAJOR per §1.3
      (reviewer enforces this).
- [ ] `### Known follow-ons` block is filled with one bullet per
      explicitly-deferred follow-on, each linked to a tracking issue
      with an SLA label.
- [ ] All contract tests green on `main` at the tagged commit.
- [ ] `tests/test_readme_model_names.py` and
      `tests/test_phase0_disclosure.py` green (R4 invariants).
- [ ] If the release transitions ADR-018 or ADR-019 to a new Phase,
      both the ADR Status line AND the README banner are updated;
      `test_phase0_disclosure.py` is updated alongside in the SAME PR
      that flips the Status.
- [ ] Release notes file `releases/vX.Y.Z.md` exists with the same bump
      rationale.
- [ ] Tag is annotated (`git tag -a vX.Y.Z -m '...'`) and pushed to
      origin alongside the merge commit.

---

## 4. Release rhythm

Target rhythm:

- **PATCH**: same-day or same-week — bug-fix only, no policy change.
- **MINOR**: every 2–4 weeks at minimum; never multiple MINORs per day
  in normal operation. The R3-window pattern of 3+ MINORs in a single
  hour was a release-discipline failure and is explicitly disavowed.
- **MAJOR**: opportunistic but rare. Every MAJOR requires an ADR
  documenting the contract change, the migration path, and the rollback
  plan if the change has to be reverted.

Hot-fix MINORs (closing a Critical via a feature flag rather than a
contract change) are permitted but should be rare; a hot-fix MINOR is
NOT permission to close a contract-touching bug under MINOR.

---

## 5. Reviewer responsibilities

The merging reviewer is responsible for:

1. Checking the bump level against §1 and refusing the merge if the
   level is wrong (regardless of how many CI gates are green — this is
   a judgment gate, not an automated one).
2. Verifying the `### Breaking for adopters` block is present when
   any §1.3 item is touched.
3. Verifying `MIGRATION.md` is updated alongside any MAJOR or any
   adopter-visible contract change at MINOR (rare, requires explicit
   reviewer note).
4. Verifying `### Known follow-ons` is non-empty if the release is the
   close of a multi-PR initiative.

The reviewer's note in the merge commit MUST cite this document by
section.

---

## 6. Exceptions

There are no automatic exceptions. Any deviation from §1 requires:

- An ADR documenting the deviation (e.g. ADR-020 documents the
  re-anchoring policy at v1.12.0).
- Approval from CODEOWNERS in the merge.
- A `### Audit deviation` block in the release notes explaining the
  deviation in plain language.

The audit trail for each release is:

- Tag annotation message (signed if release-keys are configured).
- `releases/vX.Y.Z.md`.
- `CHANGELOG.md` entry.
- Any new ADR(s) that ratify breaking changes.
