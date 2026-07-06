# =============================================================================
# Edge Protection — Cloud Armor + SSL Policy (ADR-042, D-38)
# =============================================================================
# Optional — these resources are only useful once an adopter has wired the
# `edge-gcp` Kustomize Component into an overlay's kustomization.yaml
# (templates/service/k8s/components/edge-gcp/). `enable_edge_protection`
# defaults to false so a plain `terraform apply` does not silently start
# creating public-facing security infrastructure (mirrors D-35's
# local-first-by-default philosophy at the Terraform layer).
#
# One security policy + one SSL policy PER SERVICE in var.service_names,
# named to match exactly what the K8s-side BackendConfig/FrontendConfig CRDs
# reference: "${service}-edge-policy" / "${service}-ssl-policy" (see
# k8s/components/edge-gcp/backendconfig.yaml + frontendconfig.yaml).
#
# terraform apply of these resources is CONSULT in every environment,
# including dev — creates public exposure + real cost regardless of the
# environment label (rule 17-edge-protection.md, ADR-042 §2.2). Disabling or
# loosening a rule afterward is STOP in every environment, no exceptions.
# =============================================================================

resource "google_compute_security_policy" "edge" {
  for_each = var.enable_edge_protection ? toset(var.service_names) : []

  name        = "${each.value}-edge-policy"
  description = "Cloud Armor edge protection for ${each.value} (ADR-042, D-38)"
  project     = var.project_id

  # Default rule (required by the API, lowest priority): allow anything not
  # matched by a more specific rule below.
  rule {
    action   = "allow"
    priority = "2147483647"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "Default allow"
  }

  # OWASP Top-10 preconfigured WAF rules. `waf_mode` starts at "count" so an
  # adopter can observe the false-positive rate against real traffic before
  # graduating to "deny" (see docs/runbooks/edge-protection-setup.md).
  rule {
    action   = var.waf_mode
    priority = "1000"
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('sqli-v33-stable')"
      }
    }
    description = "SQL injection (OWASP)"
  }

  rule {
    action   = var.waf_mode
    priority = "1001"
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('xss-v33-stable')"
      }
    }
    description = "Cross-site scripting (OWASP)"
  }

  rule {
    action   = var.waf_mode
    priority = "1002"
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('lfi-v33-stable')"
      }
    }
    description = "Local file inclusion (OWASP)"
  }

  # Per-IP rate limiting — throttles (HTTP 429) rather than hard-blocks, so a
  # legitimate traffic spike degrades gracefully instead of a false-positive
  # lockout. Threshold is a starting point, not a tuned production value —
  # adjust per-service based on observed p99 request rate.
  rule {
    action   = "throttle"
    priority = "2000"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = var.rate_limit_requests_per_minute
        interval_sec = 60
      }
    }
    description = "Per-IP rate limit"
  }

  adaptive_protection_config {
    layer_7_ddos_defense_config {
      enable = true
    }
  }
}

resource "google_compute_ssl_policy" "edge" {
  for_each = var.enable_edge_protection ? toset(var.service_names) : []

  name            = "${each.value}-ssl-policy"
  project         = var.project_id
  profile         = "MODERN"
  min_tls_version = "TLS_1_2"
}

output "edge_security_policy_names" {
  description = "Cloud Armor security policy names, keyed by service — copy into BackendConfig (already wired by k8s/components/edge-gcp if names match)"
  value       = { for k, v in google_compute_security_policy.edge : k => v.name }
}

output "edge_ssl_policy_names" {
  description = "SSL policy names, keyed by service — copy into FrontendConfig (already wired by k8s/components/edge-gcp if names match)"
  value       = { for k, v in google_compute_ssl_policy.edge : k => v.name }
}
