import pytest
import requests

import ddragon
from ddragon import fetch_champions, fetch_versions, flatten_champions, patch_of

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


class FakeResponse:
    """Ce que renvoie le faux requests.get : une reponse reglee a la main."""

    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Server Error")

    def json(self):
        return self._data


class FakeHttp:
    """Remplace requests.get pendant un test. On regle la reponse a renvoyer,
    et chaque appel est note pour verifier ce que le code a demande."""

    def __init__(self):
        self.reponse = FakeResponse([])
        self.appels = []

    def get(self, url, **options):
        self.appels.append((url, options))
        return self.reponse


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
