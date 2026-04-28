# ============================================================================
# Live-layer KMS — keyring + key for app data encryption (parity with AWS)
# ============================================================================
# Separate from the bootstrap KMS keyring (templates/infra/terraform/gcp/
# bootstrap/kms.tf) which encrypts STATE. This live-layer keyring encrypts
# WORKLOAD data: Secret Manager entries + future Cloud Logging buckets.
#
# Why two keyrings instead of one shared:
#   * Lifecycle: bootstrap keys rotate yearly; live keys rotate every 90d.
#   * Privilege boundary: bootstrap requires owner; live runs as the CI
#     identity provisioned by bootstrap.
#   * Blast radius: revoking a workload key does not lock out the state
#     bucket (and vice versa).
# Same pattern as AWS — `aws_kms_key.eks_secrets` + `aws_kms_key.s3` are
# distinct resources for the same reason.

resource "google_kms_key_ring" "workload" {
  name     = "${var.project_name}-workload-${var.environment}"
  location = var.region
  project  = var.project_id

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_kms_crypto_key" "secrets" {
  name     = "secrets"
  key_ring = google_kms_key_ring.workload.id

  rotation_period = "7776000s" # 90 days

  destroy_scheduled_duration = "2592000s" # 30 days

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_kms_crypto_key" "logs" {
  name     = "logs"
  key_ring = google_kms_key_ring.workload.id

  rotation_period = "7776000s" # 90 days

  destroy_scheduled_duration = "2592000s" # 30 days

  lifecycle {
    prevent_destroy = true
  }
}

# Allow the Secret Manager service agent to encrypt/decrypt secret payloads.
data "google_project" "this" {
  project_id = var.project_id
}

resource "google_kms_crypto_key_iam_member" "secret_manager_kms" {
  crypto_key_id = google_kms_crypto_key.secrets.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-secretmanager.iam.gserviceaccount.com"
}

# Allow Cloud Logging service agent to encrypt log buckets.
resource "google_kms_crypto_key_iam_member" "logging_kms" {
  crypto_key_id = google_kms_crypto_key.logs.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-logging.iam.gserviceaccount.com"
}

output "workload_keyring_id" {
  description = "Live-layer keyring ID (consumed by secrets.tf, logging.tf)."
  value       = google_kms_key_ring.workload.id
}

output "secrets_kms_key_id" {
  description = "KMS key encrypting Secret Manager payloads."
  value       = google_kms_crypto_key.secrets.id
}

output "logs_kms_key_id" {
  description = "KMS key encrypting Cloud Logging buckets."
  value       = google_kms_crypto_key.logs.id
}
