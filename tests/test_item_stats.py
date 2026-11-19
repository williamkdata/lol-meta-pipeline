from google.api_core.exceptions import NotFound

from fakes import FakeBigQuery, FakeHttp, FakeQueryJob, FakeResponse
from item_stats import (
    ITEM_GROUPS_SCHEMA,
    ITEM_GROUPS_TABLE,
    ITEM_STATS_TABLE,
    flatten_item_groups,
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


# Quatre objets reels du 16.22 dont certaines stats s'ecrivent SANS le "m" du
# debut dans les fichiers du jeu (bug trouve le 09/11/2026 : jamais chargees).
SANS_M = {
    # Echo de Luden : son mana (flatMPPoolMod).
    "Items/6655": {
        "itemID": 6655,
        "price": 450,
        "epicness": 5,
        "mAbilityHasteMod": 10.0,
        "mFlatMagicDamageMod": 100.0,
        "flatMPPoolMod": 600.0,
    },
    # Lame fantome de Youmuu : sa letalite (PhysicalLethality).
    "Items/3142": {
        "itemID": 3142,
        "mPercentMovementSpeedMod": 0.03999999910593033,
        "mFlatPhysicalDamageMod": 55.0,
        "PhysicalLethality": 18.0,
    },
    # Lame de Doran : son omnivampirisme ; sellBackModifier contient "Mod"
    # mais n'est pas une stat (la part du prix rendue a la revente).
    "Items/1055": {
        "itemID": 1055,
        "mFlatHPPoolMod": 80.0,
        "mFlatPhysicalDamageMod": 10.0,
        "PercentOmnivampMod": 0.02500000037252903,
        "sellBackModifier": 0.4000000059604645,
    },
    # Charme feerique : sa regeneration de mana ; et des nombres qui ne sont
    # pas des stats, avec ou sans "m".
    "Items/1004": {
        "itemID": 1004,
        "percentBaseMPRegenMod": 0.5,
        "specialRecipe": 3003,
        "{4f958685}": 2526,
        "LastMajorChangeMajorPatchVersion": 16,
        "mRequiredLevel": 9,
    },
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


def test_flatten_item_stats_keeps_stats_written_without_the_m_prefix():
    """Mana, letalite, omnivampirisme, regeneration de mana : ecrits sans "m"
    dans les fichiers du jeu. Nommes comme les autres (majuscule au debut)."""
    lignes = flatten_item_stats("16.22", SANS_M)

    assert stats_de(lignes, 6655) == {
        "AbilityHasteMod": 10.0,
        "FlatMagicDamageMod": 100.0,
        "FlatMPPoolMod": 600.0,
    }
    assert stats_de(lignes, 3142) == {
        "PercentMovementSpeedMod": 0.03999999910593033,
        "FlatPhysicalDamageMod": 55.0,
        "PhysicalLethality": 18.0,
    }
    assert stats_de(lignes, 1004) == {"PercentBaseMPRegenMod": 0.5}


def test_flatten_item_stats_ignores_numbers_that_are_not_stats_even_without_m():
    """La part de revente contient "Mod" (sellBackModifier) : pas une stat.
    Ni le niveau requis, ni la recette, ni la version du dernier changement."""
    stats = stats_de(flatten_item_stats("16.22", SANS_M), 1055)

    assert stats == {
        "FlatHPPoolMod": 80.0,
        "FlatPhysicalDamageMod": 10.0,
        "PercentOmnivampMod": 0.02500000037252903,
    }


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


class BigQueryParTable(FakeBigQuery):
    """Un faux BigQuery qui repond SELON LA TABLE interrogee (le faux commun
    repond la meme chose a toutes les requetes) : {table: patches en base}.
    Une table absente du dictionnaire n'existe pas encore."""

    def __init__(self, patches_par_table):
        super().__init__()
        self._par_table = patches_par_table

    def query(self, sql):
        self.requetes.append(sql)
        for table, patches in self._par_table.items():
            if f"`{table}`" in sql:
                return FakeQueryJob([{"patch": p} for p in patches])
        raise NotFound("table absente")


def serveur_objets(fichier_16_22):
    http = FakeHttp()
    http.reponse = FakeResponse(status_code=404)
    http.reponses[item_stats_url("16.22")] = FakeResponse(fichier_16_22)
    return http


def test_load_item_stats_season_loads_only_the_missing_patches():
    # Stats ET groupes manquent au 16.22 : les deux tables sont chargees, avec
    # un seul telechargement. Le Couperet noir (3 stats) ; Lord Dominik et
    # Rappel mortel (2 groupes chacun).
    http = serveur_objets({**GROUPES, **OBJETS})
    client = BigQueryParTable(
        {ITEM_STATS_TABLE: ["16.21"], ITEM_GROUPS_TABLE: ["16.21"]}
    )

    bilans = load_item_stats_season(["16.22.1", "16.21.1"], http, client)

    assert bilans == [{"patch": "16.22", "objets": 1, "stats": 3, "groupes": 4}]
    assert [destination for _, destination, _ in client.appels] == [
        ITEM_STATS_TABLE,
        ITEM_GROUPS_TABLE,
    ]
    assert [url for url, _ in http.appels] == [item_stats_url("16.22")]


def test_a_new_table_fills_its_own_missing_patches_only():
    # Les stats du 16.22 sont deja la, pas les groupes (table ajoutee le
    # 19/11) : seuls les groupes sont charges, rien n'est charge deux fois.
    http = serveur_objets({**GROUPES, **OBJETS})
    client = BigQueryParTable({ITEM_STATS_TABLE: ["16.22"]})

    bilans = load_item_stats_season(["16.22.1"], http, client)

    assert bilans == [{"patch": "16.22", "groupes": 4}]
    [(rows, destination, config)] = client.appels
    assert destination == ITEM_GROUPS_TABLE
    assert config.schema == ITEM_GROUPS_SCHEMA
    assert len(rows) == 4


def test_nothing_is_downloaded_when_every_table_is_complete():
    http = serveur_objets({**GROUPES, **OBJETS})
    client = BigQueryParTable(
        {ITEM_STATS_TABLE: ["16.22"], ITEM_GROUPS_TABLE: ["16.22"]}
    )

    assert load_item_stats_season(["16.22.1"], http, client) == []
    assert http.appels == []


def test_load_item_stats_season_loads_nothing_for_a_patch_not_yet_published():
    http = FakeHttp()
    http.reponse = FakeResponse(status_code=404)
    client = FakeBigQuery(table_absente=True)

    bilans = load_item_stats_season(["16.23.1"], http, client)

    assert client.appels == []
    assert bilans == [{"patch": "16.23", "objets": 0, "stats": 0, "groupes": 0}]


# --- Les groupes d'objets (18/11/2026) : le jeu limite certains cumuls --------
# Le Lord Dominik et le Rappel mortel (16.23) : groupe "LastWhisper", 1 au plus.
GROUPES = {
    "Items/3036": {
        "itemID": 3036,
        "mItemGroups": ["Items/ItemGroups/Default", "Items/ItemGroups/LastWhisper"],
        "__type": "ItemData",
    },
    "Items/3033": {
        "itemID": 3033,
        "mItemGroups": ["Items/ItemGroups/Default", "Items/ItemGroups/LastWhisper"],
        "__type": "ItemData",
    },
    "Items/3071": {"itemID": 3071, "__type": "ItemData"},
    "Items/ItemGroups/LastWhisper": {
        "mItemGroupID": "LastWhisper",
        "mMaxGroupOwnable": 1,
        "__type": "ItemGroup",
    },
    "Items/ItemGroups/Default": {"mItemGroupID": "Default", "__type": "ItemGroup"},
}


def lignes_de(lignes, item_id):
    return sorted(
        (ligne["item_group"], ligne["max_ownable"], ligne["group_defined"])
        for ligne in lignes
        if ligne["item_id"] == item_id
    )


def test_un_objet_a_une_ligne_par_groupe():
    lignes = flatten_item_groups("16.23", GROUPES)

    assert lignes_de(lignes, 3036) == [
        ("Default", None, True),
        ("LastWhisper", 1, True),
    ]
    assert all(ligne["patch"] == "16.23" for ligne in lignes)


def test_deux_objets_du_meme_groupe_limite():
    # Le moteur de build saura qu'on ne peut pas avoir les deux.
    lignes = flatten_item_groups("16.23", GROUPES)

    dans_last_whisper = {
        ligne["item_id"] for ligne in lignes if ligne["item_group"] == "LastWhisper"
    }
    assert dans_last_whisper == {3033, 3036}


def test_un_objet_sans_groupe_n_a_pas_de_ligne():
    assert lignes_de(flatten_item_groups("16.23", GROUPES), 3071) == []


def test_un_groupe_cite_mais_absent_du_fichier_est_garde_et_signale():
    # Jamais perdu en silence : sans sa definition, on ne connait pas sa
    # limite. La ligne reste, marquee "groupe non defini".
    fichier = {
        **GROUPES,
        "Items/3036": {
            "itemID": 3036,
            "mItemGroups": ["Items/ItemGroups/Mystere"],
            "__type": "ItemData",
        },
    }
    assert lignes_de(flatten_item_groups("16.23", fichier), 3036) == [
        ("Mystere", None, False)
    ]


def test_un_groupe_a_la_cle_chiffree_est_retrouve_par_son_empreinte():
    # CommunityDragon remplace une cle par son nom quand il le connait ;
    # sinon, la cle est l'empreinte FNV-1a 32 bits du chemin en minuscules
    # (la meme que pour la fiche des champions). "items/itemgroups/boots" ->
    # {eae58fd1} (controle : "mrperlevel" -> {01262a25}, verifie le 16/11).
    fichier = {
        "Items/3006": {
            "itemID": 3006,
            "mItemGroups": ["Items/ItemGroups/Boots"],
            "__type": "ItemData",
        },
        "{eae58fd1}": {
            "mItemGroupID": "Boots",
            "mMaxGroupOwnable": 1,
            "__type": "ItemGroup",
        },
    }
    assert lignes_de(flatten_item_groups("16.23", fichier), 3006) == [
        ("Boots", 1, True)
    ]
