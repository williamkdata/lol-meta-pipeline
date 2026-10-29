"""Client Oracle's Elixir : les matchs pro de la saison, un fichier par an."""

import hashlib
import re

from google.cloud import bigquery

from oe_columns import OE_COLUMNS

DRIVE_FOLDER_ID = "1gLSw0RLjBbtaNy0dgnGQDAZOHIgCe-HH"
DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
TIMEOUT_S = 30
OE_TABLE = "lol-meta-pipeline.lol_raw.oe_matches"


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
