-- Les builds du ladder : pour chaque champion a son poste et par patch, le
-- chemin des DEUX PREMIERS OBJETS TERMINES achetes (par exemple Collector puis
-- Lame d'infini), sa part des parties du champion et son taux de victoire.
-- L'ordre d'achat (achats annules exclus) vient de
-- int_ladder__completed_purchases, partage avec les familles de builds.

WITH termines AS (
    SELECT patch_key, item_id, item_name
    FROM {{ ref('stg_ddragon__items') }}
    WHERE is_completed
),

chemins AS (
    SELECT
        match_id,
        participant_id,
        MAX(IF(purchase_rank = 1, item_id, NULL)) AS first_item_id,
        MAX(IF(purchase_rank = 2, item_id, NULL)) AS second_item_id
    FROM {{ ref('int_ladder__completed_purchases') }}
    WHERE purchase_rank <= 2
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
