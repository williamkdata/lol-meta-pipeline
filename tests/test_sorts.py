import pytest

from sorts import evaluate_formula

# Les vraies formules et valeurs par rang d'Ahri (16.22, stg_kit__formulas et
# stg_kit__values).
AHRI_Q = {
    "TotalDamage": {
        "__type": "GameCalculation",
        "mFormulaParts": [
            {"__type": "NamedDataValueCalculationPart", "mDataValue": "BaseDamage"},
            {"__type": "StatByCoefficientCalculationPart", "mCoefficient": 0.5},
        ],
    }
}
AHRI_Q_VALEURS = {"BaseDamage": [35.0, 60.0, 85.0, 110.0, 135.0, 160.0]}

AHRI_W = {
    "SingleFireDamage": {
        "__type": "GameCalculation",
        "mFormulaParts": [
            {"__type": "NamedDataValueCalculationPart", "mDataValue": "BaseDamage"},
            {"__type": "StatByNamedDataValueCalculationPart", "mDataValue": "APRatio"},
        ],
    },
    "MultiFireDamage": {
        "__type": "GameCalculationModified",
        "mModifiedGameCalculation": "SingleFireDamage",
        "mMultiplier": {
            "__type": "NamedDataValueCalculationPart",
            "mDataValue": "RepeatDamageMod",
        },
    },
}
AHRI_W_VALEURS = {
    "BaseDamage": [40.0, 60.0, 80.0, 100.0, 120.0, 140.0],
    "APRatio": [0.4] * 6,
    "RepeatDamageMod": [0.4] * 6,
}


def nombre(x):
    """Un morceau "nombre fixe", pour ecrire les arbres plus court."""
    return {"__type": "NumberCalculationPart", "mNumber": x}


STATS = {"ap": 300.0, "ad": 150.0, "ad_bonus": 50.0, "hp": 2000.0, "hp_bonus": 500.0}


def test_ahri_q_au_rang_5():
    # 135 (rang 5) + 0,5 x 300 d'AP.
    assert evaluate_formula("TotalDamage", AHRI_Q, AHRI_Q_VALEURS, 5, STATS) == 285


def test_le_rang_1_est_la_premiere_valeur():
    assert evaluate_formula("TotalDamage", AHRI_Q, AHRI_Q_VALEURS, 1, STATS) == 185


def test_ahri_w_un_ratio_par_rang():
    # 40 + 0,4 x 300.
    resultat = evaluate_formula("SingleFireDamage", AHRI_W, AHRI_W_VALEURS, 1, STATS)
    assert resultat == pytest.approx(160)


def test_ahri_w_une_formule_qui_en_reprend_une_autre():
    # MultiFireDamage = SingleFireDamage x RepeatDamageMod = 160 x 0,4.
    resultat = evaluate_formula("MultiFireDamage", AHRI_W, AHRI_W_VALEURS, 1, STATS)
    assert resultat == pytest.approx(64)


def test_un_ratio_d_ad_bonus():
    # Code de stat 2 (attaque), code de formule 2 (bonus) : 1,5 x 50.
    formules = {
        "Degats": {
            "__type": "GameCalculation",
            "mFormulaParts": [
                {
                    "__type": "StatByCoefficientCalculationPart",
                    "mCoefficient": 1.5,
                    "mStat": 2,
                    "mStatFormula": 2,
                }
            ],
        }
    }
    assert evaluate_formula("Degats", formules, {}, 1, STATS) == 75


def test_somme_produit_et_stat_d_un_sous_morceau():
    # 10 + (2 x 3) ; puis PV totaux x (0,01 + 0,01) : 2000 x 0,02 = 40.
    formules = {
        "Calcul": {
            "__type": "GameCalculation",
            "mFormulaParts": [
                {
                    "__type": "SumOfSubPartsCalculationPart",
                    "mSubparts": [
                        nombre(10.0),
                        {
                            "__type": "ProductOfSubPartsCalculationPart",
                            "mPart1": nombre(2.0),
                            "mPart2": nombre(3.0),
                        },
                    ],
                },
                {
                    "__type": "StatBySubPartCalculationPart",
                    "mStat": 12,
                    "mSubpart": {
                        "__type": "SumOfSubPartsCalculationPart",
                        "mSubparts": [
                            nombre(0.01),
                            nombre(0.01),
                        ],
                    },
                },
            ],
        }
    }
    assert evaluate_formula("Calcul", formules, {}, 1, STATS) == pytest.approx(56)


