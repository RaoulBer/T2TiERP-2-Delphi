resource "google_compute_network" "study" {
  name                    = "${var.prefix}-network"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "study" {
  name          = "${var.prefix}-subnet"
  network       = google_compute_network.study.id
  ip_cidr_range = var.private_cidr
}

resource "google_compute_router" "study" {
  name    = "${var.prefix}-router"
  network = google_compute_network.study.id
}

resource "google_compute_router_nat" "study" {
  name                               = "${var.prefix}-nat"
  router                             = google_compute_router.study.name
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}

resource "google_compute_firewall" "database" {
  name          = "${var.prefix}-database"
  network       = google_compute_network.study.name
  source_ranges = [var.private_cidr]
  target_tags   = ["${var.prefix}-database"]
  allow {
    protocol = "tcp"
    ports    = ["3306", "33061"]
  }
}

resource "google_compute_firewall" "iap" {
  name          = "${var.prefix}-iap"
  network       = google_compute_network.study.name
  source_ranges = ["35.235.240.0/20"]
  allow {
    protocol = "tcp"
    ports    = ["3389"]
  }
}
