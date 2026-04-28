variable "project_name" {
  description = "Project name used in resource naming (lower-case, hyphens; matches live layer)"
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.project_name))
    error_message = "project_name must be lower-case alphanumeric with hyphens"
  }
}

variable "region" {
  description = "AWS region. State bucket lives here; live-layer regions can differ."
  type        = string
  default     = "us-east-1"
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

variable "kms_key_deletion_window_days" {
  description = "KMS key deletion window. 30 days = max recoverability."
  type        = number
  default     = 30

  validation {
    condition     = var.kms_key_deletion_window_days >= 7 && var.kms_key_deletion_window_days <= 30
    error_message = "kms_key_deletion_window_days must be 7..30 (AWS limits)"
  }
}
