import pytest

from combat import basic_attack_time_to_kill

# 100 d'AD, 1 attaque par seconde, ni critique ni penetration.
SIMPLE = {
    "ad": 100.0,
    "attack_speed": 1.0,
    "crit_chance": 0.0,
    "crit_damage": 2.0,
    "armor_pen_pct": 0.0,
    "lethality": 0.0,
}


def test_le_premier_coup_part_tout_de_suite():
    # 1 000 PV, 100 par coup : 10 coups, aux secondes 0, 1, ..., 9.
    assert basic_attack_time_to_kill(SIMPLE, {"hp": 1000, "armor": 0}) == 9


def test_un_point_de_vie_de_plus_coute_un_coup_de_plus():
    assert basic_attack_time_to_kill(SIMPLE, {"hp": 1001, "armor": 0}) == 10


def test_un_seul_coup_suffit():
    assert basic_attack_time_to_kill(SIMPLE, {"hp": 50, "armor": 0}) == 0


def test_la_vitesse_d_attaque_raccourcit_l_attente():
    rapide = {**SIMPLE, "attack_speed": 2.0}
    assert basic_attack_time_to_kill(rapide, {"hp": 1000, "armor": 0}) == 4.5


def test_le_piege_des_nombres_a_virgule():
    # Contre 1 d'armure, un coup fait 100 x 100 / 101. Une cible de
    # exactement 15 coups donne PV / coup = 15,000000000000002 : un arrondi
    # naif vers le haut compterait 16 coups.
    coup = 100 * 100 / 101
    cible = {"hp": 15 * coup, "armor": 1}
    assert basic_attack_time_to_kill(SIMPLE, cible) == 14


def test_jinx_contre_zed():
    # Jinx 16.22 niveau 11 + Lame d'infini + Lord Dominik + Dague, contre Zed
    # niveau 11 sans objet (1 522,7 PV, 73,2 d'armure). Coup moyen :
    # 195,325 x 1,65 x 100 / (100 + 73,2425 x 0,65) = 218,3 ; 7 coups ;
    # 6 intervalles de 1 / 0,7423 s = 8,08 s.
    jinx = {
        "ad": 195.325,
        "attack_speed": 0.74234375,
        "crit_chance": 0.5,
        "crit_damage": 2.3,
        "armor_pen_pct": 0.35,
        "lethality": 0.0,
    }
    zed = {"hp": 1522.725, "armor": 73.2425}
    assert basic_attack_time_to_kill(jinx, zed) == pytest.approx(8.0825, abs=1e-4)


def test_une_cible_sans_pv_est_refusee():
    with pytest.raises(ValueError, match="PV"):
        basic_attack_time_to_kill(SIMPLE, {"hp": 0, "armor": 0})
