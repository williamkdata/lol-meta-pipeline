import gzip
import json

import requests

from fakes import FakeBigQuery, FakeResponse, FakeStorage
from ladder import (
    EVENTS_TABLE,
    FRAMES_TABLE,
    PARTICIPANTS_TABLE,
    collect_ladder,
    collected_match_ids,
    flatten_match,
    flatten_timeline,
    select_new_ids,
)

# --- collected_match_ids ----------------------------------------------------


def test_collected_match_ids_reads_the_ids_already_in_bigquery():
    client = FakeBigQuery(
        resultat_requete=[{"match_id": "EUW1_1"}, {"match_id": "EUW1_2"}]
    )

    assert collected_match_ids(client) == {"EUW1_1", "EUW1_2"}


def test_collected_match_ids_is_empty_on_the_very_first_run():
    """Au premier run, la table n'existe pas encore : ce n'est pas une erreur."""
    assert collected_match_ids(FakeBigQuery(table_absente=True)) == set()


# --- select_new_ids ---------------------------------------------------------


def test_select_new_ids_downloads_a_shared_match_only_once():
    """Deux Challenger dans la meme partie : elle est dans leurs deux listes,
    mais une seule requete doit partir chez Riot."""
    listes = [["EUW1_1", "EUW1_2"], ["EUW1_2", "EUW1_3"]]

    assert select_new_ids(listes, set()) == ["EUW1_1", "EUW1_2", "EUW1_3"]


def test_select_new_ids_skips_the_matches_already_collected():
    listes = [["EUW1_1", "EUW1_2"]]

    assert select_new_ids(listes, {"EUW1_1"}) == ["EUW1_2"]


def test_select_new_ids_does_not_modify_the_set_it_receives():
    """L'ensemble des parties deja collectees appartient a l'appelant : la
    fonction ne doit pas y ajouter les nouvelles en cachette."""
    deja = {"EUW1_1"}

    select_new_ids([["EUW1_2"]], deja)

    assert deja == {"EUW1_1"}


# --- flatten_match ----------------------------------------------------------

PUUID_AHRI = "puuid-secret-ahri"


def joueur(numero, champion_id, champion, poste, equipe, gagne, puuid):
    """Un participant tel que match-v5 le decrit (champs utiles + identite)."""
    return {
        "participantId": numero,
        "teamId": equipe,
        "teamPosition": poste,
        "championId": champion_id,
        "championName": champion,
        "win": gagne,
        "kills": 7,
        "deaths": 2,
        "assists": 5,
        "goldEarned": 12500,
        "totalDamageDealtToChampions": 21000,
        "totalMinionsKilled": 190,
        "neutralMinionsKilled": 8,
        "champLevel": 16,
        # Ahri : Ombre de Luden, slot vide, Chaussures de sorcier ; balise jaune
        "item0": 6655,
        "item1": 0,
        "item2": 3020,
        "item3": 0,
        "item4": 0,
        "item5": 0,
        "item6": 3340,
        "summoner1Id": 4,  # Saut eclair
        "summoner2Id": 14,  # Embrasement
        "perks": {
            "statPerks": {"offense": 5008, "flex": 5008, "defense": 5011},
            # Riot renvoie le style secondaire en premier ici, expres :
            # la fonction doit se fier a la description, pas a la position.
            "styles": [
                {
                    "description": "subStyle",
                    "style": 8300,
                    "selections": [{"perk": 8345}, {"perk": 8347}],
                },
                {
                    "description": "primaryStyle",
                    "style": 8100,
                    "selections": [
                        {"perk": 8112},  # Electrocution
                        {"perk": 8139},
                        {"perk": 8138},
                        {"perk": 8135},
                    ],
                },
            ],
        },
        "gameEndedInEarlySurrender": False,
        "puuid": puuid,
        "riotIdGameName": "PseudoSecret",
        "riotIdTagline": "EUW",
        "summonerName": "PseudoSecret",
    }


