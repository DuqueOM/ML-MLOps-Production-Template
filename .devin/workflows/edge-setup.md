---
description: Wire native-cloud edge protection (Cloud Armor / AWS WAF+Shield) or optional Cloudflare into an overlay — CONSULT for apply, STOP for disabling an existing rule
---

# /edge-setup Workflow

Implements ADR-042. Default is native-cloud (Cloud Armor for GCP
overlays, AWS WAFv2 + Shield Standard for AWS overlays); Cloudflare is
opt-in for genuine multi-cloud or zero-cloud-account use (`--provider
cloudflare`).

## 1. Audit current coverage first (AUTO)

```bash
# Invoke the edge-audit skill, or run its checks directly
kubectl kustomize k8s/overlays/<overlay>/ | grep -A3 "edge-protection.mlops-template.io/implementation"
```

If the overlay already has a PASSing edge component wired in, stop here
and report — do not re-wire something that already works. This mirrors
`/ci-green`'s own first step: verify before acting.

## 2. Propose the Terraform plan (CONSULT — D-38, ADR-042 §2.2)

This is a **hard CONSULT in every environment, including dev** — unlike
most `terraform apply` calls in this template (`03-terraform.md`'s
per-environment table), edge-protection resources create public
exposure and real cost regardless of the environment label. Never
treat a dev overlay as license to apply this with AUTO.

```bash
# GCP
terraform -chdir=infra/terraform/gcp plan \
  -target=google_compute_security_policy.edge_policy \
  -var-file=environments/<env>.tfvars

# AWS
terraform -chdir=infra/terraform/aws plan \
  -target=aws_wafv2_web_acl.edge_acl \
  -var-file=environments/<env>.tfvars
```

Present the plan diff to the operator. Wait for explicit approval
before `apply`.
// turbo-all

## 3. Apply (only after approval)

```bash
terraform -chdir=infra/terraform/<cloud> apply \
  -target=<the same resource(s) planned in step 2> \
  -var-file=environments/<env>.tfvars
```

Record a `scripts/audit_record.py` entry for the apply, same
requirement as any other CONSULT-class infra change.

## 4. Wire the Kustomize Component into the overlay

```yaml
# k8s/overlays/<overlay>/kustomization.yaml
components:
  - ../../components/edge-gcp   # or edge-aws, or your Cloudflare equivalent
```

Fill in the placeholders the component expects (`{DOMAIN}` in
`managedcertificate.yaml` for GCP; `{ACM_CERT_ARN}` and
`{WAFV2_ACL_ARN}` in `edge-aws/ingress.yaml`) with real values —
usually the Terraform outputs from step 3.

## 5. Render and verify

```bash
kubectl kustomize k8s/overlays/<overlay>/ > /tmp/rendered.yaml
grep -c "edge-protection.mlops-template.io/implementation" /tmp/rendered.yaml
```

Expect exactly one match, with a value matching the cloud you just
configured. Then re-run the `edge-audit` skill (step 1's check) — it
should now report PASS for this overlay.

## 6. Post-setup verification

- Confirm the LB actually terminates through the new Ingress: `curl -I
  https://<domain>/health` should succeed and the response should NOT
  be reachable via any bypassing `LoadBalancer`/`NodePort` Service for
  the same workload (rule `17-edge-protection.md`).
- Confirm the WAF is in "block" or "count" mode as intended — a
  freshly-applied policy in count-only mode looks protected in the
  audit but blocks nothing. Document which mode was chosen and why.

## Disabling or loosening an existing rule (STOP — always, any environment)

This is the one action this workflow will NOT walk through as a normal
numbered step. Removing, disabling, or loosening a WAF rule or
rate-limit — in dev, staging, or prod — is **STOP-class**, same as
`/rollback` and D-36's CI-override: propose nothing, execute nothing,
until a human explicitly instructs it, and record the decision via
`scripts/audit_record.py` before making the change. There is no
environment or urgency exception (ADR-042 §2.2).

## Related

- `docs/decisions/ADR-042-native-cloud-edge-protection.md`
- `agentic/skills/edge-audit/SKILL.md` — the AUTO-mode audit this
  workflow's step 1 delegates to
- `agentic/rules/17-edge-protection.md`
- `agentic/workflows/release.md` §1 — the same "verify before acting"
  opening-step pattern
