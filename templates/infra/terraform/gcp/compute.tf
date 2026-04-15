# GKE Cluster
resource "google_container_cluster" "gke" {
  name                     = "${var.project_name}-gke-${var.environment}"
  location                 = var.region
  enable_autopilot         = false
  networking_mode          = "VPC_NATIVE"
  initial_node_count       = 1
  remove_default_node_pool = true

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  network_policy {
    enabled = true
  }

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = "172.16.0.0/28"
  }

  ip_allocation_policy {}

  release_channel {
    channel = "REGULAR"
  }
}

# Node Pool
resource "google_container_node_pool" "nodes" {
  name       = "${var.project_name}-node-pool"
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
      environment = var.environment
      managed-by  = "terraform"
    }
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }
}
