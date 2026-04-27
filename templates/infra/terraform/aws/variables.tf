variable "project_name" {
  description = "Project name used in resource naming"
  type        = string
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (staging, production)"
  type        = string
  default     = "production"
}

variable "k8s_version" {
  description = "Kubernetes version for EKS"
  type        = string
  default     = "1.29"
}

variable "instance_type" {
  description = "EKS node instance type"
  type        = string
  default     = "t3.medium"
}

variable "initial_node_count" {
  description = "Desired number of nodes"
  type        = number
  default     = 2
}

variable "min_node_count" {
  description = "Minimum nodes in autoscaling"
  type        = number
  default     = 1
}

variable "max_node_count" {
  description = "Maximum nodes in autoscaling"
  type        = number
  default     = 5
}

variable "subnet_ids" {
  description = "List of subnet IDs for EKS"
  type        = list(string)
}

# -----------------------------------------------------------------------------
# PR-R2-6 — AWS parity additions
# -----------------------------------------------------------------------------
# Each variable below has a sane production default and an explicit reason
# (linked to ADR-016 §"PR-R2-6 — AWS parity") so the template is operable
# without forcing every adopter to read every doc first.
# -----------------------------------------------------------------------------

variable "allow_public_endpoint" {
  description = <<-EOT
    EKS API server reachability. Default is private-only (audit R2 §3.1).
    Set true for environments where bastion/VPN access is impractical;
    public access is gated by `public_endpoint_access_cidrs` so it is
    never wide-open. ADR-018 captures the parity tier where flipping
    this is acceptable.
  EOT
  type        = bool
  default     = false
}

variable "public_endpoint_access_cidrs" {
  description = <<-EOT
    CIDR blocks that may reach the EKS public endpoint when
    `allow_public_endpoint=true`. Empty list = block everyone, which
    AWS would reject — so when `allow_public_endpoint=true` this MUST
    be a non-empty list of office/VPN CIDRs.
  EOT
  type        = list(string)
  default     = []
}

variable "model_archive_days" {
  description = "Days before archiving model artifacts to S3 Glacier Instant Retrieval (parity with GCS NEARLINE)."
  type        = number
  default     = 90
}

variable "model_delete_days" {
  description = "Days before deleting old model artifact versions (post-archive lifecycle)."
  type        = number
  default     = 365
}

variable "log_retention_days" {
  description = <<-EOT
    CloudWatch log retention in days. Default 30 matches the dev tier;
    overlays bump this to 90 (staging) and 365 (prod). Setting 0 means
    "never expire" — explicitly rejected by the validate block below.
  EOT
  type        = number
  default     = 30
  validation {
    condition     = var.log_retention_days >= 1 && var.log_retention_days <= 3653
    error_message = "log_retention_days must be 1..3653 (CloudWatch caps at ~10y)."
  }
}

variable "monthly_budget" {
  description = "Monthly budget in USD (used by AWS Budgets alarm; parity with GCP variant)."
  type        = number
  default     = 500
}

variable "enable_secret_rotation" {
  description = <<-EOT
    Enable Secrets Manager automatic rotation. Off by default because
    rotation requires a customer-supplied Lambda (rotation logic is
    secret-shape-specific, e.g. RDS vs API key). Operators flip this
    to true after wiring `rotation_lambda_arn`.
  EOT
  type        = bool
  default     = false
}

variable "rotation_lambda_arn" {
  description = "ARN of the Lambda implementing the rotation contract. Required iff enable_secret_rotation=true."
  type        = string
  default     = ""
}

variable "secret_names" {
  description = <<-EOT
    Logical names of secrets to provision (one Secrets Manager entry
    per name). Defaults to the canonical set used by the template:
    api_key (predict auth), admin_api_key (admin gate), mlflow_password.
  EOT
  type        = list(string)
  default     = ["api_key", "admin_api_key", "mlflow_password"]
}

variable "service_names" {
  description = <<-EOT
    Logical service names that need IRSA roles (one per ML service
    deployed to this cluster). Each gets a narrow per-service IAM
    policy (read on data bucket, write on its own model prefix).
  EOT
  type        = list(string)
  default     = ["fraud-detector"]
}
