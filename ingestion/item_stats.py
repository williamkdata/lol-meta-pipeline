"""Les stats des objets, par patch, depuis les fichiers du jeu (CommunityDragon).

Data Dragon oublie certaines stats (les 20 d'acceleration de competence du
Couperet noir, verifie le 04/11/2026). Les fichiers du jeu sont complets, et
identiques a Data Dragon la ou il les a (1 174 recoupements, 0 ecart au 16.22).
Prix, carte et arbre de fabrication restent pris dans Data Dragon."""

import logging

import requests
from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from bigquery_loader import load_rows
from ddragon import fetch_versions
from kits import CDRAGON_URL, TIMEOUT_S, season_patches

journal = logging.getLogger(__name__)

ITEM_STATS_TABLE = "lol-meta-pipeline.lol_raw.item_stats"
ITEM_STATS_SCHEMA = [
    bigquery.SchemaField("patch", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("item_id", "INTEGER", mode="REQUIRED"),
    # Le nom de Data Dragon, sans le "m" des fichiers du jeu : FlatHPPoolMod.
    bigquery.SchemaField("stat", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("value", "FLOAT"),
]
# Les 24 sortes de stats recensees au 16.22 ont toutes un de ces mots dans leur
# nom (mFlatHPPoolMod, mAbilityHasteMod, mFlatMagicPenetrationMod...).
MOTS_DE_STAT = ("Mod", "Lethality", "Penetration", "Haste")


def item_stats_url(patch: str) -> str:
    """Le fichier de tous les objets d'un patch (~15 Mo)."""
    return f"{CDRAGON_URL}/{patch}/game/items.cdtb.bin.json"


def _est_une_stat(nom: str, valeur) -> bool:
    # True est AUSSI un entier pour Python (isinstance(True, int) vaut vrai) :
    # sans cette exclusion, mCanBeSold: true passerait pour une stat valant 1.
    if isinstance(valeur, bool) or not isinstance(valeur, int | float):
        return False
    return nom.startswith("m") and any(mot in nom for mot in MOTS_DE_STAT)


def flatten_item_stats(patch: str, fichier: dict) -> list[dict]:
    """Une ligne par objet et par stat. Seules les entrees "Items/<numero>" sont
    des objets ; les autres (groupes d'objets...) sont ignorees."""
    lignes = []
    for cle, objet in fichier.items():
        numero = cle.removeprefix("Items/")
        if not cle.startswith("Items/") or not numero.isdigit():
            continue
        if not isinstance(objet, dict):
            continue
        for nom, valeur in objet.items():
            if _est_une_stat(nom, valeur):
                lignes.append(
                    {
                        "patch": patch,
                        "item_id": int(numero),
                        "stat": nom.removeprefix("m"),
                        "value": float(valeur),
                    }
                )
    return lignes


def loaded_item_stat_patches(client) -> set[str]:
    """Les patches deja en base. Vide si la table n'existe pas encore."""
    sql = f"SELECT DISTINCT patch FROM `{ITEM_STATS_TABLE}`"
    try:
        lignes = client.query(sql).result()
    except NotFound:
        return set()
    return {ligne["patch"] for ligne in lignes}


def load_item_stats_season(versions: list[str], session, client) -> list[dict]:
    """Charge les stats des objets des patches de la saison PAS ENCORE en base.
    Un patch pas encore publie (404) ne charge rien : repris le lendemain."""
    deja = loaded_item_stat_patches(client)
    bilans = []
    for patch in season_patches(versions):
        if patch in deja:
            continue
        reponse = session.get(item_stats_url(patch), timeout=TIMEOUT_S)
        if reponse.status_code == 404:
            lignes = []
        else:
            reponse.raise_for_status()
            lignes = flatten_item_stats(patch, reponse.json())
        load_rows(lignes, ITEM_STATS_TABLE, ITEM_STATS_SCHEMA, client)
        bilan = {
            "patch": patch,
            "objets": len({ligne["item_id"] for ligne in lignes}),
            "stats": len(lignes),
        }
        journal.info("stats des objets %s : %s", patch, bilan)
        bilans.append(bilan)
    return bilans


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s : %(message)s"
    )
    client = bigquery.Client(project="lol-meta-pipeline")
    bilans = load_item_stats_season(fetch_versions(), requests.Session(), client)
    journal.info("%d patches charges", len(bilans))
