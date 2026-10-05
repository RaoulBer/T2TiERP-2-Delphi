variable "project_id" { type = string }

variable "region" {
  type    = string
  default = "europe-west3"
}

variable "prefix" {
  type = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,21}$", var.prefix))
    error_message = "Use an independent resource prefix with 3 to 22 characters."
  }
}

variable "bucket_name" { type = string }
