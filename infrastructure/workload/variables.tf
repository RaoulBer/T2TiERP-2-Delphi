variable "project_id" { type = string }

variable "region" {
  type    = string
  default = "europe-west3"
}

variable "zone" {
  type    = string
  default = "europe-west3-c"
}

variable "prefix" {
  type = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,21}$", var.prefix))
    error_message = "Use an independent resource prefix with 3 to 22 characters."
  }
}

variable "bucket_name" { type = string }

variable "application_count" {
  type = number
  validation {
    condition     = contains([1, 2, 4], var.application_count)
    error_message = "Measured application topologies use 1, 2 or 4 hosts."
  }
}

variable "database_count" {
  type = number
  validation {
    condition     = contains([1, 2, 3, 4], var.database_count)
    error_message = "Measured database topologies use 1, 2, 3 or 4 hosts."
  }
}

variable "application_disk_type" {
  type    = string
  default = "pd-standard"
  validation {
    condition     = contains(["pd-standard", "pd-balanced"], var.application_disk_type)
    error_message = "Use a measured application disk type."
  }
}

variable "windows_image" {
  type    = string
  default = "projects/windows-cloud/global/images/family/windows-2025"
}

variable "private_cidr" {
  type    = string
  default = "10.88.0.0/24"
}
variable "runtime_service_account" { type = string }
