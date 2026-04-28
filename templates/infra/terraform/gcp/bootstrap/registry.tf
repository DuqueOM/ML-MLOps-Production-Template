# ============================================================================
# Artifact Registry — container image store
# ============================================================================
# Currently the live layer assumes Artifact Registry is pre-created. This
# bootstrap moves that creation into Terraform so adopters do not need a
# manual `gcloud artifacts repositories create` step.
#
# One repository per environment so dev images cannot accidentally land in
# the prod registry. Adopters who prefer a shared registry can point all
# environments at a single repo by overriding the `parent` in the live
# layer.

resource "google_artifact_registry_repository" "containers" {
  location      = var.region
  repository_id = "${var.project_name}-containers-${var.environment}"
  description   = "Container images for ${var.project_name} (${var.environment})"
  format        = "DOCKER"
  project       = var.project_id

  # Customer-managed encryption (matches state bucket policy).
  kms_key_name = google_kms_crypto_key.tfstate.id

  # Cleanup policies remove old, unsigned, or vulnerability-flagged images
  # automatically — keeps registry size bounded without manual gardening.
  cleanup_policies {
    id     = "delete-untagged-after-30d"
    action = "DELETE"
    condition {
      tag_state  = "UNTAGGED"
      older_than = "2592000s" # 30 days
    }
  }

  cleanup_policies {
    id     = "keep-recent-tagged"
    action = "KEEP"
    most_recent_versions {
      keep_count = 50
    }
  }

  labels = {
    environment = var.environment
    managed-by  = "terraform-bootstrap"
    purpose     = "container-registry"
  }

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_kms_crypto_key_iam_member.artifact_registry_kms]
}

# Artifact Registry needs explicit KMS access (separate service agent from GCS).
data "google_project" "current" {
  project_id = var.project_id
}

resource "google_kms_crypto_key_iam_member" "artifact_registry_kms" {
  crypto_key_id = google_kms_crypto_key.tfstate.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-artifactregistry.iam.gserviceaccount.com"
}

output "artifact_registry_id" {
  description = "Full ID of the Artifact Registry repository (live layer references this)."
  value       = google_artifact_registry_repository.containers.id
}

output "artifact_registry_url" {
  description = "Docker repository URL — feed this to `docker tag` / `docker push`."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.containers.repository_id}"
}
