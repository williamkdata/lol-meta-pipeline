# Etape 6 de la sortie du PC (18/11/2026) : un courriel si le run quotidien
# echoue. Sans elle, un echec passe inapercu tant que personne ne regarde.
#
# Une alerte sur des lignes du journal ("log-based alert"). Prix verifie sur la
# page officielle le 18/11/2026 : gratuite jusqu'au 31/08/2027, puis 0,35 $ par
# mois (une condition). Accord de William le 18/11/2026.
#
# L'adresse vient de terraform.tfvars (ignore par git) : jamais dans le code.

resource "google_monitoring_notification_channel" "courriel" {
  count = var.deployer_le_job ? 1 : 0

  display_name = "Courriel du proprietaire du projet"
  type         = "email"
  labels = {
    email_address = var.alerte_courriel
  }

  depends_on = [google_project_service.apis]
}

resource "google_monitoring_alert_policy" "run_quotidien_echoue" {
  count = var.deployer_le_job ? 1 : 0

  display_name = "Run quotidien lol-quotidien en echec"
  combiner     = "OR"

  conditions {
    display_name = "Une etape echoue, le conteneur sort en erreur, ou le reveil ne lance pas le job"

    condition_matched_log {
      # Trois cas, une seule condition (donc un seul prix) :
      # 1. le bilan du chef d'orchestre (ingestion/quotidien.py) dit qu'une
      #    etape a echoue ou n'a pas ete lancee. Une etape echouee puis reussie
      #    a la relance ne declenche RIEN : seul le bilan final compte ;
      # 2. le conteneur sort avec un code different de 0, ou Cloud Run signale
      #    une erreur (plantage, delai de 14 h depasse) ;
      # 3. le reveil n'arrive pas a lancer le job (droits, job introuvable).
      # Pas de "\" dans les motifs : un "[^ ]+" plutot qu'un "\S+", pour ne
      # pas empiler les echappements de HCL et du langage de requete.
      filter = <<-EOT
        (
          resource.type="cloud_run_job"
          AND resource.labels.job_name="${google_cloud_run_v2_job.quotidien[0].name}"
          AND (
            textPayload=~"bilan : [^ ]+ (echouee|pas lancee)"
            OR (textPayload:"Container called exit(" AND NOT textPayload:"exit(0)")
            OR severity>=ERROR
          )
        )
        OR (
          resource.type="cloud_scheduler_job"
          AND resource.labels.job_id="${google_cloud_scheduler_job.quotidien[0].name}"
          AND severity>=ERROR
        )
      EOT
    }
  }

  alert_strategy {
    # Au plus un courriel par heure (obligatoire pour une alerte sur le
    # journal) : un run qui echoue ecrit plusieurs lignes d'erreur.
    notification_rate_limit {
      period = "3600s"
    }
    # L'incident se ferme seul au bout de 30 min (le minimum) : l'echec du
    # lendemain en ouvre un nouveau, donc un nouveau courriel.
    auto_close = "1800s"
  }

  notification_channels = [google_monitoring_notification_channel.courriel[0].name]

  documentation {
    mime_type = "text/markdown"
    content   = <<-EOT
      Le run quotidien de lol-meta-pipeline (job Cloud Run lol-quotidien) a echoue.

      1. Lire le journal du dernier run : console Google Cloud > Cloud Run > Jobs > lol-quotidien > Executions.
      2. Chercher la ligne "bilan : <etape> echouee" et l'erreur juste avant.
      3. Relancer a la main seulement apres avoir compris la cause (jamais en meme temps qu'un autre run).

      Explications : suivi/projets/projet3_explications.md, § 9.64 (retour au PC si besoin).
    EOT
  }
}
