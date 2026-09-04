# Security Baseline Review

**Cadence**: quarterly
**Owner**: `security_owner` (see `templates/config/company_context.example.yaml`)
**Enforcement**: `scripts/check_baselines_expiry.py` + the `security-baseline-expiry` job in `.github/workflows/validate-templates.yml`
**Procedure**: `.security-baselines/README.md` step 4
**Related**: ADR-024 §Review (the decision that made tfsec/checkov/trivy hard-fail with explicit baselines)

## Why this document exists

`.security-baselines/README.md` has instructed reviewers to "update
`docs/audit/baseline-review.md` (next quarterly review)" since the
baselines were introduced. The document did not exist, so three
HIGH-severity suppressions had a written justification in a YAML comment
and no review record anywhere.

A suppression without a review record is indistinguishable from a
suppression nobody remembers making. This is that record.

## Review — 2026-09-04

### What the review found first: the gate was not watching

`scripts/check_baselines_expiry.py` reported `OK — no expired or
unannotated entries` while three HIGH GKE checks sat suppressed. It was
not lying about the entries it saw; it saw none.

Its `yaml_entry` pattern required a suppression id to begin with an
uppercase letter, which matches checkov ids (`CKV_AWS_18`) and misses
every tfsec id (`google-gke-enable-master-networks`). The file was
scanned, zero entries matched, and zero expired entries is a pass.

Two changes were needed, because the obvious one is wrong on its own:

1. The pattern is now case-insensitive.
2. Matching lowercase alone would have swept in `framework: [terraform,
   kubernetes, dockerfile]` from `checkov.yml`, which is a sequence but
   not a suppression. The scanner is now **block-aware** and only treats
   items under `exclude:` / `skip-check:` as entries — which is what the
   code's own comment had claimed since it was written.

The three entries also carried `Review-by: 2027-01`, a format the gate
does not parse; the gate requires `# expiry: YYYY-MM-DD` on the entry line
or the line directly above it. They were normalised, keeping the original
prose justification intact above the annotation.

Verified after the change: the gate reports all three today (in-date), and
`--as-of 2027-06-01` fails all three as expired.

### Suppressions in force

All three are tfsec exclusions. `checkov.yml` carries `skip-check: []` —
no suppressions — and no trivy ignore file is present.

| Check | Severity | Why suppressed | Compensating control | Expiry |
|---|---|---|---|---|
| `google-gke-enforce-pod-security-policy` | HIGH | PodSecurityPolicy was deprecated in Kubernetes 1.21 and **removed** in 1.25. GKE REGULAR channel runs 1.27+, so enabling it would fail the apply outright. | Pod Security Standards enforced via namespace labels in every overlay (D-29, `templates/service/k8s/overlays/*/namespace.yaml`) | 2027-01-01 |
| `google-gke-enable-master-networks` | HIGH | `master_authorized_networks_config` **is** present, as a `dynamic` block. tfsec v1.28 does not evaluate dynamic blocks and reports it absent even when the HCL is correct. | The block is real; staging and prod must supply a non-empty `master_authorized_networks`, enforced by a variable validation rule in `variables.tf` | 2027-01-01 |
| `google-gke-metadata-endpoints-disabled` | HIGH | tfsec reads `node_config.metadata` on `google_container_cluster` only. This module uses `remove_default_node_pool = true` plus two `google_container_node_pool` resources, so the cluster has no `node_config` and the attribute lives on the pools. | Workload Identity on both pools (alone sufficient against metadata SSRF) **plus** `disable-legacy-endpoints = "true"` on each pool | 2027-01-01 |

Every one is a **tool limitation, not an accepted risk**: in all three
cases the control exists and tfsec cannot see it. That distinction is the
reason the expiries are tied to the tfsec → trivy migration rather than to
a risk-acceptance window.

### Verdict

All three suppressions remain justified. No new suppressions were added.
No entry was extended.

## Next review

**Due 2027-01-01**, when all three expiries land together and CI will fail
until each is re-justified or removed. The trigger to close them early is
the tfsec → trivy migration: trivy evaluates dynamic blocks and correlates
node pools to their cluster, so at least the second and third suppressions
are expected to become unnecessary rather than merely re-approved.

## How to run a review

1. `python3 scripts/check_baselines_expiry.py` — confirms nothing is
   expired or unannotated today.
2. `python3 scripts/check_baselines_expiry.py --as-of <next quarter>` —
   shows what is about to come due.
3. For each entry still in force: confirm the compensating control still
   exists, in the file the justification names. A justification that
   points at a control that has since moved is a suppression with no
   backing.
4. Record the outcome as a new dated section in this file. Do not edit a
   previous review; the point of the record is that it accumulates.
