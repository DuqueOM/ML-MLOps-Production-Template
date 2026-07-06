# =============================================================================
# Edge Protection — AWS WAFv2 + Shield Standard (ADR-042, D-38)
# =============================================================================
# Optional — these resources are only useful once an adopter has wired the
# `edge-aws` Kustomize Component into an overlay's kustomization.yaml
# (templates/service/k8s/components/edge-aws/). `enable_edge_protection`
# defaults to false so a plain `terraform apply` does not silently start
# creating public-facing security infrastructure (mirrors D-35's
# local-first-by-default philosophy at the Terraform layer).
#
# One REGIONAL WAFv2 Web ACL per service in var.service_names. Unlike the GCP
# module, Terraform does NOT own the association to the load balancer here:
# the aws-load-balancer-controller creates the ALB dynamically from the
# Ingress resource, so the association happens via the K8s-side
# `alb.ingress.kubernetes.io/wafv2-acl-arn` annotation. Copy this file's
# `edge_wafv2_web_acl_arns` output into that annotation's {WAFV2_ACL_ARN}
# placeholder (see docs/runbooks/edge-protection-setup.md).
#
# Shield Standard requires no Terraform resource — AWS enables it
# automatically, at no cost, for any resource behind an ALB. Shield Advanced
# (paid, ~$3k/mo) is explicitly out of scope (ADR-042 §4).
#
# terraform apply of these resources is CONSULT in every environment,
# including dev — creates public exposure + real cost regardless of the
# environment label (rule 17-edge-protection.md, ADR-042 §2.2). Disabling or
# loosening a rule afterward is STOP in every environment, no exceptions.
# =============================================================================

resource "aws_wafv2_web_acl" "edge" {
  for_each = var.enable_edge_protection ? toset(var.service_names) : []

  name        = "${each.value}-edge-acl"
  description = "AWS WAFv2 edge protection for ${each.value} (ADR-042, D-38)"
  scope       = "REGIONAL"

  default_action {
    allow {}
  }

  # AWS Managed Rules — Core rule set (OWASP Top-10 coverage). `waf_mode`
  # starts at "count" so an adopter can observe the false-positive rate
  # against real traffic before graduating to "block" (see
  # docs/runbooks/edge-protection-setup.md).
  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 0

    override_action {
      dynamic "count" {
        for_each = var.waf_mode == "count" ? [1] : []
        content {}
      }
      dynamic "none" {
        for_each = var.waf_mode == "block" ? [1] : []
        content {}
      }
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${each.value}-common-rule-set"
      sampled_requests_enabled   = true
    }
  }

  # SQL injection managed rule group.
  rule {
    name     = "AWSManagedRulesSQLiRuleSet"
    priority = 1

    override_action {
      dynamic "count" {
        for_each = var.waf_mode == "count" ? [1] : []
        content {}
      }
      dynamic "none" {
        for_each = var.waf_mode == "block" ? [1] : []
        content {}
      }
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesSQLiRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${each.value}-sqli-rule-set"
      sampled_requests_enabled   = true
    }
  }

  # Per-IP rate limiting. WAFv2 rate-based rules evaluate over a fixed
  # 5-minute rolling window (an AWS API constraint, not a template choice) —
  # NOT directly comparable to the GCP module's 60-second window. Always
  # blocks (not throttled/429) once the threshold is crossed within the
  # window; AWS WAFv2 rate-based rules have no native "throttle" action.
  rule {
    name     = "RateLimitPerIP"
    priority = 2

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = var.rate_limit_requests_per_5min
        aggregate_key_type = "IP"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${each.value}-rate-limit"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${each.value}-edge-acl"
    sampled_requests_enabled   = true
  }
}

output "edge_wafv2_web_acl_arns" {
  description = "WAFv2 Web ACL ARNs, keyed by service — copy into the ALB Ingress's alb.ingress.kubernetes.io/wafv2-acl-arn annotation"
  value       = { for k, v in aws_wafv2_web_acl.edge : k => v.arn }
}
