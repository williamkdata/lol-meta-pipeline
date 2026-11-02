"""Collecte du ladder EUW (Challenger + Grandmaster) : parties classees solo et
leurs timelines, deposees brutes dans le bucket, aplaties dans BigQuery."""

import argparse
import json
import os
import time
from datetime import UTC, datetime

import requests
from google.api_core.exceptions import NotFound
from google.cloud import bigquery, storage
from google.oauth2 import service_account

from bigquery_loader import load_rows
from landing import upload_to_gcs
from riot import (
    RiotClient,
    fetch_match,
    fetch_timeline,
    ladder_puuids,
    match_ids,
    read_api_key,
)

CLE_COMPTE_DE_SERVICE = os.environ.get("LOL_SA_KEY", "secrets/lol-pipeline-key.json")

# Une timeline pese plusieurs centaines de Ko : 50 parties a la fois tiennent
# en memoire, 1 000 non. Chaque lot est depose puis charge avant le suivant.
TAILLE_LOT = 50
# On regarde 2 jours en arriere : un jour PC eteint ne fait rien perdre, et
# les parties deja en base sont ecartees de toute facon.
FENETRE_S = 2 * 24 * 3600

LADDER_DATASET = "lol-meta-pipeline.lol_raw_ladder"
# Chargee EN DERNIER : une partie presente ici a deja ses timelines en base.
PARTICIPANTS_TABLE = f"{LADDER_DATASET}.participants"


def _champ(nom, type_, mode="NULLABLE"):
    return bigquery.SchemaField(nom, type_, mode=mode)


# Une ligne par joueur et par partie. Aucun identifiant de joueur (puuid,
# pseudo) : l'analyse de la meta n'en a pas besoin.
PARTICIPANTS_SCHEMA = [
    _champ("match_id", "STRING", "REQUIRED"),
    _champ("game_start", "TIMESTAMP", "REQUIRED"),
    _champ("game_duration_s", "INTEGER"),
    _champ("game_version", "STRING"),
    _champ("queue_id", "INTEGER"),
    _champ("ingested_at", "TIMESTAMP", "REQUIRED"),
    _champ("participant_id", "INTEGER", "REQUIRED"),
    _champ("team_id", "INTEGER"),
    _champ("team_position", "STRING"),
    _champ("champion_id", "INTEGER"),
    _champ("champion_name", "STRING"),
    _champ("win", "BOOLEAN"),
    _champ("kills", "INTEGER"),
    _champ("deaths", "INTEGER"),
    _champ("assists", "INTEGER"),
    _champ("gold_earned", "INTEGER"),
    _champ("damage_to_champions", "INTEGER"),
    _champ("minions_killed", "INTEGER"),
    _champ("neutral_minions_killed", "INTEGER"),
    _champ("champ_level", "INTEGER"),
    _champ("item_ids", "INTEGER", "REPEATED"),
    _champ("trinket_id", "INTEGER"),
    _champ("summoner_spell_ids", "INTEGER", "REPEATED"),
    _champ("primary_style", "INTEGER"),
    _champ("sub_style", "INTEGER"),
    _champ("keystone_id", "INTEGER"),
    _champ("rune_ids", "INTEGER", "REPEATED"),
    _champ("stat_shard_ids", "INTEGER", "REPEATED"),
    _champ("early_surrender", "BOOLEAN"),
]

FRAMES_TABLE = f"{LADDER_DATASET}.timeline_frames"
EVENTS_TABLE = f"{LADDER_DATASET}.timeline_events"

# Une photo par joueur et par minute : de quoi calculer l'avance en or a 10 min.
FRAMES_SCHEMA = [
    _champ("match_id", "STRING", "REQUIRED"),
    _champ("game_start", "TIMESTAMP", "REQUIRED"),
    _champ("ingested_at", "TIMESTAMP", "REQUIRED"),
    _champ("frame_index", "INTEGER", "REQUIRED"),
    _champ("timestamp_ms", "INTEGER"),
    _champ("participant_id", "INTEGER", "REQUIRED"),
    _champ("total_gold", "INTEGER"),
    _champ("xp", "INTEGER"),
    _champ("level", "INTEGER"),
    _champ("minions_killed", "INTEGER"),
    _champ("jungle_minions_killed", "INTEGER"),
]

