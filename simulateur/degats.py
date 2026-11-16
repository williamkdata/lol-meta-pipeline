"""Les degats du simulateur de combat : ce qui passe l'armure et la resistance magique.

Formules verifiees sur les vraies parties quand c'est possible (recapitulatifs de
mort des timelines brutes) ; sinon, la source est dite dans la fonction.
"""


def damage_multiplier(resistance: float) -> float:
    """La part des degats qui passe, selon l'armure (ou la RM) de la cible.

    0 d'armure : tout passe (1,0) ; 100 : la moitie (0,5) ; 300 : un quart.
    Verifie le 16/11/2026 sur 31 160 attaques de base de vraies parties : la
    formule 100 / (100 + armure) est la meilleure dans toutes les tranches
    d'armure, loin devant les autres essayees.

    Une resistance negative (apres une reduction d'armure, un effet) n'est pas
    encore geree : elle leve une erreur au lieu de donner un chiffre faux.
    """
    if resistance < 0:
        raise ValueError(f"resistance negative ({resistance}) : pas encore geree")
    return 100 / (100 + resistance)


def effective_resistance(
    resistance: float, percent_pen: float = 0.0, flat_pen: float = 0.0
) -> float:
    """L'armure (ou la RM) que les degats "voient" apres la penetration.

    percent_pen : la penetration en pourcentage, en FRACTION (0.35 = 35 %,
    Salutations de Lord Dominik), comme dans les fichiers d'objets. L'API de
    Riot l'ecrit 35 : un 35 passe ici leve une erreur.
    flat_pen : la letalite (armure) ou la penetration magique fixe.

    Ordre : le pourcentage d'abord, puis le fixe. La letalite compte en entier
    a tous les niveaux depuis le patch 14.1 et ne descend pas sous 0. Source :
    wiki de la communaute (16/11/2026) ; PAS mesure : les recapitulatifs de
    mort ne montrent pas la letalite, et les coups de fin de partie melangent
    trop d'effets.
    Plusieurs sources de pourcentage se multiplient : (1 - p1) x (1 - p2).
    C'est a l'appelant de les combiner avant.
    """
    if resistance < 0:
        raise ValueError(f"resistance negative ({resistance}) : pas encore geree")
    if not 0 <= percent_pen <= 1:
        raise ValueError(f"percent_pen doit etre entre 0 et 1 (recu {percent_pen})")
    if flat_pen < 0:
        raise ValueError(f"penetration fixe negative ({flat_pen})")
    apres_pourcentage = resistance * (1 - percent_pen)
    return max(apres_pourcentage - flat_pen, 0.0)


def basic_attack_dps(attacker: dict, target_armor: float) -> float:
    """Degats MOYENS par seconde des attaques de base contre une cible, sans effets.

    attacker : les stats que rend stats_with_items (ad, attack_speed,
    crit_chance, crit_damage, armor_pen_pct, lethality).
    target_armor : l'armure totale de la cible (le mannequin).

    Le critique compte en moyenne : avec 50 % de chances et 200 % de degats,
    un coup vaut 1 + 0,5 x (2 - 1) = 1,5 coup normal. Critique a 200 %
    mesure le 16/11/2026 sur les recapitulatifs de mort (pic a 2,0 ; avec la
    Lame d'infini, vers 2,3) ; le fichier du jeu donne 2,0 a 172 champions et
    1,0 a Ashe.
    """
    armure = effective_resistance(
        target_armor, attacker["armor_pen_pct"], attacker["lethality"]
    )
    critique = 1 + attacker["crit_chance"] * (attacker["crit_damage"] - 1)
    return (
        attacker["ad"] * critique * attacker["attack_speed"] * damage_multiplier(armure)
    )
