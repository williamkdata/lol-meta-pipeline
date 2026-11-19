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
# Recensement fait le 09/11/2026 sur le fichier BRUT du 16.22 (tous les champs
# numeriques des objets, pas seulement ceux qui passaient l'ancien filtre) :
# 29 sortes de stats. 24 s'ecrivent avec un "m" au debut (mFlatHPPoolMod), 5
# SANS (flatMPPoolMod : le mana ; percentBaseMPRegenMod, flatMPRegenMod : la
# regeneration de mana ; PhysicalLethality : la letalite ; PercentOmnivampMod).
# L'ancien filtre exigeait le "m" : ces 5 n'etaient jamais chargees.
# Regle : le nom finit par "Mod", ou c'est la letalite. Les autres nombres
# (price, epicness, mRequiredLevel, specialRecipe...) ne sont pas des stats ;
# sellBackModifier contient "Mod" mais finit par "Modifier".


def item_stats_url(patch: str) -> str:
    """Le fichier de tous les objets d'un patch (~15 Mo)."""
    return f"{CDRAGON_URL}/{patch}/game/items.cdtb.bin.json"


def _est_une_stat(nom: str, valeur) -> bool:
    # True est AUSSI un entier pour Python (isinstance(True, int) vaut vrai) :
    # sans cette exclusion, mCanBeSold: true passerait pour une stat valant 1.
    if isinstance(valeur, bool) or not isinstance(valeur, int | float):
        return False
    return nom.endswith("Mod") or "Lethality" in nom


def _nom_de_stat(nom: str) -> str:
    """Le nom comme dans Data Dragon : mFlatHPPoolMod -> FlatHPPoolMod,
    flatMPPoolMod -> FlatMPPoolMod, PhysicalLethality inchange."""
    # Le "m" n'est un prefixe que s'il est suivi d'une majuscule (mFlat...).
    if nom[:1] == "m" and nom[1:2].isupper():
        nom = nom[1:]
    return nom[:1].upper() + nom[1:]


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
                        "stat": _nom_de_stat(nom),
                        "value": float(valeur),
                    }
                )
    return lignes


# Les groupes d'objets (18/11/2026) : le jeu limite certains cumuls (un seul
# objet du groupe "LastWhisper" : Lord Dominik, Rappel mortel... ; une seule
# paire de bottes). Le moteur de build ne doit jamais proposer un build
# impossible. Au 16.23 : 2 051 liens objet -> groupe, tous en clair ; 274
# groupes limites cites par des objets (beaucoup pour le mode Arena).
ITEM_GROUPS_TABLE = "lol-meta-pipeline.lol_raw.item_groups"
ITEM_GROUPS_SCHEMA = [
    bigquery.SchemaField("patch", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("item_id", "INTEGER", mode="REQUIRED"),
    # Le dernier morceau du chemin : Items/ItemGroups/LastWhisper -> LastWhisper.
    bigquery.SchemaField("item_group", "STRING", mode="REQUIRED"),
    # Combien d'objets du groupe on peut avoir. Vide : pas de limite (Default).
    bigquery.SchemaField("max_ownable", "INTEGER"),
    # Faux si le groupe est cite par l'objet mais introuvable dans le fichier :
    # sa limite est alors inconnue (a ne pas confondre avec "sans limite").
    bigquery.SchemaField("group_defined", "BOOLEAN", mode="REQUIRED"),
]


def _empreinte(chemin: str) -> str:
    """La cle chiffree d'un chemin du fichier : FNV-1a 32 bits du chemin en
    minuscules, comme CommunityDragon quand il ne connait pas le nom (la meme
    que pour la fiche des champions : "mrperlevel" -> {01262a25})."""
    valeur = 0x811C9DC5
    for octet in chemin.lower().encode("utf-8"):
        valeur = ((valeur ^ octet) * 0x01000193) & 0xFFFFFFFF
    return f"{{{valeur:08x}}}"


def flatten_item_groups(patch: str, fichier: dict) -> list[dict]:
    """Une ligne par objet et par groupe qu'il cite (mItemGroups).

    Le groupe est cherche sous son chemin, sinon sous son empreinte. Un groupe
    introuvable est GARDE, marque group_defined = False : jamais perdu en
    silence."""
    lignes = []
    for cle, objet in fichier.items():
        numero = cle.removeprefix("Items/")
        if not cle.startswith("Items/") or not numero.isdigit():
            continue
        if not isinstance(objet, dict):
            continue
        for chemin in objet.get("mItemGroups", []):
            groupe = fichier.get(chemin) or fichier.get(_empreinte(chemin))
            lignes.append(
                {
                    "patch": patch,
                    "item_id": int(numero),
                    "item_group": chemin.rsplit("/", 1)[-1],
                    "max_ownable": groupe.get("mMaxGroupOwnable") if groupe else None,
                    "group_defined": groupe is not None,
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