def test_le_multiplicateur_d_une_formule():
    formules = {
        "Calcul": {
            "__type": "GameCalculation",
            "mFormulaParts": [nombre(10.0)],
            "mMultiplier": nombre(0.5),
        }
    }
    assert evaluate_formula("Calcul", formules, {}, 1, STATS) == 5


def test_un_nombre_absent_vaut_zero():
    # 7 morceaux au 16.22, tous des formules d'affichage (tooltipOnly).
    formules = {
        "Affichage": {
            "__type": "GameCalculation",
            "mFormulaParts": [{"__type": "NumberCalculationPart"}],
        }
    }
    assert evaluate_formula("Affichage", formules, {}, 1, STATS) == 0


def test_un_code_de_stat_pas_encore_decode_fait_du_bruit():
    formules = {
        "Calcul": {
            "__type": "GameCalculation",
            "mFormulaParts": [
                {
                    "__type": "StatByCoefficientCalculationPart",
                    "mCoefficient": 1,
                    # 15 : un seul cas au 16.23 (W d'Ekko, nom de formule
                    # chiffre), sens inconnu. (Le 9, utilise ici jusqu'au
                    # 18/11, est decode : les degats critiques.)
                    "mStat": 15,
                }
            ],
        }
    }
    with pytest.raises(ValueError, match=r"\(15, 0\)"):
        evaluate_formula("Calcul", formules, {}, 1, STATS)


def test_un_morceau_pas_encore_gere_fait_du_bruit():
    formules = {
        "Calcul": {
            "__type": "GameCalculation",
            "mFormulaParts": [
                {
                    "__type": "EffectValueCalculationPart",
                    "mEffectIndex": 1,
                }
            ],
        }
    }
    # Une ancienne "valeur d'effet" (5 formules de degats au 16.23) : elle
    # renvoie a un tableau que nous ne chargeons pas. (Le compteur de cumuls,
    # utilise ici jusqu'au 18/11, est gere depuis : voir plus bas.)
    with pytest.raises(ValueError, match="EffectValueCalculationPart"):
        evaluate_formula("Calcul", formules, {}, 1, STATS)


def test_une_valeur_par_rang_absente_fait_du_bruit():
    with pytest.raises(ValueError, match="BaseDamage"):
        evaluate_formula("TotalDamage", AHRI_Q, {}, 1, STATS)


# --- Les morceaux qui dependent du niveau du champion ---
# Regles verifiees le 17/11/2026 : wiki (valeurs niveau par niveau) et vrais
# coups des recapitulatifs de mort (paliers d'Ekko).


def formule_seule(morceau):
    return {"Calcul": {"__type": "GameCalculation", "mFormulaParts": [morceau]}}


def au_niveau(formules, niveau):
    return evaluate_formula("Calcul", formules, {}, 1, STATS, niveau=niveau)


LEONA_P = formule_seule(
    {
        "__type": "ByCharLevelFormulaCalculationPart",
        "values": [25.0 + 7 * i for i in range(31)],
    }
)


def test_liste_par_niveau_la_valeur_du_niveau_est_a_sa_position():
    # Wiki : Leona, passif, 32 - 151 selon le niveau (la position 0 ne sert pas).
    assert au_niveau(LEONA_P, 1) == 32
    assert au_niveau(LEONA_P, 18) == 151


HWEI_P = formule_seule(
    {
        "__type": "ByCharLevelInterpolationCalculationPart",
        "mStartValue": 40.0,
        "mEndValue": 285.0,
    }
)


def test_interpolation_en_ligne_droite():
    # Wiki, niveau par niveau : 40 ; 54,41 ; ... ; 285 au niveau 18.
    assert au_niveau(HWEI_P, 2) == pytest.approx(54.41, abs=0.01)
    assert au_niveau(HWEI_P, 18) == 285


def test_interpolation_bloquee_au_niveau_18():
    assert au_niveau(HWEI_P, 20) == 285


