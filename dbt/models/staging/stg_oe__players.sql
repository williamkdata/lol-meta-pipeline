-- Une ligne par joueur et par match pro, colonnes typees.
-- Le brut est tout en texte : c'est ici que chaque colonne prend son vrai type.

SELECT
    gameid AS game_id,
    SAFE_CAST(participantid AS INT64) AS participant_id,
    league,
    SAFE_CAST(year AS INT64) AS season_year,
    split,
    playoffs = '1' AS is_playoffs,
    SAFE_CAST(date AS TIMESTAMP) AS played_at,
    SAFE_CAST(game AS INT64) AS game_number_in_series,

    -- Le patch tel qu'Oracle's Elixir l'ecrit ("16.01"), et la cle commune
    -- a toutes les sources (1601) — meme calcul que pour Data Dragon.
    patch AS patch_label,
    SAFE_CAST(SPLIT(patch, '.')[SAFE_OFFSET(0)] AS INT64) * 100
    + SAFE_CAST(SPLIT(patch, '.')[SAFE_OFFSET(1)] AS INT64) AS patch_key,

    side,
    position,
    playername AS player_name,
    teamname AS team_name,
    champion AS champion_name,
    result = '1' AS is_win,
    SAFE_CAST(gamelength AS INT64) AS game_length_s,

    SAFE_CAST(kills AS INT64) AS kills,
    SAFE_CAST(deaths AS INT64) AS deaths,
    SAFE_CAST(assists AS INT64) AS assists,
    SAFE_CAST(damagetochampions AS FLOAT64) AS damage_to_champions,
    SAFE_CAST(earnedgold AS FLOAT64) AS earned_gold,

    -- Les ecarts a 10 et 15 minutes. VIDES (NULL) si le match est "partial"
    -- ou s'il s'est termine avant : NULL veut dire "inconnu", pas zero.
    SAFE_CAST(golddiffat10 AS FLOAT64) AS gold_diff_at_10,
    SAFE_CAST(golddiffat15 AS FLOAT64) AS gold_diff_at_15,
    SAFE_CAST(xpdiffat10 AS FLOAT64) AS xp_diff_at_10,
    SAFE_CAST(csdiffat10 AS FLOAT64) AS cs_diff_at_10,

    datacompleteness = 'complete' AS is_complete

FROM {{ source('lol_raw', 'oe_matches') }}

-- Les 2 lignes "team" de chaque match vont dans stg_oe__teams.
WHERE position != 'team'
