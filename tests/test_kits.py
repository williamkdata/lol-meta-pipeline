import json

from fakes import FakeBigQuery, FakeHttp, FakeResponse
from kits import (
    KIT_TABLES,
    champion_file_url,
    flatten_data_values,
    flatten_formula,
    kit_rows,
    load_kits_season,
    load_patch_kits,
    loaded_kit_patches,
    season_patches,
    spell_slots,
)

RACINE = "Characters/Ambessa/CharacterRecords/Root"
SORTS = "Characters/Ambessa/Spells/"


def fichier_ambessa():
    """Un fichier de champion CommunityDragon, reduit a ce qui sert ici : la
    fiche du champion et ses sorts (structure relevee le 04/11 sur 16.21)."""
    return {
        RACINE: {
            "mCharacterName": "Ambessa",
            "spellNames": [
                "AmbessaQAbility/AmbessaQ",
                "AmbessaWAbility/AmbessaW",
                "AmbessaEAbility/AmbessaE",
                "AmbessaRAbility/AmbessaR",
            ],
            "passiveSpell": "AmbessaPassive",
            "__type": "CharacterRecord",
        },
        SORTS + "AmbessaQAbility/AmbessaQ": {"mSpell": {}, "__type": "SpellObject"},
        SORTS + "AmbessaWAbility/AmbessaW": {"mSpell": {}, "__type": "SpellObject"},
        SORTS + "AmbessaEAbility/AmbessaE": {"mSpell": {}, "__type": "SpellObject"},
        SORTS + "AmbessaRAbility/AmbessaR": {"mSpell": {}, "__type": "SpellObject"},
        SORTS + "AmbessaPassiveAbility/AmbessaPassive": {
            "mSpell": {},
            "__type": "SpellObject",
        },
        # Un sort secondaire (le bouclier du W) : il n'est derriere aucune touche.
        SORTS + "AmbessaWAbility/AmbessaWShield": {
            "mSpell": {},
            "__type": "SpellObject",
        },
    }


def test_spell_slots_reads_q_w_e_r_in_order():
    """La position dans spellNames EST la touche. Verifie le 04/11 sur les 173
    champions du 16.21 : meme ordre dans CommunityDragon et Data Dragon, et memes
    noms que le client du jeu range par son champ explicite spellKey. Les noms
    INTERNES, eux, peuvent mentir : chez Naafiri, "NaafiriR" est sur W."""
    touches = spell_slots(fichier_ambessa())

    assert touches["Q"] == SORTS + "AmbessaQAbility/AmbessaQ"
    assert touches["W"] == SORTS + "AmbessaWAbility/AmbessaW"
    assert touches["E"] == SORTS + "AmbessaEAbility/AmbessaE"
    assert touches["R"] == SORTS + "AmbessaRAbility/AmbessaR"


def test_spell_slots_finds_the_passive_from_its_short_name():
    """La fiche ne donne que "AmbessaPassive" : il faut retrouver le chemin."""
    touches = spell_slots(fichier_ambessa())

    assert touches["P"] == SORTS + "AmbessaPassiveAbility/AmbessaPassive"


def test_spell_slots_ignores_secondary_spells():
    """Le bouclier du W est un sort a part, mais aucune touche ne le lance."""
    assert len(spell_slots(fichier_ambessa())) == 5


def test_spell_slots_skips_a_spell_missing_from_the_file():
    """Certains noms internes sont des empreintes illisibles : un sort peut
    manquer. La touche est absente, sans erreur : on pourra la compter."""
    fichier = fichier_ambessa()
    del fichier[SORTS + "AmbessaEAbility/AmbessaE"]

    touches = spell_slots(fichier)

    assert "E" not in touches
    assert set(touches) == {"Q", "W", "R", "P"}


def test_spell_slots_works_without_a_passive_name():
    fichier = fichier_ambessa()
    del fichier[RACINE]["passiveSpell"]

    assert set(spell_slots(fichier)) == {"Q", "W", "E", "R"}


