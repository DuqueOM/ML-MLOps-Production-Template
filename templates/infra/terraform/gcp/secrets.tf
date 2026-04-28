# ============================================================================
# GCP Secret Manager — per-service entries (parity with AWS secrets.tf)
# ============================================================================
# One Secret Manager secret per (service × secret_name). Naming scheme
# `${project_name}-${service}-${secret}` matches the IAM resource scope
# in iam.tf so a service's runtime SA can read only its own secrets.
#
# Encryption: every secret uses `google_kms_crypto_key.secrets` from
# kms.tf (CMEK = customer-managed encryption key) — same blast-radius
# property as AWS where `aws_secretsmanager_secret.kms_key_id` references
# `aws_kms_key.eks_secrets`. Default Google-managed encryption is also
# fine, but CMEK gives operators a single revocation point if a
# compromise demands it.
#
# Replication: REGIONAL replication pinned to var.region to comply with
# data residency requirements (most templates target a single region per
# ADR-001 boundaries; multi-region replication adds latency without HA
# gain at this scale).
#
# Versions: this module deliberately does NOT create secret VERSIONS
# (the actual ciphertext payloads). Operators populate them out-of-band
# via `gcloud secrets versions add` to keep the state clean of secret
# values — same pattern as AWS where rotation Lambdas write versions.
# ============================================================================

resource "google_secret_manager_secret" "service" {
  # Cartesian product of service_names × secret_names.
  for_each = {
    for pair in setproduct(var.service_names, var.secret_names) :
    "${pair[0]}/${pair[1]}" => {
      service = pair[0]
      secret  = pair[1]
    }
  }

  secret_id = "${var.project_name}-${each.value.service}-${each.value.secret}"
  project   = var.project_id

  replication {
    user_managed {
      replicas {
        location = var.region

        customer_managed_encryption {
          kms_key_name = google_kms_crypto_key.secrets.id
        }
      }
    }
  }

  labels = {
    environment = var.environment
    managed-by  = "terraform"
    service     = each.value.service
    secret      = each.value.secret
  }

  depends_on = [google_kms_crypto_key_iam_member.secret_manager_kms]
}

# Grant the per-service runtime SA permission to access ITS OWN secrets.
# This is the granular alternative to the project-wide
# `roles/secretmanager.secretAccessor` already on `runtime` (iam.tf):
# both work; this resource-level binding adds defense-in-depth and shows
# up cleanly in audit logs as "secret X accessed by SA Y".
resource "google_secret_manager_secret_iam_member" "runtime_accessor" {
  for_each = {
    for pair in setproduct(var.service_names, var.secret_names) :
    "${pair[0]}/${pair[1]}" => {
      service = pair[0]
      secret  = pair[1]
    }
  }

  project   = var.project_id
  secret_id = google_secret_manager_secret.service[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

output "secret_ids" {
  description = "Map of '<service>/<secret>' → Secret Manager secret_id (use with `gcloud secrets versions add`)."
  value       = { for k, s in google_secret_manager_secret.service : k => s.secret_id }
  sensitive   = false # IDs are not secret values
}
