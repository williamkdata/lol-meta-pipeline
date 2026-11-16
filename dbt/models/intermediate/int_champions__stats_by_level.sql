-- Les stats de chaque champion a chaque niveau, de 1 au niveau maximum
-- (simulateur de combat, etape 1). Une ligne par patch, champion et niveau.
--
-- La croissance n'est pas une ligne droite : macro level_growth (la courbe de
-- LoL, verifiee sur les vraies stats des parties du ladder le 16/11/2026).
-- Niveau maximum : variable champion_max_level (20 : les joueurs du haut
-- montent jusqu'a 20 ; les autres s'arretent a 18).
--
-- Sans objets, sans runes, sans passifs : ce sont les stats "nues" du
-- champion, comme dans l'outil d'entrainement sans rien acheter.
-- Arrondi a 4 decimales : assez pour un combat (un dix-millieme de PV ne
-- change rien) et evite les 1394.9600000000003 des nombres a virgule.

SELECT
    b.patch_key,
    b.patch,
    b.champion_id,
    b.champion_code,
    level,

    ROUND(b.hp_base + b.hp_per_level * {{ level_growth('level') }}, 4) AS hp,
    -- Regenerations PAR SECONDE (Data Dragon : par 5 secondes).
    ROUND(b.hp_regen_base + b.hp_regen_per_level * {{ level_growth('level') }}, 4) AS hp_regen,
    ROUND(b.armor_base + b.armor_per_level * {{ level_growth('level') }}, 4) AS armor,
    ROUND(b.mr_base + b.mr_per_level * {{ level_growth('level') }}, 4) AS mr,
    ROUND(b.ad_base + b.ad_per_level * {{ level_growth('level') }}, 4) AS ad,

    -- Le bonus de vitesse d'attaque gagne par les niveaux, en % (l'API de Riot
    -- affiche 100 + ce bonus dans les stats de chaque minute).
    ROUND(b.as_per_level * {{ level_growth('level') }}, 4) AS as_bonus_pct,
    -- Recopies pour le simulateur : les bonus des objets s'ajoutent a celui
    -- des niveaux, puis le tout est multiplie par le ratio.
    b.as_base,
    b.as_ratio,
    -- La vitesse d'attaque totale : le bonus est multiplie par le RATIO, pas
    -- par la vitesse d'attaque de base (Ahri : 0,625, pas 0,668 ; Jhin : 0,
    -- sa vitesse d'attaque ne monte jamais).
    ROUND(
        b.as_base
        + b.as_ratio * b.as_per_level / 100 * {{ level_growth('level') }},
        4
    ) AS attack_speed,

    b.attack_range,
    b.move_speed,
    b.crit_damage,

    ROUND(b.resource_base + b.resource_per_level * {{ level_growth('level') }}, 4) AS resource,
    ROUND(
        b.resource_regen_base
        + b.resource_regen_per_level * {{ level_growth('level') }},
        4
    ) AS resource_regen,
    b.resource_type

FROM {{ ref('int_champions__base_stats') }} AS b

-- Chaque champion, repete une fois par niveau : GENERATE_ARRAY(1, 20) fabrique
-- la liste 1, 2, ..., 20 ; UNNEST en fait des lignes.
CROSS JOIN UNNEST(GENERATE_ARRAY(1, {{ var('champion_max_level') }})) AS level
