-- La valeur theorique de chaque objet termine pour chaque champion, par patch :
-- les stats de l'objet x le profil de sensibilite du champion. Exemple : un objet
-- a 45 d'attaque, pour un champion dont les ratios d'attaque font 2,0 au total,
-- vaut 45 x 2,0 = 90 "points de ratio". Rapportee a 1 000 pieces d'or pour
-- comparer des objets de prix differents, avec le rang de l'objet pour ce
-- champion et l'ecart avec le patch precedent (un ratio buffe -> les objets de
-- cette stat gagnent en valeur).
--
-- Approximation assumee (version A) : passifs des objets ignores, degats,
-- boucliers et soins additionnes, temps de recharge ignores.

WITH profil AS (
    -- Un coefficient par champion et par stat d'objet (total et bonus reunis :
    -- un objet donne des stats bonus, qui comptent aussi dans le total).
    SELECT
        patch_key,
        champion_id,
        champion_code,
        item_stat,
        SUM(total_coefficient) AS coefficient
    FROM {{ ref('mart_champion_stat_profile') }}
    GROUP BY patch_key, champion_id, champion_code, item_stat
),

objets AS (
    SELECT
        i.patch_key,
        i.item_id,
        i.item_name,
        i.gold_total,
        s.stat,
        s.value
    FROM {{ ref('stg_ddragon__items') }} AS i
    INNER JOIN {{ ref('stg_item_stats') }} AS s
        ON i.patch_key = s.patch_key AND i.item_id = s.item_id
    WHERE i.is_completed
),

valeurs AS (
    SELECT
        p.patch_key,
        p.champion_id,
        p.champion_code,
        o.item_id,
        o.item_name,
        o.gold_total,
        SUM(p.coefficient * o.value) AS theory_value
    FROM profil AS p
    INNER JOIN objets AS o
        ON p.patch_key = o.patch_key AND p.item_stat = o.stat
    GROUP BY p.patch_key, p.champion_id, p.champion_code, o.item_id, o.item_name, o.gold_total
)

SELECT
    patch_key,
    champion_id,
    champion_code,
    item_id,
    item_name,
    gold_total,
    ROUND(theory_value, 2) AS theory_value,
    ROUND(SAFE_DIVIDE(theory_value, gold_total) * 1000, 2) AS theory_value_per_1000_gold,
    -- Le rang de l'objet pour ce champion (1 = le plus rentable).
    RANK() OVER (
        PARTITION BY patch_key, champion_id
        ORDER BY SAFE_DIVIDE(theory_value, gold_total) DESC
    ) AS rank_for_champion,
    -- L'ecart avec le patch precedent : ce qu'un patch change pour cet objet.
    ROUND(
        theory_value
        - LAG(theory_value) OVER (PARTITION BY champion_id, item_id ORDER BY patch_key),
        2
    ) AS change_vs_previous_patch
FROM valeurs