def partie():
    return {
        "metadata": {"matchId": "EUW1_7000", "participants": [PUUID_AHRI, "p-vi"]},
        "info": {
            "gameStartTimestamp": 1793563200000,  # 01/11/2026 20:00 UTC
            "gameDuration": 1834,
            "gameVersion": "16.21.834.2754",
            "queueId": 420,
            "participants": [
                joueur(1, 103, "Ahri", "MIDDLE", 100, True, PUUID_AHRI),
                joueur(7, 254, "Vi", "JUNGLE", 200, False, "p-vi"),
            ],
        },
    }


INGERE = "2026-11-02T15:00:00+00:00"


def test_flatten_match_gives_one_row_per_player():
    lignes = flatten_match(partie(), INGERE)

    assert [ligne["champion_name"] for ligne in lignes] == ["Ahri", "Vi"]
    assert [ligne["participant_id"] for ligne in lignes] == [1, 7]


def test_flatten_match_repeats_the_match_information_on_each_row():
    ahri = flatten_match(partie(), INGERE)[0]

    assert ahri["match_id"] == "EUW1_7000"
    assert ahri["game_start"] == "2026-11-01T20:00:00+00:00"
    assert ahri["game_duration_s"] == 1834
    assert ahri["game_version"] == "16.21.834.2754"
    assert ahri["queue_id"] == 420
    assert ahri["ingested_at"] == INGERE


def test_flatten_match_keeps_the_player_statistics():
    ahri = flatten_match(partie(), INGERE)[0]

    assert ahri["team_id"] == 100
    assert ahri["team_position"] == "MIDDLE"
    assert ahri["champion_id"] == 103
    assert ahri["win"] is True
    assert (ahri["kills"], ahri["deaths"], ahri["assists"]) == (7, 2, 5)
    assert ahri["gold_earned"] == 12500
    assert ahri["damage_to_champions"] == 21000
    assert (ahri["minions_killed"], ahri["neutral_minions_killed"]) == (190, 8)
    assert ahri["champ_level"] == 16
    assert ahri["early_surrender"] is False


def test_flatten_match_drops_empty_item_slots_and_separates_the_trinket():
    """Un slot vide vaut 0 chez Riot : ce n'est pas un objet."""
    ahri = flatten_match(partie(), INGERE)[0]

    assert ahri["item_ids"] == [6655, 3020]
    assert ahri["trinket_id"] == 3340
    assert ahri["summoner_spell_ids"] == [4, 14]


def test_flatten_match_puts_the_keystone_first_whatever_the_style_order():
    ahri = flatten_match(partie(), INGERE)[0]

    assert ahri["primary_style"] == 8100  # Domination
    assert ahri["sub_style"] == 8300  # Inspiration
    assert ahri["keystone_id"] == 8112  # Electrocution
    assert ahri["rune_ids"] == [8112, 8139, 8138, 8135, 8345, 8347]
    assert ahri["stat_shard_ids"] == [5008, 5008, 5011]


def test_flatten_match_never_keeps_who_the_player_is():
    """L'analyse de la meta n'a pas besoin de savoir QUI joue : ni puuid, ni
    pseudo ne doivent arriver dans BigQuery. Ce qu'on ne stocke pas ne fuit pas."""
    for ligne in flatten_match(partie(), INGERE):
        assert PUUID_AHRI not in ligne.values()
        assert "PseudoSecret" not in ligne.values()
        assert not [cle for cle in ligne if "puuid" in cle or "riot" in cle]


# --- flatten_timeline -------------------------------------------------------


def photo(numero, or_total, xp, niveau, sbires, jungle):
    return {
        "participantId": numero,
        "totalGold": or_total,
        "currentGold": 300,
        "xp": xp,
        "level": niveau,
        "minionsKilled": sbires,
        "jungleMinionsKilled": jungle,
        "position": {"x": 7000, "y": 7000},
    }


