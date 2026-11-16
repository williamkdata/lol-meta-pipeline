"""Le combat contre le mannequin : le temps pour le tuer (simulateur, etape 2)."""

import math

from degats import basic_attack_dps


def basic_attack_time_to_kill(attacker: dict, target: dict) -> float:
    """Secondes pour tuer la cible avec les seules attaques de base (degats moyens).

    attacker : les stats que rend stats_with_items.
    target : le mannequin, {"hp": ses PV, "armor": son armure}.

    Les coups tombent un par un : le premier a la seconde 0, puis un toutes les
    1 / vitesse d'attaque secondes. Il faut assez de coups pour vider les PV
    (le dernier peut deborder) ; le temps est celui du DERNIER coup.
    Pas encore pris en compte : le temps d'armer le premier coup, la
    regeneration de la cible.
    """
    if target["hp"] <= 0:
        raise ValueError(f"la cible doit avoir des PV (recu {target['hp']})")
    # Degats d'un coup = degats par seconde / coups par seconde.
    coup = basic_attack_dps(attacker, target["armor"]) / attacker["attack_speed"]
    # round(..., 9) avant d'arrondir vers le haut : 15,000000000000002 est 15
    # coups, pas 16 (le piege des nombres a virgule).
    coups = math.ceil(round(target["hp"] / coup, 9))
    return (coups - 1) / attacker["attack_speed"]
