-- Les chiffres des sorts qui changent d'un patch au suivant : les buffs et
-- nerfs ("Q d'Ahri, degats de base au rang 3 : 90 -> 100", "Q de Kayle, temps
-- de recharge au rang 1 : 12 -> 10 s"). Chaque chiffre vient de la meilleure
-- source pour lui (verifie contre les notes du 26.22) :
--   communitydragon : valeurs par rang des sorts (degats, ratios nommes...) ;
--   data_dragon     : temps de recharge et cout (le champ cooldownTime de
--                     CommunityDragon est perime, Data Dragon est a jour).
-- Le "patch precedent" est le precedent dans la liste des patches charges :
-- les cles ne se suivent pas de 1 en 1 (1601 vient apres 1524).

WITH rangs_max AS (
    SELECT DISTINCT patch_key, champion_id, slot, max_rank
    FROM {{ ref('stg_ddragon__spells') }}
),

valeurs_kit AS (
    SELECT
        v.patch_key,
        v.champion_id,
        v.champion_code,
        v.slot,
        v.spell_name,
        v.value_name,
        v.spell_rank,
        v.value,
        'communitydragon' AS source
    FROM {{ ref('stg_kit__values') }} AS v
    LEFT JOIN rangs_max AS r
        ON v.patch_key = r.patch_key AND v.champion_id = r.champion_id AND v.slot = r.slot
    -- Les listes ont 7 cases : au-dela du rang max du sort (5, ou 3 pour un
    -- ultime), des rangs fantomes. Le passif n'a pas de rang max : tout est garde.
    WHERE r.max_rank IS NULL OR v.spell_rank <= r.max_rank
),

valeurs_data_dragon AS (
    SELECT
        patch_key, champion_id, champion_code, slot, spell_id AS spell_name,
        'Cooldown' AS value_name, spell_rank, cooldown AS value, 'data_dragon' AS source
    FROM {{ ref('stg_ddragon__spells') }}
    UNION ALL
    SELECT
        patch_key, champion_id, champion_code, slot, spell_id AS spell_name,
        'Cost' AS value_name, spell_rank, cost AS value, 'data_dragon' AS source
    FROM {{ ref('stg_ddragon__spells') }}
),

valeurs AS (
    SELECT
        *,
        DENSE_RANK() OVER (ORDER BY patch_key) AS patch_index
    FROM (
        SELECT * FROM valeurs_kit
        UNION ALL
        SELECT * FROM valeurs_data_dragon
    )
),

changements AS (
    SELECT
        nouveau.patch_key,
        ancien.patch_key AS previous_patch_key,
        nouveau.source,
        nouveau.champion_id,
        nouveau.champion_code,
        nouveau.slot,
        nouveau.spell_name,
        nouveau.value_name,
        nouveau.spell_rank,
        ancien.value AS old_value,
        nouveau.value AS new_value
    FROM valeurs AS nouveau
    INNER JOIN valeurs AS ancien
        ON nouveau.patch_index - 1 = ancien.patch_index
        AND nouveau.source = ancien.source
        AND nouveau.champion_id = ancien.champion_id
        AND nouveau.slot = ancien.slot
        AND nouveau.spell_name = ancien.spell_name
        AND nouveau.value_name = ancien.value_name
        AND nouveau.spell_rank = ancien.spell_rank
    -- Tolerance : les valeurs sont des decimaux (0.2249999...), une difference
    -- infime n'est pas un changement.
    WHERE ABS(nouveau.value - ancien.value) > 0.000001
)

SELECT
    c.patch_key,
    c.previous_patch_key,
    c.source,
    c.champion_id,
    -- Le code vient de la source : lisible le jour meme d'un nouveau patch, avant
    -- que le nom affiche (stg_ddragon__champions) soit charge.
    c.champion_code,
    d.champion_name,
    c.slot,
    c.spell_name,
    c.value_name,
    c.spell_rank,
    c.old_value,
    c.new_value,
    ROUND(c.new_value - c.old_value, 4) AS delta,
    -- Variation relative ; vide si l'ancienne valeur valait 0.
    ROUND(SAFE_DIVIDE(c.new_value - c.old_value, ABS(c.old_value)), 4) AS delta_pct
FROM changements AS c
LEFT JOIN {{ ref('stg_ddragon__champions') }} AS d
    ON c.patch_key = d.patch_key AND c.champion_id = d.champion_id
