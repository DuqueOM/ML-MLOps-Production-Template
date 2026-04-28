# GKE Cluster
#
# Network wiring (ADR-017 / PR-A1):
#   * `network` and `subnetwork` come from `local.*_self_link` defined in
#     network.tf. Whether the VPC was created here (managed mode) or
#     looked up via data source (existing mode) is invisible at this layer.
#   * Secondary ranges for pods + services are referenced by name; the
#     names match what network.tf creates in managed mode and what callers
#     MUST pre-create in their existing subnetwork.
resource "google_container_cluster" "gke" {
  name                     = "${var.project_name}-gke-${var.environment}"
  location                 = var.region
  networking_mode          = "VPC_NATIVE"
  initial_node_count       = 1
  remove_default_node_pool = true

  network    = local.network_self_link
  subnetwork = local.subnetwork_self_link

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  network_policy {
    enabled = true
  }

  # ADR-015 PR-A3 — control-plane reachability.
  # `enable_private_endpoint` is now opt-in (default false). When flipped
  # to true, kubectl reaches the master via VPC only — bastion / IAP /
  # VPN required. `master_authorized_networks_config` gates ALL public
  # control-plane access (relevant when enable_private_endpoint=false).
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = var.enable_private_endpoint
    master_ipv4_cidr_block  = "172.16.0.0/28"
  }

  dynamic "master_authorized_networks_config" {
    for_each = length(var.master_authorized_networks) > 0 ? [1] : []
    content {
      dynamic "cidr_blocks" {
        for_each = var.master_authorized_networks
        content {
          cidr_block   = cidr_blocks.value.cidr_block
          display_name = cidr_blocks.value.display_name
        }
      }
    }
  }

  ip_allocation_policy {
    cluster_secondary_range_name  = local.pods_range_name
    services_secondary_range_name = local.services_range_name
  }

  release_channel {
    channel = "REGULAR"
  }
}

# ============================================================================
# Node pools (ADR-015 PR-A3)
# ============================================================================
# Two pools by purpose:
#
#   system   — kube-system, monitoring, ingress controllers, Kyverno
#              (no taint; everything tolerates it)
#   workload — ML service pods (taint: workload-type=ml-services:NoSchedule)
#
# Why split:
#   * Blast radius: an OOM in a workload pod cannot evict kube-dns or the
#     Prometheus stateful set, because those land on system nodes.
#   * Cost: the system pool is small (e2-small, 1-2 nodes); the workload
#     pool autoscales independently with HPA-driven demand.
#   * Upgrades: surge upgrades on the workload pool don't disturb the
#     control-plane add-ons.
#
# ML services MUST set tolerations matching the workload taint:
#   tolerations:
#     - key: workload-type
#       operator: Equal
#       value: ml-services
#       effect: NoSchedule
# ============================================================================

# System pool — small, no taint; runs kube-system + cluster add-ons.
resource "google_container_node_pool" "system" {
  name       = "${var.project_name}-system-pool"
  location   = var.region
  cluster    = google_container_cluster.gke.name
  node_count = var.system_node_count

  autoscaling {
    min_node_count = 1
    max_node_count = 3
  }

  node_config {
    machine_type = var.system_machine_type
    disk_size_gb = 30
    disk_type    = "pd-standard"

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]

    labels = {
      environment   = var.environment
      managed-by    = "terraform"
      workload-type = "system"
    }
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }
}

# Workload pool — taint scheduled-only for ML services.
resource "google_container_node_pool" "workload" {
  name       = "${var.project_name}-workload-pool"
  location   = var.region
  cluster    = google_container_cluster.gke.name
  node_count = var.initial_node_count

  autoscaling {
    min_node_count = var.min_node_count
    max_node_count = var.max_node_count
  }

  node_config {
    machine_type = var.machine_type
    disk_size_gb = 50
    disk_type    = "pd-standard"

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]

    labels = {
      environment   = var.environment
      managed-by    = "terraform"
      workload-type = var.workload_node_taint_value
    }

    # NoSchedule taint — pods without a matching toleration cannot land here.
    # ML service Deployments must add the matching toleration (see PR-A3
    # docs in templates/k8s/base/deployment.yaml).
    taint {
      key    = var.workload_node_taint_key
      value  = var.workload_node_taint_value
      effect = "NO_SCHEDULE"
    }
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }
}
