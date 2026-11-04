-- Les formules entieres des sorts (JSON canonique), une par patch, champion,
-- touche et nom de formule, avec la cle de patch commune.

SELECT
    CAST(SPLIT(patch, '.')[OFFSET(0)] AS INT64) * 100
    + CAST(SPLIT(patch, '.')[OFFSET(1)] AS INT64) AS patch_key,
    patch,
    champion_id,
    champion_code,
    slot,
    spell_name,
    calc_name,
    formula

FROM {{ source('lol_raw', 'kit_formulas') }}
WHERE STRPOS(champion_code, '_') = 0
