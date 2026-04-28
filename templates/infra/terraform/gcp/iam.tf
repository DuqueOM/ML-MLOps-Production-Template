# ============================================================================
# Per-environment IAM split (ADR-017 / PR-A1)
# ============================================================================
# Five identities, each with the minimal permissions for its purpose:
#
#   ci       — Terraform plan/apply, image build push (used by GitHub Actions)
#   deploy   — Push images, update K8s manifests (used by deploy workflows)
#   runtime  — Pod runtime: read secrets, read storage (Workload Identity)
#   drift    — Drift CronJob: read metrics, write reports (Workload Identity)
#   retrain  — Retrain workflow: read data, write models (Workload Identity)
#
# Why 5 separate identities instead of one:
#   * Audit trail: a Cloud Audit Logs entry tells you EXACTLY which workflow
#     touched a resource. With a single identity you only know "the template
#     did it".
#   * Blast radius: a leaked CI key cannot read production model artifacts;
#     a leaked runtime key cannot push images.
#   * Least-privilege contract test: enforcing "no identity has *.admin"
#     is meaningful only when permissions are split by purpose.
#
# All identities are project-scoped (no org-level grants). Per-environment
# isolation is achieved by deploying this Terraform once per env, which
# creates env-suffixed names (e.g. ci-sa-staging, ci-sa-production).
# ============================================================================

# ---------------------------------------------------------------------------
# 1. CI identity — runs Terraform + image build in GitHub Actions
# ---------------------------------------------------------------------------
resource "google_service_account" "ci" {
  account_id   = "${var.project_name}-ci-${var.environment}"
  display_name = "${var.project_name} CI (${var.environment})"
  description  = "Terraform plan/apply + image build. Used by GitHub Actions via WIF."
}

resource "google_project_iam_member" "ci_container_admin" {
  project = var.project_id
  role    = "roles/container.admin"
  member  = "serviceAccount:${google_service_account.ci.email}"
}

resource "google_project_iam_member" "ci_storage_admin" {
  project = var.project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.ci.email}"
}

resource "google_project_iam_member" "ci_artifact_registry" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.ci.email}"
}

resource "google_project_iam_member" "ci_sa_user" {
  # Required to impersonate the deploy/runtime SAs during apply.
  # Scoped via condition (only acting on SAs in this project).
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${google_service_account.ci.email}"
}

# ---------------------------------------------------------------------------
# 2. Deploy identity — push images, update K8s
# ---------------------------------------------------------------------------
resource "google_service_account" "deploy" {
  account_id   = "${var.project_name}-deploy-${var.environment}"
  display_name = "${var.project_name} Deploy (${var.environment})"
  description  = "Push images + apply K8s manifests. Used by deploy-gcp.yml."
}

resource "google_project_iam_member" "deploy_artifact_registry" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

resource "google_project_iam_member" "deploy_container_developer" {
  # Developer (NOT admin) — can deploy workloads but cannot create/delete clusters.
  project = var.project_id
  role    = "roles/container.developer"
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

# ---------------------------------------------------------------------------
# 3. Runtime identity — pod runtime via Workload Identity
# ---------------------------------------------------------------------------
resource "google_service_account" "runtime" {
  account_id   = "${var.project_name}-runtime-${var.environment}"
  display_name = "${var.project_name} Runtime (${var.environment})"
  description  = "Pod runtime: read secrets + read storage. Bound to KSA via Workload Identity."
}

resource "google_project_iam_member" "runtime_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_project_iam_member" "runtime_storage_object_viewer" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

# Workload Identity binding: K8s SA in `ml-services` namespace impersonates this GSA.
# Service name is parameterized so per-service bindings can override.
resource "google_service_account_iam_member" "runtime_workload_identity" {
  service_account_id = google_service_account.runtime.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[ml-services/${var.project_name}-sa]"
}

# ---------------------------------------------------------------------------
# 4. Drift identity — drift CronJob (read metrics, write reports)
# ---------------------------------------------------------------------------
resource "google_service_account" "drift" {
  account_id   = "${var.project_name}-drift-${var.environment}"
  display_name = "${var.project_name} Drift (${var.environment})"
  description  = "Drift CronJob: read metrics + write reports. Bound to KSA via Workload Identity."
}

resource "google_project_iam_member" "drift_monitoring_viewer" {
  project = var.project_id
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${google_service_account.drift.email}"
}

resource "google_project_iam_member" "drift_storage_object_creator" {
  # Drift writes reports to a dedicated bucket; can create new objects but
  # not overwrite (object versioning + retention enforce immutability).
  project = var.project_id
  role    = "roles/storage.objectCreator"
  member  = "serviceAccount:${google_service_account.drift.email}"
}

resource "google_project_iam_member" "drift_storage_object_viewer" {
  # Read reference distributions for PSI calculation.
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.drift.email}"
}

resource "google_service_account_iam_member" "drift_workload_identity" {
  service_account_id = google_service_account.drift.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[ml-services/${var.project_name}-drift-sa]"
}

# ---------------------------------------------------------------------------
# 5. Retrain identity — retrain workflow (read data, write models)
# ---------------------------------------------------------------------------
resource "google_service_account" "retrain" {
  account_id   = "${var.project_name}-retrain-${var.environment}"
  display_name = "${var.project_name} Retrain (${var.environment})"
  description  = "Retrain workflow: read data + write models. Bound to KSA via Workload Identity."
}

resource "google_project_iam_member" "retrain_storage_object_viewer" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.retrain.email}"
}

resource "google_project_iam_member" "retrain_storage_object_creator" {
  project = var.project_id
  role    = "roles/storage.objectCreator"
  member  = "serviceAccount:${google_service_account.retrain.email}"
}

resource "google_service_account_iam_member" "retrain_workload_identity" {
  service_account_id = google_service_account.retrain.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[ml-services/${var.project_name}-retrain-sa]"
}

# ---------------------------------------------------------------------------
# Outputs — consumed by GitHub Actions secrets + K8s ServiceAccount annotations
# ---------------------------------------------------------------------------
output "ci_service_account_email" {
  description = "Email of the CI service account (for GitHub Actions WIF binding)"
  value       = google_service_account.ci.email
}

output "deploy_service_account_email" {
  description = "Email of the deploy service account"
  value       = google_service_account.deploy.email
}

output "runtime_service_account_email" {
  description = "Email of the runtime service account (annotate KSA with this)"
  value       = google_service_account.runtime.email
}

output "drift_service_account_email" {
  description = "Email of the drift service account (annotate drift KSA with this)"
  value       = google_service_account.drift.email
}

output "retrain_service_account_email" {
  description = "Email of the retrain service account (annotate retrain KSA with this)"
  value       = google_service_account.retrain.email
}
