"""Un apercu du PBE, le serveur de test de Riot (18/11/2026).

Le prochain patch y est teste pendant environ deux semaines avant sa sortie.
CommunityDragon publie ses fichiers dans un dossier "pbe", a cote des dossiers
par patch. L'apercu sert a predire un patch AVANT qu'il sorte (bulletin de
patch, mart_patch_predictions).

Jamais dans les vraies tables : la collecte des kits saute les patches deja en
base, et le vrai patch serait ignore le jour de sa sortie.
"""

import logging

import requests
from google.cloud import bigquery

from bigquery_loader import load_rows
from ddragon import fetch_versions, patch_of, season_versions
from item_stats import ITEM_STATS_SCHEMA, flatten_item_stats, item_stats_url
from kits import (
    CDRAGON_URL,
    KIT_DATASET,
    KIT_SCHEMAS,
    TIMEOUT_S,
    champion_file_url,
    champions_of,
    kit_rows,
    loaded_kit_patches,
)

journal = logging.getLogger(__name__)

PBE_DOSSIER = "pbe"
PBE_METADONNEES_URL = f"{CDRAGON_URL}/{PBE_DOSSIER}/content-metadata.json"

# Des tables A PART, a cote des vraies, avec les memes schemas. Chargees dans
# cet ordre ; remplacees a chaque fois (une seule version du PBE a la fois).
PBE_TABLES = {
    "values": f"{KIT_DATASET}.pbe_kit_data_values",
    "parts": f"{KIT_DATASET}.pbe_kit_formula_parts",
    "item_stats": f"{KIT_DATASET}.pbe_item_stats",
}
PBE_SCHEMAS = {
    "values": KIT_SCHEMAS["values"],
    "parts": KIT_SCHEMAS["parts"],
    "item_stats": ITEM_STATS_SCHEMA,
}


def pbe_patch(metadonnees: dict) -> str:
    """Le patch que le PBE prepare, d'apres son content-metadata.json.

    "16.24.8394663+branch.main.content.beta" -> "16.24". Ce qui suit le "+"
    decrit la branche de fabrication, pas le patch : on le coupe, puis
    patch_of garde les deux premiers nombres (et refuse le reste)."""
    version = metadonnees["version"].split("+", 1)[0]
    return patch_of(version)


def pbe_preview_rows(patch: str, champions, session) -> dict[str, list[dict]]:
    """Les lignes de l'apercu : valeurs et morceaux de formules de chaque
    champion, stats des objets. Telechargees dans le dossier pbe, mais
    etiquetees du vrai patch ("16.24") : les modeles dbt les traitent alors
    comme un patch ordinaire.

    Les memes fonctions d'aplatissement que la collecte normale (kit_rows,
    flatten_item_stats) : l'apercu ne differe d'un vrai patch que par
    l'endroit ou il est telecharge.

    Un champion absent du PBE (404) est saute. Les objets absents, eux,
    arretent tout : sans eux, aucun objet ne paraitrait change, et les
    predictions seraient fausses sans le dire."""
    lignes = {"values": [], "parts": [], "item_stats": []}
    absents = []
    for champion_id, code in champions:
        reponse = session.get(champion_file_url(PBE_DOSSIER, code), timeout=TIMEOUT_S)
        if reponse.status_code == 404:
            absents.append(code)
            continue
        reponse.raise_for_status()
        # None : pas de texte du jeu, l'apercu n'a besoin ni des infobulles
        # ni des formules entieres.
        kit = kit_rows(patch, champion_id, code, reponse.json(), None)
        lignes["values"].extend(kit["values"])
        lignes["parts"].extend(kit["parts"])
    if absents:
        journal.warning("PBE : %d champions absents : %s", len(absents), absents)

    reponse = session.get(item_stats_url(PBE_DOSSIER), timeout=TIMEOUT_S)
    reponse.raise_for_status()
    lignes["item_stats"] = flatten_item_stats(patch, reponse.json())
    return lignes


def load_pbe_preview(versions: list[str], session, client) -> dict:
    """Charge l'apercu du PBE dans les tables pbe_*, en les remplacant.
    Retourne le bilan.

    versions : les versions de Data Dragon, la plus recente en premier (pour
    la liste des champions ; Data Dragon n'a pas encore le patch du PBE).

    Rien n'est charge si le patch est deja sorti (il est dans les vraies
    tables des kits) : l'apercu ne sert plus. Un apercu vide est refuse AVANT
    tout chargement : sinon une table serait remplacee et pas les autres."""
    reponse = session.get(PBE_METADONNEES_URL, timeout=TIMEOUT_S)
    reponse.raise_for_status()
    metadonnees = reponse.json()
    patch = pbe_patch(metadonnees)
    bilan = {"patch": patch, "version_pbe": metadonnees["version"]}

    if patch in loaded_kit_patches(client):
        journal.info("PBE %s : patch deja sorti, apercu inutile", patch)
        return {**bilan, "statut": "deja sorti"}

    champions = champions_of(season_versions(versions)[0], session)
    lignes = pbe_preview_rows(patch, champions, session)

    vides = [table for table in PBE_TABLES if not lignes[table]]
    if vides:
        raise ValueError(f"apercu du PBE {patch} vide pour : {vides}")

    for table, destination in PBE_TABLES.items():
        load_rows(
            lignes[table], destination, PBE_SCHEMAS[table], client, remplacer=True
        )

    bilan = {**bilan, "statut": "charge", **{t: len(lignes[t]) for t in PBE_TABLES}}
    journal.info("apercu du PBE : %s", bilan)
    return bilan


if __name__ == "__main__":
    # A lancer a la main (pas dans le run quotidien) : un apercu quand on veut
    # predire le prochain patch. Meme demarrage que kits.py.
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s : %(message)s"
    )
    client = bigquery.Client(project="lol-meta-pipeline")
    load_pbe_preview(fetch_versions(), requests.Session(), client)
