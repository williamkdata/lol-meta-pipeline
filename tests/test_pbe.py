"""L'apercu du PBE (le serveur de test de Riot), pour predire un patch avant sa
sortie (18/11/2026)."""

import pytest
import requests
from google.cloud import bigquery

from fakes import FakeBigQuery, FakeHttp, FakeResponse
from item_stats import ITEM_STATS_SCHEMA, flatten_item_stats, item_stats_url
from kits import KIT_SCHEMAS, champion_file_url, game_texts_url, kit_rows
from pbe import (
    PBE_METADONNEES_URL,
    PBE_TABLES,
    load_pbe_preview,
    pbe_patch,
    pbe_preview_rows,
)

# Les memes fichiers de jeu que les tests des kits et des objets : un vrai
# fichier d'Ambessa et le Couperet noir, pas une copie qui pourrait diverger.
from test_item_stats import OBJETS
from test_kits import TEXTES_16_21, kit_ambessa

# Le fichier content-metadata.json du dossier pbe de CommunityDragon, tel qu'il
# etait le 18/11/2026 (le 16.23 venait de sortir, le PBE testait le 16.24).
METADONNEES_PBE = {"version": "16.24.8394663+branch.main.content.beta"}


def test_the_pbe_patch_is_the_two_first_numbers_of_its_version():
    assert pbe_patch(METADONNEES_PBE) == "16.24"


def test_a_version_without_build_details_gives_the_same_patch():
    assert pbe_patch({"version": "16.24.8394663"}) == "16.24"


def test_an_unreadable_version_is_refused():
    # Sans numero de patch, on ne sait pas quel patch le PBE prepare : mieux
    # vaut s'arreter que charger un apercu sous un faux nom.
    with pytest.raises(ValueError):
        pbe_patch({"version": "branch.main.content.beta"})


def serveur_pbe(champions_presents=("Ambessa",), objets=True, textes=True):
    """Un faux CommunityDragon : le dossier pbe repond pour les champions
    presents, pour les objets et pour le texte du jeu (les infobulles) ; tout
    le reste repond 404."""
    http = FakeHttp()
    http.reponse = FakeResponse(status_code=404)
    if textes:
        http.reponses[game_texts_url("pbe")] = FakeResponse(
            {"entries": TEXTES_16_21, "version": "test"}
        )
    for code in champions_presents:
        http.reponses[champion_file_url("pbe", code)] = FakeResponse(kit_ambessa())
    if objets:
        http.reponses[item_stats_url("pbe")] = FakeResponse(OBJETS)
    return http


def test_the_preview_is_downloaded_from_the_pbe_folder():
    http = serveur_pbe()

    pbe_preview_rows("16.24", [(799, "Ambessa")], http)

    assert [url for url, _ in http.appels] == [
        game_texts_url("pbe"),
        champion_file_url("pbe", "Ambessa"),
        item_stats_url("pbe"),
    ]


def test_every_preview_row_carries_the_real_patch_name():
    lignes = pbe_preview_rows("16.24", [(799, "Ambessa")], serveur_pbe())

    for table in ("values", "parts", "tooltips", "item_stats"):
        assert lignes[table], f"aucune ligne dans {table} : le test ne prouverait rien"
        assert {ligne["patch"] for ligne in lignes[table]} == {"16.24"}


def test_preview_rows_are_those_of_a_normal_patch_except_the_folder():
    # Memes fonctions d'aplatissement que la collecte normale : l'apercu ne
    # doit differer d'un vrai patch que par l'endroit ou il est telecharge.
    lignes = pbe_preview_rows("16.24", [(799, "Ambessa")], serveur_pbe())

    kit = kit_rows("16.24", 799, "Ambessa", kit_ambessa(), TEXTES_16_21)
    assert lignes["values"] == kit["values"]
    assert lignes["parts"] == kit["parts"]
    assert lignes["tooltips"] == kit["tooltips"]
    assert lignes["item_stats"] == flatten_item_stats("16.24", OBJETS)


def test_the_preview_knows_which_formulas_are_shields():
    # Les infobulles disent quelle formule est un bouclier ou un soin : sans
    # elles, le moteur theorique range toute la survie dans les degats (vu le
    # 20/11 : 77 fausses predictions au 16.24, Shen +1 402 %).
    lignes = pbe_preview_rows("16.24", [(799, "Ambessa")], serveur_pbe())

    balises = {(ligne["name"], ligne["tag"]) for ligne in lignes["tooltips"]}
    assert ("calc_shield", "shield") in balises


def test_a_champion_missing_from_the_pbe_is_skipped():
    http = serveur_pbe(champions_presents=("Ambessa",))

    lignes = pbe_preview_rows("16.24", [(799, "Ambessa"), (103, "Ahri")], http)

    assert {ligne["champion_id"] for ligne in lignes["values"]} == {799}


