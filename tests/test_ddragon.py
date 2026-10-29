import pytest
import requests

import ddragon
from ddragon import (
    fetch_champions,
    fetch_versions,
    flatten_champions,
    load_season,
    patch_of,
    season_versions,
)
from fakes import FakeBigQuery, FakeHttp, FakeResponse

# --- patch_of ---------------------------------------------------------------


def test_patch_of_keeps_the_first_two_numbers():
    assert patch_of("16.21.1") == "16.21"


def test_patch_of_does_not_confuse_patch_2_and_patch_21():
    """Couper a un nombre fixe de caracteres donnerait '16.2.' pour le patch 16.2.
    Il faut couper sur les points, pas compter les caracteres."""
    assert patch_of("16.2.1") == "16.2"


def test_patch_of_reads_the_long_version_of_a_match():
    """Le detail d'un match porte une version plus longue. Meme patch."""
    assert patch_of("16.21.628.4012") == "16.21"


@pytest.mark.parametrize("version", ["lolpatch_7.20", "16", "", "16.x.1"])
def test_patch_of_refuses_an_unreadable_version(version):
    """98 des 502 versions publiees par Data Dragon ont un format ancien, comme
    'lolpatch_7.20'. On refuse bruyamment plutot que de produire du charabia."""
    with pytest.raises(ValueError):
        patch_of(version)


# --- flatten_champions ------------------------------------------------------

# Extrait reduit du vrai champion.json (version 16.21.1, en_US). Wukong est
# garde expres : son code interne ("MonkeyKing") differe de son nom affiche.
CHAMPIONS = {
    "type": "champion",
    "format": "standAloneComplex",
    "version": "16.21.1",
    "data": {
        "Ahri": {
            "id": "Ahri",
            "key": "103",
            "name": "Ahri",
            "title": "the Nine-Tailed Fox",
            "tags": ["Mage", "Assassin"],
        },
        "MonkeyKing": {
            "id": "MonkeyKing",
            "key": "62",
            "name": "Wukong",
            "title": "the Monkey King",
            "tags": ["Fighter", "Tank"],
        },
    },
}


def row_for(rows, code):
    """La ligne du champion `code`. Echoue s'il y en a zero ou plusieurs."""
    [row] = [r for r in rows if r["champion_code"] == code]
    return row


def test_flatten_champions_gives_one_row_per_champion():
    assert len(flatten_champions(CHAMPIONS)) == 2


def test_flatten_champions_converts_the_key_to_a_number():
    """Dans le fichier, la cle est un TEXTE ("103"). Les parties de l'API Riot
    donnent un NOMBRE (103). Sans conversion, la jointure echouerait."""
    ahri = row_for(flatten_champions(CHAMPIONS), "Ahri")

    assert ahri["champion_id"] == 103
    assert isinstance(ahri["champion_id"], int)


def test_flatten_champions_keeps_code_and_name_apart():
    """21 champions sur 173 ont un code interne different de leur nom affiche."""
    wukong = row_for(flatten_champions(CHAMPIONS), "MonkeyKing")

    assert wukong["champion_name"] == "Wukong"
    assert wukong["champion_id"] == 62


def test_flatten_champions_stamps_every_row_with_its_patch():
    """La cle de la dimension est (champion, patch) : chaque ligne porte le sien."""
    for row in flatten_champions(CHAMPIONS):
        assert row["patch"] == "16.21"
        assert row["version"] == "16.21.1"


def test_flatten_champions_keeps_title_and_tags():
    ahri = row_for(flatten_champions(CHAMPIONS), "Ahri")

    assert ahri["title"] == "the Nine-Tailed Fox"
    assert ahri["tags"] == ["Mage", "Assassin"]


def test_flatten_champions_refuses_a_malformed_version():
    """La protection de patch_of doit se transmettre : aucune ligne ne sort
    avec un patch illisible."""
    ancien = {**CHAMPIONS, "version": "lolpatch_7.20"}

    with pytest.raises(ValueError):
        flatten_champions(ancien)


def test_flatten_champions_without_any_champion():
    assert flatten_champions({**CHAMPIONS, "data": {}}) == []


# --- fetch_versions ---------------------------------------------------------


@pytest.fixture
def http(monkeypatch):
    """Aucun appel reseau reel : requests.get est remplace dans le module ddragon."""
    faux = FakeHttp()
    monkeypatch.setattr(ddragon.requests, "get", faux.get)
    return faux


def test_fetch_versions_returns_the_published_list(http):
    http.reponse = FakeResponse(["16.21.1", "16.20.1"])

    assert fetch_versions() == ["16.21.1", "16.20.1"]


def test_fetch_versions_calls_data_dragon_with_a_timeout(http):
    """Sans delai maximum, un serveur lent fait attendre le code indefiniment.
    C'est l'erreur ReadTimeout vue 291 fois sur adsb.lol au projet 2."""
    http.reponse = FakeResponse(["16.21.1"])

    fetch_versions()

    [(url, options)] = http.appels
    assert url == "https://ddragon.leagueoflegends.com/api/versions.json"
    assert options["timeout"] > 0


