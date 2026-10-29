# Bucket de landing : le JSON brut de l'API Riot et les CSV d'Oracle's Elixir
# y atterrissent tels quels. Seuls les evenements utiles sont ensuite aplatis
# vers BigQuery - c'est ce qui protege les 10 Gio gratuits.
#
# ATTENTION : ce bucket n'est PAS couvert par le free tier BigQuery. Cloud
# Storage a son propre free tier, limite a us-east1, us-west1 et us-central1.
resource "google_storage_bucket" "landing" {
  # Un nom de bucket est unique au niveau MONDIAL : on le prefixe par l'ID du
  # projet pour eviter toute collision.
  name          = "${var.project_id}-landing"
  location      = var.region
  storage_class = "STANDARD"

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  # Refuse de detruire un bucket non vide : une erreur de terraform destroy ne
  # doit pas effacer des semaines de collecte.
  force_destroy = false

  # Le brut n'est pas garde indefiniment : cout de stockage, et les CGU de Riot
  # n'encouragent pas l'accumulation. Tant que le fichier existe, il peut etre
  # rejoue ; au-dela, seule la version aplatie dans BigQuery subsiste.
  lifecycle_rule {
    condition {
      age = var.landing_retention_days
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.apis]
}
