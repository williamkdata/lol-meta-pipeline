"""Client Oracle's Elixir : les matchs pro de la saison, un fichier par an."""

import hashlib

from oe_columns import OE_COLUMNS

DRIVE_FOLDER_ID = "1gLSw0RLjBbtaNy0dgnGQDAZOHIgCe-HH"
DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
TIMEOUT_S = 30


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
