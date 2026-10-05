resource "google_service_account" "study" {
  account_id   = "${var.prefix}-runtime"
  display_name = "Sales experiment runtime"
}

resource "google_storage_bucket_iam_member" "read" {
  bucket = google_storage_bucket.study.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.study.email}"
}

resource "google_storage_bucket_iam_member" "create" {
  bucket = google_storage_bucket.study.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.study.email}"
}

