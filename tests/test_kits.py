import json

from fakes import FakeBigQuery, FakeHttp, FakeQueryJob, FakeResponse
from kits import (
    KIT_SCHEMAS,
    KIT_TABLES,
    ORDRE_CHARGEMENT,
    champion_file_url,
    flatten_champion_record,
    flatten_data_values,
    flatten_formula,
    game_texts_url,
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
            # Deux vraies stats de sa fiche au 16.21 (relevees le 09/11).
            "baseHPModifiable": {"baseValue": 630.0, "__type": "ModifiableFloat"},
            "hpPerLevelModifiable": {"baseValue": 110.0, "__type": "ModifiableFloat"},
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


# --- flatten_champion_record ----------------------------------------------------

AHRI = "Characters/Ahri/CharacterRecords/Root"


def fiche_ahri_16_22():
    """La fiche d'Ahri au 16.22, reduite (releve du 09/11/2026) : stats dans des
    enveloppes {"baseValue": ...}, ressource a cles hachees, une liste de
    nombres, un booleen, du texte, et un sort qui n'est pas la fiche."""
    return {
        AHRI: {
            "baseHPModifiable": {"baseValue": 590.0, "__type": "ModifiableFloat"},
            "damagePerLevelModifiable": {"baseValue": 3.0, "__type": "ModifiableFloat"},
            "baseMR": {"baseValue": 30.0, "__type": "ModifiableFloat"},
            "critDamageMultiplier": 2.0,
            "primaryAbilityResource": {
                "arType": 0,
                "{726ee5cd}": {"baseValue": 418.0, "__type": "ModifiableFloat"},
                "__type": "AbilityResourceSlotInfo",
            },
            "secondaryAbilityResource": {
                "arType": 12,
                "arAllowMaxValueToBeOverridden": True,
            },
            "mAbilitySlotCC": [1, 0],
            "passiveName": "game_character_passiveName_Ahri",
            "__type": "CharacterRecord",
        },
        "Characters/Ahri/Spells/AhriQAbility/AhriQ": {"mCastTime": 0.25},
    }


def test_flatten_champion_record_gives_every_number_of_the_record():
    """Tous les nombres de la fiche, sous leur chemin dans le fichier :
    l'enveloppe {"baseValue": ...} garde le nom de son champ."""
    lignes = flatten_champion_record(fiche_ahri_16_22())

    assert {ligne["field"]: ligne["value"] for ligne in lignes} == {
        "baseHPModifiable": 590.0,
        "damagePerLevelModifiable": 3.0,
        "baseMR": 30.0,
        "critDamageMultiplier": 2.0,
        "primaryAbilityResource.arType": 0.0,
        "primaryAbilityResource.{726ee5cd}": 418.0,
        "secondaryAbilityResource.arType": 12.0,
        "mAbilitySlotCC.0": 1.0,
        "mAbilitySlotCC.1": 0.0,
    }


def test_flatten_champion_record_ignores_booleans_text_and_other_entries():
    """True est aussi un entier pour Python : sans exclusion, il passerait pour 1.
    Le temps d'incantation du Q n'est pas dans la fiche : ignore."""
    champs = {ligne["field"] for ligne in flatten_champion_record(fiche_ahri_16_22())}

    assert "secondaryAbilityResource.arAllowMaxValueToBeOverridden" not in champs
    assert "passiveName" not in champs
    assert not any("mCastTime" in champ for champ in champs)


def test_flatten_champion_record_keeps_the_older_field_names_as_they_are():
    """Au 16.1, les memes stats s'appelaient baseHP (nombre nu) et
    baseSpellBlock. On les garde telles quelles : le renommage se fait en
    staging, ou un test signale un champ attendu qui manque."""
    fichier = {AHRI: {"baseHP": 590.0, "baseSpellBlock": 30.0, "hpPerLevel": 104.0}}

    lignes = flatten_champion_record(fichier)

    assert sorted((ligne["field"], ligne["value"]) for ligne in lignes) == [
        ("baseHP", 590.0),
        ("baseSpellBlock", 30.0),
        ("hpPerLevel", 104.0),
    ]


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


# Le texte du jeu du 16.21 (lol.stringtable.json), reduit a l'infobulle du W
# d'Ambessa (vrai texte, coupe apres le mainText).
TEXTES_16_21 = {
    "generatedtip_spell_ambessaw_tooltipextended": (
        "<mainText>Ambessa gains <shield>@Calc_Shield@ Shield</shield> for "
        "@Shield_Duration@ seconds and braces herself for @Buff_Duration@ "
        "seconds. She then slams the ground, dealing <physicalDamage>"
        "@Calc_Damage_Low@ physical damage</physicalDamage> to nearby enemies, "
        "which increases to <physicalDamage>@Calc_Damage_High@ physical "
        "damage</physicalDamage> if she braced herself from damage from an "
        "enemy champion, large monster, or structure."
        "@SpellModifierDescriptionAppend@</mainText>"
    ),
}


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


def test_kit_rows_includes_the_champion_record():
    """La fiche du champion (stats de base) : une ligne par nombre, avec le
    patch et le champion ; pas de touche ni de sort, elle concerne tout le
    champion."""
    fiche = lignes_ambessa()["record"]

    assert sorted(fiche, key=lambda ligne: ligne["field"]) == [
        {
            "patch": "16.21",
            "champion_id": 799,
            "champion_code": "Ambessa",
            "field": "baseHPModifiable",
            "value": 630.0,
        },
        {
            "patch": "16.21",
            "champion_id": 799,
            "champion_code": "Ambessa",
            "field": "hpPerLevelModifiable",
            "value": 110.0,
        },
    ]


def test_kit_rows_reads_the_tooltip_of_each_spell():
    """Chaque nombre de l'infobulle, avec sa balise et le sort qui le porte."""
    infobulles = kit_rows("16.21", 799, "Ambessa", kit_ambessa(), TEXTES_16_21)[
        "tooltips"
    ]

    commun = {
        "patch": "16.21",
        "champion_id": 799,
        "champion_code": "Ambessa",
        "slot": "W",
        "spell_name": "AmbessaW",
    }
    assert [(ligne["name"], ligne["tag"]) for ligne in infobulles] == [
        ("buff_duration", "mainText"),
        ("calc_damage_high", "physicalDamage"),
        ("calc_damage_low", "physicalDamage"),
        ("calc_shield", "shield"),
        ("shield_duration", "mainText"),
        ("spellmodifierdescriptionappend", "mainText"),
    ]
    for ligne in infobulles:
        assert {k: ligne[k] for k in commun} == commun
    mots = {ligne["name"]: ligne["following_text"] for ligne in infobulles}
    assert mots["calc_shield"] == "Shield for"
    assert mots["calc_damage_low"] == (
        "physical damage to nearby enemies, which increases to"
    )


# Les renvois et les nombres qualifies (26/11, version C) : au 16.23, 173
# infobulles sur 1 568 ne sont que des renvois ({{spell_GnarQ_Tooltip}}), et
# leurs nombres nomment leur sort (@spell.GnarQ:MiniTotalDamage@).


def infobulles_ambessa(textes):
    """Les lignes d'infobulles d'Ambessa : (touche, sort, nom, balise, mots)."""
    lignes = kit_rows("16.21", 799, "Ambessa", kit_ambessa(), textes)["tooltips"]
    return sorted(
        (
            ligne["slot"],
            ligne["spell_name"],
            ligne["name"],
            ligne["tag"],
            ligne["following_text"],
        )
        for ligne in lignes
    )


def test_kit_rows_follows_the_references_of_a_tooltip():
    textes = {
        "generatedtip_spell_ambessaw_tooltipextended": "{{spell_AmbessaW_Tooltip}}",
        "spell_ambessaw_tooltip": TEXTES_16_21[
            "generatedtip_spell_ambessaw_tooltipextended"
        ],
    }

    assert infobulles_ambessa(textes) == infobulles_ambessa(TEXTES_16_21)
    assert infobulles_ambessa(textes) != []


def test_a_number_naming_another_spell_goes_to_that_spell():
    # Le Q de Karma cite des calculs de son R (KarmaMantra) : le Q renforce est
    # calcule dans le R. Le nombre va au sort qui porte le calcul.
    textes = {
        "generatedtip_spell_ambessaq_tooltipextended": (
            "<physicalDamage>@spell.AmbessaR:Calc_Damage@ physical "
            "damage</physicalDamage>"
        ),
    }

    assert infobulles_ambessa(textes) == [
        ("R", "AmbessaR", "calc_damage", "physicalDamage", "physical damage"),
    ]


def test_a_number_of_the_spell_itself_written_two_ways_gives_one_row():
    textes = {
        "generatedtip_spell_ambessaw_tooltipextended": (
            "<shield>@Calc_Shield@ Shield</shield> puis "
            "<shield>@spell.AmbessaW:Calc_Shield@ encore</shield>"
        ),
    }

    assert infobulles_ambessa(textes) == [
        ("W", "AmbessaW", "calc_shield", "shield", "Shield puis"),
    ]


def test_the_spell_own_tooltip_gives_the_words_first():
    # Le meme calcul du R cite par l'infobulle du Q (lue avant) et par celle du
    # R : les mots qui le suivent (de quoi un pourcentage est pris) viennent de
    # l'infobulle du R lui-meme.
    textes = {
        "generatedtip_spell_ambessaq_tooltipextended": (
            "<physicalDamage>@spell.AmbessaR:Calc_Damage@ vu du Q</physicalDamage>"
        ),
        "generatedtip_spell_ambessar_tooltipextended": (
            "<physicalDamage>@Calc_Damage@ vu du R</physicalDamage>"
        ),
    }

    assert infobulles_ambessa(textes) == [
        ("R", "AmbessaR", "calc_damage", "physicalDamage", "vu du R"),
    ]


def test_the_own_tooltip_wins_even_when_it_names_its_own_spell():
    # Le R ecrit son propre nombre sous la forme qualifiee : il reste a lui
    # (sabotage du 26/11 : compare sans minuscules, il passait pour cite, et
    # les mots du Q gagnaient).
    textes = {
        "generatedtip_spell_ambessaq_tooltipextended": (
            "<physicalDamage>@spell.AmbessaR:Calc_Damage@ vu du Q</physicalDamage>"
        ),
        "generatedtip_spell_ambessar_tooltipextended": (
            "<physicalDamage>@spell.AmbessaR:Calc_Damage@ vu du R</physicalDamage>"
        ),
    }

    assert infobulles_ambessa(textes) == [
        ("R", "AmbessaR", "calc_damage", "physicalDamage", "vu du R"),
    ]


def test_the_same_number_with_two_tags_keeps_both():
    textes = {
        "generatedtip_spell_ambessaq_tooltipextended": (
            "<physicalDamage>@spell.AmbessaR:Calc_Damage@</physicalDamage>"
        ),
        "generatedtip_spell_ambessar_tooltipextended": (
            "<trueDamage>@Calc_Damage@</trueDamage>"
        ),
    }

    assert [ligne[:4] for ligne in infobulles_ambessa(textes)] == [
        ("R", "AmbessaR", "calc_damage", "physicalDamage"),
        ("R", "AmbessaR", "calc_damage", "trueDamage"),
    ]


def test_a_number_naming_a_spell_without_a_key_is_left_out():
    # AmbessaWShield est un sort secondaire, derriere aucune touche : ses
    # formules ne sont pas chargees, la ligne ne rejoindrait rien.
    textes = {
        "generatedtip_spell_ambessaw_tooltipextended": (
            "<shield>@spell.AmbessaWShield:Calc_Shield@</shield>"
        ),
    }

    assert infobulles_ambessa(textes) == []


def test_every_column_of_a_kit_row_is_in_its_table_schema():
    """Une colonne fabriquee mais absente du schema serait refusee par BigQuery
    au premier vrai chargement (following_text, ajoute le 18/11)."""
    lignes = kit_rows("16.21", 799, "Ambessa", kit_ambessa(), TEXTES_16_21)
    for table, rangees in lignes.items():
        colonnes = {champ.name for champ in KIT_SCHEMAS[table]}
        for rangee in rangees:
            assert set(rangee) <= colonnes, (table, set(rangee) - colonnes)


def test_kit_rows_without_the_game_texts_gives_no_tooltip():
    assert lignes_ambessa()["tooltips"] == []


def test_every_kit_table_has_a_schema_and_a_place_in_the_loading_order():
    """Une table ajoutee sans schema, ou oubliee dans l'ordre de chargement,
    ne serait jamais chargee : les trois listes doivent dire la meme chose."""
    assert set(KIT_SCHEMAS) == set(KIT_TABLES) == set(ORDRE_CHARGEMENT)
    assert ORDRE_CHARGEMENT[-1] == "formulas"


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
        http.reponses[game_texts_url(patch)] = FakeResponse(
            {"entries": TEXTES_16_21, "version": "test"}
        )
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
        KIT_TABLES["record"],
        KIT_TABLES["tooltips"],
        KIT_TABLES["formulas"],
    ]


