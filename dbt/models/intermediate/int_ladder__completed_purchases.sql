-- L'ordre d'achat des objets TERMINES de chaque joueur du ladder : une ligne
-- par joueur et par objet, avec son rang (1 = premier objet termine achete).
-- La partie ne donne que l'inventaire final : l'ORDRE vient de la timeline.
-- Partage par mart_ladder_builds (les deux premiers objets) et par les familles
-- de builds (les trois premiers) : la regle des achats annules n'est ecrite
-- qu'ici (sortie de mart_ladder_builds le 06/11/2026).

WITH termines AS (
    SELECT patch_key, item_id
    FROM {{ ref('stg_ddragon__items') }}
    WHERE is_completed
),

evenements AS (
    SELECT match_id, participant_id, event_type, item_id, before_item_id, timestamp_ms
    FROM {{ ref('stg_ladder__events') }}
    WHERE event_type IN ('ITEM_PURCHASED', 'ITEM_UNDO')
),

achats AS (
    -- Les achats d'objets termines, sauf ceux annules dans la minute.
    SELECT
        a.match_id,
        a.participant_id,
        a.item_id,
        a.timestamp_ms
    FROM evenements AS a
    INNER JOIN {{ ref('stg_ladder__participants') }} AS p
        ON a.match_id = p.match_id AND a.participant_id = p.participant_id
    INNER JOIN termines AS t
        ON p.patch_key = t.patch_key AND a.item_id = t.item_id
    WHERE a.event_type = 'ITEM_PURCHASED'
        -- Annuler un achat produit un ITEM_UNDO dont before_item_id est l'objet
        -- achete (verifie : 189 annulations d'achat sur 218 ITEM_UNDO).
        AND NOT EXISTS (
            SELECT 1
            FROM evenements AS u
            WHERE u.event_type = 'ITEM_UNDO'
                AND u.match_id = a.match_id
                AND u.participant_id = a.participant_id
                AND u.before_item_id = a.item_id
                AND u.timestamp_ms BETWEEN a.timestamp_ms AND a.timestamp_ms + 60000
        )
)

-- Le rang de chaque objet dans le build. Un objet revendu puis rachete ne
-- compte qu'une fois, a son premier achat (MIN).
SELECT
    match_id,
    participant_id,
    item_id,
    ROW_NUMBER() OVER (
        PARTITION BY match_id, participant_id
        ORDER BY MIN(timestamp_ms), item_id
    ) AS purchase_rank
FROM achats
GROUP BY match_id, participant_id, item_id
