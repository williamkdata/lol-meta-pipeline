# Compte de service du pipeline : l'identite d'Airflow et de dbt en production.
#
# AUCUNE CLE n'est creee ici : une cle generee par Terraform finirait en clair
# dans le tfstate. Elle sera creee a la main avec gcloud, a l'etape ou Airflow
# en aura besoin, et rangee dans secrets/ (ignore par git).
resource "google_service_account" "pipeline" {
  account_id   = "lol-pipeline"
  display_name = "Pipeline LoL (Airflow local + dbt prod)"

  depends_on = [google_project_service.apis]
}

# Lancer des jobs (requetes, chargements) se donne au niveau du projet...
resource "google_project_iam_member" "pipeline_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

# ...mais lire et ecrire des tables se donne dataset par dataset. Le compte n'a
# aucun droit sur un dataset absent de cette liste.
resource "google_bigquery_dataset_iam_member" "pipeline_editor" {
  for_each = {
    raw        = google_bigquery_dataset.raw.dataset_id
    raw_ladder = google_bigquery_dataset.raw_ladder.dataset_id
    analytics  = google_bigquery_dataset.analytics.dataset_id
  }

  dataset_id = each.value
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.pipeline.email}"
}

# objectUser : lire, creer, REMPLACER et supprimer des objets, sans aucun droit
# sur le bucket lui-meme ni sur ses permissions.
# Le droit de remplacer compte : dans GCS, reecrire un objet existant est une
# suppression suivie d'une creation. Sans lui, rejouer une ingestion sur le
# meme nom de fichier echouerait.
resource "google_storage_bucket_iam_member" "pipeline_objects" {
  bucket = google_storage_bucket.landing.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.pipeline.email}"
}