def test_load_patch_kits_downloads_the_game_texts_once_per_patch():
    """32 Mo par patch : une seule fois, pas une fois par champion."""
    http = serveur(champions=((799, "Ambessa"), (800, "Bis")))

    load_patch_kits("16.21", [(799, "Ambessa"), (800, "Bis")], http, FakeBigQuery())

    assert [url for url, _ in http.appels].count(game_texts_url("16.21")) == 1


def test_load_patch_kits_downloads_the_game_texts_only_when_needed():
    http = serveur()

    load_patch_kits(
        "16.21", [(799, "Ambessa")], http, FakeBigQuery(), tables=("values",)
    )

    assert game_texts_url("16.21") not in [url for url, _ in http.appels]


def test_load_patch_kits_waits_for_game_texts_not_yet_published():
    """Texte du jeu absent (404) : les autres tables sont chargees, pas les
    infobulles ; le patch y manquera encore, il sera repris le lendemain."""
    http = serveur()
    http.reponses[game_texts_url("16.21")] = FakeResponse(status_code=404)
    client = FakeBigQuery()

    load_patch_kits("16.21", [(799, "Ambessa")], http, client)

    chargees = [destination for _, destination, _ in client.appels]
    assert KIT_TABLES["tooltips"] not in chargees
    assert KIT_TABLES["formulas"] in chargees


