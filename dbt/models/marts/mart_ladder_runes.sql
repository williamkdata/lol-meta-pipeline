-- Les runes du ladder : pour chaque champion a son poste et par patch, chaque
-- page (rune principale + arbre principal + arbre secondaire), sa part des
-- parties du champion, et son taux de victoire avec sa fourchette. Les noms
-- viennent de Data Dragon (runesReforged.json).

WITH par_page AS (
    SELECT
        patch_key,
        team_position,
        champion_id,
        keystone_id,
        primary_style,
        sub_style,
        COUNT(*) AS games,
        COUNTIF(is_win) AS wins
    FROM {{ ref('stg_ladder__participants') }}
    GROUP BY patch_key, team_position, champion_id, keystone_id, primary_style, sub_style
),

arbres AS (
    -- Un arbre par patch : son numero (8100) et son nom (Domination).
    SELECT DISTINCT patch_key, tree_id, tree_name
    FROM {{ ref('stg_ddragon__runes') }}
)

SELECT
    r.patch_key,
    r.team_position,
    r.champion_id,
    r.keystone_id,
    k.rune_name AS keystone_name,
    r.primary_style,
    a1.tree_name AS primary_style_name,
    r.sub_style,
    a2.tree_name AS sub_style_name,
    r.games,
    r.wins,
    -- SUM(...) OVER (PARTITION BY ...) : le total des parties du champion a son
    -- poste, ecrit sur chaque ligne sans regrouper. La part d'une page = ses
    -- parties / ce total.
    ROUND(
        r.games / SUM(r.games) OVER (PARTITION BY r.patch_key, r.team_position, r.champion_id),
        4
    ) AS share_of_champion_games,
    ROUND(r.wins / r.games, 4) AS win_rate,
    ROUND({{ wilson_bound('r.wins', 'r.games', '-') }}, 4) AS win_rate_low,
    ROUND({{ wilson_bound('r.wins', 'r.games', '+') }}, 4) AS win_rate_high

FROM par_page AS r
LEFT JOIN {{ ref('stg_ddragon__runes') }} AS k
    ON r.patch_key = k.patch_key AND r.keystone_id = k.rune_id
LEFT JOIN arbres AS a1
    ON r.patch_key = a1.patch_key AND r.primary_style = a1.tree_id
LEFT JOIN arbres AS a2
    ON r.patch_key = a2.patch_key AND r.sub_style = a2.tree_id