def test_interpolation_au_dela_de_18_si_le_fichier_le_dit():
    formules = formule_seule(
        {**HWEI_P["Calcul"]["mFormulaParts"][0], "mScalePastDefaultMaxLevel": True}
    )
    assert au_niveau(formules, 19) == pytest.approx(299.41, abs=0.01)


def test_interpolation_sur_la_courbe_des_stats():
    # Wiki, bouclier du passif de Yasuo : 125 ; 145,12 ; ... ; 600.
    yasuo = formule_seule(
        {
            "__type": "ByCharLevelInterpolationCalculationPart",
            "mStartValue": 125.0,
            "mEndValue": 600.0,
            "mScaleByStatProgressionMultiplier": True,
        }
    )
    assert au_niveau(yasuo, 2) == pytest.approx(145.12, abs=0.01)
    assert au_niveau(yasuo, 18) == pytest.approx(600)


EKKO_P = formule_seule(
    {
        "__type": "ByCharLevelBreakpointsCalculationPart",
        "mLevel1Value": 30.0,
        "mInitialBonusPerLevel": 10.0,
        "mBreakpoints": [
            {"__type": "Breakpoint", "mLevel": 7, "mBonusPerLevelAtAndAfter": 5.0}
        ],
    }
)


def test_paliers_le_bonus_du_palier_remplace_celui_de_depart():
    # Wiki : Ekko, passif, 30 - 140 (+10 par niveau, puis +5 a partir du 7).
    assert au_niveau(EKKO_P, 6) == 80
    assert au_niveau(EKKO_P, 7) == 85
    assert au_niveau(EKKO_P, 18) == 140


def test_un_palier_vide_arrete_la_progression():
    # Camille Q : 40 % -> 100 % de degats bruts, +4 % par niveau ; le palier
    # du niveau 17 n'a pas de bonus : la progression s'arrete (100 % des 16).
    camille = formule_seule(
        {
            "__type": "ByCharLevelBreakpointsCalculationPart",
            "mLevel1Value": 0.4,
            "mInitialBonusPerLevel": 0.04,
            "mBreakpoints": [{"__type": "Breakpoint", "mLevel": 17}],
        }
    )
    assert au_niveau(camille, 16) == pytest.approx(1.0)
    assert au_niveau(camille, 18) == pytest.approx(1.0)


def test_un_palier_peut_ajouter_un_bonus_une_seule_fois():
    # Caitlyn, tir a la tete : 60 %, 70 % au niveau 7, 80 % au niveau 13.
    caitlyn = formule_seule(
        {
            "__type": "ByCharLevelBreakpointsCalculationPart",
            "mLevel1Value": 0.6,
            "mBreakpoints": [
                {
                    "__type": "Breakpoint",
                    "mLevel": niv,
                    "mAdditionalBonusAtThisLevel": 0.1,
                }
                for niv in (7, 13)
            ],
        }
    )
    assert au_niveau(caitlyn, 6) == pytest.approx(0.6)
    assert au_niveau(caitlyn, 7) == pytest.approx(0.7)
    assert au_niveau(caitlyn, 18) == pytest.approx(0.8)


def test_sans_niveau_un_morceau_par_niveau_fait_du_bruit():
    with pytest.raises(ValueError, match="niveau"):
        evaluate_formula("Calcul", LEONA_P, {}, 1, STATS)


# --- Codes decodes le 18/11/2026 (vitesse d'attaque bonus, critique, letalite) ---
# Les vraies formules du 16.23 (stg_kit__formulas, stg_kit__values).


def ratio(coefficient, stat, formule=0):
    """Un morceau "coefficient x stat", pour ecrire les arbres plus court."""
    return {
        "__type": "StatByCoefficientCalculationPart",
        "mCoefficient": coefficient,
        "mStat": stat,
        "mStatFormula": formule,
    }


