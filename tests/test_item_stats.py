from fakes import FakeBigQuery, FakeHttp, FakeResponse
from item_stats import (
    ITEM_STATS_TABLE,
    flatten_item_stats,
    item_stats_url,
    load_item_stats_season,
)

# Le Couperet noir au 16.22, tel que les fichiers du jeu le decrivent : les
# 20 d'acceleration de competence que Data Dragon n'a pas (verifie le 04/11).
OBJETS = {
    "Items/3071": {
        "itemID": 3071,
        "maxStack": 1,
        "mCanBeSold": True,
        "mItemCalloutSpectator": True,
        "mAbilityHasteMod": 20.0,
        "mFlatHPPoolMod": 400.0,
        "mFlatPhysicalDamageMod": 45.0,
        "__type": "ItemData",
    },
    # Une entree qui n'est pas un objet (pas un numero) : ignoree.
    "Items/ItemGroups/Boots": {"mMaxGroupOwnable": 1, "__type": "ItemGroup"},
}


def stats_de(lignes, item_id):
    return {
        ligne["stat"]: ligne["value"] for ligne in lignes if ligne["item_id"] == item_id
    }


def test_flatten_item_stats_gives_one_row_per_stat_named_like_data_dragon():
    """Sans le "m" du debut : FlatHPPoolMod, comme dans Data Dragon, pour
    pouvoir recouper les deux sources."""
    lignes = flatten_item_stats("16.22", OBJETS)

    assert stats_de(lignes, 3071) == {
        "AbilityHasteMod": 20.0,
        "FlatHPPoolMod": 400.0,
        "FlatPhysicalDamageMod": 45.0,
    }


def test_flatten_item_stats_ignores_fields_that_are_not_stats():
    """maxStack n'est pas une stat ; mCanBeSold vaut True, et True est AUSSI un
    entier pour Python : sans exclusion explicite, il passerait pour 1."""
    stats = stats_de(flatten_item_stats("16.22", OBJETS), 3071)

    assert "CanBeSold" not in stats
    assert "ItemCalloutSpectator" not in stats
    assert "axStack" not in stats


def test_flatten_item_stats_keeps_only_numbered_items():
    lignes = flatten_item_stats("16.22", OBJETS)

    assert {ligne["item_id"] for ligne in lignes} == {3071}


def test_flatten_item_stats_stamps_the_patch():
    for ligne in flatten_item_stats("16.22", OBJETS):
        assert ligne["patch"] == "16.22"


def test_item_stats_url_uses_the_patch_folder():
    assert item_stats_url("16.22") == (
        "https://raw.communitydragon.org/16.22/game/items.cdtb.bin.json"
    )


def test_load_item_stats_season_loads_only_the_missing_patches():
    http = FakeHttp()
    http.reponse = FakeResponse(status_code=404)
    http.reponses[item_stats_url("16.22")] = FakeResponse(OBJETS)
    client = FakeBigQuery(resultat_requete=[{"patch": "16.21"}])

    bilans = load_item_stats_season(["16.22.1", "16.21.1"], http, client)

    assert [bilan["patch"] for bilan in bilans] == ["16.22"]
    [(rows, destination, _)] = client.appels
    assert destination == ITEM_STATS_TABLE
    assert len(rows) == 3


def test_load_item_stats_season_loads_nothing_for_a_patch_not_yet_published():
    http = FakeHttp()
    http.reponse = FakeResponse(status_code=404)
    client = FakeBigQuery(table_absente=True)

    bilans = load_item_stats_season(["16.23.1"], http, client)

    assert client.appels == []
    assert bilans == [{"patch": "16.23", "objets": 0, "stats": 0}]
