---
paths:
  - "**/*"
---

# Security & Secrets Rules (always-applicable)

## Non-negotiable invariants (D-17 to D-19)

### D-17 — No hardcoded credentials
- Never write literal keys, tokens, passwords
- Never `os.environ["API_KEY"]` in production — use `common_utils.secrets.get_secret`
- Never commit `.env`, `.env.local`, `terraform.tfstate`

### D-18 — Cloud-native credential delegation
- AWS: IRSA only (no `AWS_ACCESS_KEY_ID`)
- GCP: Workload Identity only (no JSON keys)
- Static creds only in `.env.local` (gitignored)

### D-19 — Supply chain verification
- Production images: Cosign keyless signature + CycloneDX SBOM attestation
- Kyverno admission rejects unsigned images in `environment=production`
- Staging/prod: image refs digest-pinned (`@sha256:...`), never tags

## Pre-commit sequence (automatic)
```bash
gitleaks detect --no-git --source=. --redact
grep -rEI "AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|ghp_[A-Za-z0-9]{36}" --include="*.py" --include="*.yaml"
grep -E "os\.environ\[.(API_KEY|SECRET|TOKEN|PASSWORD)" --include="*.py"
```
Any hit → STOP, chain to `/secret-breach`.

## Environment → secret backend
- local → `.env.local` (dotenv)
- ci → GitHub Secrets
- staging/prod → AWS Secrets Manager or GCP Secret Manager (via IRSA/WI + CSI driver)

## Rotation is STOP-class
Never silent. Always audit trail. Use `/secret-breach` workflow.

## NOT covered here (deferred by ADR-001)
HashiCorp Vault, SLSA L3+, SOC2/HIPAA compliance programs.

See AGENTS.md (D-17 to D-19), ADR-005, `.windsurf/rules/12-security-secrets.md`.
