data "google_compute_image" "windows" {
  project = split("/", var.windows_image)[1]
  name    = strcontains(var.windows_image, "/family/") ? null : split("/", var.windows_image)[4]
  family  = strcontains(var.windows_image, "/family/") ? split("/", var.windows_image)[5] : null
}

locals {
  nodes = merge(
    { for i in range(var.application_count) : "app-${i + 1}" => "application" },
    { for i in range(var.database_count) : "db-${i + 1}" => "database" }
  )
}

