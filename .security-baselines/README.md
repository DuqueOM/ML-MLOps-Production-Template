# Security baselines

The May 2026 audit (HIGH-1) flipped `tfsec`, `checkov`, and `trivy` in
`.github/workflows/validate-templates.yml` from `soft_fail: true` to
**hard-fail**. To prevent legitimate, accepted findings from blocking
unrelated PRs, the workflow consults the per-tool baseline files in this
directory.

| Tool | File | Format |
|------|------|--------|
| tfsec | `tfsec.yml` | tfsec config (`exclude:` list with rationale comments) |
| Checkov | `checkov.yml` | Checkov config (skip-check + soft-fail-on lists) |
| Trivy | `.trivyignore` | One CVE-ID per line; `# rationale` comments allowed |

## Adding a finding to the baseline

1. **Confirm the finding cannot be fixed**: a vendor-side CVE without a
   patched release, an IaC pattern explicitly required by another invariant,
   or an upstream-only false positive.
2. **Open an ADR or issue** documenting the rationale and the expiry date.
   Baseline entries are time-bounded; the goal is zero baseline by
   `v1.0.0`.
3. **Add the entry** to the appropriate file with a line comment citing the
   ADR/issue.
4. **Update `docs/audit/baseline-review.md`** (next quarterly review).

## Removing a finding

When a CVE is patched, an ADR closes, or the upstream resource is fixed,
remove the entry from the baseline file. CI then enforces it as a regular
finding on the next run.

## Why hard-fail matters

Soft-fail produces a green CI badge that lies. A reviewer reading the badge
believes the IaC is clean when in reality CRITICAL Terraform findings or
HIGH CVEs in container base layers are being ignored. The baseline files
make every accepted finding **explicit, dated, and reviewable**.
