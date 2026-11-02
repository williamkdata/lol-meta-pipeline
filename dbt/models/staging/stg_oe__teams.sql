-- Une ligne par equipe et par match pro : resultat et bans.

SELECT
    gameid AS game_id,
    league,
    SAFE_CAST(date AS TIMESTAMP) AS played_at,
    patch AS patch_label,
    SAFE_CAST(SPLIT(patch, '.')[SAFE_OFFSET(0)] AS INT64) * 100
    + SAFE_CAST(SPLIT(patch, '.')[SAFE_OFFSET(1)] AS INT64) AS patch_key,
    side,
    teamname AS team_name,
    result = '1' AS is_win,
    SAFE_CAST(gamelength AS INT64) AS game_length_s,

    -- Les 5 bans de l'equipe, gardes en colonnes. La mart les deplie en
    -- lignes ; un ban peut etre vide (ban perdu, ou non saisi).
    ban1,
    ban2,
    ban3,
    ban4,
    ban5

FROM {{ source('lol_raw', 'oe_matches') }}
WHERE position = 'team'
