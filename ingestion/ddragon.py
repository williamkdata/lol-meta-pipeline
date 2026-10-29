"""Client Data Dragon : le referentiel des champions, objets et runes, par patch."""

import requests

VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
TIMEOUT_S = 15
CDN_URL = "https://ddragon.leagueoflegends.com/cdn"
LANGUE = "en_US"


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