# Q de Sivir : (base + 70 % AD bonus + 60 % AP) x (1 + CritRatio x chances de
# critique x (degats critiques - 1)). La forme exacte du critique "en moyenne".
SIVIR_Q = {
    "TotalDamage": {
        "__type": "GameCalculation",
        "mFormulaParts": [
            {"__type": "NamedDataValueCalculationPart", "mDataValue": "BaseDamage"},
            {
                "__type": "StatByNamedDataValueCalculationPart",
                "mDataValue": "ADRatio",
                "mStat": 2,
                "mStatFormula": 2,
            },
            {"__type": "StatByNamedDataValueCalculationPart", "mDataValue": "APRatio"},
        ],
        "mMultiplier": {
            "__type": "SumOfSubPartsCalculationPart",
            "mSubparts": [
                nombre(1.0),
                {
                    "__type": "ProductOfSubPartsCalculationPart",
                    "mPart1": {
                        "__type": "StatByNamedDataValueCalculationPart",
                        "mDataValue": "CritRatio",
                        "mStat": 8,
                    },
                    "mPart2": {
                        "__type": "SumOfSubPartsCalculationPart",
                        "mSubparts": [ratio(1.0, 9), nombre(-1.0)],
                    },
                },
            ],
        },
    }
}
SIVIR_Q_VALEURS = {
    "BaseDamage": [60.0, 85.0, 110.0, 135.0, 160.0, 185.0],
    "ADRatio": [0.7] * 6,
    "APRatio": [0.6] * 6,
    "CritRatio": [0.4] * 6,
}


def test_sivir_q_avec_des_chances_de_critique():
    # (160 + 0,7 x 50 + 0,6 x 300) x (1 + 0,4 x 0,5 x (2 - 1)) = 375 x 1,2.
    stats = {**STATS, "crit_chance": 0.5, "crit_damage": 2.0}
    assert evaluate_formula("TotalDamage", SIVIR_Q, SIVIR_Q_VALEURS, 5, stats) == (
        pytest.approx(450)
    )


def test_sivir_q_sans_critique_ne_gagne_rien():
    stats = {**STATS, "crit_chance": 0.0, "crit_damage": 2.0}
    assert evaluate_formula("TotalDamage", SIVIR_Q, SIVIR_Q_VALEURS, 5, stats) == (
        pytest.approx(375)
    )


def test_les_degats_critiques_comptent_aussi():
    # Lame d'infini : degats critiques 2,3 -> 375 x (1 + 0,4 x 0,5 x 1,3).
    stats = {**STATS, "crit_chance": 0.5, "crit_damage": 2.3}
    assert evaluate_formula("TotalDamage", SIVIR_Q, SIVIR_Q_VALEURS, 5, stats) == (
        pytest.approx(472.5)
    )


def test_pyke_r_un_ratio_de_letalite():
    # R de Pyke : 150 % de la letalite. 20 de letalite -> 30.
    formules = {
        "RLethalityDamage": {
            "__type": "GameCalculation",
            "mFormulaParts": [ratio(1.5, 29)],
        }
    }
    stats = {**STATS, "lethality": 20.0}
    assert evaluate_formula("RLethalityDamage", formules, {}, 1, stats) == 30


def test_varus_passif_la_vitesse_d_attaque_bonus_est_une_fraction():
    # Passif de Varus : 42 x vitesse d'attaque bonus. +50 % -> 0,5 -> 21 d'AD
    # (en pourcentage, 42 x 50 donnerait 2 100 d'AD : absurde).
    formules = {
        "ChampionAD": {
            "__type": "GameCalculation",
            "mFormulaParts": [
                {
                    "__type": "StatByNamedDataValueCalculationPart",
                    "mDataValue": "AStoADChampion",
                    "mStat": 4,
                    "mStatFormula": 2,
                }
            ],
        }
    }
    valeurs = {"AStoADChampion": [42.0] * 6}
    stats = {**STATS, "as_bonus": 0.5}
    assert evaluate_formula("ChampionAD", formules, valeurs, 1, stats) == 21


def test_la_vitesse_d_attaque_totale_reste_inconnue():
    # (4, 0) : probablement la vitesse d'attaque totale, mais ses seuls exemples
    # (Kalista, Bel'Veth : noms chiffres ; Kai'Sa : un temps d'incantation) ne
    # permettent pas d'en verifier l'unite. Mieux vaut une erreur qu'un faux
    # nombre.
    formules = {"Calcul": {"__type": "GameCalculation", "mFormulaParts": [ratio(1, 4)]}}
    with pytest.raises(ValueError, match=r"\(4, 0\)"):
        evaluate_formula("Calcul", formules, {}, 1, STATS)


