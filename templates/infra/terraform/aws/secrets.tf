# =============================================================================
# AWS Secrets Manager — per-service secret entries (PR-R2-6, audit R2 §3.5).
#
# One Secrets Manager secret per (service × secret_name). The naming
# scheme `${project_name}/${service}/${secret}` matches the IAM
# resource scope in iam.tf, so a service can read only its own secrets.
#
# Rotation: gated behind var.enable_secret_rotation. Rotation in AWS
# requires a customer-supplied Lambda because the rotation logic is
# secret-shape-specific (RDS dual-user vs API key vs SSH key…). The
# template ships the AWS-managed RDS rotation lambdas, but for an
# api_key the operator must write their own. Defaulting to OFF avoids
# silently shipping a half-configured rotation that fails open.
#
# Encryption: every secret uses the dedicated KMS key from compute.tf
# (eks_secrets) — same key that envelope-encrypts K8s Secrets, so a
# single key revocation revokes both surfaces if a compromise demands
# it. Rotation is enabled on that key (compute.tf).
# =============================================================================

resource "aws_secretsmanager_secret" "service" {
  # Cartesian product of service_names × secret_names. Map key is
  # "<service>/<secret>" so for_each is stable across plans.
  for_each = {
    for pair in setproduct(var.service_names, var.secret_names) :
    "${pair[0]}/${pair[1]}" => {
      service = pair[0]
      secret  = pair[1]
    }
  }

  name        = "${var.project_name}/${each.value.service}/${each.value.secret}"
  description = "Secret '${each.value.secret}' for service '${each.value.service}' in ${var.environment}."
  kms_key_id  = aws_kms_key.eks_secrets.arn

  # 30-day recovery window matches AWS default. Setting 0 (immediate
  # delete) is reserved for the /secret-breach workflow which is a
  # STOP-class operation per ADR-014.
  recovery_window_in_days = 30

  tags = {
    environment = var.environment
    managed-by  = "terraform"
    service     = each.value.service
    secret      = each.value.secret
  }
}

# Rotation configuration — present only when the operator has wired a
# rotation Lambda. The for_each combines the gating var with the same
# product so we can index identically to aws_secretsmanager_secret.
resource "aws_secretsmanager_secret_rotation" "service" {
  for_each = var.enable_secret_rotation && var.rotation_lambda_arn != "" ? {
    for pair in setproduct(var.service_names, var.secret_names) :
    "${pair[0]}/${pair[1]}" => {
      service = pair[0]
      secret  = pair[1]
    }
  } : {}

  secret_id           = aws_secretsmanager_secret.service[each.key].id
  rotation_lambda_arn = var.rotation_lambda_arn

  rotation_rules {
    # 30-day cadence is the industry default for short-lived API keys.
    # RDS dual-user pattern usually rotates every 7 days; tune per
    # secret type by overriding rotation_lambda_arn + this block.
    automatically_after_days = 30
  }
}

# Plan-time guard: enabling rotation without supplying a Lambda ARN
# would create silently-broken rotation jobs in the AWS console.
resource "terraform_data" "validate_rotation_lambda" {
  count = var.enable_secret_rotation && var.rotation_lambda_arn == "" ? 1 : 0
  input = "ERROR: enable_secret_rotation=true requires rotation_lambda_arn (PR-R2-6)."

  lifecycle {
    precondition {
      condition     = !(var.enable_secret_rotation && var.rotation_lambda_arn == "")
      error_message = "enable_secret_rotation=true requires a non-empty rotation_lambda_arn (PR-R2-6)."
    }
  }
}

output "secret_arns" {
  description = "Map of '<service>/<secret>' → Secrets Manager ARN."
  value       = { for k, s in aws_secretsmanager_secret.service : k => s.arn }
  sensitive   = false # ARNs are not secret values
}
