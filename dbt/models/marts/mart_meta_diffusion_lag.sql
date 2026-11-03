-- Le delai de diffusion de la meta : pour chaque champion, le premier patch ou
-- il entre dans le coeur de la meta pro, le premier ou il entre dans celui de
-- la ladder, et l'ecart en patches. Positif : le pro d'abord. Negatif : la
-- ladder d'abord.
--
-- CENSURE A GAUCHE : la ladder n'est collectee que depuis le 31/10/2026 (patch
-- 16.21). Un champion deja dans le coeur ladder au premier patch collecte y
-- etait peut-etre depuis longtemps : on ne sait pas QUAND il y est entre. Son
-- delai n'est pas calcule ; son statut le dit. Meme chose pour un champion
-- entre dans le coeur pro AVANT le debut de la collecte ladder : ce que la
-- ladder a fait pendant la periode non observee est inconnu.

WITH couverture AS (
    -- Le premier patch couvert de chaque cote.
    SELECT
        MIN(IF(pro_matches IS NOT NULL, patch_index, NULL)) AS premier_index_pro,
        MIN(IF(ladder_matches IS NOT NULL, patch_index, NULL)) AS premier_index_ladder
    FROM {{ ref('mart_meta_diffusion') }}
),

entrees AS (
    SELECT
        champion_id,
        -- Le nom du dernier patch : un champion peut etre renomme.
        ARRAY_AGG(champion_name ORDER BY patch_key DESC LIMIT 1)[OFFSET(0)] AS champion_name,
        MIN(IF(in_pro_core, patch_index, NULL)) AS pro_entry_index,
        MIN(IF(in_pro_core, patch_key, NULL)) AS pro_entry_patch_key,
        MIN(IF(in_ladder_core, patch_index, NULL)) AS ladder_entry_index,
        MIN(IF(in_ladder_core, patch_key, NULL)) AS ladder_entry_patch_key
    FROM {{ ref('mart_meta_diffusion') }}
    GROUP BY champion_id
),

statuts AS (
    SELECT
        e.*,
        CASE
            WHEN e.pro_entry_index IS NULL AND e.ladder_entry_index IS NULL
                THEN 'hors meta'
            WHEN e.pro_entry_index = c.premier_index_pro
                OR e.ladder_entry_index = c.premier_index_ladder
                THEN 'deja dans la meta au debut de la collecte'
            -- Entre en pro AVANT que la ladder soit collectee : il a peut-etre
            -- ete dans le coeur ladder pendant la periode non observee. Aucun
            -- delai ne peut etre affirme.
            WHEN e.pro_entry_index < c.premier_index_ladder
                THEN 'entree pro avant la collecte ladder'
            WHEN e.pro_entry_index IS NULL
                THEN 'ladder seulement'
            WHEN e.ladder_entry_index IS NULL
                THEN 'pro seulement (pas encore descendu)'
            ELSE 'mesure'
        END AS status
    FROM entrees AS e
    CROSS JOIN couverture AS c
)

SELECT
    *,
    IF(status = 'mesure', ladder_entry_index - pro_entry_index, NULL) AS lag_patches
FROM statuts
