# Hosts GuardGap itself. Assumes an existing Cloud SQL PostgreSQL instance,
# database/user, and Secret Manager secrets; does not provision a billable database.
terraform {
  required_version = ">= 1.6"
  required_providers {
    google = { source = "hashicorp/google", version = ">= 6.0, < 8.0" }
  }
}
provider "google" {
  project = var.project_id
  region  = var.region
}
variable "project_id" { type = string }
variable "region" {
  type    = string
  default = "us-central1"
}
variable "image" { type = string }
variable "cloud_sql_connection_name" { type = string }
variable "database_url_secret" { type = string }
variable "admin_password_hash_secret" { type = string }
variable "public_login_endpoint" {
  type    = bool
  default = false
}
resource "google_service_account" "guardgap" {
  account_id   = "guardgap-server"
  display_name = "GuardGap service"
}
resource "google_project_iam_member" "cloudsql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.guardgap.email}"
}
resource "google_secret_manager_secret_iam_member" "database" {
  secret_id = var.database_url_secret
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.guardgap.email}"
}
resource "google_secret_manager_secret_iam_member" "admin" {
  secret_id = var.admin_password_hash_secret
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.guardgap.email}"
}
resource "google_cloud_run_v2_service" "guardgap" {
  name     = "guardgap"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"
  template {
    service_account = google_service_account.guardgap.email
    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }
    volumes {
      name = "cloudsql"
      cloud_sql_instance { instances = [var.cloud_sql_connection_name] }
    }
    containers {
      image = var.image
      ports { container_port = 8000 }
      resources { limits = { cpu = "1", memory = "512Mi" } }
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = var.database_url_secret
            version = "latest"
          }
        }
      }
      env {
        name = "GUARDGAP_ADMIN_PASSWORD_HASH"
        value_source {
          secret_key_ref {
            secret  = var.admin_password_hash_secret
            version = "latest"
          }
        }
      }
      env {
        name  = "GUARDGAP_SECURE_COOKIE"
        value = "true"
      }
      env {
        name  = "GUARDGAP_DEMO"
        value = "false"
      }
    }
  }
  depends_on = [google_project_iam_member.cloudsql, google_secret_manager_secret_iam_member.database, google_secret_manager_secret_iam_member.admin]
}
resource "google_cloud_run_v2_service_iam_member" "public" {
  count    = var.public_login_endpoint ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.guardgap.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
output "guardgap_url" { value = google_cloud_run_v2_service.guardgap.uri }
