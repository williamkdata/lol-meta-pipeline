import pytest

from degats import (
    basic_attack_dps,
    damage_multiplier,
    effective_resistance,
    spell_hit_damage,
)


def test_sans_armure_tout_passe():
    assert damage_multiplier(0) == 1.0


def test_100_d_armure_laisse_passer_la_moitie():
    assert damage_multiplier(100) == 0.5


def test_armure_d_ahri_au_niveau_1():
    # 21 d'armure (Ahri, 16.22) : 100 / 121 des degats passent.
    assert damage_multiplier(21) == pytest.approx(0.8264, abs=1e-4)


def test_beaucoup_d_armure():
    assert damage_multiplier(300) == 0.25


def test_resistance_negative_refusee():
    # Une resistance negative vient d'une REDUCTION d'armure (un effet) :
    # pas encore geree. Elle doit faire du bruit, pas donner un chiffre faux.
    with pytest.raises(ValueError, match="negative"):
        damage_multiplier(-10)


# --- effective_resistance : l'armure (ou la RM) qui reste apres penetration ---


def test_sans_penetration_rien_ne_change():
    assert effective_resistance(100) == 100


def test_pourcentage_seul():
    # Salutations de Lord Dominik : 35 % de penetration d'armure.
    assert effective_resistance(100, percent_pen=0.35) == pytest.approx(65)


def test_letalite_seule():
    # Lame fantome de Youmuu : 18 de letalite, contre 30 d'armure.
    assert effective_resistance(30, flat_pen=18) == 12


def test_la_letalite_ne_descend_pas_sous_zero():
    assert effective_resistance(10, flat_pen=18) == 0


def test_le_pourcentage_passe_avant_la_letalite():
    # 100 x 0,65 - 18 = 47. Dans l'autre ordre : (100 - 18) x 0,65 = 53,3.
    assert effective_resistance(100, percent_pen=0.35, flat_pen=18) == pytest.approx(47)


def test_zero_armure_reste_zero():
    assert effective_resistance(0, percent_pen=0.35, flat_pen=18) == 0


def test_pourcentage_ecrit_comme_l_api_refuse():
    # L'API de Riot ecrit 35 ; les fichiers d'objets ecrivent 0.35. Un 35
    # passe par erreur donnerait 0 d'armure, sans aucune erreur visible.
    with pytest.raises(ValueError, match="entre 0 et 1"):
        effective_resistance(100, percent_pen=35)


def test_letalite_negative_refusee():
    with pytest.raises(ValueError, match="negative"):
        effective_resistance(100, flat_pen=-5)


def test_resistance_negative_refusee_aussi_ici():
    with pytest.raises(ValueError, match="negative"):
        effective_resistance(-10, flat_pen=5)


# --- basic_attack_dps : degats moyens par seconde des attaques de base ---

# Un attaquant simple : 100 d'AD, 1 attaque par seconde, ni critique ni
# penetration. Les cles sont celles que rend stats_with_items.
SIMPLE = {
    "ad": 100.0,
    "attack_speed": 1.0,
    "crit_chance": 0.0,
    "crit_damage": 2.0,
    "armor_pen_pct": 0.0,
    "lethality": 0.0,
}


def test_dps_contre_un_mannequin_sans_armure():
    assert basic_attack_dps(SIMPLE, target_armor=0) == 100


def test_dps_contre_100_d_armure():
    assert basic_attack_dps(SIMPLE, target_armor=100) == 50


def test_dps_moyen_avec_50_pourcent_de_critique():
    # En moyenne, 1 coup sur 2 fait 200 % : 1 + 0,5 x (2 - 1) = 1,5.
    attaquant = {**SIMPLE, "crit_chance": 0.5}
    assert basic_attack_dps(attaquant, target_armor=0) == 150


def test_les_critiques_d_ashe_ne_font_pas_plus_de_degats():
    # Le fichier du jeu donne 1,0 de degats critiques a Ashe (16.22).
    ashe = {**SIMPLE, "crit_chance": 1.0, "crit_damage": 1.0}
    assert basic_attack_dps(ashe, target_armor=0) == 100


def test_la_penetration_compte():
    # 35 % puis 18 de letalite : 100 d'armure en deviennent 47.
    attaquant = {**SIMPLE, "armor_pen_pct": 0.35, "lethality": 18.0}
    assert basic_attack_dps(attaquant, target_armor=100) == pytest.approx(
        100 * 100 / 147
    )