# Les evenements gardes : l'ordre du build, l'ordre des sorts, les kills, les
# objectifs. Les wards (~150 par partie) ne servent a aucune question du projet.
EVENEMENTS_GARDES = {
    "ITEM_PURCHASED",
    "ITEM_SOLD",
    "ITEM_UNDO",
    "SKILL_LEVEL_UP",
    "CHAMPION_KILL",
    "ELITE_MONSTER_KILL",
    "BUILDING_KILL",
    "TURRET_PLATE_DESTROYED",
}

# Champ Riot -> colonne BigQuery. Chaque type d'evenement n'en remplit que
# quelques-uns ; les autres restent vides (NULL).
COLONNES_EVENEMENT = {
    "participantId": "participant_id",
    "itemId": "item_id",
    "beforeId": "before_item_id",
    "afterId": "after_item_id",
    "skillSlot": "skill_slot",
    "killerId": "killer_id",
    "victimId": "victim_id",
    "killerTeamId": "killer_team_id",
    "teamId": "team_id",
    "monsterType": "monster_type",
    "monsterSubType": "monster_sub_type",
    "buildingType": "building_type",
    "laneType": "lane_type",
    "towerType": "tower_type",
}

_TYPES_COLONNES = {
    "monster_type": "STRING",
    "monster_sub_type": "STRING",
    "building_type": "STRING",
    "lane_type": "STRING",
    "tower_type": "STRING",
}

EVENTS_SCHEMA = [
    _champ("match_id", "STRING", "REQUIRED"),
    _champ("game_start", "TIMESTAMP", "REQUIRED"),
    _champ("ingested_at", "TIMESTAMP", "REQUIRED"),
    _champ("event_index", "INTEGER", "REQUIRED"),
    _champ("timestamp_ms", "INTEGER"),
    _champ("event_type", "STRING", "REQUIRED"),
    *[
        _champ(colonne, _TYPES_COLONNES.get(colonne, "INTEGER"))
        for colonne in COLONNES_EVENEMENT.values()
    ],
    _champ("assisting_ids", "INTEGER", "REPEATED"),
]


def collected_match_ids(client) -> set[str]:
    """Les parties deja en base. Vide si la table n'existe pas encore."""
    sql = f"SELECT DISTINCT match_id FROM `{PARTICIPANTS_TABLE}`"
    try:
        lignes = client.query(sql).result()
    except NotFound:
        return set()
    return {ligne["match_id"] for ligne in lignes}


def select_new_ids(listes_par_joueur, deja_collectes) -> list[str]:
    """Les parties a telecharger : chacune une seule fois, aucune deja en base.
    L'ordre de decouverte est garde ; le plafond est applique par l'appelant."""
    vues = set(deja_collectes)  # une copie : l'ensemble recu n'est pas modifie
    nouvelles = []
    for ids in listes_par_joueur:
        for match_id in ids:
            if match_id not in vues:
                vues.add(match_id)
                nouvelles.append(match_id)
    return nouvelles


