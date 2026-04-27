# =============================================================================
# AWS ECR registry — parity with GCP Artifact Registry (PR-R2-6, audit R2 §3.3).
#
# One repository per service (driven by var.service_names). Compared to a
# single shared repo, per-service repos give:
#   * independent IAM scoping (a service's IRSA role can pull only its
#     own image, never another service's)
#   * per-service lifecycle policies (some services may need longer
#     image retention than others)
#   * cleaner blast radius for any compromised pull credential
#
# Security defaults:
#   * image_tag_mutability = IMMUTABLE — once a tag is pushed it cannot
#     be replaced. Combined with the digest-pinning lint in
#     validate-templates.yml, this makes "the image deployed yesterday"
#     reproducible at any future point.
#   * scan_on_push = true with ENHANCED scanning. ENHANCED uses Amazon
#     Inspector and catches CVEs in OS packages AND application
#     dependencies; basic scanning misses application-layer issues.
#   * encryption_configuration = KMS — uses the same key as S3 for
#     simpler audit; rotation already enabled on that key.
#   * Lifecycle policy expires untagged images after 14 days so a
#     failed push or stale CI run does not accumulate cost forever.
#
# What is NOT enforced here:
#   * Cosign signature verification at PULL time. ECR has no native
#     hook for that; the gate lives in the cluster (Kyverno admission
#     policy, see templates/k8s/policies/). This file makes signing
#     POSSIBLE; the cluster gate makes it MANDATORY.
# =============================================================================

resource "aws_ecr_repository" "service" {
  for_each = toset(var.service_names)

  name                 = "${var.project_name}/${each.value}-predictor"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.s3.arn
  }

  tags = {
    environment = var.environment
    managed-by  = "terraform"
    service     = each.value
  }
}

# Account-level enhanced scanning. This is set at the registry level
# (one per AWS account), not per-repository, so we configure it once
# even if multiple services are present.
resource "aws_ecr_registry_scanning_configuration" "enhanced" {
  scan_type = "ENHANCED"

  # Continuous scanning rescans existing images when new vulnerability
  # data lands; without it, images scanned 6 months ago are treated as
  # current. Filter "*" applies to every repo.
  rule {
    scan_frequency = "CONTINUOUS_SCAN"
    repository_filter {
      filter      = "*"
      filter_type = "WILDCARD"
    }
  }
}

resource "aws_ecr_lifecycle_policy" "expire_untagged" {
  for_each   = toset(var.service_names)
  repository = aws_ecr_repository.service[each.value].name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Expire untagged images older than 14 days"
      selection = {
        tagStatus   = "untagged"
        countType   = "sinceImagePushed"
        countUnit   = "days"
        countNumber = 14
      }
      action = {
        type = "expire"
      }
    }]
  })
}
