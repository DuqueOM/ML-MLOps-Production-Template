# ============================================================================
# Network topology (ADR-017 / PR-A1)
# ============================================================================
# Two modes:
#
#   network_mode = "managed"   → template creates VPC + subnetwork
#   network_mode = "existing"  → caller provides network_name + subnetwork_name
#
# Locals at the bottom expose `network_self_link` and `subnetwork_self_link`
# so compute.tf does not need to branch on the mode — it just references
# `local.network_self_link` regardless.
# ============================================================================

# ---------------------------------------------------------------------------
# Managed mode: create VPC + subnetwork with secondary ranges
# ---------------------------------------------------------------------------
# Why disable auto_create_subnetworks: auto-mode VPCs create a /20 subnet in
# every region, which (a) wastes CIDR space, (b) makes peering with on-prem
# painful, (c) mixes regions in the same VPC against ADR-001 single-region
# scope. Custom-mode VPC + explicit subnetwork is the GCP best practice.
resource "google_compute_network" "vpc" {
  count = var.network_mode == "managed" ? 1 : 0

  name                    = "${var.project_name}-vpc-${var.environment}"
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"

  # Avoid the v4 -> v5 provider change that flipped delete_default_routes_on_create
  # default. Explicit is safer in long-lived infra.
  delete_default_routes_on_create = false
}

# ---------------------------------------------------------------------------
# Subnetwork with secondary ranges for GKE Pods + Services (VPC-native).
# Secondary range names match the values referenced by ip_allocation_policy
# in compute.tf so a typo here surfaces at terraform plan time, not runtime.
# ---------------------------------------------------------------------------
resource "google_compute_subnetwork" "gke" {
  count = var.network_mode == "managed" ? 1 : 0

  name                     = "${var.project_name}-subnet-${var.environment}"
  ip_cidr_range            = var.subnetwork_cidr
  region                   = var.region
  network                  = google_compute_network.vpc[0].id
  private_ip_google_access = true

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = var.pods_cidr
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = var.services_cidr
  }

  # Enable VPC Flow Logs for forensics / drift investigation. Sample rate
  # 0.5 keeps cost bounded; flip to 1.0 in incident-mode.
  log_config {
    aggregation_interval = "INTERVAL_5_SEC"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }
}

# ---------------------------------------------------------------------------
# Existing mode: data lookups against caller-provided names
# ---------------------------------------------------------------------------
# Validation uses preconditions so a missing name fails plan with an
# actionable error rather than a confusing "data source not found".
data "google_compute_network" "existing" {
  count = var.network_mode == "existing" ? 1 : 0

  name    = var.network_name
  project = var.project_id

  lifecycle {
    postcondition {
      condition     = var.network_name != ""
      error_message = "network_mode='existing' requires var.network_name"
    }
  }
}

data "google_compute_subnetwork" "existing" {
  count = var.network_mode == "existing" ? 1 : 0

  name    = var.subnetwork_name
  region  = var.region
  project = var.project_id

  lifecycle {
    postcondition {
      condition     = var.subnetwork_name != ""
      error_message = "network_mode='existing' requires var.subnetwork_name"
    }
  }
}

# ---------------------------------------------------------------------------
# Locals — single source of truth consumed by compute.tf
# ---------------------------------------------------------------------------
locals {
  network_self_link = (
    var.network_mode == "managed"
    ? google_compute_network.vpc[0].self_link
    : data.google_compute_network.existing[0].self_link
  )

  subnetwork_self_link = (
    var.network_mode == "managed"
    ? google_compute_subnetwork.gke[0].self_link
    : data.google_compute_subnetwork.existing[0].self_link
  )

  # Secondary range names. In managed mode they are the names we just
  # created; in existing mode the caller's subnetwork must already define
  # secondary ranges with these names (documented requirement in README).
  pods_range_name     = var.network_mode == "managed" ? "pods" : "pods"
  services_range_name = var.network_mode == "managed" ? "services" : "services"
}
