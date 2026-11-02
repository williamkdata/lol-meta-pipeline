"""Client Data Dragon : le referentiel des champions, objets et runes, par patch."""

import requests
from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from bigquery_loader import load_rows

VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
TIMEOUT_S = 15
CDN_URL = "https://ddragon.leagueoflegends.com/cdn"
LANGUE = "en_US"
CHAMPIONS_TABLE = "lol-meta-pipeline.lol_raw.ddragon_champions"
ITEMS_TABLE = "lol-meta-pipeline.lol_raw.ddragon_items"
RUNES_TABLE = "lol-meta-pipeline.lol_raw.ddragon_runes"

CHAMPIONS_SCHEMA = [
    bigquery.SchemaField("patch", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("version", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("champion_id", "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("champion_code", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("champion_name", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("title", "STRING"),
    bigquery.SchemaField("tags", "STRING", mode="REPEATED"),
]

# Une ligne par objet et par patch. builds_into vide = objet termine (il ne se
# transforme en rien) : c'est ce qui reperera les objets d'un build.
ITEMS_SCHEMA = [
    bigquery.SchemaField("patch", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("version", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("item_id", "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("item_name", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("gold_total", "INTEGER"),
    bigquery.SchemaField("purchasable", "BOOLEAN"),
    bigquery.SchemaField("on_summoners_rift", "BOOLEAN"),
    bigquery.SchemaField("builds_into", "INTEGER", mode="REPEATED"),
    bigquery.SchemaField("builds_from", "INTEGER", mode="REPEATED"),
    bigquery.SchemaField("depth", "INTEGER"),
    bigquery.SchemaField("tags", "STRING", mode="REPEATED"),
]

# Une ligne par rune et par patch. slot 0 = rangee des runes principales.
RUNES_SCHEMA = [
    bigquery.SchemaField("patch", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("version", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("rune_id", "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("rune_name", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("tree_id", "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("tree_name", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("slot", "INTEGER", mode="REQUIRED"),
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


def flatten_items(payload: dict) -> list[dict]:
    """Une ligne par objet, a partir du fichier item.json d'une version."""
    version = payload["version"]
    patch = patch_of(version)

    lignes = []
    # Les cles du dictionnaire "data" sont les numeros des objets, en texte.
    for item_id, objet in payload["data"].items():
        lignes.append(
            {
                "patch": patch,
                "version": version,
                "item_id": int(item_id),
                "item_name": objet["name"],
                "gold_total": objet["gold"]["total"],
                "purchasable": objet["gold"]["purchasable"],
                # La carte 11 est la Faille de l'invocateur.
                "on_summoners_rift": objet.get("maps", {}).get("11", False),
                "builds_into": [int(i) for i in objet.get("into", [])],
                "builds_from": [int(i) for i in objet.get("from", [])],
                "depth": objet.get("depth"),
                "tags": objet.get("tags", []),
            }
        )
    return lignes


def flatten_runes(version: str, arbres: list[dict]) -> list[dict]:
    """Une ligne par rune, a partir de runesReforged.json : une liste d'arbres
    (Domination, Inspiration...), chacun fait de rangees de runes."""
    patch = patch_of(version)

    lignes = []
    for arbre in arbres:
        for rangee, slot in enumerate(arbre["slots"]):
            for rune in slot["runes"]:
                lignes.append(
                    {
                        "patch": patch,
                        "version": version,
                        "rune_id": rune["id"],
                        "rune_name": rune["name"],
                        "tree_id": arbre["id"],
                        "tree_name": arbre["name"],
                        "slot": rangee,
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


def _fetch_json(version: str, fichier: str):
    """Un fichier de donnees d'une version, en anglais."""
    url = f"{CDN_URL}/{version}/data/{LANGUE}/{fichier}"
    reponse = requests.get(url, timeout=TIMEOUT_S)
    reponse.raise_for_status()
    return reponse.json()


def _check_version(payload: dict, version: str) -> dict:
    """Refuse un fichier d'une autre version que celle demandee."""
    if payload["version"] != version:
        raise ValueError(f"version demandee {version}, recue {payload['version']}")
    return payload


def fetch_champions(version: str) -> dict:
    """Le fichier champion.json d'une version, en anglais."""
    return _check_version(_fetch_json(version, "champion.json"), version)


def fetch_items(version: str) -> dict:
    """Le fichier item.json d'une version, en anglais."""
    return _check_version(_fetch_json(version, "item.json"), version)


def fetch_runes(version: str) -> list[dict]:
    """Le fichier runesReforged.json d'une version. C'est une liste, sans champ
    version : on ne peut pas la verifier comme les deux autres."""
    return _fetch_json(version, "runesReforged.json")


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


def missing_versions(saison: list[str], deja_chargees: set[str]) -> list[str]:
    """Les versions de la saison qui ne sont pas encore dans BigQuery."""
    manquantes = []
    for version in saison:
        if version not in deja_chargees:
            manquantes.append(version)
    return manquantes


def loaded_versions(client, table: str = CHAMPIONS_TABLE) -> set[str]:
    """Les versions deja presentes dans la table. Vide si la table n'existe pas."""
    sql = f"SELECT DISTINCT version FROM `{table}`"
    try:
        lignes = client.query(sql).result()
    except NotFound:
        return set()
    return {ligne["version"] for ligne in lignes}


def _load_missing(client, table: str, schema: list, lignes_de) -> int:
    """Charge les patches de la saison absents de `table`. `lignes_de` est une
    FONCTION : elle recoit une version et rend ses lignes aplaties."""
    a_charger = missing_versions(
        season_versions(fetch_versions()), loaded_versions(client, table)
    )
    lignes = []
    for version in a_charger:
        lignes.extend(lignes_de(version))
    return load_rows(lignes, table, schema, client)


def _champions_of(version: str) -> list[dict]:
    return flatten_champions(fetch_champions(version))


def _items_of(version: str) -> list[dict]:
    return flatten_items(fetch_items(version))


def _runes_of(version: str) -> list[dict]:
    return flatten_runes(version, fetch_runes(version))


def load_season(client) -> int:
    """Charge les champions des patches de la saison PAS ENCORE charges."""
    return _load_missing(client, CHAMPIONS_TABLE, CHAMPIONS_SCHEMA, _champions_of)


def load_items_season(client) -> int:
    """Charge les objets des patches de la saison PAS ENCORE charges."""
    return _load_missing(client, ITEMS_TABLE, ITEMS_SCHEMA, _items_of)


def load_runes_season(client) -> int:
    """Charge les runes des patches de la saison PAS ENCORE charges."""
    return _load_missing(client, RUNES_TABLE, RUNES_SCHEMA, _runes_of)


if __name__ == "__main__":
    client = bigquery.Client(project="lol-meta-pipeline")
    print(f"{load_season(client)} lignes chargees dans {CHAMPIONS_TABLE}")
    print(f"{load_items_season(client)} lignes chargees dans {ITEMS_TABLE}")
    print(f"{load_runes_season(client)} lignes chargees dans {RUNES_TABLE}")
