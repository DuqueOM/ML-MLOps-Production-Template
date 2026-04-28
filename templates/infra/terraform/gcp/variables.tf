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

# ----------------------------------------------------------------------
# Network mode (ADR-017 / PR-A1)
# ----------------------------------------------------------------------
# 'managed':  template creates VPC + subnetwork with secondary ranges
# 'existing': caller provides network_name + subnetwork_name (data lookup)
#
# Default 'managed' preserves backwards compatibility for adopters who
# accepted the implicit auto-mode VPC. Teams with existing VPCs flip to
# 'existing' and pass their network/subnetwork names.
# ----------------------------------------------------------------------
variable "network_mode" {
  description = "Network topology mode: 'managed' (template creates VPC) or 'existing' (use provided VPC/subnets)"
  type        = string
  default     = "managed"

  validation {
    condition     = contains(["managed", "existing"], var.network_mode)
    error_message = "network_mode must be 'managed' or 'existing'"
  }
}

variable "network_name" {
  description = "Existing VPC network name (required when network_mode='existing')"
  type        = string
  default     = ""
}

variable "subnetwork_name" {
  description = "Existing subnetwork name (required when network_mode='existing')"
  type        = string
  default     = ""
}

variable "subnetwork_cidr" {
  description = "Subnetwork primary CIDR (managed mode only)"
  type        = string
  default     = "10.10.0.0/20"
}

variable "pods_cidr" {
  description = "Secondary range CIDR for GKE pods (managed mode only)"
  type        = string
  default     = "10.20.0.0/14"
}

variable "services_cidr" {
  description = "Secondary range CIDR for GKE services (managed mode only)"
  type        = string
  default     = "10.30.0.0/20"
}
