import pytest

from champion import stats_with_items

# Stats "nues" au niveau 11, patch 16.22 (int_champions__stats_by_level).
JINX_11 = {
    "champion_code": "Jinx",
    "level": 11,
    "hp": 1531.375,
    "armor": 62.855,
    "mr": 42.6525,
    "ad": 85.325,
    "as_bonus_pct": 8.775,
    "as_base": 0.625,
    "as_ratio": 0.625,
    "attack_speed": 0.6798,
    "crit_damage": 2.0,
    "resource": 698.75,
    "resource_type": "mana",
}
ZED_11 = {
    **JINX_11,
    "champion_code": "Zed",
    "ad": 92.835,
    "as_bonus_pct": 28.9575,
    "as_base": 0.651,
    "as_ratio": 0.651,
    "resource": 200.0,
    "resource_type": "energie",
}
JHIN_11 = {**JINX_11, "champion_code": "Jhin", "as_bonus_pct": 0.0, "as_ratio": 0.0}

# Stats des objets au 16.22 (stg_item_stats).
LAME_D_INFINI = {
    "FlatPhysicalDamageMod": 75.0,
    "FlatCritChanceMod": 0.25,
    "FlatCritDamageMod": 0.3,
}
LORD_DOMINIK = {
    "FlatPhysicalDamageMod": 35.0,
    "FlatCritChanceMod": 0.25,
    "PercentArmorPenetrationMod": 0.35,
}
DAGUE = {"PercentAttackSpeedMod": 0.1}
MANAMUNE = {
    "FlatPhysicalDamageMod": 35.0,
    "FlatMPPoolMod": 500.0,
    "AbilityHasteMod": 15.0,
}


def test_sans_objet_les_stats_du_niveau():
    s = stats_with_items(JINX_11, [])
    assert s["ad"] == 85.325
    assert s["ad_bonus"] == 0
    # Le meme calcul que dbt : 0,625 + 0,625 x 8,775 % = 0,6798.
    assert s["attack_speed"] == pytest.approx(0.6798, abs=1e-4)


def test_jinx_avec_trois_objets():
    s = stats_with_items(JINX_11, [LAME_D_INFINI, LORD_DOMINIK, DAGUE])
    assert s["ad"] == pytest.approx(195.325)
    assert s["ad_bonus"] == pytest.approx(110)
    assert s["crit_chance"] == pytest.approx(0.5)
    assert s["crit_damage"] == pytest.approx(2.3)
    assert s["armor_pen_pct"] == pytest.approx(0.35)
    # Bonus : 8,775 % (niveaux) + 10 % (Dague) ; x le ratio 0,625.
    assert s["attack_speed"] == pytest.approx(0.625 + 0.625 * 0.18775)


def test_deux_sources_de_pourcentage_se_multiplient():
    # Regle de calcul seulement : en partie, Lord Dominik et Dernier souffle
    # ne se cumulent PAS (meme groupe d'objets, "LastWhisper", 1 au plus ;
    # Lord Dominik se construit a partir de Dernier souffle : remarque de
    # William, 16/11). La regle servira quand un objet se combinera a un
    # sort de champion (Darius, Nilah, Pantheon...). Sources fictives ici.
    source_a = {"PercentArmorPenetrationMod": 0.35}
    source_b = {"PercentArmorPenetrationMod": 0.18}
    s = stats_with_items(JINX_11, [source_a, source_b])
    # 1 - 0,65 x 0,82 = 0,467 ; une addition donnerait 0,53.
    assert s["armor_pen_pct"] == pytest.approx(0.467)


def test_le_mana_ne_sert_qu_aux_champions_a_mana():
    s = stats_with_items(ZED_11, [MANAMUNE])
    assert s["resource"] == 200.0
    assert s["ad"] == pytest.approx(92.835 + 35)
    assert s["ability_haste"] == 15


def test_jhin_ne_gagne_pas_de_vitesse_d_attaque():
    # Ratio 0 : la Dague ne change rien a sa vitesse d'attaque.
    assert stats_with_items(JHIN_11, [DAGUE])["attack_speed"] == 0.625


def test_les_chances_de_critique_plafonnent_a_100_pourcent():
    s = stats_with_items(JINX_11, [LAME_D_INFINI] * 5)
    assert s["crit_chance"] == 1.0


def test_la_vitesse_d_attaque_plafonne():
    s = stats_with_items(JINX_11, [{"PercentAttackSpeedMod": 10.0}])
    assert s["attack_speed"] == 3.003


def test_une_stat_ignoree_expres_ne_change_rien():
    bottes = {"FlatMovementSpeedMod": 45.0, "PercentMovementSpeedMod": 0.04}
    assert stats_with_items(JINX_11, [bottes]) == stats_with_items(JINX_11, [])


def test_une_stat_inconnue_fait_du_bruit():
    with pytest.raises(ValueError, match="FlatNouvelleStatMod"):
        stats_with_items(JINX_11, [{"FlatNouvelleStatMod": 10.0}])
