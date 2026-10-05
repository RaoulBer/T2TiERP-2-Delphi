resource "google_compute_instance" "node" {
  for_each     = local.nodes
  name         = "${var.prefix}-${each.key}"
  machine_type = "e2-standard-2"
  tags         = ["${var.prefix}-${each.value}"]
  boot_disk {
    auto_delete = true
    initialize_params {
      image = data.google_compute_image.windows.self_link
      size  = 80
      type  = each.value == "database" ? "pd-balanced" : var.application_disk_type
    }
  }
  network_interface {
    subnetwork = google_compute_subnetwork.study.id
  }
  service_account {
    email  = var.runtime_service_account
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }
  metadata = {
    "study-bucket"               = var.bucket_name
    "study-role"                 = each.key
    "windows-startup-script-ps1" = templatefile("${path.module}/../../reviewer/agent.ps1", { agent_script = filebase64("${path.module}/../../reviewer/runtime-agent.ps1") })
  }
  depends_on = [google_compute_router_nat.study]
}

