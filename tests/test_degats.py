import pytest

from degats import basic_attack_dps, damage_multiplier, effective_resistance


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
