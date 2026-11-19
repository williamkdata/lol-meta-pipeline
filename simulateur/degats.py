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


# Ce que multiplie la valeur d'une formule de degats, d'apres les mots de son
# infobulle (int_kit__damage_formulas.scales_with, 18/11/2026). 'other' (un %
# d'AD bonus, Udyr Q2 mal lu...) n'en fait pas partie : il leve une erreur.
CIBLES_DES_POURCENTAGES = (
    "flat",
    "target_max_hp",
    "target_missing_hp",
    "target_current_hp",
)


def spell_hit_damage(
    valeur: float,
    damage_type: str,
    scales_with: str,
    attacker: dict,
    target: dict,
    target_current_hp: float | None = None,
) -> float:
    """Ce que la cible encaisse d'UN coup de sort, apres ses resistances.

    valeur : ce que rend evaluate_formula. Un nombre de degats ('flat'), ou une
    FRACTION si la formule est en pourcentage (0.09 = 9 %).
    damage_type : 'physical', 'magic' ou 'true' (la balise de l'infobulle).
    scales_with : ce que multiplie la fraction (voir CIBLES_DES_POURCENTAGES).
    attacker : les stats que rend stats_with_items (penetrations, letalite).
    target : 'hp' (PV max), 'armor', 'mr' (totaux).
    target_current_hp : PV actuels de la cible ; par defaut, pleine vie.

    Les degats bruts ('true') ignorent armure et RM. Pas encore geres : les
    plafonds contre les monstres, les reductions de degats, les boucliers.
    """
    pv_max = target["hp"]
    pv_actuels = pv_max if target_current_hp is None else target_current_hp
    if not 0 <= pv_actuels <= pv_max:
        raise ValueError(f"PV actuels hors de [0, {pv_max}] : {pv_actuels}")

    if scales_with == "flat":
        brut = valeur
    elif scales_with == "target_max_hp":
        brut = valeur * pv_max
    elif scales_with == "target_missing_hp":
        brut = valeur * (pv_max - pv_actuels)
    elif scales_with == "target_current_hp":
        brut = valeur * pv_actuels
    else:
        raise ValueError(f"pourcentage de quoi ? '{scales_with}' : pas gere")

    if damage_type == "true":
        return brut
    if damage_type == "physical":
        resistance = effective_resistance(
            target["armor"], attacker["armor_pen_pct"], attacker["lethality"]
        )
    elif damage_type == "magic":
        resistance = effective_resistance(
            target["mr"], attacker["magic_pen_pct"], attacker["magic_pen_flat"]
        )
    else:
        raise ValueError(f"type de degats inconnu : '{damage_type}'")
    return brut * damage_multiplier(resistance)
