# ============================================================================
# Terraform state bucket — GCS
# ============================================================================
# Audit High-6 mandate: state is per-environment to prevent dev applies from
# mutating prod state. Backend config files (../backend-configs/<env>.hcl)
# reference these bucket names.

resource "google_storage_bucket" "tfstate" {
  name     = "${var.project_name}-tfstate-${var.environment}"
  location = var.region
  project  = var.project_id

  # Uniform bucket-level access disables per-object ACLs (forces IAM-only).
  # Required by D-17 — granular ACLs are a known foot-gun for state files.
  uniform_bucket_level_access = true

  # Versioning catches an accidental `terraform state rm` or `tf destroy`.
  # Restore by reading the previous version of the .tfstate object.
  versioning {
    enabled = true
  }

  # Lifecycle rule: retain non-current versions for the configured window,
  # then delete. Keeps cost bounded while preserving recovery capability.
  lifecycle_rule {
    condition {
      age        = var.state_bucket_retention_days
      with_state = "ARCHIVED"
    }
    action {
      type = "Delete"
    }
  }

  # Soft-delete: 7-day recovery for accidentally-deleted CURRENT versions.
  soft_delete_policy {
    retention_duration_seconds = 7 * 24 * 3600
  }

  # Customer-managed encryption with a KMS key in this same bootstrap.
  # This means even GCP's at-rest encryption is layered on a key under
  # our control — relevant for compliance audits.
  encryption {
    default_kms_key_name = google_kms_crypto_key.tfstate.id
  }

  labels = {
    environment = var.environment
    managed-by  = "terraform-bootstrap"
    purpose     = "tfstate"
  }

  # Uniform access requires the bucket be empty before deletion.
  # Treat the state bucket as PROTECTED — `terraform destroy` from the
  # bootstrap dir would orphan the live state. Operators must explicitly
  # `terraform state rm` before destroy.
  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_kms_crypto_key_iam_member.gcs_kms_user]
}

# ----------------------------------------------------------------------------
# Backend-config helper output
# ----------------------------------------------------------------------------
# After `terraform apply` in this dir, the operator copies these values into
# `../backend-configs/<env>.hcl` (or the live layer auto-discovers via
# `bucket = data.terraform_remote_state.bootstrap.outputs.tfstate_bucket`
# when both layers share state — see runbook).

output "tfstate_bucket" {
  description = "GCS bucket name for the live layer's remote state."
  value       = google_storage_bucket.tfstate.name
}

output "tfstate_bucket_url" {
  description = "gs:// URL for the state bucket (paste into terraform init -backend-config)."
  value       = "gs://${google_storage_bucket.tfstate.name}"
}
