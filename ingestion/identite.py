"""L'identite Google du programme, sur le PC comme dans le cloud.

Sur le PC (Airflow en Docker) : le fichier cle du compte de service, monte en
lecture seule depuis secrets/.
Dans le cloud (job Cloud Run, decide le 18/11/2026) : aucun fichier. Google
fournit l'identite du compte de service a chaque run, comme un badge prete a
l'entree : les "identifiants par defaut". Un fichier cle de moins qui pourrait
fuiter.
"""

import os

import google.auth
from google.oauth2 import service_account

CLE_COMPTE_DE_SERVICE = os.environ.get("LOL_SA_KEY", "secrets/lol-pipeline-key.json")


def google_credentials(scopes: list[str], chemin_cle: str = CLE_COMPTE_DE_SERVICE):
    """L'identite a utiliser pour parler a Google (BigQuery, bucket, Drive).

    Le fichier cle s'il existe, sinon les identifiants par defaut.
    scopes : les droits demandes (cloud-platform ; drive.readonly pour Oracle's
    Elixir). Dans le cloud, l'acces a Drive avec les identifiants par defaut
    n'est PAS encore verifie : a tester au premier run (repli prevu :
    l'emprunt d'identite par le compte de service lui-meme).
    """
    if os.path.exists(chemin_cle):
        return service_account.Credentials.from_service_account_file(
            chemin_cle, scopes=scopes
        )
    # google.auth.default rend deux choses : l'identite et le projet. Le "_"
    # dit qu'on ne se sert pas du second.
    identite, _ = google.auth.default(scopes=scopes)
    return identite
