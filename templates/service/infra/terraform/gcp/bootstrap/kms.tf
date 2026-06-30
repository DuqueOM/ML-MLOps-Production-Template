# ============================================================================
# KMS keyring + key for envelope encryption
# ============================================================================
# Used by:
#   * State bucket (state.tf) — encrypts terraform.tfstate at rest
#   * Future: GKE Secret Manager envelope encryption (live layer references)
#   * Future: GCS data buckets (live layer references)
#
# Rotation: every 90 days by default (var.kms_key_rotation_period).

resource "google_kms_key_ring" "main" {
  name     = "${var.project_name}-keyring-${var.environment}"
  location = var.region
  project  = var.project_id

  # KMS keyrings cannot be deleted — only their keys are scheduled for
  # destruction. Once created, the keyring is permanent for this region.
  lifecycle {
    prevent_destroy = true
  }
}

resource "google_kms_crypto_key" "tfstate" {
  name     = "tfstate"
  key_ring = google_kms_key_ring.main.id

  rotation_period = var.kms_key_rotation_period

  # 30-day destroy window — accidental destroys are recoverable.
  destroy_scheduled_duration = "2592000s"

  lifecycle {
    prevent_destroy = true
  }
}

# Allow the GCS service account to use the key for the state bucket.
# Without this binding, GCS rejects the encryption.default_kms_key_name
# field with a confusing "key not accessible" error.
data "google_storage_project_service_account" "gcs" {
  project = var.project_id
}

resource "google_kms_crypto_key_iam_member" "gcs_kms_user" {
  crypto_key_id = google_kms_crypto_key.tfstate.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${data.google_storage_project_service_account.gcs.email_address}"
}

output "kms_keyring_id" {
  description = "Full ID of the KMS keyring (for live-layer references)."
  value       = google_kms_key_ring.main.id
}

output "tfstate_kms_key_id" {
  description = "Full ID of the KMS key encrypting the state bucket."
  value       = google_kms_crypto_key.tfstate.id
}
