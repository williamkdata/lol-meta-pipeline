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
                    "mStat": 9,
                }
            ],
        }
    }
    with pytest.raises(ValueError, match=r"\(9, 0\)"):
        evaluate_formula("Calcul", formules, {}, 1, STATS)


def test_un_morceau_pas_encore_gere_fait_du_bruit():
    formules = {
        "Calcul": {
            "__type": "GameCalculation",
            "mFormulaParts": [
                {
                    "__type": "BuffCounterByCoefficientCalculationPart",
                    "mCoefficient": 15.0,
                }
            ],
        }
    }
    # Un compteur de cumuls : il faudrait savoir combien de cumuls on a.
    with pytest.raises(ValueError, match="BuffCounterByCoefficientCalculationPart"):
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
