# =============================================================================
# AWS S3 buckets — parity with templates/infra/terraform/gcp/storage.tf
# (PR-R2-6, audit R2 §3.2). Layout mirrors GCP one-for-one:
#
#   ${project_name}-data-${env}              ↔ data
#   ${project_name}-models-${env}            ↔ models
#   ${project_name}-mlflow-artifacts-${env}  ↔ mlflow_artifacts
#   ${project_name}-access-logs-${env}       ↔ access logs (target bucket)
#
# Security defaults (each applies to every bucket below; we set them as
# discrete resources because aws_s3_bucket no longer accepts inline
# blocks for these — current AWS provider best practice):
#
#   * Block ALL public access (BlockPublicAcls + IgnorePublicAcls +
#     BlockPublicPolicy + RestrictPublicBuckets).
#   * SSE-KMS with a dedicated KMS key (rotation enabled).
#   * Object Ownership = BucketOwnerEnforced (disables ACLs entirely).
#   * Versioning enabled on every bucket except access-logs (logs are
#     append-only by design; versioning would balloon costs).
#   * Server-access logging on data/models/mlflow buckets, target =
#     access-logs bucket.
#   * Lifecycle rules on models bucket mirror GCS NEARLINE→DELETE:
#     archive to GLACIER_IR after `var.model_archive_days`, expire
#     versions after `var.model_delete_days`.
# =============================================================================

# Dedicated KMS key for S3 SSE. We use a separate key from the EKS
# Secrets key (compute.tf) so secret-data and bucket-data have
# independent rotation/audit boundaries.
resource "aws_kms_key" "s3" {
  description             = "${var.project_name}-s3-${var.environment} bucket SSE key (PR-R2-6)"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = {
    environment = var.environment
    managed-by  = "terraform"
    purpose     = "s3-sse"
  }
}

resource "aws_kms_alias" "s3" {
  name          = "alias/${var.project_name}-s3-${var.environment}"
  target_key_id = aws_kms_key.s3.key_id
}

# -----------------------------------------------------------------------------
# Bucket: data (raw + processed)
# -----------------------------------------------------------------------------
resource "aws_s3_bucket" "data" {
  bucket        = "${var.project_name}-data-${var.environment}"
  force_destroy = false

  tags = {
    environment = var.environment
    managed-by  = "terraform"
    purpose     = "data"
  }
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.s3.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_logging" "data" {
  bucket        = aws_s3_bucket.data.id
  target_bucket = aws_s3_bucket.access_logs.id
  target_prefix = "data/"
}

# -----------------------------------------------------------------------------
# Bucket: models (with NEARLINE-equivalent lifecycle)
# -----------------------------------------------------------------------------
resource "aws_s3_bucket" "models" {
  bucket        = "${var.project_name}-models-${var.environment}"
  force_destroy = false

  tags = {
    environment = var.environment
    managed-by  = "terraform"
    purpose     = "models"
  }
}

resource "aws_s3_bucket_public_access_block" "models" {
  bucket                  = aws_s3_bucket.models.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "models" {
  bucket = aws_s3_bucket.models.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "models" {
  bucket = aws_s3_bucket.models.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "models" {
  bucket = aws_s3_bucket.models.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.s3.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "models" {
  bucket = aws_s3_bucket.models.id

  # Mirrors GCP: NEARLINE after `model_archive_days`, then DELETE after
  # `model_delete_days`. AWS GLACIER_IR is the closest analogue to
  # NEARLINE on retrieval-cost trade-off; switch to GLACIER_FLEXIBLE
  # if archives are accessed less than monthly.
  rule {
    id     = "archive-and-expire"
    status = "Enabled"

    filter {} # apply to all objects

    transition {
      days          = var.model_archive_days
      storage_class = "GLACIER_IR"
    }

    expiration {
      days = var.model_delete_days
    }

    noncurrent_version_expiration {
      noncurrent_days = var.model_delete_days
    }
  }
}

resource "aws_s3_bucket_logging" "models" {
  bucket        = aws_s3_bucket.models.id
  target_bucket = aws_s3_bucket.access_logs.id
  target_prefix = "models/"
}

# -----------------------------------------------------------------------------
# Bucket: mlflow_artifacts
# -----------------------------------------------------------------------------
resource "aws_s3_bucket" "mlflow_artifacts" {
  bucket        = "${var.project_name}-mlflow-artifacts-${var.environment}"
  force_destroy = false

  tags = {
    environment = var.environment
    managed-by  = "terraform"
    purpose     = "mlflow-artifacts"
  }
}

resource "aws_s3_bucket_public_access_block" "mlflow_artifacts" {
  bucket                  = aws_s3_bucket.mlflow_artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "mlflow_artifacts" {
  bucket = aws_s3_bucket.mlflow_artifacts.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "mlflow_artifacts" {
  bucket = aws_s3_bucket.mlflow_artifacts.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "mlflow_artifacts" {
  bucket = aws_s3_bucket.mlflow_artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.s3.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_logging" "mlflow_artifacts" {
  bucket        = aws_s3_bucket.mlflow_artifacts.id
  target_bucket = aws_s3_bucket.access_logs.id
  target_prefix = "mlflow-artifacts/"
}

# -----------------------------------------------------------------------------
# Bucket: access_logs (target for server-access logging on the others)
# Versioning OFF — logs are append-only and versioning would multiply
# storage cost without forensic benefit. Lifecycle expiry parity with
# GCP (90 days).
# -----------------------------------------------------------------------------
resource "aws_s3_bucket" "access_logs" {
  bucket        = "${var.project_name}-access-logs-${var.environment}"
  force_destroy = false

  tags = {
    environment = var.environment
    managed-by  = "terraform"
    purpose     = "access-logs"
  }
}

resource "aws_s3_bucket_public_access_block" "access_logs" {
  bucket                  = aws_s3_bucket.access_logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "access_logs" {
  bucket = aws_s3_bucket.access_logs.id
  rule {
    # S3 server-access logging requires the LogDeliveryWrite ACL on the
    # target bucket; that is incompatible with BucketOwnerEnforced.
    # ObjectWriter keeps ACLs minimally enabled, restricted to the
    # log-delivery group via the bucket ACL below.
    object_ownership = "ObjectWriter"
  }
}

resource "aws_s3_bucket_acl" "access_logs" {
  depends_on = [aws_s3_bucket_ownership_controls.access_logs]
  bucket     = aws_s3_bucket.access_logs.id
  acl        = "log-delivery-write"
}

resource "aws_s3_bucket_server_side_encryption_configuration" "access_logs" {
  bucket = aws_s3_bucket.access_logs.id
  rule {
    apply_server_side_encryption_by_default {
      # SSE-S3 (AES256) instead of SSE-KMS — log delivery service does
      # not support customer KMS keys, so KMS would silently break
      # logging. AES256 is the documented AWS guidance.
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "access_logs" {
  bucket = aws_s3_bucket.access_logs.id
  rule {
    id     = "expire-old-logs"
    status = "Enabled"
    filter {}
    expiration {
      days = 90
    }
  }
}