# --- Les compteurs de cumuls (18/11/2026) ------------------------------------
# Le nombre de cumuls n'est pas dans les fichiers du jeu : c'est un reglage de
# scenario, donne par l'appelant, sous le nom (chiffre) du cumul.

# Q de Nasus (16.23) : bonus par rang + 100 % de l'AD + 1 x les cumuls.
NASUS_Q = {
    "TotalDamage": {
        "__type": "GameCalculation",
        "mFormulaParts": [
            {"__type": "NamedDataValueCalculationPart", "mDataValue": "BonusDamage"},
            ratio(1.0, 2),
            {
                "__type": "BuffCounterByCoefficientCalculationPart",
                "mBuffName": "{1b1d7345}",
                "mCoefficient": 1.0,
            },
        ],
    }
}
NASUS_Q_VALEURS = {"BonusDamage": [30.0, 50.0, 70.0, 90.0, 110.0, 130.0]}


def test_nasus_q_avec_200_cumuls():
    # 110 (rang 5) + 150 d'AD + 200 cumuls.
    valeur = evaluate_formula(
        "TotalDamage",
        NASUS_Q,
        NASUS_Q_VALEURS,
        5,
        STATS,
        cumuls={"{1b1d7345}": 200},
    )
    assert valeur == 460


def test_zero_cumul_donne_explicitement_ne_compte_rien():
    valeur = evaluate_formula(
        "TotalDamage", NASUS_Q, NASUS_Q_VALEURS, 5, STATS, cumuls={"{1b1d7345}": 0}
    )
    assert valeur == 260


def test_sans_cumuls_donnes_le_calcul_fait_du_bruit():
    # Jamais un 0 silencieux : un Nasus a 0 cumul et un Nasus a 600 ne sont
    # pas le meme champion. Le message nomme le cumul attendu.
    with pytest.raises(ValueError, match=r"\{1b1d7345\}"):
        evaluate_formula("TotalDamage", NASUS_Q, NASUS_Q_VALEURS, 5, STATS)


def test_un_autre_cumul_ne_remplace_pas_celui_attendu():
    with pytest.raises(ValueError, match=r"\{1b1d7345\}"):
        evaluate_formula(
            "TotalDamage",
            NASUS_Q,
            NASUS_Q_VALEURS,
            5,
            STATS,
            cumuls={"{8682fc00}": 6},
        )


def test_cho_gath_e_une_valeur_par_rang_par_cumul():
    # E de Cho'Gath (16.23) : (pourcentage du rang + 0,5 par cumul de Festin)
    # x 0,01. Rang 5, 6 cumuls : (3,9 + 3) x 0,01 = 0,069 (6,9 % des PV max).
    formules = {
        "MaxHealthPercentCalc": {
            "__type": "GameCalculation",
            "mDisplayAsPercent": True,
            "mFormulaParts": [
                {
                    "__type": "NamedDataValueCalculationPart",
                    "mDataValue": "PercentHealthDamage",
                },
                {
                    "__type": "BuffCounterByNamedDataValueCalculationPart",
                    "mBuffName": "{8682fc00}",
                    "mDataValue": "FeastStackMultiplier",
                },
            ],
            "mMultiplier": nombre(0.01),
        }
    }
    valeurs = {
        "PercentHealthDamage": [2.5, 2.85, 3.2, 3.55, 3.9, 4.25],
        "FeastStackMultiplier": [0.5] * 6,
    }
    valeur = evaluate_formula(
        "MaxHealthPercentCalc", formules, valeurs, 5, STATS, cumuls={"{8682fc00}": 6}
    )
    assert valeur == pytest.approx(0.069)


