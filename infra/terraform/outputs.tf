output "landing_bucket" {
  description = "Bucket de landing du JSON et des CSV bruts."
  value       = google_storage_bucket.landing.name
}

output "pipeline_service_account" {
  description = "Compte de service d'Airflow et de dbt en production."
  value       = google_service_account.pipeline.email
}

output "datasets" {
  description = "Datasets BigQuery, par politique de retention."
  value = {
    raw        = google_bigquery_dataset.raw.dataset_id
    raw_ladder = google_bigquery_dataset.raw_ladder.dataset_id
    analytics  = google_bigquery_dataset.analytics.dataset_id
  }
}