def test_fetch_versions_raises_on_a_server_error(http):
    """Une page d'erreur ne doit jamais etre lue comme des donnees."""
    http.reponse = FakeResponse(None, status_code=503)

    with pytest.raises(requests.HTTPError):
        fetch_versions()


def test_fetch_versions_refuses_an_empty_list(http):
    """Une liste vide n'est pas « aucune version » : c'est une reponse anormale.
    Mieux vaut s'arreter ici que planter plus loin sans explication."""
    http.reponse = FakeResponse([])

    with pytest.raises(ValueError):
        fetch_versions()


# --- fetch_champions --------------------------------------------------------


def test_fetch_champions_requests_the_english_file_of_the_version(http):
    """Anglais : c'est la langue des noms de champions dans les donnees pro."""
    http.reponse = FakeResponse(CHAMPIONS)

    fetch_champions("16.21.1")

    [(url, options)] = http.appels
    assert url == (
        "https://ddragon.leagueoflegends.com/cdn/16.21.1/data/en_US/champion.json"
    )
    assert options["timeout"] > 0


def test_fetch_champions_returns_the_file(http):
    http.reponse = FakeResponse(CHAMPIONS)

    assert fetch_champions("16.21.1") == CHAMPIONS


def test_fetch_champions_raises_on_an_unknown_version(http):
    """Une version pas encore publiee (ou mal tapee) donne une page 404."""
    http.reponse = FakeResponse(None, status_code=404)

    with pytest.raises(requests.HTTPError):
        fetch_champions("16.99.1")


def test_fetch_champions_refuses_a_file_of_another_version(http):
    """Le fichier annonce sa propre version. Si ce n'est pas celle demandee,
    toutes les lignes seraient etiquetees avec le mauvais patch, sans message."""
    http.reponse = FakeResponse(CHAMPIONS)  # ce faux fichier est en 16.21.1

    with pytest.raises(ValueError):
        fetch_champions("16.20.1")


# --- season_versions --------------------------------------------------------


def test_season_versions_keeps_only_the_latest_season():
    """Les donnees pro couvrent toute la saison : la dimension aussi."""
    versions = ["16.21.1", "16.20.1", "15.24.1", "15.23.1"]

    assert season_versions(versions) == ["16.21.1", "16.20.1"]


def test_season_versions_ignores_malformed_versions():
    """Les 98 versions au format ancien sont ecartees sans faire echouer le tri."""
    versions = ["16.21.1", "16.20.1", "lolpatch_7.20"]

    assert season_versions(versions) == ["16.21.1", "16.20.1"]


def test_season_versions_keeps_the_most_recent_first():
    versions = ["16.3.1", "16.2.1", "16.1.1"]

    assert season_versions(versions) == ["16.3.1", "16.2.1", "16.1.1"]


def test_season_versions_refuses_an_empty_list():
    """Sans cette protection, versions[0] leverait une IndexError obscure."""
    with pytest.raises(ValueError):
        season_versions([])


# --- load_season ------------------------------------------------------------

CDN = "https://ddragon.leagueoflegends.com/cdn"
VERSIONS = "https://ddragon.leagueoflegends.com/api/versions.json"


def champions_url(version):
    return f"{CDN}/{version}/data/en_US/champion.json"


@pytest.fixture
def saison(http):
    """Un Data Dragon miniature : deux patches de la saison 16, un de la 15."""
    http.reponses[VERSIONS] = FakeResponse(["16.2.1", "16.1.1", "15.24.1"])
    for version in ("16.2.1", "16.1.1"):
        http.reponses[champions_url(version)] = FakeResponse(
            {**CHAMPIONS, "version": version}
        )
    return http


def test_load_season_loads_every_patch_of_the_season_in_one_load(saison):
    """2 champions x 2 patches = 4 lignes, en UN seul chargement : le controle
    du nombre de lignes porte alors sur toute la saison."""
    client = FakeBigQuery()

    load_season(client)

    [(rows, destination, _)] = client.appels
    assert len(rows) == 4
    assert destination == "lol-meta-pipeline.lol_raw.ddragon_champions"
    assert {row["patch"] for row in rows} == {"16.2", "16.1"}


def test_load_season_does_not_fetch_the_previous_season(saison):
    load_season(FakeBigQuery())

    urls = [url for url, _ in saison.appels]
    assert champions_url("15.24.1") not in urls


def test_load_season_imposes_the_champions_schema(saison):
    """Le numero est un entier, les roles une liste : BigQuery ne devine rien."""
    client = FakeBigQuery()

    load_season(client)

    [(_, _, config)] = client.appels
    types = {champ.name: (champ.field_type, champ.mode) for champ in config.schema}
    assert types["champion_id"] == ("INTEGER", "REQUIRED")
    assert types["tags"] == ("STRING", "REPEATED")


def test_load_season_returns_the_number_of_rows_loaded(saison):
    assert load_season(FakeBigQuery()) == 4
