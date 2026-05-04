# Deploy GKE Runbook

## Procedure

1. Confirm GitHub variables for WIF, project id, region, and GKE cluster names.
2. Confirm Artifact Registry repositories exist and image verification policy is installed.
3. Run the GCP deploy workflow from `main` for dev/staging or a version tag for production.
4. Verify namespace, rollout status, `/ready`, `/predict`, metrics, and audit entry.
5. For production, confirm environment protection reviewers approved the deployment.

## Exit Criteria

GKE deploy is complete when the digest-pinned image is running and smoke evidence is attached to the workflow summary.