def test_load_patch_kits_reports_only_the_tables_it_loaded():
    """Le journal du 09/11 comptait aussi les tables non chargees, et trompait."""
    bilan = load_patch_kits(
        "16.21", [(799, "Ambessa")], serveur(), FakeBigQuery(), tables=("record",)
    )

    assert bilan["record"] == 2
    assert "formulas" not in bilan
    assert "tooltips" not in bilan


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
    assert fichiers == [game_texts_url("16.21"), champion_file_url("16.21", "Ambessa")]


class FakeBigQueryParTable(FakeBigQuery):
    """Un faux BigQuery qui repond, pour chaque table du kit, SES patches deja
    charges (le faux de base repond la meme chose a toutes les requetes)."""

    def __init__(self, patches_par_table):
        super().__init__()
        self.patches_par_table = patches_par_table

    def query(self, sql):
        self.requetes.append(sql)
        for table, patches in self.patches_par_table.items():
            # Les accents graves evitent de confondre kit_formulas et
            # kit_formula_parts (le premier nom est le debut du second).
            if f"`{KIT_TABLES[table]}`" in sql:
                return FakeQueryJob([{"patch": patch} for patch in patches])
        raise AssertionError(f"requete inattendue : {sql}")


def test_loaded_kit_patches_reads_the_table_it_is_asked_for():
    client = FakeBigQueryParTable({"record": ["16.20"], "formulas": ["16.21"]})

    assert loaded_kit_patches(client, "record") == {"16.20"}
    assert loaded_kit_patches(client) == {"16.21"}


