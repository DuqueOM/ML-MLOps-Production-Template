variable "project_id" {
  description = "GCP project ID (must already exist; create via `gcloud projects create`)"
  type        = string
}

variable "project_name" {
  description = "Project name used in resource naming (lower-case, hyphens; matches live layer)"
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.project_name))
    error_message = "project_name must be lower-case alphanumeric with hyphens (matches GCP naming rules)"
  }
}

variable "region" {
  description = "GCP region. State bucket is regional; multi-region adds latency without HA gain for state."
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment name (dev | staging | prod). Suffixes all bootstrap resources."
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod"
  }
}

variable "state_bucket_retention_days" {
  description = "Days to retain non-current state object versions before deletion."
  type        = number
  default     = 90
}

variable "kms_key_rotation_period" {
  description = "KMS key rotation period (Google duration format, e.g. 7776000s = 90d)."
  type        = string
  default     = "7776000s"
}