def test_spell_slots_ignores_upper_and_lower_case():
    """Fiddlesticks : fiche sous "FiddleSticks", sorts sous "Fiddlesticks". Et
    Naafiri ecrit "Naafiriw" pour un sort range sous "NaafiriW"."""
    fichier = {
        "Characters/FiddleSticks/CharacterRecords/Root": {
            "spellNames": [
                "FiddleSticksQAbility/FiddleSticksQ",
                "FiddleSticksWAbility/FiddlesticksW",
                "FiddleSticksEAbility/FiddleSticksE",
                "FiddleSticksRAbility/FiddleSticksR",
            ],
            "__type": "CharacterRecord",
        },
        "Characters/Fiddlesticks/Spells/FiddleSticksQAbility/FiddleSticksQ": {},
        "Characters/Fiddlesticks/Spells/FiddleSticksWAbility/FiddleSticksW": {},
        "Characters/Fiddlesticks/Spells/FiddleSticksEAbility/FiddleSticksE": {},
        "Characters/Fiddlesticks/Spells/FiddleSticksRAbility/FiddleSticksR": {},
    }

    touches = spell_slots(fichier)

    assert (
        touches["W"]
        == "Characters/Fiddlesticks/Spells/FiddleSticksWAbility/FiddleSticksW"
    )
    assert set(touches) == {"Q", "W", "E", "R"}


def test_spell_slots_finds_the_passive_through_its_ability_when_unnamed():
    """Ahri n'a pas de champ passiveSpell : son passif se retrouve par la
    capacite "...PassiveAbility" et son sort principal (mRootSpell)."""
    fichier = fichier_ambessa()
    del fichier[RACINE]["passiveSpell"]
    fichier[SORTS + "AmbessaPassiveAbility"] = {
        "mRootSpell": SORTS + "AmbessaPassiveAbility/AmbessaPassive",
        "__type": "AbilityObject",
    }

    assert spell_slots(fichier)["P"] == SORTS + "AmbessaPassiveAbility/AmbessaPassive"


MALPHITE = "Characters/Malphite/Spells/"


def fichier_malphite(capacites_en_plus=()):
    """Malphite : pas de passiveSpell, et son passif (Bouclier de granit)
    s'appelle "MalphiteShield", sans le mot "passive". mAbilities n'est pas
    range par touche (verifie le 04/11 : 85 champions sur 173 dans le desordre)."""
    noms = {
        "Q": "SeismicShardAbility/SeismicShard",
        "W": "ObduracyAbility/Obduracy",
        "E": "LandslideAbility/Landslide",
        "R": "UFSlashAbility/UFSlash",
    }
    capacites = {
        MALPHITE + "MalphiteShieldAbility": MALPHITE
        + "MalphiteShieldAbility/MalphiteShield",
        MALPHITE + "UFSlashAbility": MALPHITE + noms["R"],
        MALPHITE + "SeismicShardAbility": MALPHITE + noms["Q"],
        MALPHITE + "LandslideAbility": MALPHITE + noms["E"],
        MALPHITE + "ObduracyAbility": MALPHITE + noms["W"],
    }
    capacites.update(dict(capacites_en_plus))
    fichier = {
        "Characters/Malphite/CharacterRecords/Root": {
            "spellNames": [noms[t] for t in "QWER"],
            "mAbilities": list(capacites),
            "__type": "CharacterRecord",
        }
    }
    for capacite, sort_principal in capacites.items():
        fichier[capacite] = {"mRootSpell": sort_principal, "__type": "AbilityObject"}
        fichier[sort_principal] = {"mSpell": {}, "__type": "SpellObject"}
    return fichier


def test_spell_slots_finds_the_passive_by_elimination():
    """Le passif est la capacite qui reste quand on a retire Q, W, E et R :
    ni l'ordre de mAbilities ni les noms ne comptent."""
    touches = spell_slots(fichier_malphite())

    assert touches["P"] == MALPHITE + "MalphiteShieldAbility/MalphiteShield"
    assert touches["Q"] == MALPHITE + "SeismicShardAbility/SeismicShard"


