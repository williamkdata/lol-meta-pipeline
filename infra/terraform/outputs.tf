output "landing_bucket" {
  description = "Bucket de landing du JSON et des CSV bruts."
  value       = google_storage_bucket.landing.name
}

output "pipeline_service_account" {
  description = "Compte de service d'Airflow et de dbt en production."
  value       = google_service_account.pipeline.email
}

output "job_image_repository" {
  description = "L'etagere d'images du job quotidien (pour docker push)."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.job.repository_id}"
}

output "riot_key_secret" {
  description = "Le coffre de la cle Riot (la valeur se colle dans la console, jamais ici)."
  value       = google_secret_manager_secret.riot_api_key.secret_id
}

output "datasets" {
  description = "Datasets BigQuery, par politique de retention."
  value = {
    raw        = google_bigquery_dataset.raw.dataset_id
    raw_ladder = google_bigquery_dataset.raw_ladder.dataset_id
    analytics  = google_bigquery_dataset.analytics.dataset_id
  }
}
