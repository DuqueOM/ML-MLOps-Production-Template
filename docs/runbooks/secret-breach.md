# Secret Breach Runbook

## Trigger

Use this when gitleaks, cloud audit logs, or an operator identifies a leaked credential.

## Procedure

1. Treat the credential as compromised and stop using it immediately.
2. Identify scope: repository, environment, cloud account, secret name, and first-seen time.
3. Revoke or rotate the secret following `docs/runbooks/secret-rotation.md`.
4. Scan git history and logs using `docs/runbooks/secret-history-scan.md`.
5. Record blast-radius analysis, replacement version, and preventive control.

## Exit Criteria

The breach is closed only after the old secret is unusable, consumers are on the new version, and history scan evidence is attached.
