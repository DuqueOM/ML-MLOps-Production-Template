# ============================================================================
# KMS key for state + future workload encryption
# ============================================================================
# Single key for the state bucket + DynamoDB lock table. Live-layer
# workloads (S3 data buckets, EKS Secrets envelope) get their OWN keys
# in their own files — keeps blast radius bounded if a key is rotated
# or compromised.

resource "aws_kms_key" "tfstate" {
  description             = "${var.project_name} Terraform state encryption (${var.environment})"
  enable_key_rotation     = true
  deletion_window_in_days = var.kms_key_deletion_window_days

  # Key policy: account root + future CI role.
  # Granting account root is the AWS-recommended pattern (without it,
  # IAM cannot delegate access via roles). The CI role's S3+DynamoDB
  # permissions automatically inherit the necessary kms:Decrypt /
  # kms:GenerateDataKey access via this principal.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "RootAccountAdmin"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "AllowS3Service"
        Effect = "Allow"
        Principal = {
          Service = "s3.amazonaws.com"
        }
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey",
        ]
        Resource = "*"
      },
      {
        Sid    = "AllowDynamoDBService"
        Effect = "Allow"
        Principal = {
          Service = "dynamodb.amazonaws.com"
        }
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey",
        ]
        Resource = "*"
      },
    ]
  })

  tags = {
    Name    = "${var.project_name}-tfstate-key-${var.environment}"
    purpose = "tfstate-encryption"
  }
}

resource "aws_kms_alias" "tfstate" {
  name          = "alias/${var.project_name}-tfstate-${var.environment}"
  target_key_id = aws_kms_key.tfstate.key_id
}

data "aws_caller_identity" "current" {}
