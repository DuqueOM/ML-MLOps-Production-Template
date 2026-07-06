# DNS — one record per service, pointing at that service's real cloud origin
# (a GCP static IP or an AWS ALB hostname; see variables.tf). Proxied
# (orange-cloud) so traffic actually flows through Cloudflare's edge and the
# WAF/rate-limit rules below apply — an unproxied (DNS-only) record would
# bypass this entire module.
resource "cloudflare_dns_record" "origin" {
  for_each = var.origin_by_service

  zone_id = var.cloudflare_zone_id
  name    = coalesce(lookup(var.dns_subdomain_by_service, each.key, null), each.key)
  type    = each.value.type
  content = each.value.hostname
  proxied = true
  ttl     = 1 # "Auto" — required by the API when proxied = true
}

# WAF — Cloudflare's managed ruleset (OWASP Top-10 + Cloudflare-curated CVEs),
# executed at the http_request_firewall_managed phase. `waf_mode` starts at
# "log" so an adopter can observe the false-positive rate against real
# traffic before graduating to "block" (docs/runbooks/edge-protection-setup.md).
resource "cloudflare_ruleset" "waf_managed" {
  zone_id     = var.cloudflare_zone_id
  name        = "edge-waf-managed"
  description = "Managed WAF rules (ADR-042, D-38)"
  kind        = "zone"
  phase       = "http_request_firewall_managed"

  rules = [
    {
      action      = "execute"
      description = "Execute Cloudflare Managed Ruleset"
      expression  = "true"
      enabled     = true
      action_parameters = {
        id = "efb7b8c949ac4650a09736fc376e9aee" # Cloudflare Managed Ruleset (stable ID, all zones)
        overrides = {
          action = var.waf_mode == "block" ? "block" : "log"
        }
      }
    }
  ]
}

# Rate limiting — per-IP, executed at the http_ratelimit phase. Blocks
# (429) once the threshold is crossed within the configured window, mirroring
# the throttle-not-hard-ban intent of the GCP/AWS modules (a legitimate spike
# gets a 429 the client can retry after, not a long-lived IP ban).
resource "cloudflare_ruleset" "rate_limit" {
  zone_id     = var.cloudflare_zone_id
  name        = "edge-rate-limit"
  description = "Per-IP rate limiting (ADR-042, D-38)"
  kind        = "zone"
  phase       = "http_ratelimit"

  rules = [
    {
      action      = "block"
      description = "Per-IP rate limit"
      expression  = "true"
      enabled     = true
      action_parameters = {
        response = {
          status_code  = 429
          content      = "{\"error\":\"rate limited\"}"
          content_type = "application/json"
        }
      }
      ratelimit = {
        characteristics     = ["ip.src"]
        period              = 10
        requests_per_period = var.rate_limit_requests_per_10s
        mitigation_timeout  = 10
      }
    }
  ]
}

# "I'm Under Attack" mode — off by default (see variables.tf docstring for
# why this is a STOP-class toggle, not a default posture).
resource "cloudflare_zone_setting" "under_attack_mode" {
  zone_id    = var.cloudflare_zone_id
  setting_id = "security_level"
  value      = var.under_attack_mode ? "under_attack" : "medium"
}

output "cloudflare_dns_records" {
  description = "Created DNS record names, keyed by service"
  value       = { for k, v in cloudflare_dns_record.origin : k => v.name }
}
