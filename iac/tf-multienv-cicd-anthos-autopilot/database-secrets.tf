# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

locals {
  database_environments = {
    development = {
      namespace                 = "bank-of-anthos-development"
      accounts_db_uri           = "postgresql://accounts-admin:accounts-pwd@accounts-db:5432/accounts-db"
      ledger_db_url             = "jdbc:postgresql://ledger-db:5432/postgresdb"
      ledger_db_username        = "admin"
      ledger_db_password        = "password"
    }
    staging = {
      namespace                 = "bank-of-anthos-staging"
      accounts_db_uri           = "postgresql://admin:admin@127.0.0.1:5432/accounts-db"
      ledger_db_url             = "jdbc:postgresql://127.0.0.1:5432/ledger-db"
      ledger_db_username        = "admin"
      ledger_db_password        = "admin"
    }
    production = {
      namespace                 = "bank-of-anthos-production"
      accounts_db_uri           = "postgresql://admin:admin@127.0.0.1:5432/accounts-db"
      ledger_db_url             = "jdbc:postgresql://127.0.0.1:5432/ledger-db"
      ledger_db_username        = "admin"
      ledger_db_password        = "admin"
    }
  }
}

resource "google_secret_manager_secret" "accounts_db_credentials" {
  for_each = local.database_environments

  project   = var.project_id
  secret_id = "accounts-db-credentials-${each.key}"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "accounts_db_credentials" {
  for_each = local.database_environments

  secret      = google_secret_manager_secret.accounts_db_credentials[each.key].id
  secret_data = jsonencode({ uri = each.value.accounts_db_uri })
}

resource "google_secret_manager_secret" "ledger_db_credentials" {
  for_each = local.database_environments

  project   = var.project_id
  secret_id = "ledger-db-credentials-${each.key}"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "ledger_db_credentials" {
  for_each = local.database_environments

  secret = google_secret_manager_secret.ledger_db_credentials[each.key].id
  secret_data = jsonencode({
    url      = each.value.ledger_db_url
    username = each.value.ledger_db_username
    password = each.value.ledger_db_password
  })
}

resource "google_service_account" "gke_userservice" {
  for_each = local.database_environments

  project    = var.project_id
  account_id = "gke-userservice-${each.key}"
}

resource "google_service_account" "gke_balancereader" {
  for_each = local.database_environments

  project    = var.project_id
  account_id = "gke-balancereader-${each.key}"
}

resource "google_service_account_iam_member" "userservice_workload_identity" {
  for_each = local.database_environments

  service_account_id = google_service_account.gke_userservice[each.key].id
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${each.value.namespace}/userservice]"
}

resource "google_service_account_iam_member" "balancereader_workload_identity" {
  for_each = local.database_environments

  service_account_id = google_service_account.gke_balancereader[each.key].id
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${each.value.namespace}/balancereader]"
}

resource "google_secret_manager_secret_iam_member" "userservice_accounts_db_accessor" {
  for_each = local.database_environments

  project   = var.project_id
  secret_id = google_secret_manager_secret.accounts_db_credentials[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.gke_userservice[each.key].email}"
}

resource "google_secret_manager_secret_iam_member" "balancereader_ledger_db_accessor" {
  for_each = local.database_environments

  project   = var.project_id
  secret_id = google_secret_manager_secret.ledger_db_credentials[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.gke_balancereader[each.key].email}"
}
