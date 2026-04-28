# ============================================================================
# Terraform Bootstrap — AWS (ADR-015 PR-A2)
# ============================================================================
# One-time foundation per (account, environment). Provisions:
#
#   1. S3 bucket for the live layer's remote state (versioned, encrypted)
#   2. DynamoDB table for state locking
#   3. KMS key for state encryption + future workload encryption
#   4. ECR repository for container images
#   5. (Future) GitHub OIDC Provider for keyless CI auth (already in live
#      layer, but should migrate here in a follow-up since it's account-wide)
#
# State strategy: bootstrap uses LOCAL state (chicken-and-egg with the S3
# backend it provisions). Operators back up the local state file to a
# personal/private location after each apply.
# ============================================================================

terraform {
  required_version = ">= 1.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # NO `backend` block — local state, by design.
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      managed-by  = "terraform-bootstrap"
      environment = var.environment
      project     = var.project_name
    }
  }
}
