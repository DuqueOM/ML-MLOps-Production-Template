# ============================================================================
# Terraform Bootstrap — GCP (ADR-015 PR-A2)
# ============================================================================
# One-time foundation. Run ONCE per (project, environment) BEFORE the live
# Terraform in the parent directory. Provisions:
#
#   1. GCS bucket for the live layer's remote state (with versioning,
#      uniform access, customer-managed encryption, soft-delete window)
#   2. KMS keyring + key for envelope encryption of state + future workloads
#   3. Artifact Registry repository for container images
#   4. (Future) GitHub OIDC Workload Identity Pool for CI keyless auth
#
# Why bootstrap is SEPARATE from live:
#   * Chicken-and-egg: the live layer's `backend "gcs"` needs the state
#     bucket to exist BEFORE init. Bootstrap creates it with LOCAL state.
#   * Lifecycle mismatch: bootstrap resources are touched once a year;
#     live resources are touched on every PR. Mixing them in the same
#     plan creates blast-radius proportional to lifecycle frequency.
#   * Privilege boundary: bootstrap requires `roles/owner`; live runs as
#     a least-privilege ci SA created BY bootstrap.
#
# State strategy:
#   * Bootstrap uses LOCAL state, committed to a separate file
#     (`terraform.tfstate.<env>`) that is gitignored — see .gitignore in
#     this directory. The state contains no secrets (only resource IDs).
#   * Operators back up the local state to a personal/private bucket
#     after each apply. Lossy is acceptable (resources can be re-imported).
# ============================================================================

terraform {
  required_version = ">= 1.7"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  # Deliberate: NO `backend` block. Bootstrap uses local state because
  # the very bucket we need to use as backend is created here.
}

provider "google" {
  project = var.project_id
  region  = var.region
}
