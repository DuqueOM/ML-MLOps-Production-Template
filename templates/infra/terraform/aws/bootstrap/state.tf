# ============================================================================
# Terraform state bucket (S3) + lock table (DynamoDB)
# ============================================================================
# Audit High-6 — per-environment state. The live layer's `backend "s3"`
# block in main.tf points at these resources via backend-configs/<env>.hcl.
#
# Why S3 + DynamoDB (not just S3): S3 provides eventual consistency
# guarantees that are insufficient for concurrent terraform applies.
# DynamoDB provides strong consistency for the lock; without it two
# operators can corrupt state.

# ----------------------------------------------------------------------------
# State bucket
# ----------------------------------------------------------------------------
resource "aws_s3_bucket" "tfstate" {
  bucket = "${var.project_name}-tfstate-${var.environment}"

  tags = {
    Name    = "${var.project_name}-tfstate-${var.environment}"
    purpose = "tfstate"
  }

  # Treat as PROTECTED — destroy from this dir would orphan the live state.
  lifecycle {
    prevent_destroy = true
  }
}

# Versioning catches accidental rollback / `terraform state rm`.
resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Server-side encryption with our KMS key (envelope encryption).
resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.tfstate.arn
    }
    bucket_key_enabled = true
  }
}

# Block all public access — state files contain resource IDs that should
# not be enumerable from outside the account.
resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Lifecycle: archive old non-current versions, delete after retention.
resource "aws_s3_bucket_lifecycle_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    id     = "expire-old-state-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = var.state_bucket_retention_days
    }
  }
}

# ----------------------------------------------------------------------------
# DynamoDB lock table
# ----------------------------------------------------------------------------
# Pay-per-request: state lock acquisitions are infrequent (handful per day),
# so on-demand pricing wins over provisioned capacity for this workload.
resource "aws_dynamodb_table" "tfstate_locks" {
  name         = "${var.project_name}-tfstate-lock-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  # SSE with our KMS key.
  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.tfstate.arn
  }

  # Point-in-time recovery enables 35-day rollback if the lock table is
  # deleted or corrupted (e.g. an errant `terraform force-unlock` storm).
  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name    = "${var.project_name}-tfstate-lock-${var.environment}"
    purpose = "tfstate-lock"
  }

  lifecycle {
    prevent_destroy = true
  }
}

# ----------------------------------------------------------------------------
# Outputs — paste into backend-configs/<env>.hcl
# ----------------------------------------------------------------------------
output "tfstate_bucket" {
  description = "S3 bucket for live-layer remote state."
  value       = aws_s3_bucket.tfstate.id
}

output "tfstate_lock_table" {
  description = "DynamoDB table for state locking."
  value       = aws_dynamodb_table.tfstate_locks.name
}

output "tfstate_kms_key_arn" {
  description = "KMS key ARN for envelope encryption."
  value       = aws_kms_key.tfstate.arn
}
