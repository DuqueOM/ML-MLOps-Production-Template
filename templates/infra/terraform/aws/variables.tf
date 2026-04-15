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