def test_spell_slots_does_not_guess_when_two_abilities_are_left():
    """Un champion qui se transforme a plus de 5 capacites : s'il en reste deux
    et qu'aucune ne s'appelle "...PassiveAbility", pas de passif plutot qu'un
    mauvais."""
    en_plus = {
        MALPHITE + "MalphiteRockFormAbility": MALPHITE
        + "MalphiteRockFormAbility/RockForm"
    }

    assert "P" not in spell_slots(fichier_malphite(en_plus))


# --- flatten_formula --------------------------------------------------------

# Vraies formules relevees le 04/11 sur CommunityDragon 16.21.
BOUCLIER_AMBESSA_W = {
    "mFormulaParts": [
        {
            "mStartValue": 50.0,
            "mEndValue": 320.0,
            "__type": "ByCharLevelInterpolationCalculationPart",
        },
        {
            "mStat": 2,
            "mStatFormula": 2,
            "mCoefficient": 1.5,
            "__type": "StatByCoefficientCalculationPart",
        },
    ],
    "__type": "GameCalculation",
}

DEGATS_AHRI_Q = {
    "mSimpleTooltipCalculationDisplay": 6,
    "mFormulaParts": [
        {"mDataValue": "BaseDamage", "__type": "NamedDataValueCalculationPart"},
        {"mCoefficient": 0.5, "__type": "StatByCoefficientCalculationPart"},
    ],
    "__type": "GameCalculation",
}

DEGATS_FORTS_AMBESSA_W = {
    "mMultiplier": {
        "mDataValue": "HighDamageMultiplier",
        "__type": "NamedDataValueCalculationPart",
    },
    "mModifiedGameCalculation": "Calc_Damage_Low",
    "__type": "GameCalculationModified",
}


def par_chemin(lignes):
    return {ligne["part_path"]: ligne for ligne in lignes}


def test_flatten_formula_gives_one_row_per_piece_with_its_path():
    lignes = par_chemin(flatten_formula(BOUCLIER_AMBESSA_W))

    assert set(lignes) == {"", "mFormulaParts.0", "mFormulaParts.1"}
    assert lignes[""]["part_type"] == "GameCalculation"


def test_flatten_formula_reads_a_value_that_grows_with_level():
    niveau = par_chemin(flatten_formula(BOUCLIER_AMBESSA_W))["mFormulaParts.0"]

    assert niveau["part_type"] == "ByCharLevelInterpolationCalculationPart"
    assert (niveau["start_value"], niveau["end_value"]) == (50.0, 320.0)


def test_flatten_formula_reads_a_stat_ratio_with_its_codes():
    """Ambessa W : 1,5 x la stat 2 en formule 2 = 150 % de l'attaque bonus."""
    ratio = par_chemin(flatten_formula(BOUCLIER_AMBESSA_W))["mFormulaParts.1"]

    assert (ratio["stat"], ratio["stat_formula"], ratio["coefficient"]) == (2, 2, 1.5)


def test_flatten_formula_applies_the_default_codes_to_stat_pieces():
    """Ahri Q : {"mCoefficient": 0.5} sans aucun code. Le fichier omet les
    valeurs par defaut : stat 0 (AP), formule 0 (totale) -- verifie avec Meraki."""
    ratio = par_chemin(flatten_formula(DEGATS_AHRI_Q))["mFormulaParts.1"]

    assert (ratio["stat"], ratio["stat_formula"], ratio["coefficient"]) == (0, 0, 0.5)


def test_flatten_formula_leaves_the_stat_empty_on_other_pieces():
    """Une valeur par rang n'est pas un ratio AP : sa stat reste vide."""
    par_rang = par_chemin(flatten_formula(DEGATS_AHRI_Q))["mFormulaParts.0"]

    assert par_rang["data_value"] == "BaseDamage"
    assert par_rang["stat"] is None
    assert par_rang["stat_formula"] is None


def test_flatten_formula_keeps_the_link_of_a_modified_formula():
    """Les degats forts du W = les degats faibles x un multiplicateur."""
    lignes = par_chemin(flatten_formula(DEGATS_FORTS_AMBESSA_W))

    assert lignes[""]["modified_calc"] == "Calc_Damage_Low"
    assert lignes["mMultiplier"]["data_value"] == "HighDamageMultiplier"