def test_thresh_e_le_coefficient_multiplie_les_cumuls():
    # Ajoute apres un sabotage (18/11) : "coefficient ignore" passait, car le
    # coefficient de Nasus vaut 1. E de Thresh (16.23) : 1,7 par ame + ratio
    # d'AD du rang. Rang 1, 30 ames, 150 d'AD : 51 + 0,9 x 150 = 186.
    formules = {
        "PAttackDamageMax": {
            "__type": "GameCalculation",
            "mFormulaParts": [
                {
                    "__type": "BuffCounterByCoefficientCalculationPart",
                    "mBuffName": "{5fbfbf13}",
                    "mCoefficient": 1.7,
                },
                {
                    "__type": "StatByNamedDataValueCalculationPart",
                    "mDataValue": "PassiveADRatioTT",
                    "mStat": 2,
                },
            ],
        }
    }
    valeurs = {"PassiveADRatioTT": [0.9, 1.2, 1.5, 1.8, 2.1, 2.4]}
    valeur = evaluate_formula(
        "PAttackDamageMax", formules, valeurs, 1, STATS, cumuls={"{5fbfbf13}": 30}
    )
    assert valeur == pytest.approx(186)


# --- La ressource (18/11/2026) : un % du mana, total ou bonus ----------------
# Meme regle que les autres stats : formule absente = total, 2 = bonus. Ryze
# (mana BONUS) et Kassadin (mana MAX) : ce que disent leurs infobulles en jeu.
STATS_MANA = {**STATS, "resource": 1500.0, "resource_bonus": 1000.0}


def ressource(coefficient, formule=None):
    morceau = {
        "__type": "AbilityResourceByCoefficientCalculationPart",
        "mCoefficient": coefficient,
    }
    if formule is not None:
        morceau["mStatFormula"] = formule
    return morceau


def test_ryze_q_un_pourcentage_du_mana_bonus():
    # Rang 5 : 155 + 0,55 x 300 d'AP + 0,02 x 1 000 de mana bonus = 340.
    formules = {
        "QDamageCalc": {
            "__type": "GameCalculation",
            "mFormulaParts": [
                {"__type": "NamedDataValueCalculationPart", "mDataValue": "BaseDamage"},
                {"__type": "StatByCoefficientCalculationPart", "mCoefficient": 0.55},
                ressource(0.02, formule=2),
            ],
        }
    }
    valeurs = {"BaseDamage": [75.0, 95.0, 115.0, 135.0, 155.0, 175.0]}
    assert evaluate_formula(
        "QDamageCalc", formules, valeurs, 5, STATS_MANA
    ) == pytest.approx(340)


def test_kassadin_r_un_pourcentage_du_mana_max():
    # Rang 2 : 95 + 0,5 x 300 d'AP + 0,02 x 1 500 de mana max = 275.
    formules = {
        "BaseDamage": {
            "__type": "GameCalculation",
            "mFormulaParts": [
                {
                    "__type": "NamedDataValueCalculationPart",
                    "mDataValue": "RBaseDamage",
                },
                {
                    "__type": "StatByNamedDataValueCalculationPart",
                    "mDataValue": "APRatio",
                },
                ressource(0.02),
            ],
        }
    }
    valeurs = {"RBaseDamage": [80.0, 95.0, 110.0], "APRatio": [0.5, 0.5, 0.5]}
    assert evaluate_formula(
        "BaseDamage", formules, valeurs, 2, STATS_MANA
    ) == pytest.approx(275)


def test_une_formule_de_ressource_inconnue_fait_du_bruit():
    formules = {
        "Calcul": {"__type": "GameCalculation", "mFormulaParts": [ressource(0.02, 1)]}
    }
    with pytest.raises(ValueError, match="ressource"):
        evaluate_formula("Calcul", formules, {}, 1, STATS_MANA)


# --- La casse des noms de valeurs (18/11/2026) --------------------------------
# Le jeu chiffre ses noms EN MINUSCULES (FNV-1a) : pour lui, BADRatio et
# bADRatio sont le meme nom. Au 16.23, 12 formules de degats citent une valeur
# avec une autre casse que celle du sort (Fiora Q : BADRatio / bADRatio ;
# Morgana W : BaseApRatio / BaseAPRatio).


