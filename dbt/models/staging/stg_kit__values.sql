-- Les valeurs par rang des sorts (degats de base, durees...), une par patch,
-- champion, touche, nom et rang, avec la cle de patch commune.

SELECT
    -- "16.21" -> 1621 : la meme cle que toutes les autres sources.
    CAST(SPLIT(patch, '.')[OFFSET(0)] AS INT64) * 100
    + CAST(SPLIT(patch, '.')[OFFSET(1)] AS INT64) AS patch_key,
    patch,
    champion_id,
    champion_code,
    slot,
    spell_name,
    value_name,
    spell_rank,
    value

FROM {{ source('lol_raw', 'kit_data_values') }}

-- Les 60 entrees speciales Jade_ du 16.15 : meme filtre que pour les champions.
WHERE STRPOS(champion_code, '_') = 0

-- Le Q de Rek'Sai contient deux fois BuffDuration (meme valeur) dans le fichier
-- du jeu : on n'en garde qu'une.
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY patch, champion_id, slot, spell_name, value_name, spell_rank
    ORDER BY value
) = 1