def flatten_match(partie: dict, ingere_le: str) -> list[dict]:
    """Le JSON d'une partie -> une ligne plate par joueur, sans son identite."""
    info = partie["info"]
    debut = datetime.fromtimestamp(info["gameStartTimestamp"] / 1000, tz=UTC)
    commun = {
        "match_id": partie["metadata"]["matchId"],
        "game_start": debut.isoformat(),
        "game_duration_s": info["gameDuration"],
        "game_version": info["gameVersion"],
        "queue_id": info["queueId"],
        "ingested_at": ingere_le,
    }

    lignes = []
    for joueur in info["participants"]:
        # Les deux arbres de runes, retrouves par leur description et non par
        # leur position dans la liste.
        styles = {style["description"]: style for style in joueur["perks"]["styles"]}
        principal = [choix["perk"] for choix in styles["primaryStyle"]["selections"]]
        secondaire = [choix["perk"] for choix in styles["subStyle"]["selections"]]
        fragments = joueur["perks"]["statPerks"]

        lignes.append(
            {
                **commun,
                "participant_id": joueur["participantId"],
                "team_id": joueur["teamId"],
                "team_position": joueur["teamPosition"],
                "champion_id": joueur["championId"],
                "champion_name": joueur["championName"],
                "win": joueur["win"],
                "kills": joueur["kills"],
                "deaths": joueur["deaths"],
                "assists": joueur["assists"],
                "gold_earned": joueur["goldEarned"],
                "damage_to_champions": joueur["totalDamageDealtToChampions"],
                "minions_killed": joueur["totalMinionsKilled"],
                "neutral_minions_killed": joueur["neutralMinionsKilled"],
                "champ_level": joueur["champLevel"],
                # item0 a item5 : l'inventaire ; 0 = slot vide. item6 : la balise.
                "item_ids": [
                    joueur[f"item{i}"] for i in range(6) if joueur[f"item{i}"] != 0
                ],
                "trinket_id": joueur["item6"],
                "summoner_spell_ids": [joueur["summoner1Id"], joueur["summoner2Id"]],
                "primary_style": styles["primaryStyle"]["style"],
                "sub_style": styles["subStyle"]["style"],
                "keystone_id": principal[0],
                "rune_ids": principal + secondaire,
                "stat_shard_ids": [
                    fragments["offense"],
                    fragments["flex"],
                    fragments["defense"],
                ],
                "early_surrender": joueur["gameEndedInEarlySurrender"],
            }
        )
    return lignes


def flatten_timeline(timeline: dict, game_start: str, ingere_le: str):
    """La timeline d'une partie -> (photos par minute, evenements utiles).

    game_start vient de la partie : la timeline ne donne pas sa date, et les
    trois tables doivent etre partitionnees sur la meme colonne."""
    commun = {
        "match_id": timeline["metadata"]["matchId"],
        "game_start": game_start,
        "ingested_at": ingere_le,
    }

    frames = []
    evenements = []
    rang = 0  # numero de l'evenement dans toute la partie, wards comprises
    for numero, frame in enumerate(timeline["info"]["frames"]):
        for photo in frame["participantFrames"].values():
            frames.append(
                {
                    **commun,
                    "frame_index": numero,
                    "timestamp_ms": frame["timestamp"],
                    "participant_id": photo["participantId"],
                    "total_gold": photo["totalGold"],
                    "xp": photo["xp"],
                    "level": photo["level"],
                    "minions_killed": photo["minionsKilled"],
                    "jungle_minions_killed": photo["jungleMinionsKilled"],
                }
            )

        for evenement in frame["events"]:
            if evenement["type"] in EVENEMENTS_GARDES:
                ligne = {
                    **commun,
                    "event_index": rang,
                    "timestamp_ms": evenement["timestamp"],
                    "event_type": evenement["type"],
                    "assisting_ids": evenement.get("assistingParticipantIds", []),
                }
                for champ_riot, colonne in COLONNES_EVENEMENT.items():
                    ligne[colonne] = evenement.get(champ_riot)
                evenements.append(ligne)
            rang += 1
    return frames, evenements


def land_jsonl(objets: list[dict], chemin: str, storage_client) -> str:
    """Depose une liste de JSON dans le bucket, un objet par ligne (JSON Lines)."""
    contenu = "\n".join(json.dumps(objet) for objet in objets)
    return upload_to_gcs(contenu.encode("utf-8"), chemin, storage_client)


def _telecharger(riot, match_id):
    """La partie et sa timeline, ou None si Riot ne les trouve pas (404)."""
    try:
        return fetch_match(riot, match_id), fetch_timeline(riot, match_id)
    except requests.HTTPError as erreur:
        if erreur.response is not None and erreur.response.status_code == 404:
            return None
        raise


