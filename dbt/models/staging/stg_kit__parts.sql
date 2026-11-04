-- Les morceaux des formules des sorts, un par patch, champion, touche, formule
-- et position dans l'arbre, avec la cle de patch commune.

SELECT
    CAST(SPLIT(patch, '.')[OFFSET(0)] AS INT64) * 100
    + CAST(SPLIT(patch, '.')[OFFSET(1)] AS INT64) AS patch_key,
    patch,
    champion_id,
    champion_code,
    slot,
    spell_name,
    calc_name,
    part_path,
    part_type,
    -- Codes decodes et verifies (projet3_explications.md, 9.7) :
    -- stat 0 = AP, 1 = armure, 2 = AD, 6 = RM, 12 = PV ;
    -- formule 0 = total, 2 = bonus. Les autres codes restent inconnus.
    stat,
    stat_formula,
    coefficient,
    data_value,
    number,
    start_value,
    end_value,
    modified_calc

FROM {{ source('lol_raw', 'kit_formula_parts') }}
WHERE STRPOS(champion_code, '_') = 0
