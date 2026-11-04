-- Les stats des objets (fichiers du jeu, CommunityDragon), une par patch, objet
-- et stat, avec la cle de patch commune. Noms comme dans Data Dragon
-- (FlatHPPoolMod...) ; plus complet que Data Dragon (acceleration de competence).

SELECT
    CAST(SPLIT(patch, '.')[OFFSET(0)] AS INT64) * 100
    + CAST(SPLIT(patch, '.')[OFFSET(1)] AS INT64) AS patch_key,
    patch,
    item_id,
    stat,
    value

FROM {{ source('lol_raw', 'item_stats') }}
