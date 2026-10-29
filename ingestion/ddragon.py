"""Client Data Dragon : le referentiel des champions, objets et runes, par patch."""

import requests
from google.cloud import bigquery

from bigquery_loader import load_rows

VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
TIMEOUT_S = 15
CDN_URL = "https://ddragon.leagueoflegends.com/cdn"
LANGUE = "en_US"
CHAMPIONS_TABLE = "lol-meta-pipeline.lol_raw.ddragon_champions"

CHAMPIONS_SCHEMA = [
    bigquery.SchemaField("patch", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("version", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("champion_id", "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("champion_code", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("champion_name", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("title", "STRING"),
    bigquery.SchemaField("tags", "STRING", mode="REPEATED"),
]


def patch_of(version: str) -> str:
    """Le patch d'une version : ses deux premiers nombres. 16.21.1 -> 16.21."""
    parties = version.split(".")
    if len(parties) < 2:
        raise ValueError(f"version illisible : {version}")

    for partie in parties:
        if not partie.isdigit():
            raise ValueError(f"version illisible : {version}")

    return f"{parties[0]}.{parties[1]}"


def flatten_champions(payload: dict) -> list[dict]:
    """Une ligne par champion, a partir du fichier champion.json d'une version."""
    version = payload["version"]
    patch = patch_of(version)

    lignes = []
    for champion in payload["data"].values():
        lignes.append(
            {
                "patch": patch,
                "version": version,
                "champion_id": int(champion["key"]),
                "champion_code": champion["id"],
                "champion_name": champion["name"],
                "title": champion["title"],
                "tags": champion["tags"],
            }
        )
    return lignes


def fetch_versions() -> list[str]:
    """Les versions publiees par Data Dragon, la plus recente en premier."""
    reponse = requests.get(VERSIONS_URL, timeout=TIMEOUT_S)
    reponse.raise_for_status()

    versions = reponse.json()
    if not versions:
        raise ValueError("Data Dragon n'a renvoye aucune version")
    return versions


def fetch_champions(version: str) -> dict:
    """Le fichier champion.json d'une version, en anglais."""
    url = f"{CDN_URL}/{version}/data/{LANGUE}/champion.json"
    reponse = requests.get(url, timeout=TIMEOUT_S)
    reponse.raise_for_status()

    payload = reponse.json()
    if payload["version"] != version:
        raise ValueError(f"version demandee {version}, recue {payload['version']}")
    return payload


def season_versions(versions: list[str]) -> list[str]:
    """Les versions de la saison la plus recente, la plus recente en premier."""
    if not versions:
        raise ValueError("aucune version a trier")

    saison = versions[0].split(".")[0]
    retenues = []
    for version in versions:
        if version.split(".")[0] == saison:
            retenues.append(version)
    return retenues


def load_season(client) -> int:
    """Charge les champions de tous les patches de la saison en cours."""
    lignes = []
    for version in season_versions(fetch_versions()):
        lignes.extend(flatten_champions(fetch_champions(version)))
    return load_rows(lignes, CHAMPIONS_TABLE, CHAMPIONS_SCHEMA, client)


if __name__ == "__main__":
    client = bigquery.Client(project="lol-meta-pipeline")
    chargees = load_season(client)
    print(f"{chargees} lignes chargees dans {CHAMPIONS_TABLE}")