def test_flatten_formula_descends_into_nested_pieces():
    """Une somme de morceaux dans un produit : le chemin dit ou est chacun."""
    formule = {
        "mFormulaParts": [
            {
                "mPart1": {
                    "mSubparts": [
                        {"mNumber": 10.0, "__type": "NumberCalculationPart"},
                        {
                            "mStat": 12,
                            "mCoefficient": 0.04,
                            "__type": "StatByCoefficientCalculationPart",
                        },
                    ],
                    "__type": "SumOfSubPartsCalculationPart",
                },
                "mPart2": {"mNumber": 2.0, "__type": "NumberCalculationPart"},
                "__type": "ProductOfSubPartsCalculationPart",
            }
        ],
        "__type": "GameCalculation",
    }

    lignes = par_chemin(flatten_formula(formule))

    assert lignes["mFormulaParts.0.mPart1.mSubparts.0"]["number"] == 10.0
    assert lignes["mFormulaParts.0.mPart1.mSubparts.1"]["stat"] == 12
    assert lignes["mFormulaParts.0.mPart2"]["number"] == 2.0
    assert len(lignes) == 6


def test_flatten_formula_keeps_an_unknown_piece_type():
    """Un type jamais vu n'est pas perdu : il apparait, on pourra le compter."""
    formule = {
        "mFormulaParts": [{"mFoo": 1, "__type": "TypeInconnuCalculationPart"}],
        "__type": "GameCalculation",
    }

    lignes = par_chemin(flatten_formula(formule))

    assert lignes["mFormulaParts.0"]["part_type"] == "TypeInconnuCalculationPart"


# --- flatten_data_values ----------------------------------------------------

# Le W d'Ambessa au 16.21 : 7 cases ; la case 0 est le rang 0 (sort pas appris).
SORT_AMBESSA_W = {
    "DataValues": [
        {
            "name": "BaseDamage",
            "values": [25.0, 50.0, 75.0, 100.0, 125.0, 150.0, 175.0],
            "__type": "SpellDataValue",
        },
        {
            "name": "Shield_Duration",
            "values": [1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5],
            "__type": "SpellDataValue",
        },
    ]
}


def test_flatten_data_values_starts_at_rank_1():
    """Meraki : 50/75/100/125/150. Lire la case 0 comme le rang 1 decalerait
    toutes les valeurs d'un cran."""
    degats = [
        ligne
        for ligne in flatten_data_values(SORT_AMBESSA_W)
        if ligne["value_name"] == "BaseDamage"
    ]

    assert [(ligne["spell_rank"], ligne["value"]) for ligne in degats[:5]] == [
        (1, 50.0),
        (2, 75.0),
        (3, 100.0),
        (4, 125.0),
        (5, 150.0),
    ]
    assert min(ligne["spell_rank"] for ligne in degats) == 1


def test_flatten_data_values_keeps_ranks_up_to_6():
    """Toutes les listes ont 7 cases ; 11 sorts ont 6 rangs (Data Dragon). Le
    vrai nombre de rangs de chaque sort viendra de Data Dragon (maxrank)."""
    lignes = flatten_data_values(SORT_AMBESSA_W)

    assert len(lignes) == 2 * 6
    assert max(ligne["spell_rank"] for ligne in lignes) == 6


def test_flatten_data_values_skips_a_value_without_a_list():
    """102 valeurs sans liste au 16.21 ("Test", "URFManaCost"...). On n'invente
    pas de zeros : un sort a 0 degat serait une fausse information."""
    sort = {"DataValues": [{"name": "Test", "__type": "SpellDataValue"}]}

    assert flatten_data_values(sort) == []


def test_flatten_data_values_reads_the_older_field_names():
    """Jusqu'au 16.5, les memes valeurs s'appelaient mName / mValues (name /
    values depuis le 16.6). Sans ce cas, 0 ligne pour 5 patches, sans erreur."""
    ancien = {
        "DataValues": [
            {
                "mName": "BaseDamage",
                "mValues": [25.0, 50.0, 75.0, 100.0, 125.0, 150.0, 175.0],
                "__type": "SpellDataValue",
            }
        ]
    }

    assert flatten_data_values(ancien) == [
        ligne
        for ligne in flatten_data_values(SORT_AMBESSA_W)
        if ligne["value_name"] == "BaseDamage"
    ]


