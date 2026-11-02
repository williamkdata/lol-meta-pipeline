-- Les builds du ladder : pour chaque champion a son poste et par patch, le
-- chemin des DEUX PREMIERS OBJETS TERMINES achetes (par exemple Collector puis
-- Lame d'infini), sa part des parties du champion et son taux de victoire.
-- La partie ne donne que l'inventaire final : l'ORDRE vient de la timeline.

WITH termines AS (
    SELECT patch_key, item_id, item_name
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
),

ordonnes AS (
    -- Le rang de chaque objet dans le build. Un objet revendu puis rachete ne
    -- compte qu'une fois, a son premier achat (MIN).
    SELECT
        match_id,
        participant_id,
        item_id,
        ROW_NUMBER() OVER (
            PARTITION BY match_id, participant_id
            ORDER BY MIN(timestamp_ms), item_id
        ) AS rang
    FROM achats
    GROUP BY match_id, participant_id, item_id
),

chemins AS (
    SELECT
        match_id,
        participant_id,
        MAX(IF(rang = 1, item_id, NULL)) AS first_item_id,
        MAX(IF(rang = 2, item_id, NULL)) AS second_item_id
    FROM ordonnes
    WHERE rang <= 2
    GROUP BY match_id, participant_id
),

par_chemin AS (
    SELECT
        p.patch_key,
        p.team_position,
        p.champion_id,
        c.first_item_id,
        c.second_item_id,
        COUNT(*) AS games,
        COUNTIF(p.is_win) AS wins
    FROM {{ ref('stg_ladder__participants') }} AS p
    INNER JOIN chemins AS c
        ON p.match_id = c.match_id AND p.participant_id = c.participant_id
    GROUP BY p.patch_key, p.team_position, p.champion_id, c.first_item_id, c.second_item_id
)

SELECT
    b.patch_key,
    b.team_position,
    b.champion_id,
    b.first_item_id,
    i1.item_name AS first_item_name,
    -- Vide si la partie s'est finie avant le deuxieme objet termine.
    b.second_item_id,
    i2.item_name AS second_item_name,
    b.games,
    b.wins,
    ROUND(
        b.games / SUM(b.games) OVER (PARTITION BY b.patch_key, b.team_position, b.champion_id),
        4
    ) AS share_of_champion_games,
    ROUND(b.wins / b.games, 4) AS win_rate,
    ROUND({{ wilson_bound('b.wins', 'b.games', '-') }}, 4) AS win_rate_low,
    ROUND({{ wilson_bound('b.wins', 'b.games', '+') }}, 4) AS win_rate_high

FROM par_chemin AS b
LEFT JOIN termines AS i1
    ON b.patch_key = i1.patch_key AND b.first_item_id = i1.item_id
LEFT JOIN termines AS i2
    ON b.patch_key = i2.patch_key AND b.second_item_id = i2.item_id
