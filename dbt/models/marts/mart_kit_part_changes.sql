-- Les morceaux de formule qui changent d'un patch au suivant, compares AU MEME
-- ENDROIT de l'arbre (part_path) :
--   modifie : chiffres differents ("bouclier : 1,5 -> 1,8 x l'attaque bonus") ;
--   ajoute  : morceau nouveau (Riot ajoute un ratio de PV, par exemple) ;
--   retire  : morceau disparu.
-- Seuls les champions presents dans les DEUX patches sont compares : un
-- champion qui sort n'est pas une liste d'"ajouts".

WITH morceaux AS (
    SELECT
        *,
        DENSE_RANK() OVER (ORDER BY patch_key) AS patch_index
    FROM {{ ref('stg_kit__parts') }}
),

patches AS (
    SELECT DISTINCT patch_index, patch_key FROM morceaux
),

presences AS (
    -- Quels champions existent a quel patch.
    SELECT DISTINCT patch_index, champion_id FROM morceaux
),

comparaison AS (
    SELECT
        COALESCE(n.patch_index, a.patch_index + 1) AS patch_index,
        COALESCE(n.champion_id, a.champion_id) AS champion_id,
        COALESCE(n.champion_code, a.champion_code) AS champion_code,
        COALESCE(n.slot, a.slot) AS slot,
        COALESCE(n.calc_name, a.calc_name) AS calc_name,
        COALESCE(n.part_path, a.part_path) AS part_path,
        COALESCE(n.part_type, a.part_type) AS part_type,
        CASE
            WHEN a.part_path IS NULL THEN 'ajoute'
            WHEN n.part_path IS NULL THEN 'retire'
            ELSE 'modifie'
        END AS change_kind,
        a.stat AS old_stat,
        n.stat AS new_stat,
        a.stat_formula AS old_stat_formula,
        n.stat_formula AS new_stat_formula,
        a.coefficient AS old_coefficient,
        n.coefficient AS new_coefficient,
        a.data_value AS old_data_value,
        n.data_value AS new_data_value,
        a.number AS old_number,
        n.number AS new_number,
        a.start_value AS old_start_value,
        n.start_value AS new_start_value,
        a.end_value AS old_end_value,
        n.end_value AS new_end_value
    FROM morceaux AS n
    FULL OUTER JOIN morceaux AS a
        ON n.patch_index - 1 = a.patch_index
        AND n.champion_id = a.champion_id
        AND n.slot = a.slot
        AND n.calc_name = a.calc_name
        AND n.part_path = a.part_path
)

SELECT
    p.patch_key,
    prec.patch_key AS previous_patch_key,
    c.champion_id,
    -- Le code vient du kit : lisible le jour meme d'un nouveau patch.
    c.champion_code,
    d.champion_name,
    c.slot,
    c.calc_name,
    c.part_path,
    c.part_type,
    c.change_kind,
    c.* EXCEPT (
        patch_index, champion_id, champion_code, slot, calc_name, part_path,
        part_type, change_kind
    )
FROM comparaison AS c
INNER JOIN patches AS p ON c.patch_index = p.patch_index
INNER JOIN patches AS prec ON c.patch_index - 1 = prec.patch_index
-- Le champion existe dans les deux patches.
INNER JOIN presences AS avant
    ON c.patch_index - 1 = avant.patch_index AND c.champion_id = avant.champion_id
INNER JOIN presences AS apres
    ON c.patch_index = apres.patch_index AND c.champion_id = apres.champion_id
LEFT JOIN {{ ref('stg_ddragon__champions') }} AS d
    ON p.patch_key = d.patch_key AND c.champion_id = d.champion_id
WHERE c.change_kind != 'modifie'
    -- IS DISTINCT FROM : traite le vide comme une valeur. "NULL != 1.5" ne vaut
    -- ni vrai ni faux, et raterait le passage d'un vide a un nombre.
    OR c.old_stat IS DISTINCT FROM c.new_stat
    OR c.old_stat_formula IS DISTINCT FROM c.new_stat_formula
    OR c.old_coefficient IS DISTINCT FROM c.new_coefficient
    OR c.old_data_value IS DISTINCT FROM c.new_data_value
    OR c.old_number IS DISTINCT FROM c.new_number
    OR c.old_start_value IS DISTINCT FROM c.new_start_value
    OR c.old_end_value IS DISTINCT FROM c.new_end_value
