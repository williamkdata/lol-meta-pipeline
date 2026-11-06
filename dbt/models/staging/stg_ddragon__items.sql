-- Les objets, un par patch, avec la cle de patch commune et un drapeau
-- is_completed : l'objet compte-t-il dans un build ?

SELECT
    CAST(SPLIT(patch, '.')[OFFSET(0)] AS INT64) * 100
    + CAST(SPLIT(patch, '.')[OFFSET(1)] AS INT64) AS patch_key,
    patch,
    version,
    item_id,
    item_name,
    gold_total,
    purchasable,
    on_summoners_rift,
    builds_into,
    builds_from,
    depth,
    tags,

    -- Un objet TERMINE : sur la Faille, achetable, il ne se transforme en rien,
    -- ce n'est ni une potion ni une balise, et il coute au moins le seuil
    -- (dbt_project.yml : 2 000, le trou de la distribution des prix, qui ecarte
    -- objets de depart, bottes et objets de support ameliores). Les variantes
    -- d'autres modes (identifiants a 6 chiffres, que Data Dragon marque pourtant
    -- sur la Faille) sont ecartees : jamais achetees en ladder (05/11/2026).
    (
        on_summoners_rift
        AND item_id < {{ var('mode_variant_min_item_id') }}
        AND purchasable
        AND ARRAY_LENGTH(builds_into) = 0
        AND 'Consumable' NOT IN UNNEST(tags)
        AND 'Trinket' NOT IN UNNEST(tags)
        AND gold_total >= {{ var('completed_item_min_gold') }}
    ) AS is_completed

FROM {{ source('lol_raw', 'ddragon_items') }}

-- Meme dedoublonnage que les champions : une ligne par objet et par patch.
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY item_id, patch
    ORDER BY version DESC
) = 1
