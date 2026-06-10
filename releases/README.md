# Release notes index

This directory holds two release lines (R6 audit S1-3 — the coexistence
confused external reviewers):

| Line | Range | Status |
|------|-------|--------|
| **Legacy `v1.x`** | `v1.0.0` (2026-04-15) … `v1.12.0` (2026-04-29) | Immutable audit snapshots from before the post-audit versioning reset. NOT the current line. |
| **Active `v0.x`** | `v0.13.0` (2026-05-03) … | The public pre-GA hardening channel. |

Per the reset (documented in [`v0.13.0.md`](v0.13.0.md) §Release
Classification and [`docs/RELEASING.md`](../docs/RELEASING.md)), the
**next** `v1.0.0` is reserved for the first release carrying real-cloud
golden-path evidence on GKE **and** EKS (the L4 gate in
[`VALIDATION_LOG.md`](../VALIDATION_LOG.md)). The legacy `v1.x` files are
kept because tags are immutable (ADR-026) and the audit trail references
them.

Every release note longer than a hotfix must carry a
`## Known follow-ons` section — enforced by
`templates/service/tests/test_release_notes_follow_ons.py`.
