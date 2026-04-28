# ============================================================================
# ECR repository — container image store
# ============================================================================
# The live layer's ecr.tf currently creates a per-service repository inside
# the same Terraform plan as workloads. That's a lifecycle mismatch: ECR
# repositories are touched once a year; workloads are touched on every PR.
#
# This bootstrap creates a SHARED repository per environment that downstream
# services can push to with prefixed image names (e.g.
# `<repo>:fraud-detector-v1.2.3`). Adopters who prefer per-service repos
# can keep using the live-layer ecr.tf and ignore this file.

resource "aws_ecr_repository" "shared" {
  name                 = "${var.project_name}-${var.environment}"
  image_tag_mutability = "IMMUTABLE" # blocks `:latest` tag overwrites

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.tfstate.arn
  }

  tags = {
    Name    = "${var.project_name}-${var.environment}"
    purpose = "container-registry"
  }

  lifecycle {
    prevent_destroy = true
  }
}

# Lifecycle policy: untagged images expire after 30 days; tagged keep last 50.
# Bounded registry size without manual gardening.
resource "aws_ecr_lifecycle_policy" "shared" {
  repository = aws_ecr_repository.shared.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images older than 30 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 30
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Keep last 50 tagged images"
        selection = {
          tagStatus   = "tagged"
          tagPatternList = ["*"]
          countType   = "imageCountMoreThan"
          countNumber = 50
        }
        action = {
          type = "expire"
        }
      },
    ]
  })
}

output "ecr_repository_url" {
  description = "ECR repository URL — feed to `docker tag` / `docker push`."
  value       = aws_ecr_repository.shared.repository_url
}

output "ecr_repository_arn" {
  description = "ECR repository ARN (for IAM policy resource references)."
  value       = aws_ecr_repository.shared.arn
}