def test_the_preview_stops_when_the_items_are_missing():
    # Sans les objets, l'apercu ne verrait aucun objet change : les
    # predictions seraient fausses sans le dire. Mieux vaut s'arreter.
    with pytest.raises(requests.HTTPError):
        pbe_preview_rows("16.24", [(799, "Ambessa")], serveur_pbe(objets=False))


CHAMPIONS_DD = "https://ddragon.leagueoflegends.com/cdn/{}/data/en_US/champion.json"
VERSIONS_DD = ["16.23.1", "16.22.1"]


def serveur_complet(champions_presents=("Ambessa",)):
    """Le faux internet de la fonction 4 : le content-metadata du PBE, la liste
    des champions de Data Dragon (16.23.1), et le dossier pbe."""
    http = serveur_pbe(champions_presents)
    http.reponses[PBE_METADONNEES_URL] = FakeResponse(METADONNEES_PBE)
    http.reponses[CHAMPIONS_DD.format("16.23.1")] = FakeResponse(
        {"data": {"Ambessa": {"key": "799", "id": "Ambessa"}}}
    )
    return http


def bigquery_au_16_23():
    """Les vraies tables des kits s'arretent au 16.23 : le 16.24 n'est pas sorti."""
    return FakeBigQuery(resultat_requete=[{"patch": "16.22"}, {"patch": "16.23"}])


def test_the_preview_replaces_the_four_pbe_tables():
    client = bigquery_au_16_23()

    load_pbe_preview(VERSIONS_DD, serveur_complet(), client)

    destinations = [destination for _, destination, _ in client.appels]
    assert destinations == [
        PBE_TABLES["values"],
        PBE_TABLES["parts"],
        PBE_TABLES["tooltips"],
        PBE_TABLES["item_stats"],
    ]
    # Jamais les vraies tables : le vrai 16.24 serait ignore a sa sortie.
    assert all(".pbe_" in destination for destination in destinations)
    for _, _, config in client.appels:
        assert config.write_disposition == bigquery.WriteDisposition.WRITE_TRUNCATE


def test_the_preview_tables_use_the_schemas_of_the_real_tables():
    client = bigquery_au_16_23()

    load_pbe_preview(VERSIONS_DD, serveur_complet(), client)

    schemas = [config.schema for _, _, config in client.appels]
    assert schemas == [
        KIT_SCHEMAS["values"],
        KIT_SCHEMAS["parts"],
        KIT_SCHEMAS["tooltips"],
        ITEM_STATS_SCHEMA,
    ]


def test_nothing_is_loaded_once_the_patch_is_out():
    # Le vrai 16.24 est dans les tables des kits : l'apercu ne sert plus.
    client = FakeBigQuery(resultat_requete=[{"patch": "16.23"}, {"patch": "16.24"}])
    http = serveur_complet()

    bilan = load_pbe_preview(VERSIONS_DD, http, client)

    assert bilan["statut"] == "deja sorti"
    assert client.appels == []
    # Pas meme un champion telecharge : seulement la version du PBE.
    assert [url for url, _ in http.appels] == [PBE_METADONNEES_URL]


def test_an_empty_preview_is_refused_before_loading_anything():
    # Aucun champion sur le PBE : les tables ne doivent pas etre a moitie
    # remplacees (les objets seuls, sans les kits).
    client = bigquery_au_16_23()

    with pytest.raises(ValueError):
        load_pbe_preview(VERSIONS_DD, serveur_complet(champions_presents=()), client)
    assert client.appels == []


def test_the_preview_is_refused_without_the_game_text_of_the_pbe():
    # Sans le texte du jeu, aucune infobulle : toute la survie passerait dans
    # les degats. Refuse avant tout chargement, comme un apercu vide.
    client = bigquery_au_16_23()
    http = serveur_complet()
    del http.reponses[game_texts_url("pbe")]

    with pytest.raises(ValueError, match="tooltips"):
        load_pbe_preview(VERSIONS_DD, http, client)
    assert client.appels == []


def test_the_report_gives_the_patch_the_pbe_build_and_the_row_counts():
    attendu = pbe_preview_rows("16.24", [(799, "Ambessa")], serveur_pbe())

    bilan = load_pbe_preview(VERSIONS_DD, serveur_complet(), bigquery_au_16_23())

    assert bilan == {
        "patch": "16.24",
        "version_pbe": "16.24.8394663+branch.main.content.beta",
        "statut": "charge",
        "values": len(attendu["values"]),
        "parts": len(attendu["parts"]),
        "tooltips": len(attendu["tooltips"]),
        "item_stats": len(attendu["item_stats"]),
    }
