# Le run quotidien dans le cloud (18/11/2026) : un job Cloud Run reveille
# chaque jour par Cloud Scheduler. Le PC n'a plus besoin d'etre allume.
#
# En DEUX TEMPS (variable deployer_le_job) :
#   1. false : l'etagere d'images, le coffre (vide) de la cle Riot, les droits.
#      Puis : l'image est deposee sur l'etagere, et William colle la cle Riot
#      dans le coffre (console Google). La valeur n'est JAMAIS dans Terraform :
#      elle finirait en clair dans le tfstate.
#   2. true : le job (qui a besoin de l'image et de la cle) et le reveil,
#      EN PAUSE tant que la bascule n'est pas faite (variable reveil_en_pause).
#
# Couts verifies sur les pages officielles le 18/11/2026 : niveau gratuit des
# jobs Cloud Run (240 000 vCPU-secondes, 450 000 Gio-secondes par mois et par
# compte de facturation) ; 3 reveils gratuits ; 0,5 Gio d'images gratuit.
# Un run (~1 h, 1 vCPU, 2 Gio) : ~47 % et ~50 % du gratuit sur un mois.

# --- L'etagere d'images -------------------------------------------------------
resource "google_artifact_registry_repository" "job" {
  location      = var.region
  repository_id = "lol-job"
  format        = "DOCKER"
  description   = "Images du job quotidien (job/Dockerfile)."

  # Le stockage gratuit est de 0,5 Gio ; l'image pese ~250 Mo compressee.
  # On garde les 3 dernieres versions (pour revenir en arriere), on supprime
  # le reste. Une regle KEEP l'emporte toujours sur une regle DELETE.
  cleanup_policy_dry_run = false
  cleanup_policies {
    id     = "garder-les-3-dernieres"
    action = "KEEP"
    most_recent_versions {
      keep_count = 3
    }
  }
  cleanup_policies {
    id     = "supprimer-les-autres"
    action = "DELETE"
    condition {
      tag_state = "ANY"
    }
  }

  depends_on = [google_project_service.apis]
}

# --- Le coffre de la cle Riot (vide) ------------------------------------------
resource "google_secret_manager_secret" "riot_api_key" {
  secret_id = "riot-api-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

# Le compte de service du pipeline (l'identite du job) peut LIRE la cle, et
# rien d'autre dans le coffre.
resource "google_secret_manager_secret_iam_member" "pipeline_riot_key" {
  secret_id = google_secret_manager_secret.riot_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.pipeline.email}"
}

# --- Le job ---------------------------------------------------------------------
resource "google_cloud_run_v2_job" "quotidien" {
  count = var.deployer_le_job ? 1 : 0

  name     = "lol-quotidien"
  location = var.region

  template {
    task_count = 1

    template {
      # L'identite du job : le meme compte de service qu'Airflow, avec les
      # memes droits (BigQuery, bucket) plus la lecture de la cle Riot.
      service_account = google_service_account.pipeline.email

      # Par defaut, Cloud Run coupe un essai au bout de 10 MINUTES. Le pire
      # jour (toutes les relances, dont 3 pauses de 2 h d'Oracle's Elixir et
      # un ladder relance deux fois) : ~13 h. Maximum permis : 168 h.
      timeout = "50400s"

      # Aucune relance par Cloud Run : le chef d'orchestre gere deja les
      # relances, etape par etape. Une relance du job entier recollecterait
      # tout et consommerait le quota Riot pour rien.
      max_retries = 0

      containers {
        image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.job.repository_id}/lol-job:${var.job_image_tag}"

        resources {
          limits = {
            cpu = "1"
            # 2 Gio : le texte du jeu (32 Mo de JSON) devient plusieurs
            # centaines de Mo une fois lu par Python, le jour d'un patch.
            memory = "2Gi"
          }
        }

        # La cle Riot, lue dans le coffre au demarrage de chaque run. Le client
        # Riot la cherche d'abord dans cette variable d'environnement.
        env {
          name = "RIOT_API_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.riot_api_key.secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  depends_on = [google_secret_manager_secret_iam_member.pipeline_riot_key]
}

# --- Le reveil --------------------------------------------------------------------
# Une identite a part pour le reveil : il peut lancer CE job, rien d'autre.
resource "google_service_account" "reveil" {
  account_id   = "lol-reveil"
  display_name = "Reveil du job quotidien (Cloud Scheduler)"

  depends_on = [google_project_service.apis]
}

resource "google_cloud_run_v2_job_iam_member" "reveil_lance_le_job" {
  count = var.deployer_le_job ? 1 : 0

  name     = google_cloud_run_v2_job.quotidien[0].name
  location = var.region
  # "Demandeur Cloud Run" : suffit pour lancer un job (documentation
  # officielle, "Executer des jobs selon un calendrier", lue le 18/11/2026).
  role   = "roles/run.invoker"
  member = "serviceAccount:${google_service_account.reveil.email}"
}

resource "google_cloud_scheduler_job" "quotidien" {
  count = var.deployer_le_job ? 1 : 0

  name      = "lol-quotidien"
  region    = var.region
  schedule  = "30 14 * * *"
  time_zone = "Etc/UTC"

  # En pause tant que la bascule n'est pas faite : jamais deux collectes en
  # meme temps (PC et cloud), elles partagent la meme cle et le meme quota.
  paused = var.reveil_en_pause

  # Le reveil ne relance pas : en cas d'echec, le job a deja tout tente.
  # C'est le comportement PAR DEFAUT (retryCount = 0, documentation de l'API
  # Cloud Scheduler, lue le 18/11/2026). Pas de bloc retry_config : Google ne
  # renvoie pas une valeur par defaut, et Terraform voyait un ecart a chaque
  # plan (constate apres le premier apply).

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.quotidien[0].name}:run"

    oauth_token {
      service_account_email = google_service_account.reveil.email
    }
  }

  depends_on = [google_cloud_run_v2_job_iam_member.reveil_lance_le_job]
}
