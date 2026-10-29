"""Client Oracle's Elixir : les matchs pro de la saison, un fichier par an."""

import hashlib
import os
import re
from datetime import date

from google.auth.transport.requests import AuthorizedSession
from google.cloud import bigquery, storage
from google.oauth2 import service_account

from landing import upload_to_gcs
from oe_columns import OE_COLUMNS

DRIVE_FOLDER_ID = "1gLSw0RLjBbtaNy0dgnGQDAZOHIgCe-HH"
DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
TIMEOUT_S = 30
OE_TABLE = "lol-meta-pipeline.lol_raw.oe_matches"
CLE_COMPTE_DE_SERVICE = os.environ.get("LOL_SA_KEY", "secrets/lol-pipeline-key.json")
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/cloud-platform",
]


def check_header(contenu: str) -> None:
    """Verifie que le contenu telecharge est bien le CSV d'Oracle's Elixir."""
    premiere_ligne = contenu.split("\n", 1)[0].rstrip("\r")

    if premiere_ligne.startswith("<"):
        raise ValueError("page web recue au lieu du CSV : quota Google Drive ?")

    colonnes = premiere_ligne.split(",")
    if colonnes != OE_COLUMNS:
        ajoutees = sorted(set(colonnes) - set(OE_COLUMNS))
        disparues = sorted(set(OE_COLUMNS) - set(colonnes))
        raise ValueError(
            f"en-tete inattendu : ajoutees {ajoutees}, disparues {disparues}"
        )


def bq_column_name(nom: str) -> str:
    """Le nom d'une colonne du fichier, rendu acceptable par BigQuery."""
    return re.sub(r"[^A-Za-z0-9_]+", "_", nom).strip("_")


def find_season_file(annee: int, session) -> dict:
    """La fiche Drive du fichier d'une annee : identifiant, date, taille, empreinte."""
    nom = f"{annee}_LoL_esports_match_data_from_OraclesElixir.csv"
    recherche = f"'{DRIVE_FOLDER_ID}' in parents and name = '{nom}' and trashed = false"
    reponse = session.get(
        DRIVE_FILES_URL,
        params={
            "q": recherche,
            "fields": "files(id,name,modifiedTime,size,md5Checksum)",
        },
        timeout=TIMEOUT_S,
    )
    reponse.raise_for_status()

    fichiers = reponse.json()["files"]
    if len(fichiers) != 1:
        raise ValueError(f"{len(fichiers)} fichier(s) nomme(s) {nom}, 1 attendu")
    return fichiers[0]


def download_file(fiche: dict, session) -> bytes:
    """Telecharge le fichier decrit par sa fiche, et verifie qu'il est intact."""
    reponse = session.get(
        f"{DRIVE_FILES_URL}/{fiche['id']}",
        params={"alt": "media"},
        timeout=TIMEOUT_S,
    )
    reponse.raise_for_status()
    contenu = reponse.content

    attendu = int(fiche["size"])
    if len(contenu) != attendu:
        raise ValueError(f"taille recue {len(contenu)} octets, attendue {attendu}")

    if hashlib.md5(contenu).hexdigest() != fiche["md5Checksum"]:
        raise ValueError("empreinte MD5 differente : fichier abime en route")

    check_header(contenu.decode("utf-8"))
    return contenu


OE_SCHEMA = [
    bigquery.SchemaField(bq_column_name(colonne), "STRING") for colonne in OE_COLUMNS
]


def load_oe(adresse: str, lignes_attendues: int, client) -> int:
    """Remplace la table brute par le fichier de la saison depose dans le bucket."""
    config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        schema=OE_SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    job = client.load_table_from_uri(adresse, OE_TABLE, job_config=config)
    job.result()

    if job.output_rows != lignes_attendues:
        raise RuntimeError(
            f"{lignes_attendues} lignes attendues, {job.output_rows} chargees"
        )
    return job.output_rows


def load_season_file(annee: int, session, storage_client, bq_client) -> int:
    """Telecharge le fichier de la saison, le depose dans le bucket, le charge."""
    fiche = find_season_file(annee, session)
    contenu = download_file(fiche, session)

    jour = fiche["modifiedTime"][:10]
    chemin = f"oracles_elixir/{annee}/{jour}.csv.gz"
    adresse = upload_to_gcs(contenu, chemin, storage_client)

    lignes_attendues = contenu.count(b"\n") - 1
    return load_oe(adresse, lignes_attendues, bq_client)


if __name__ == "__main__":
    identite = service_account.Credentials.from_service_account_file(
        CLE_COMPTE_DE_SERVICE, scopes=SCOPES
    )
    chargees = load_season_file(
        date.today().year,
        AuthorizedSession(identite),
        storage.Client(project="lol-meta-pipeline", credentials=identite),
        bigquery.Client(project="lol-meta-pipeline", credentials=identite),
    )
    print(f"{chargees} lignes chargees dans {OE_TABLE}")
