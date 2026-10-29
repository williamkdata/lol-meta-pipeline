# Un projet GCP neuf n'a aucune API active. Les activer ici plutot qu'a la main
# rend le projet reconstructible depuis le code seul.
#
# for_each cree UNE ressource par element de l'ensemble, chacune adressable
# separement : google_project_service.apis["bigquery.googleapis.com"].
resource "google_project_service" "apis" {
  for_each = toset([
    "bigquery.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
    # Telechargement d'Oracle's Elixir : le dossier public est sur Google
    # Drive. L'API, utilisee avec le compte de service, trouve le fichier par
    # son nom, connait sa date de modification et son empreinte MD5 — et
    # signale un quota depasse par un vrai statut d'erreur, la ou le
    # telechargement anonyme renvoyait une page web avec un statut 200.
    "drive.googleapis.com",
  ])

  service = each.value

  # Detruire cette ressource ne doit PAS couper l'API : d'autres objets du
  # projet pourraient en dependre.
  disable_on_destroy = false
}
