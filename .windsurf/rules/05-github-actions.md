---
trigger: glob
globs: [".github/workflows/*.yml", ".github/workflows/*.yaml"]
description: GitHub Actions CI/CD patterns for ML services
---

# GitHub Actions Rules

## Workflow Organization

```
.github/workflows/
├── ci.yml                    # Lint, test, build — on push to main/develop
├── ci-infra.yml              # Terraform validate, tfsec, checkov — on infra/ changes
├── deploy-gcp.yml            # Deploy to GKE — on release tag or manual
├── deploy-aws.yml            # Deploy to EKS — on release tag or manual
├── drift-detection.yml       # PSI drift check — scheduled daily
└── retrain-{service}.yml     # Retrain triggered by drift — workflow_dispatch
```

## CI Workflow (`ci.yml`)

```yaml
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  lint:
    steps:
      - flake8, black --check, isort --check
      - mypy (type checking)

  test:
    strategy:
      matrix:
        service: [ServiceA, ServiceB, ServiceC]
    steps:
      - pytest with coverage >= 90%
      - Upload coverage report

  build:
    needs: [lint, test]
    steps:
      - docker build --cache-from
      - trivy scan (image vulnerabilities)
      - docker push (only on main, not PRs)
```

## Infrastructure CI (`ci-infra.yml`)

Triggered on changes to `infra/` or `k8s/`:
```yaml
jobs:
  terraform-validate:
    strategy:
      matrix:
        cloud: [gcp, aws]
    steps:
      - terraform fmt -check
      - terraform validate
      - tfsec --format json
      - checkov -d infra/terraform/{cloud}
```

## Deploy Workflows

- Always use `kubectl apply -k k8s/overlays/{cloud}/`
- Always verify: `kubectl rollout status deployment/{service}`
- Always smoke test: `curl /health`
- Always use secrets from GitHub Secrets (never hardcoded)

## Drift Detection (`drift-detection.yml`)

```yaml
on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 02:00 UTC
  workflow_dispatch: {}

jobs:
  drift:
    strategy:
      matrix:
        service: [ServiceA, ServiceB, ServiceC]
    steps:
      - run: python src/{service}/monitoring/drift_detection.py
        continue-on-error: true
      - if: steps.drift.outcome == 'failure'
        uses: actions/github-script@v7
        # Creates GitHub Issue automatically
```

## Retraining Workflows

Triggered by `workflow_dispatch` (from drift detection or manual):
```yaml
on:
  workflow_dispatch:
    inputs:
      reason:
        description: 'Reason for retraining'
        required: true

jobs:
  retrain:
    steps:
      - Download fresh data
      - Execute Trainer.run() with Optuna
      - Evaluate quality gates
      - if ALL PASS: promote model + deploy
      - if ANY FAIL: open GitHub Issue
```

## Required Secrets

Document all required GitHub Secrets in the workflow comments:
```yaml
# Required secrets:
# GCP_SA_KEY — GCP service account key (JSON)
# AWS_ACCESS_KEY_ID — AWS access key
# AWS_SECRET_ACCESS_KEY — AWS secret key
# GCP_PROJECT_ID — GCP project ID
# MLFLOW_TRACKING_URI — MLflow server URL
```

## Rules

- NEVER store credentials in workflow files — use GitHub Secrets
- ALWAYS pin action versions to a specific SHA (not `@main` or `@v3`)
- ALWAYS use `continue-on-error: true` for drift detection (drift does not block CI)
- ALWAYS run security scans (trivy for images, tfsec/checkov for Terraform)
- ALWAYS use matrix strategies for multi-service operations
