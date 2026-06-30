# =============================================================================
# CloudWatch log groups — retention parity with GCP (PR-R2-6, audit R2 §3.6).
#
# Every long-lived log producer the template provisions gets an explicit
# CloudWatch log group with a configured retention. AWS' default is
# "Never expire", which translates to unbounded cost AND unbounded
# subpoena exposure — both unacceptable defaults for a template that
# argues for engineering calibration.
#
# Retention tiers, per environment (set via overlays, default 30):
#   * dev      → 30 days
#   * staging  → 90 days
#   * production → 365 days
#
# Encryption: every group uses the EKS Secrets KMS key (compute.tf).
# Like Secrets Manager, this gives a single revocation point for the
# data-at-rest surface area.
#
# Groups created here:
#   * /aws/eks/<cluster>/cluster — control-plane logs (EKS expects
#     this exact name, so we MUST pre-create it to set retention +
#     KMS BEFORE the cluster starts emitting; otherwise EKS auto-
#     creates with retention = "Never expire" and we lose control).
#   * /ml-services/<service> — application logs from each predictor
#     pod, written via FluentBit (or the kubelet container log
#     forwarder). One group per service so retention can be tuned.
# =============================================================================

resource "aws_cloudwatch_log_group" "eks_cluster" {
  name              = "/aws/eks/${var.project_name}-eks-${var.environment}/cluster"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.eks_secrets.arn

  tags = {
    environment = var.environment
    managed-by  = "terraform"
    purpose     = "eks-control-plane"
  }
}

resource "aws_cloudwatch_log_group" "service" {
  for_each = toset(var.service_names)

  name              = "/ml-services/${each.value}-${var.environment}"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.eks_secrets.arn

  tags = {
    environment = var.environment
    managed-by  = "terraform"
    service     = each.value
    purpose     = "service-application-logs"
  }
}

# AWS Budgets alarm — parity with GCP's monthly_budget. Fires at 80%
# and 100% of var.monthly_budget. Notifications are SNS-based; the
# topic ARN is left as a placeholder var so each org can wire its own
# (PagerDuty / email / Slack via Lambda).
resource "aws_budgets_budget" "monthly" {
  name              = "${var.project_name}-${var.environment}-monthly"
  budget_type       = "COST"
  limit_amount      = tostring(var.monthly_budget)
  limit_unit        = "USD"
  time_period_start = "2024-01-01_00:00"
  time_unit         = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    notification_type          = "ACTUAL"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    subscriber_email_addresses = []
    subscriber_sns_topic_arns  = []
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    notification_type          = "ACTUAL"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    subscriber_email_addresses = []
    subscriber_sns_topic_arns  = []
  }
}
