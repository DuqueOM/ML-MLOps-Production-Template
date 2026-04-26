# Terraform backend config — GCP / prod
# CRITICAL: this state controls production. Reviewers REQUIRED for any
# `terraform apply` against this backend (ADR-011 environment promotion).
bucket = "{project}-tfstate-prod"
prefix = "ml-mlops/prod"
