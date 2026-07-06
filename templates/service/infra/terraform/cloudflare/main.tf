# =============================================================================
# Cloudflare Edge Protection — OPTIONAL multi-cloud / zero-cloud-account module
# =============================================================================
# NOT the default (ADR-042 §2): a single-cloud deployment uses the native
# gcp/security.tf (Cloud Armor) or aws/security.tf (WAFv2 + Shield) instead.
# This module exists for two specific scenarios:
#   1. Genuinely concurrent multi-cloud (GKE + EKS both serving production
#      traffic for the same logical service) — one Cloudflare zone in front
#      of both origins is simpler to operate than two separate native WAFs.
#   2. A zero-cloud-account path to learn WAF/rate-limiting concepts before
#      touching GCP/AWS Terraform at all.
#
# terraform apply of these resources is CONSULT in every environment,
# including dev — creates public exposure + real cost regardless of the
# environment label (rule 17-edge-protection.md, ADR-042 §2.2).
# =============================================================================

terraform {
  required_version = ">= 1.7"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.21"
    }
  }

  # Same per-environment state segregation discipline as gcp/ and aws/ (D-10).
  # Defaults to GCS (GCP is this template's primary cloud per CLAUDE.md); an
  # AWS-only adopter using this module can switch to `backend "s3" {}`.
  backend "gcs" {}
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}
