variable "cloudflare_api_token" {
  description = <<-EOT
    Cloudflare API token scoped to Zone:Edit + DNS:Edit for the target zone
    only (never a Global API Key — least-privilege, matching this
    template's general no-static-broad-creds stance, D-17/D-18). Pass via
    TF_VAR_cloudflare_api_token or a CI secret, never committed to tfvars.
  EOT
  type        = string
  sensitive   = true
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID for the domain this module protects. Find via: cloudflare zones list, or the dashboard's zone overview sidebar."
  type        = string
}

variable "origin_by_service" {
  description = <<-EOT
    One entry per service this zone fronts, keyed by service name (matching
    var.service_names in the gcp/aws modules for consistency). Each value
    points at that service's real origin:
      - GCP Ingress origin: type = "A", hostname = the static IP reserved
        for the GCE Ingress (see `gcloud compute addresses list`).
      - AWS ALB origin: type = "CNAME", hostname = the ALB's DNS name
        (see `kubectl get ingress <name> -o jsonpath='{.status.loadBalancer}'`).
    Example:
      {
        "fraud-detector" = { type = "A", hostname = "203.0.113.10" }
      }
  EOT
  type = map(object({
    type     = string
    hostname = string
  }))
  default = {}
}

variable "dns_subdomain_by_service" {
  description = <<-EOT
    DNS record name (without the zone apex) to create per service, e.g.
    "fraud-detector" creates "fraud-detector.<your-zone>". Defaults to the
    service name itself when not overridden.
  EOT
  type        = map(string)
  default     = {}
}

variable "waf_mode" {
  description = <<-EOT
    Action for the managed WAF ruleset: "log" (observe matches, take no
    action — the recommended starting point to measure false positives
    against real traffic) or "block" (actually block). See
    docs/runbooks/edge-protection-setup.md for the graduation process.
  EOT
  type        = string
  default     = "log"

  validation {
    condition     = contains(["log", "block"], var.waf_mode)
    error_message = "waf_mode must be 'log' or 'block'."
  }
}

variable "rate_limit_requests_per_10s" {
  description = <<-EOT
    Per-IP request threshold over a 10-second window before Cloudflare
    responds 429. Starting point only — tune per service based on observed
    traffic. NOTE: a third, DIFFERENT window/mechanism from both the GCP
    module's 60-second Cloud Armor window and the AWS module's 5-minute
    WAFv2 window — see the cloud-equivalence matrix in
    docs/runbooks/edge-protection-setup.md.
  EOT
  type        = number
  default     = 100
}

variable "under_attack_mode" {
  description = <<-EOT
    Enables Cloudflare's "I'm Under Attack" JS challenge on every request.
    Defaults to false — this adds a multi-second interstitial challenge for
    EVERY visitor including legitimate ones, so it is only appropriate
    during an active volumetric event, not as a default posture. Toggling
    this on/off is itself a STOP-class action (rule 17-edge-protection.md,
    ADR-042 §2.2) since it changes what "protected" means for every visitor.
  EOT
  type        = bool
  default     = false
}