def test_flatten_data_values_without_any_value():
    assert flatten_data_values({}) == []


# --- kit_rows ---------------------------------------------------------------


def kit_ambessa():
    """Le fichier d'Ambessa, avec les vraies formules et valeurs de son W."""
    fichier = fichier_ambessa()
    fichier[SORTS + "AmbessaWAbility/AmbessaW"]["mSpell"] = {
        "mSpellCalculations": {
            "Calc_Shield": BOUCLIER_AMBESSA_W,
            "Calc_Damage_High": DEGATS_FORTS_AMBESSA_W,
        },
        **SORT_AMBESSA_W,
    }
    return fichier


def lignes_ambessa():
    return kit_rows("16.21", 799, "Ambessa", kit_ambessa())


def test_kit_rows_stamps_every_row_with_patch_champion_slot_and_spell():
    lignes = lignes_ambessa()

    for table in ("formulas", "parts", "values"):
        for ligne in lignes[table]:
            assert ligne["patch"] == "16.21"
            assert (ligne["champion_id"], ligne["champion_code"]) == (799, "Ambessa")
            assert (ligne["slot"], ligne["spell_name"]) == ("W", "AmbessaW")


def test_kit_rows_keeps_one_row_per_formula_with_its_whole_tree():
    """La formule entiere est gardee : pour recalculer, il faut savoir quel
    morceau multiplie quel autre, et c'est l'arbre qui le dit."""
    formules = {ligne["calc_name"]: ligne for ligne in lignes_ambessa()["formulas"]}

    assert set(formules) == {"Calc_Shield", "Calc_Damage_High"}
    assert json.loads(formules["Calc_Shield"]["formula"]) == BOUCLIER_AMBESSA_W


def test_kit_rows_writes_the_same_text_for_the_same_formula():
    """Cles dans un autre ordre, meme formule : meme texte. Sinon, comparer deux
    patches montrerait de faux changements."""
    fichier = kit_ambessa()
    calculs = fichier[SORTS + "AmbessaWAbility/AmbessaW"]["mSpell"][
        "mSpellCalculations"
    ]
    calculs["Calc_Shield"] = dict(reversed(list(BOUCLIER_AMBESSA_W.items())))

    autre = kit_rows("16.21", 799, "Ambessa", fichier)["formulas"]
    texte = {ligne["calc_name"]: ligne["formula"] for ligne in autre}
    reference = {
        ligne["calc_name"]: ligne["formula"] for ligne in lignes_ambessa()["formulas"]
    }

    assert texte["Calc_Shield"] == reference["Calc_Shield"]


def test_kit_rows_flattens_the_parts_with_their_formula_name():
    morceaux = lignes_ambessa()["parts"]

    ratio = [
        ligne
        for ligne in morceaux
        if ligne["calc_name"] == "Calc_Shield"
        and ligne["part_path"] == "mFormulaParts.1"
    ]
    assert [
        (ligne["stat"], ligne["stat_formula"], ligne["coefficient"]) for ligne in ratio
    ] == [(2, 2, 1.5)]


def test_kit_rows_includes_the_values_by_rank():
    valeurs = lignes_ambessa()["values"]

    assert len(valeurs) == 2 * 6
    assert {ligne["value_name"] for ligne in valeurs} == {
        "BaseDamage",
        "Shield_Duration",
    }


def test_kit_rows_ignores_spells_behind_no_key():
    """Le bouclier secondaire du W n'est derriere aucune touche : pas de ligne."""
    fichier = kit_ambessa()
    fichier[SORTS + "AmbessaWAbility/AmbessaWShield"]["mSpell"] = {
        "mSpellCalculations": {"Calc_Secondaire": BOUCLIER_AMBESSA_W}
    }

    noms = {
        ligne["calc_name"]
        for ligne in kit_rows("16.21", 799, "Ambessa", fichier)["formulas"]
    }

    assert "Calc_Secondaire" not in noms


