-- Les groupes d'objets, par patch (19/11/2026) : le jeu limite certains cumuls.
-- Au 16.23, le groupe LastWhisper (1 au plus) compte 7 objets, dont le
-- Couperet noir : il est exclusif avec Lord Dominik. Une seule paire de
-- bottes parmi 22. max_ownable vide = pas de limite (groupe Default).
--
-- DISTINCT : le fichier du jeu cite parfois deux fois le meme groupe pour un
-- meme objet (443061, mode Arena, PrismaticTankItems) ; le brut le garde, le
-- staging n'en fait qu'une ligne.
--
-- Premier chargement verifie le 19/11/2026 : 23 patches, 42 129 lignes, 0
-- groupe introuvable, 15 doublons (tous l'objet 443061).

SELECT DISTINCT
    -- "16.4" -> 1604 : la meme cle que toutes les autres sources.
    CAST(SPLIT(patch, '.')[OFFSET(0)] AS INT64) * 100
    + CAST(SPLIT(patch, '.')[OFFSET(1)] AS INT64) AS patch_key,
    patch,
    item_id,
    item_group,
    max_ownable,
    group_defined

FROM {{ source('lol_raw', 'item_groups') }}
