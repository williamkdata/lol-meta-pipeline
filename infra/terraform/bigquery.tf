# Un dataset par POLITIQUE DE RETENTION, pas par source. Melanger des tables qui
# expirent et des tables permanentes dans un meme dataset, c'est s'exposer a
# perdre un referentiel sans le moindre message.

# Referentiel et donnees pro : Data Dragon (champions, items, runes par patch)
# et Oracle's Elixir. Volume faible, historique precieux : aucune expiration.
resource "google_bigquery_dataset" "raw" {
  dataset_id  = "lol_raw"
  location    = var.region
  description = "Brut permanent : Data Dragon et Oracle's Elixir. Aucune expiration."

  depends_on = [google_project_service.apis]
}

# Evenements aplatis de la ladder EUW : le gros volume, en fenetre glissante.
#
# PIEGE : default_partition_expiration_ms est une valeur PAR DEFAUT, recopiee
# dans chaque table partitionnee AU MOMENT DE SA CREATION.
#   - modifier la variable plus tard ne change rien aux tables existantes ;
#   - une table NON partitionnee creee ici n'expire jamais.
# C'est le meme mecanisme qui a vide velib_raw sur le projet Velib', sans
# aucun message.
resource "google_bigquery_dataset" "raw_ladder" {
  dataset_id  = "lol_raw_ladder"
  location    = var.region
  description = "Evenements aplatis de la ladder EUW (API Riot). Fenetre glissante par partition."

  default_partition_expiration_ms = var.ladder_retention_days * 24 * 60 * 60 * 1000

  depends_on = [google_project_service.apis]
}

# Modeles dbt de production, ecrits par le compte de service d'Airflow.
# Le developpement local ecrit dans lol_analytics_dev, cree par dbt lui-meme.
resource "google_bigquery_dataset" "analytics" {
  dataset_id  = "lol_analytics"
  location    = var.region
  description = "Modeles dbt (staging, intermediate, marts) - production."

  depends_on = [google_project_service.apis]
}