def timeline():
    """Deux frames (0 et 1 min) et une derniere a la fin de la partie, pour
    deux joueurs : Ahri (1) et Vi (7)."""
    return {
        "metadata": {"matchId": "EUW1_7000", "participants": [PUUID_AHRI, "p-vi"]},
        "info": {
            "frameInterval": 60000,
            "participants": [
                {"participantId": 1, "puuid": PUUID_AHRI},
                {"participantId": 7, "puuid": "p-vi"},
            ],
            "frames": [
                {
                    "timestamp": 0,
                    "participantFrames": {
                        "1": photo(1, 500, 0, 1, 0, 0),
                        "7": photo(7, 500, 0, 1, 0, 0),
                    },
                    "events": [
                        {
                            "type": "ITEM_PURCHASED",
                            "timestamp": 1200,
                            "participantId": 1,
                            "itemId": 1056,
                        },
                        {
                            "type": "WARD_PLACED",
                            "timestamp": 1500,
                            "creatorId": 7,
                            "wardType": "YELLOW_TRINKET",
                        },
                    ],
                },
                {
                    "timestamp": 60021,
                    "participantFrames": {
                        "1": photo(1, 650, 280, 2, 4, 0),
                        "7": photo(7, 700, 310, 2, 0, 4),
                    },
                    "events": [
                        {
                            "type": "SKILL_LEVEL_UP",
                            "timestamp": 61000,
                            "participantId": 1,
                            "skillSlot": 1,
                            "levelUpType": "NORMAL",
                        },
                        {
                            "type": "CHAMPION_KILL",
                            "timestamp": 95000,
                            "killerId": 7,
                            "victimId": 1,
                            "assistingParticipantIds": [6, 8],
                            "bounty": 300,
                        },
                    ],
                },
                {
                    "timestamp": 1834000,
                    "participantFrames": {
                        "1": photo(1, 12500, 15000, 16, 190, 8),
                        "7": photo(7, 11800, 14200, 15, 30, 160),
                    },
                    "events": [
                        {
                            "type": "ELITE_MONSTER_KILL",
                            "timestamp": 1700000,
                            "killerId": 7,
                            "killerTeamId": 200,
                            "monsterType": "BARON_NASHOR",
                        },
                        {
                            "type": "BUILDING_KILL",
                            "timestamp": 1800000,
                            "killerId": 7,
                            "teamId": 100,
                            "buildingType": "INHIBITOR_BUILDING",
                            "laneType": "MID_LANE",
                        },
                        {"type": "GAME_END", "timestamp": 1834000, "winningTeam": 200},
                    ],
                },
            ],
        },
    }


DEBUT = "2026-11-01T20:00:00+00:00"


def test_flatten_timeline_gives_one_frame_row_per_player_and_minute():
    frames, _ = flatten_timeline(timeline(), DEBUT, INGERE)

    assert len(frames) == 3 * 2
    ahri_1min = [
        f for f in frames if f["frame_index"] == 1 and f["participant_id"] == 1
    ]
    assert ahri_1min == [
        {
            "match_id": "EUW1_7000",
            "game_start": DEBUT,
            "ingested_at": INGERE,
            "frame_index": 1,
            "timestamp_ms": 60021,
            "participant_id": 1,
            "total_gold": 650,
            "xp": 280,
            "level": 2,
            "minions_killed": 4,
            "jungle_minions_killed": 0,
        }
    ]


def test_flatten_timeline_numbers_the_last_frame_instead_of_rounding_it():
    """La derniere frame tombe a 30 min 34 s, pas sur une minute ronde :
    son numero (2 ici) la distingue des autres, une division ne le ferait pas."""
    frames, _ = flatten_timeline(timeline(), DEBUT, INGERE)

    assert sorted({f["frame_index"] for f in frames}) == [0, 1, 2]


def test_flatten_timeline_keeps_only_the_useful_events():
    """Les wards et la fin de partie ne servent a aucune question du projet."""
    _, evenements = flatten_timeline(timeline(), DEBUT, INGERE)

    assert [e["event_type"] for e in evenements] == [
        "ITEM_PURCHASED",
        "SKILL_LEVEL_UP",
        "CHAMPION_KILL",
        "ELITE_MONSTER_KILL",
        "BUILDING_KILL",
    ]


def test_flatten_timeline_numbers_events_in_game_order():
    """Les evenements n'ont pas d'identifiant chez Riot : leur rang dans la
    timeline en sert, et rend chaque ligne unique avec le match_id."""
    _, evenements = flatten_timeline(timeline(), DEBUT, INGERE)

    assert [e["event_index"] for e in evenements] == [0, 2, 3, 4, 5]