def test_fiora_q_une_valeur_citee_avec_une_autre_casse():
    # Q de Fiora (16.23) : la formule cite BADRatio, le sort range bADRatio.
    # Rang 3 : 1,0 x 50 d'AD bonus = 50.
    formules = {
        "TotalDamage": {
            "__type": "GameCalculation",
            "mFormulaParts": [
                {
                    "__type": "StatByNamedDataValueCalculationPart",
                    "mDataValue": "BADRatio",
                    "mStat": 2,
                    "mStatFormula": 2,
                }
            ],
        }
    }
    valeurs = {"bADRatio": [0.9, 0.95, 1.0, 1.05, 1.1, 1.15]}
    assert evaluate_formula("TotalDamage", formules, valeurs, 3, STATS) == 50


def formule_qui_cite(nom):
    return {
        "Calcul": {
            "__type": "GameCalculation",
            "mFormulaParts": [
                {"__type": "NamedDataValueCalculationPart", "mDataValue": nom}
            ],
        }
    }


def test_le_nom_exact_passe_avant_les_autres_casses():
    valeurs = {"Damage": [10.0], "DAMAGE": [99.0]}
    assert (
        evaluate_formula("Calcul", formule_qui_cite("Damage"), valeurs, 1, STATS) == 10
    )


def test_deux_valeurs_qui_ne_different_que_par_la_casse_font_du_bruit():
    # 2 sorts du 16.23 ont deux valeurs de ce genre : on ne choisit pas au
    # hasard.
    valeurs = {"Damage": [10.0], "DAMAGE": [99.0]}
    with pytest.raises(ValueError, match="ambigu"):
        evaluate_formula("Calcul", formule_qui_cite("damage"), valeurs, 1, STATS)


# --- Le morceau chiffre {ee18a47b} (18/11/2026) -------------------------------
# Une valeur de depart et une d'arrivee, toutes deux par rang (StartDataValue,
# EndDataValue). Le wiki ecrit l'eclair d'Udyr Q (chez nous : 0,015 -> 0,03)
# "1.5 + (3-1.5)/17*(x-1) for 20" : une LIGNE DROITE du niveau 1 au niveau 18,
# prolongee jusqu'au niveau 20 (prolongement non mesure).


def progression(debut, fin):
    return {"__type": "{ee18a47b}", "StartDataValue": debut, "EndDataValue": fin}


UDYR_Q = {
    "EmpoweredLightningBonus": {
        "__type": "GameCalculation",
        "mDisplayAsPercent": True,
        "mFormulaParts": [
            progression("LightningDamageLevel1", "LightningDamageLevel18")
        ],
    }
}
UDYR_Q_VALEURS = {
    "LightningDamageLevel1": [0.015] * 6,
    "LightningDamageLevel18": [0.03] * 6,
}


@pytest.mark.parametrize(
    ("niveau", "attendu"),
    [
        (1, 0.015),
        (18, 0.03),
        (10, 0.015 + 0.015 * 9 / 17),
        (20, 0.015 + 0.015 * 19 / 17),
    ],
)
def test_udyr_q_l_eclair_en_ligne_droite_selon_le_niveau(niveau, attendu):
    valeur = evaluate_formula(
        "EmpoweredLightningBonus", UDYR_Q, UDYR_Q_VALEURS, 1, STATS, niveau=niveau
    )
    assert valeur == pytest.approx(attendu)


def test_la_progression_demande_le_niveau():
    with pytest.raises(ValueError, match="niveau"):
        evaluate_formula("EmpoweredLightningBonus", UDYR_Q, UDYR_Q_VALEURS, 1, STATS)


def test_milio_passif_la_brulure_au_niveau_10():
    # Passif de Milio (16.23) : 10 -> 50 selon le niveau, + 20 % de l'AP.
    # Niveau 10 : 10 + 40 x 9 / 17 + 0,2 x 300 = 91,18.
    formules = {
        "BurnDamage": {
            "__type": "GameCalculation",
            "mFormulaParts": [
                progression("BaseDamageStart", "BaseDamageEnd"),
                {"__type": "StatByCoefficientCalculationPart", "mCoefficient": 0.2},
            ],
        }
    }
    valeurs = {"BaseDamageStart": [10.0] * 6, "BaseDamageEnd": [50.0] * 6}
    valeur = evaluate_formula("BurnDamage", formules, valeurs, 1, STATS, niveau=10)
    assert valeur == pytest.approx(10 + 40 * 9 / 17 + 60)