def collect_ladder(
    riot,
    storage_client,
    bq_client,
    depuis: int,
    ingere_le: str,
    max_joueurs: int,
    max_parties: int,
    taille_lot: int = TAILLE_LOT,
) -> dict:
    """Le run complet : joueurs -> nouvelles parties -> bucket -> BigQuery.
    Retourne le bilan du run."""
    puuids = ladder_puuids(riot)[:max_joueurs]
    listes = [match_ids(riot, puuid, depuis) for puuid in puuids]
    nouvelles = select_new_ids(listes, collected_match_ids(bq_client))
    a_prendre = nouvelles[:max_parties]

    # ids_recus / disponibles : le recouvrement entre joueurs (une partie de
    # Challenger contient plusieurs joueurs du ladder) ; disponibles / parties :
    # ce que le plafond a laisse. De quoi calibrer les plafonds.
    bilan = {
        "joueurs": len(puuids),
        "ids_recus": sum(len(ids) for ids in listes),
        "disponibles": len(nouvelles),
        "parties": 0,
        "introuvables": 0,
        "participants": 0,
        "frames": 0,
        "evenements": 0,
    }
    # "2026-11-02T15:00:00+00:00" -> dossier 2026-11-02, fichier 150000-000
    jour = ingere_le[:10]
    heure = ingere_le[11:19].replace(":", "")

    for debut in range(0, len(a_prendre), taille_lot):
        lot = a_prendre[debut : debut + taille_lot]
        numero = debut // taille_lot

        parties, timelines = [], []
        for match_id in lot:
            telecharge = _telecharger(riot, match_id)
            if telecharge is None:
                bilan["introuvables"] += 1
                continue
            parties.append(telecharge[0])
            timelines.append(telecharge[1])
        if not parties:
            continue

        # 1. Le brut d'abord : s'il est dans le bucket, on peut tout rejouer.
        land_jsonl(
            parties,
            f"riot/matches/{jour}/{heure}-{numero:03d}.jsonl.gz",
            storage_client,
        )
        land_jsonl(
            timelines,
            f"riot/timelines/{jour}/{heure}-{numero:03d}.jsonl.gz",
            storage_client,
        )

        # 2. L'aplatissement.
        participants, frames, evenements = [], [], []
        for partie, timeline in zip(parties, timelines, strict=True):
            lignes = flatten_match(partie, ingere_le)
            debut_partie = lignes[0]["game_start"]
            photos, faits = flatten_timeline(timeline, debut_partie, ingere_le)
            participants.extend(lignes)
            frames.extend(photos)
            evenements.extend(faits)

        # 3. Le chargement : participants EN DERNIER (marqueur de fin).
        load_rows(frames, FRAMES_TABLE, FRAMES_SCHEMA, bq_client, "game_start")
        load_rows(evenements, EVENTS_TABLE, EVENTS_SCHEMA, bq_client, "game_start")
        load_rows(
            participants,
            PARTICIPANTS_TABLE,
            PARTICIPANTS_SCHEMA,
            bq_client,
            "game_start",
        )

        bilan["parties"] += len(parties)
        bilan["participants"] += len(participants)
        bilan["frames"] += len(frames)
        bilan["evenements"] += len(evenements)
    return bilan


if __name__ == "__main__":
    options = argparse.ArgumentParser(description="Collecte du ladder EUW")
    options.add_argument("--max-joueurs", type=int, default=300)
    options.add_argument("--max-parties", type=int, default=400)
    reglages = options.parse_args()

    identite = service_account.Credentials.from_service_account_file(
        CLE_COMPTE_DE_SERVICE,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    maintenant = datetime.now(UTC)
    bilan = collect_ladder(
        RiotClient(read_api_key()),
        storage.Client(project="lol-meta-pipeline", credentials=identite),
        bigquery.Client(project="lol-meta-pipeline", credentials=identite),
        depuis=int(time.time()) - FENETRE_S,
        ingere_le=maintenant.isoformat(timespec="seconds"),
        max_joueurs=reglages.max_joueurs,
        max_parties=reglages.max_parties,
    )
    print(f"bilan du run : {bilan}")