def test_flatten_timeline_fills_the_columns_of_each_event_type():
    _, evenements = flatten_timeline(timeline(), DEBUT, INGERE)
    achat, sort, kill, baron, inhib = evenements

    assert (achat["participant_id"], achat["item_id"]) == (1, 1056)
    assert (sort["participant_id"], sort["skill_slot"]) == (1, 1)
    assert (kill["killer_id"], kill["victim_id"]) == (7, 1)
    assert kill["assisting_ids"] == [6, 8]
    assert (baron["killer_team_id"], baron["monster_type"]) == (200, "BARON_NASHOR")
    assert (inhib["team_id"], inhib["building_type"]) == (100, "INHIBITOR_BUILDING")
    assert inhib["lane_type"] == "MID_LANE"


def test_flatten_timeline_leaves_missing_fields_empty():
    """Un achat n'a pas de victime : la colonne est vide (NULL), pas absente."""
    _, evenements = flatten_timeline(timeline(), DEBUT, INGERE)
    achat = evenements[0]

    assert achat["victim_id"] is None
    assert achat["assisting_ids"] == []
    assert achat["match_id"] == "EUW1_7000"
    assert achat["timestamp_ms"] == 1200


def test_flatten_timeline_never_keeps_who_the_player_is():
    frames, evenements = flatten_timeline(timeline(), DEBUT, INGERE)

    for ligne in frames + evenements:
        assert PUUID_AHRI not in ligne.values()


# --- collect_ladder ---------------------------------------------------------


def partie_de(match_id):
    p = partie()
    p["metadata"]["matchId"] = match_id
    return p


def timeline_de(match_id):
    t = timeline()
    t["metadata"]["matchId"] = match_id
    return t


class FakeRiot:
    """Un faux client Riot : des joueurs Challenger, leurs parties, et le
    contenu de chaque partie. Note chaque chemin demande."""

    def __init__(self, parties_par_joueur, introuvables=()):
        self.parties_par_joueur = parties_par_joueur
        self.introuvables = set(introuvables)
        self.chemins = []

    def get(self, hote, chemin, params=None):
        self.chemins.append(chemin)
        if "challengerleagues" in chemin:
            return {"entries": [{"puuid": p} for p in self.parties_par_joueur]}
        if "grandmasterleagues" in chemin:
            return {"entries": []}
        if chemin.endswith("/ids"):
            return self.parties_par_joueur[chemin.split("/")[-2]]
        # /lol/match/v5/matches/{id} ou /lol/match/v5/matches/{id}/timeline
        match_id = chemin.split("/")[5]
        if match_id in self.introuvables:
            raise requests.HTTPError(response=FakeResponse(status_code=404))
        if chemin.endswith("/timeline"):
            return timeline_de(match_id)
        return partie_de(match_id)


def collecter(riot, bq=None, storage=None, **options):
    reglages = {"max_joueurs": 10, "max_parties": 10, "taille_lot": 50}
    reglages.update(options)
    return collect_ladder(
        riot,
        storage or FakeStorage(),
        bq or FakeBigQuery(table_absente=True),
        depuis=1_793_500_000,
        ingere_le=INGERE,
        **reglages,
    )


def test_collect_ladder_downloads_each_new_match_once_with_its_timeline():
    """EUW1_2 est chez deux joueurs, EUW1_3 est deja en base."""
    riot = FakeRiot({"a": ["EUW1_1", "EUW1_2"], "b": ["EUW1_2", "EUW1_3"]})
    bq = FakeBigQuery(resultat_requete=[{"match_id": "EUW1_3"}])

    collecter(riot, bq)

    parties = [c for c in riot.chemins if c.startswith("/lol/match/v5/matches/EUW")]
    assert parties == [
        "/lol/match/v5/matches/EUW1_1",
        "/lol/match/v5/matches/EUW1_1/timeline",
        "/lol/match/v5/matches/EUW1_2",
        "/lol/match/v5/matches/EUW1_2/timeline",
    ]