def test_jinx_niveau_11_avec_trois_objets():
    # Jinx 16.22 niveau 11 + Lame d'infini + Lord Dominik + Dague (les stats
    # de test_champion.py), contre 100 d'armure :
    # 195,325 AD x (1 + 0,5 x 1,3) x 0,7423 att/s x 100 / (100 + 65).
    jinx = {
        "ad": 195.325,
        "attack_speed": 0.74234375,
        "crit_chance": 0.5,
        "crit_damage": 2.3,
        "armor_pen_pct": 0.35,
        "lethality": 0.0,
    }
    assert basic_attack_dps(jinx, target_armor=100) == pytest.approx(144.998, abs=1e-3)


# --- spell_hit_damage : ce que la cible encaisse d'UN coup de sort (18/11) ---
# Un attaquant sans penetration, et une cible "mannequin" : 2 000 PV, 100
# d'armure, 50 de RM.
SANS_PENETRATION = {
    "armor_pen_pct": 0.0,
    "lethality": 0.0,
    "magic_pen_pct": 0.0,
    "magic_pen_flat": 0.0,
}
MANNEQUIN = {"hp": 2000.0, "armor": 100.0, "mr": 50.0}


def test_des_degats_magiques_fixes_passent_la_rm():
    # 300 magiques contre 50 de RM : 300 x 100 / 150.
    assert spell_hit_damage(
        300, "magic", "flat", SANS_PENETRATION, MANNEQUIN
    ) == pytest.approx(200)


def test_des_degats_physiques_passent_l_armure_apres_la_letalite():
    # 200 physiques, 100 d'armure moins 20 de letalite : 200 x 100 / 180.
    attaquant = {**SANS_PENETRATION, "lethality": 20.0}
    assert spell_hit_damage(
        200, "physical", "flat", attaquant, MANNEQUIN
    ) == pytest.approx(111.111, abs=1e-3)


def test_des_degats_bruts_ignorent_les_resistances():
    cible = {**MANNEQUIN, "armor": 300.0, "mr": 300.0}
    assert spell_hit_damage(100, "true", "flat", SANS_PENETRATION, cible) == 100


def test_la_penetration_magique_compte():
    # RM 50 x (1 - 0,4) = 30, moins 15 fixes = 15 : 300 x 100 / 115.
    attaquant = {**SANS_PENETRATION, "magic_pen_pct": 0.4, "magic_pen_flat": 15.0}
    assert spell_hit_damage(
        300, "magic", "flat", attaquant, MANNEQUIN
    ) == pytest.approx(260.870, abs=1e-3)


def test_un_pourcentage_des_pv_max_de_la_cible():
    # Passif de Brand : 9 % des PV max, magiques. 0,09 x 2 000 = 180, puis la
    # RM : 180 x 100 / 150 = 120.
    assert spell_hit_damage(
        0.09, "magic", "target_max_hp", SANS_PENETRATION, MANNEQUIN
    ) == pytest.approx(120)


def test_un_pourcentage_des_pv_manquants():
    # E de Kayle : 10 % des PV manquants. Cible a 1 200 PV sur 2 000 : 80,
    # magiques, contre 0 de RM.
    cible = {**MANNEQUIN, "mr": 0.0}
    assert spell_hit_damage(
        0.1,
        "magic",
        "target_missing_hp",
        SANS_PENETRATION,
        cible,
        target_current_hp=1200,
    ) == pytest.approx(80)


def test_a_pleine_vie_les_pv_manquants_ne_font_rien():
    # Sans PV actuels donnes, la cible est a pleine vie.
    assert (
        spell_hit_damage(0.1, "magic", "target_missing_hp", SANS_PENETRATION, MANNEQUIN)
        == 0
    )


def test_un_pourcentage_des_pv_actuels():
    # Q de Viego : 8 % des PV actuels, physiques. 0,08 x 1 500 = 120, contre 0
    # d'armure.
    cible = {**MANNEQUIN, "armor": 0.0}
    assert spell_hit_damage(
        0.08,
        "physical",
        "target_current_hp",
        SANS_PENETRATION,
        cible,
        target_current_hp=1500,
    ) == pytest.approx(120)


def test_un_pourcentage_d_autre_chose_fait_du_bruit():
    # 'other' : un % d'AD bonus (Jhin), Udyr Q2 mal lu... On ne sait pas ce
    # qu'il multiplie : une erreur plutot qu'un faux nombre.
    with pytest.raises(ValueError, match="other"):
        spell_hit_damage(0.3, "physical", "other", SANS_PENETRATION, MANNEQUIN)


def test_un_type_de_degats_inconnu_fait_du_bruit():
    with pytest.raises(ValueError, match="poison"):
        spell_hit_damage(100, "poison", "flat", SANS_PENETRATION, MANNEQUIN)


def test_des_pv_actuels_au_dessus_du_max_sont_refuses():
    with pytest.raises(ValueError, match="PV actuels"):
        spell_hit_damage(
            0.1,
            "magic",
            "target_current_hp",
            SANS_PENETRATION,
            MANNEQUIN,
            target_current_hp=2500,
        )