def test_load_kits_season_completes_only_the_missing_tables():
    """La fiche (ajoutee le 09/11) manque au 16.21 ; les trois autres tables y
    sont : seule la fiche est chargee, rien n'est charge deux fois."""
    http = serveur(patches_publies=("16.21", "16.20"))
    deja = ["16.21", "16.20"]
    client = FakeBigQueryParTable(
        {
            "values": deja,
            "parts": deja,
            "tooltips": deja,
            "formulas": deja,
            "record": ["16.20"],
        }
    )

    bilans = load_kits_season(["16.21.1", "16.20.1"], http, client)

    assert [bilan["patch"] for bilan in bilans] == ["16.21"]
    assert [destination for _, destination, _ in client.appels] == [
        KIT_TABLES["record"]
    ]


def test_load_kits_season_loads_a_new_patch_in_every_table():
    http = serveur(patches_publies=("16.21", "16.20"))
    client = FakeBigQueryParTable({table: ["16.20"] for table in ORDRE_CHARGEMENT})

    load_kits_season(["16.21.1", "16.20.1"], http, client)

    assert [destination for _, destination, _ in client.appels] == [
        KIT_TABLES[table] for table in ORDRE_CHARGEMENT
    ]


def test_load_kits_season_downloads_nothing_when_every_table_is_complete():
    http = serveur(patches_publies=("16.21", "16.20"))
    deja = ["16.21", "16.20"]
    client = FakeBigQueryParTable({table: deja for table in ORDRE_CHARGEMENT})

    assert load_kits_season(["16.21.1", "16.20.1"], http, client) == []
    assert not [url for url, _ in http.appels if "communitydragon" in url]
    assert client.appels == []


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
