-- Moteur theorique, VERSION B (chantier decide par William le 09/11/2026) : la
-- valeur de chaque objet termine pour chaque champion, en OR UTILE.
--
-- La version A (mart_item_theory_value) ne comptait que les stats sur
-- lesquelles le kit du champion a un ratio (AP, AD, parfois PV ou armure) :
-- Ambessa avait un top 5 d'objets de tireur, Malphite un top 5 100 % AP.
-- La version B compte toutes les stats qui ont un prix en boutique :
--   valeur utile = somme sur les stats de l'objet de
--                  quantite x prix d'un point (int_items__stat_gold_price)
--                           x utilite de la stat pour ce champion (0 a 1)
--   rentabilite utile = valeur utile / prix de l'objet
-- 1,00 = l'objet donne, en stats utiles, exactement ce qu'il coute en
-- composants de base. C'est la « rentabilite en or » des joueurs, filtree par
-- ce qui sert au champion. Une seule unite : l'or.
--
-- L'utilite d'une stat pour un champion = la plus haute de trois valeurs :
--   - sa classe principale (etiquettes de Riot : Fighter, Tank...), seed
--     stat_usefulness_by_class ;
--   - la MOITIE de sa classe secondaire (Ezreal « Marksman, Mage » : un peu
--     de mage, pas autant qu'un mage) ;
--   - la part du ratio : le ratio du kit sur cette stat / son plus gros ratio
--     (Jinx : AD 3,82 -> 1 ; AP 1,0 -> 0,26), multipliee par l'usage que la
--     classe fait de ses ratios (ligne KitRatios du seed : 1 pour les classes
--     de degats, 0,5 pour Tank et Support ; Leona a des ratios d'AP mais ne
--     build pas AP).
--
-- Limites : les passifs des objets restent ignores ; les stats sans objet de
-- base (vol de vie, penetrations, % de vitesse...) ne sont pas valorisees.
-- En dev seulement tant que William n'a pas relu le seed (comme le seed).

{{ config(enabled=target.name != 'prod') }}

WITH classes AS (
    -- Les deux premieres etiquettes de Riot ; rang 0 = classe principale.
    SELECT
        c.patch_key,
        c.champion_id,
        tag AS champion_class,
        rang
    FROM {{ ref('stg_ddragon__champions') }} AS c,
        UNNEST(c.tags) AS tag WITH OFFSET AS rang
    WHERE rang <= 1
),

par_classe AS (
    -- L'utilite donnee par la classe : pleine pour la principale, moitie pour
    -- la secondaire.
    SELECT
        cl.patch_key,
        cl.champion_id,
        u.stat,
        IF(cl.rang = 0, u.usefulness, 0.5 * u.usefulness) AS usefulness
    FROM classes AS cl
    INNER JOIN {{ ref('stat_usefulness_by_class') }} AS u
        ON u.champion_class = cl.champion_class
),

usage_des_ratios AS (
    -- A quel point le champion exploite les ratios de son kit (ligne
    -- KitRatios), selon ses classes.
    SELECT patch_key, champion_id, MAX(usefulness) AS ratio_usage
    FROM par_classe
    WHERE stat = 'KitRatios'
    GROUP BY patch_key, champion_id
),

ratios AS (
    SELECT patch_key, champion_id, item_stat AS stat, SUM(total_coefficient) AS coefficient
    FROM {{ ref('mart_champion_stat_profile') }}
    GROUP BY patch_key, champion_id, item_stat
),

utilites AS (
    -- 1. Par la classe (KitRatios n'est pas une stat d'objet : ecarte).
    SELECT patch_key, champion_id, stat, usefulness
    FROM par_classe
    WHERE stat != 'KitRatios'

    UNION ALL

    -- 2. Par les ratios du kit : part du plus gros ratio, x usage des ratios.
    SELECT
        r.patch_key,
        r.champion_id,
        r.stat,
        r.coefficient / MAX(r.coefficient) OVER (PARTITION BY r.patch_key, r.champion_id)
        * u.ratio_usage AS usefulness
    FROM ratios AS r
    INNER JOIN usage_des_ratios AS u
        ON r.patch_key = u.patch_key AND r.champion_id = u.champion_id
    WHERE r.coefficient > 0
),

utilite AS (
    SELECT patch_key, champion_id, stat, MAX(usefulness) AS usefulness
    FROM utilites
    GROUP BY patch_key, champion_id, stat
),

objets AS (
    SELECT
        i.patch_key,
        i.item_id,
        i.item_name,
        i.gold_total,
        s.stat,
        s.value,
        -- Vide pour une stat sans prix : elle ne compte pas.
        p.gold_per_unit
    FROM {{ ref('stg_ddragon__items') }} AS i
    INNER JOIN {{ ref('stg_item_stats') }} AS s
        ON i.patch_key = s.patch_key AND i.item_id = s.item_id
    LEFT JOIN {{ ref('int_items__stat_gold_price') }} AS p
        ON s.patch_key = p.patch_key AND s.stat = p.stat
    WHERE i.is_completed
),

valeurs AS (
    SELECT
        c.patch_key,
        c.champion_id,
        c.champion_code,
        c.champion_name,
        o.item_id,
        o.item_name,
        o.gold_total,
        -- COALESCE : une stat sans prix vaut 0, et la somme reste un nombre.
        SUM(COALESCE(o.value * o.gold_per_unit, 0)) AS gold_value,
        SUM(COALESCE(o.value * o.gold_per_unit * u.usefulness, 0)) AS useful_gold_value
    FROM {{ ref('stg_ddragon__champions') }} AS c
    INNER JOIN objets AS o
        ON o.patch_key = c.patch_key
    LEFT JOIN utilite AS u
        ON u.patch_key = c.patch_key AND u.champion_id = c.champion_id AND u.stat = o.stat
    GROUP BY
        c.patch_key, c.champion_id, c.champion_code, c.champion_name,
        o.item_id, o.item_name, o.gold_total
)

SELECT
    patch_key,
    champion_id,
    champion_code,
    champion_name,
    item_id,
    item_name,
    gold_total,
    ROUND(gold_value, 1) AS gold_value,
    ROUND(useful_gold_value, 1) AS useful_gold_value,
    -- Rentabilite brute : toutes les stats, comme si toutes etaient utiles.
    ROUND(gold_value / gold_total, 4) AS gold_efficiency,
    ROUND(useful_gold_value / gold_total, 4) AS useful_gold_efficiency,
    RANK() OVER (
        PARTITION BY patch_key, champion_id
        ORDER BY useful_gold_value / gold_total DESC
    ) AS rank_for_champion
FROM valeurs
