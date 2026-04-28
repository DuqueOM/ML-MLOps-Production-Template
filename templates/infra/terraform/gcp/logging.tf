# ============================================================================
# GCP Cloud Logging + Billing Budget — parity with AWS logging.tf
# ============================================================================
# The AWS counterpart (templates/infra/terraform/aws/logging.tf) provisions:
#   * Explicit CloudWatch log groups with configured retention
#   * An AWS Budgets monthly cost alarm
#
# On GCP the equivalents are:
#   * google_logging_project_bucket_config — configures retention on the
#     default _Default log bucket + a per-service log bucket with CMEK
#   * google_billing_budget — monthly budget alert with email + 80/100
#     thresholds (parity with AWS Budgets notifications)
#
# Why pre-create log buckets: GCP's default retention on _Default is
# 30 days and on _Required is 400 days — both FIXED, not configurable
# in place. To set custom retention (90d staging / 365d prod) we must
# create bucket configs explicitly. Without this, log_retention_days
# would silently have no effect on GCP, breaking parity with AWS.
# ============================================================================

# ----------------------------------------------------------------------------
# Per-service log buckets — one per ML service, CMEK-encrypted
# ----------------------------------------------------------------------------
# The _Default bucket receives ALL project logs; operators use routing
# sinks (not in this file — env-specific) to fan logs into these
# per-service buckets. Parity with `/ml-services/<service>-<env>` on AWS.
resource "google_logging_project_bucket_config" "service" {
  for_each = toset(var.service_names)

  project        = var.project_id
  location       = var.region
  retention_days = var.log_retention_days
  bucket_id      = "ml-services-${each.value}-${var.environment}"
  description    = "Application logs for service '${each.value}' in ${var.environment}."

  # CMEK via the live-layer logs KMS key (kms.tf).
  cmek_settings {
    kms_key_name = google_kms_crypto_key.logs.id
  }

  depends_on = [google_kms_crypto_key_iam_member.logging_kms]
}

# ----------------------------------------------------------------------------
# Default bucket retention — overrides GCP's fixed 30d default
# ----------------------------------------------------------------------------
# Sets retention on the _Default bucket so logs NOT routed to a per-service
# bucket still respect the configured retention policy.
resource "google_logging_project_bucket_config" "default" {
  project        = var.project_id
  location       = "global"
  retention_days = var.log_retention_days
  bucket_id      = "_Default"
}

# ----------------------------------------------------------------------------
# Monthly budget alert — parity with aws_budgets_budget.monthly
# ----------------------------------------------------------------------------
# Gated behind var.billing_account because billing-admin permissions are
# often held by a different identity than project-level IaC. When the
# variable is empty the budget resource is skipped and operators provision
# it out-of-band via the Console or a dedicated billing-level TF stack.
resource "google_billing_budget" "monthly" {
  count = var.billing_account != "" ? 1 : 0

  billing_account = var.billing_account
  display_name    = "${var.project_name}-${var.environment}-monthly"

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.monthly_budget)
    }
  }

  budget_filter {
    projects = ["projects/${data.google_project.this.number}"]
  }

  # Match AWS tiers: 80% (soft warning) + 100% (hard warning).
  threshold_rules {
    threshold_percent = 0.8
    spend_basis       = "CURRENT_SPEND"
  }

  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "CURRENT_SPEND"
  }

  dynamic "all_updates_rule" {
    for_each = length(var.budget_notification_emails) > 0 ? [1] : []
    content {
      disable_default_iam_recipients = false
      # Email notifications require a google_monitoring_notification_channel
      # per email. Operators wire these via the monitoring-channels module
      # (out of scope for this file). Empty = rely on default IAM billing
      # admins.
    }
  }
}

output "service_log_buckets" {
  description = "Map of service → Cloud Logging bucket resource name (for routing sinks)."
  value = {
    for k, b in google_logging_project_bucket_config.service : k => b.name
  }
}