# --- le chargeur ------------------------------------------------------------

CHAMPIONS_DD = "https://ddragon.leagueoflegends.com/cdn/{}/data/en_US/champion.json"


def serveur(patches_publies=("16.21",), champions=((799, "Ambessa"),)):
    """Un faux internet : Data Dragon (liste des champions) et CommunityDragon
    (un fichier par champion et par patch publie ; les autres repondent 404)."""
    http = FakeHttp()
    http.reponse = FakeResponse(status_code=404)
    for version in ("16.21.1", "16.20.1"):
        http.reponses[CHAMPIONS_DD.format(version)] = FakeResponse(
            {"data": {code: {"key": str(cid), "id": code} for cid, code in champions}}
        )
    for patch in patches_publies:
        for _, code in champions:
            http.reponses[champion_file_url(patch, code)] = FakeResponse(kit_ambessa())
    return http


def test_champion_file_url_uses_the_patch_folder_and_lower_case():
    assert champion_file_url("16.21", "MonkeyKing") == (
        "https://raw.communitydragon.org/16.21/game/data/characters/"
        "monkeyking/monkeyking.bin.json"
    )


def test_load_patch_kits_loads_the_formulas_last():
    """kit_formulas sert de marqueur : un patch qui y figure est complet."""
    client = FakeBigQuery()

    load_patch_kits("16.21", [(799, "Ambessa")], serveur(), client)

    assert [destination for _, destination, _ in client.appels] == [
        KIT_TABLES["values"],
        KIT_TABLES["parts"],
        KIT_TABLES["formulas"],
    ]


def test_load_patch_kits_skips_and_counts_a_missing_champion():
    """Un champion tout juste sorti peut manquer : on le saute et on le compte."""
    http = serveur(champions=((799, "Ambessa"), (999, "Nouveau")))
    del http.reponses[champion_file_url("16.21", "Nouveau")]

    bilan = load_patch_kits(
        "16.21", [(799, "Ambessa"), (999, "Nouveau")], http, FakeBigQuery()
    )

    assert bilan["absents"] == ["Nouveau"]
    assert bilan["champions"] == 1
    assert bilan["formulas"] == 2


def test_load_patch_kits_loads_nothing_for_a_patch_not_yet_published():
    """CommunityDragon publie un patch un peu apres sa sortie : tout repond 404,
    rien n'est charge, et le patch sera repris le lendemain."""
    client = FakeBigQuery()

    bilan = load_patch_kits("16.22", [(799, "Ambessa")], serveur(), client)

    assert client.appels == []
    assert bilan["champions"] == 0


def test_season_patches_keeps_the_latest_version_of_each_patch():
    versions = ["16.21.1", "16.20.2", "16.20.1", "15.24.1"]

    assert season_patches(versions) == {"16.21": "16.21.1", "16.20": "16.20.2"}


def test_loaded_kit_patches_is_empty_on_the_very_first_run():
    assert loaded_kit_patches(FakeBigQuery(table_absente=True)) == set()


def test_load_kits_season_loads_only_the_missing_patches():
    """16.20 est deja en base : seul 16.21 est telecharge et charge."""
    http = serveur(patches_publies=("16.21", "16.20"))
    client = FakeBigQuery(resultat_requete=[{"patch": "16.20"}])

    bilans = load_kits_season(["16.21.1", "16.20.1"], http, client)

    assert [bilan["patch"] for bilan in bilans] == ["16.21"]
    fichiers = [url for url, _ in http.appels if "communitydragon" in url]
    assert fichiers == [champion_file_url("16.21", "Ambessa")]


def test_load_patch_kits_can_load_only_some_tables():
    """Completer un patch sans rien effacer : du 16.1 au 16.5, seules les
    valeurs par rang manquaient (0 ligne) ; formules et morceaux etaient bons."""
    client = FakeBigQuery()

    bilan = load_patch_kits(
        "16.21", [(799, "Ambessa")], serveur(), client, tables=("values",)
    )

    assert [destination for _, destination, _ in client.appels] == [
        KIT_TABLES["values"]
    ]
    assert bilan["values"] == 2 * 6
