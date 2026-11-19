"""Les stats d'un champion avec ses objets, a un niveau donne (simulateur, etape 2)."""

# Les stats des objets (noms des fichiers du jeu, 16.22) qui s'ADDITIONNENT.
STATS_OBJETS = {
    "FlatHPPoolMod": "hp_bonus",
    "FlatPhysicalDamageMod": "ad_bonus",
    "FlatMagicDamageMod": "ap",
    "FlatArmorMod": "armor_bonus",
    "FlatSpellBlockMod": "mr_bonus",
    "PercentAttackSpeedMod": "as_bonus_items",  # fraction : 0.1 = +10 %
    "FlatCritChanceMod": "crit_chance",  # fraction : 0.25 = 25 %
    "FlatCritDamageMod": "crit_damage_bonus",  # Lame d'infini : +0.3
    "AbilityHasteMod": "ability_haste",
    "PhysicalLethality": "lethality",
    "FlatMagicPenetrationMod": "magic_pen_flat",
    "FlatMPPoolMod": "mana_bonus",
}

# Les % de penetration se MULTIPLIENT : 35 % puis 18 % laissent 0,65 x 0,82 de
# l'armure, soit 46,7 % de penetration (et non 53 %). Entre objets, le cas est
# rare : le jeu limite les objets par groupe (Lord Dominik, Dernier souffle et
# Rappel mortel : groupe "LastWhisper", 1 au plus). La regle sert surtout quand
# un objet s'ajoute a un sort de champion (etape des effets). Verifier qu'un
# build respecte les groupes n'est PAS le travail de cette fonction.
PENETRATIONS_POURCENT = {
    "PercentArmorPenetrationMod": "armor_pen_pct",
    "PercentMagicPenetrationMod": "magic_pen_pct",
}

# Stats sans effet sur le mannequin (il ne bouge pas, personne ne se soigne) :
# ignorees EXPRES. Une stat absente des trois listes leve une erreur : un objet
# nouveau ne doit pas perdre une stat en silence.
STATS_IGNOREES = frozenset(
    {
        "FlatMovementSpeedMod",
        "PercentMovementSpeedMod",
        "FlatHPRegenMod",
        "PercentBaseHPRegenMod",
        "FlatMPRegenMod",
        "PercentBaseMPRegenMod",
        "PercentHealingAmountMod",
        "PercentLifeStealMod",
        "PercentOmnivampMod",
        "PercentTenacityItemMod",
        "PercentSlowResistMod",
    }
)

# Bornes de la vitesse d'attaque (wiki de la communaute, lu le 16/11/2026).
VITESSE_ATTAQUE_MAX = 3.003
VITESSE_ATTAQUE_MIN = 0.2


def stats_with_items(champion: dict, items: list[dict[str, float]]) -> dict:
    """Les stats du champion avec ses objets.

    champion : une ligne de int_champions__stats_by_level (un niveau donne).
    items : une liste d'objets, chacun un dictionnaire {nom de stat: valeur}.
    Garde la part "bonus" a part (ad_bonus...) : les ratios des sorts en ont besoin.
    """
    sommes = dict.fromkeys(STATS_OBJETS.values(), 0.0)
    restes = dict.fromkeys(PENETRATIONS_POURCENT.values(), 1.0)
    for objet in items:
        for stat, valeur in objet.items():
            if stat in STATS_OBJETS:
                sommes[STATS_OBJETS[stat]] += valeur
            elif stat in PENETRATIONS_POURCENT:
                restes[PENETRATIONS_POURCENT[stat]] *= 1 - valeur
            elif stat not in STATS_IGNOREES:
                raise ValueError(f"stat d'objet inconnue : {stat}")

    # Le bonus des niveaux (en %) et celui des objets (en fraction) s'ajoutent,
    # puis le tout est multiplie par le ratio, pas par la base.
    as_bonus = champion["as_bonus_pct"] / 100 + sommes["as_bonus_items"]
    vitesse = champion["as_base"] + champion["as_ratio"] * as_bonus
    mana = sommes["mana_bonus"] if champion["resource_type"] == "mana" else 0.0

    return {
        "champion_code": champion["champion_code"],
        "level": champion["level"],
        "hp": champion["hp"] + sommes["hp_bonus"],
        "hp_bonus": sommes["hp_bonus"],
        "armor": champion["armor"] + sommes["armor_bonus"],
        "armor_bonus": sommes["armor_bonus"],
        "mr": champion["mr"] + sommes["mr_bonus"],
        "mr_bonus": sommes["mr_bonus"],
        "ad": champion["ad"] + sommes["ad_bonus"],
        "ad_bonus": sommes["ad_bonus"],
        "ap": sommes["ap"],
        "as_bonus": as_bonus,
        "attack_speed": min(max(vitesse, VITESSE_ATTAQUE_MIN), VITESSE_ATTAQUE_MAX),
        "crit_chance": min(sommes["crit_chance"], 1.0),
        "crit_damage": champion["crit_damage"] + sommes["crit_damage_bonus"],
        "ability_haste": sommes["ability_haste"],
        "lethality": sommes["lethality"],
        "armor_pen_pct": 1 - restes["armor_pen_pct"],
        "magic_pen_flat": sommes["magic_pen_flat"],
        "magic_pen_pct": 1 - restes["magic_pen_pct"],
        "resource": champion["resource"] + mana,
        # Le mana des objets seul (Ryze : ses degats montent avec le mana BONUS).
        "resource_bonus": mana,
    }
