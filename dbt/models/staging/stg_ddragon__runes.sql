-- Les runes, une par patch, avec leur arbre (Domination, Inspiration...) et
-- leur rangee : slot 0 = les runes principales (Electrocution, Conquerant...).

SELECT
    CAST(SPLIT(patch, '.')[OFFSET(0)] AS INT64) * 100
    + CAST(SPLIT(patch, '.')[OFFSET(1)] AS INT64) AS patch_key,
    patch,
    version,
    rune_id,
    rune_name,
    tree_id,
    tree_name,
    slot

FROM {{ source('lol_raw', 'ddragon_runes') }}

QUALIFY ROW_NUMBER() OVER (
    PARTITION BY rune_id, patch
    ORDER BY version DESC
) = 1