def test_collect_ladder_asks_only_the_first_players():
    """Chaque joueur coute une requete : le plafond de joueurs tient le budget."""
    riot = FakeRiot({"a": ["EUW1_1"], "b": ["EUW1_2"], "c": ["EUW1_3"]})

    collecter(riot, max_joueurs=2)

    assert len([c for c in riot.chemins if c.endswith("/ids")]) == 2


def test_collect_ladder_lands_the_raw_json_in_the_bucket():
    """Le brut, une partie par ligne (JSON Lines), compresse : de quoi tout
    rejouer sans redemander a Riot."""
    riot = FakeRiot({"a": ["EUW1_1", "EUW1_2"]})
    storage = FakeStorage()

    collecter(riot, storage=storage)

    chemins = sorted(chemin for _, chemin in storage.objets)
    assert chemins == [
        "riot/matches/2026-11-02/150000-000.jsonl.gz",
        "riot/timelines/2026-11-02/150000-000.jsonl.gz",
    ]
    objet = storage.objets[
        ("lol-meta-pipeline-landing", "riot/matches/2026-11-02/150000-000.jsonl.gz")
    ]
    lignes = gzip.decompress(objet.data).decode("utf-8").splitlines()
    assert [json.loads(ligne)["metadata"]["matchId"] for ligne in lignes] == [
        "EUW1_1",
        "EUW1_2",
    ]


def test_collect_ladder_loads_participants_last():
    """participants sert de marqueur de fin : une partie qui y figure a deja
    ses timelines en base. Elle est donc chargee en dernier."""
    bq = FakeBigQuery(table_absente=True)

    collecter(FakeRiot({"a": ["EUW1_1"]}), bq)

    assert [destination for _, destination, _ in bq.appels] == [
        FRAMES_TABLE,
        EVENTS_TABLE,
        PARTICIPANTS_TABLE,
    ]


def test_collect_ladder_partitions_every_table_on_the_game_date():
    bq = FakeBigQuery(table_absente=True)

    collecter(FakeRiot({"a": ["EUW1_1"]}), bq)

    for _, _, config in bq.appels:
        assert config.time_partitioning.field == "game_start"


def test_collect_ladder_works_in_batches():
    """3 parties, lots de 2 : deux depots et deux series de chargements. Un
    plantage au 2e lot laisserait le 1er a l'abri."""
    riot = FakeRiot({"a": ["EUW1_1", "EUW1_2", "EUW1_3"]})
    bq = FakeBigQuery(table_absente=True)
    storage = FakeStorage()

    collecter(riot, bq, storage, taille_lot=2)

    assert len(bq.appels) == 2 * 3
    assert len(storage.objets) == 2 * 2


def test_collect_ladder_skips_a_match_riot_cannot_find():
    """Sans ca, une partie introuvable ferait planter le run tous les jours."""
    riot = FakeRiot({"a": ["EUW1_1", "EUW1_2"]}, introuvables={"EUW1_2"})

    bilan = collecter(riot)

    assert bilan["introuvables"] == 1
    assert bilan["parties"] == 1


def test_collect_ladder_returns_a_summary_of_the_run():
    bilan = collecter(FakeRiot({"a": ["EUW1_1", "EUW1_2"], "b": []}))

    assert bilan == {
        "joueurs": 2,
        "ids_recus": 2,
        "disponibles": 2,
        "parties": 2,
        "introuvables": 0,
        "participants": 2 * 2,
        "frames": 2 * 6,
        "evenements": 2 * 5,
    }


def test_collect_ladder_respects_the_budget_and_reports_what_it_left():
    """Chaque partie coute deux requetes : le run s'arrete au plafond, et le
    bilan dit combien de parties nouvelles il a laissees, pour calibrer."""
    riot = FakeRiot({"a": ["EUW1_1", "EUW1_2", "EUW1_3"], "b": ["EUW1_3"]})

    bilan = collecter(riot, max_parties=2)

    assert bilan["parties"] == 2
    assert bilan["disponibles"] == 3
    assert bilan["ids_recus"] == 4
