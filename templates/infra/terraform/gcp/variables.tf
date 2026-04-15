variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "project_name" {
  description = "Project name used in resource naming"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment name (staging, production)"
  type        = string
  default     = "production"
}

variable "machine_type" {
  description = "GKE node pool machine type"
  type        = string
  default     = "e2-medium"
}

variable "initial_node_count" {
  description = "Initial number of nodes"
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

variable "model_archive_days" {
  description = "Days before archiving model artifacts to Nearline"
  type        = number
  default     = 90
}

variable "model_delete_days" {
  description = "Days before deleting old model artifacts"
  type        = number
  default     = 365
}

variable "monthly_budget" {
  description = "Monthly budget in USD"
  type        = number
  default     = 500
}
