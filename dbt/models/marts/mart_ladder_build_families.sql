-- Les familles de builds du ladder : pour chaque champion a son poste et par
-- patch, combien de parties dans chaque famille, le taux de victoire et sa
-- fourchette. Une famille devient un CHOIX a partir de build_family_min_games
-- parties (decision 4 de William, 05/11/2026 : 10 parties, nombre toujours
-- affiche) ; les choix sont classes par le BAS de la fourchette de Wilson, pour
-- qu'un 80 % sur 10 parties ne passe pas devant un 54 % sur 500.

WITH par_famille AS (
    SELECT
        patch_key,
        team_position,
        champion_id,
        build_family,
        COUNT(*) AS games,
        COUNTIF(is_win) AS wins,
        -- Les builds complets ; les autres sont classes sur 1 ou 2 objets.
        COUNTIF(items_counted = 3) AS games_with_three_items
    FROM {{ ref('int_ladder__build_families') }}
    GROUP BY patch_key, team_position, champion_id, build_family
),

mesures AS (
    SELECT
        *,
        ROUND(
            games / SUM(games) OVER (PARTITION BY patch_key, team_position, champion_id),
            4
        ) AS share_of_champion_games,
        ROUND(wins / games, 4) AS win_rate,
        ROUND({{ wilson_bound('wins', 'games', '-') }}, 4) AS win_rate_low,
        ROUND({{ wilson_bound('wins', 'games', '+') }}, 4) AS win_rate_high,
        games >= {{ var('build_family_min_games') }} AS is_choice
    FROM par_famille
)

SELECT
    m.patch_key,
    m.team_position,
    m.champion_id,
    c.champion_name,
    m.build_family,
    m.games,
    m.wins,
    m.games_with_three_items,
    m.share_of_champion_games,
    m.win_rate,
    m.win_rate_low,
    m.win_rate_high,
    m.is_choice,
    -- Le rang parmi les choix du champion (1 = la fourchette la plus haute),
    -- vide pour une famille qui n'est pas un choix.
    IF(
        m.is_choice,
        RANK() OVER (
            PARTITION BY m.patch_key, m.team_position, m.champion_id, m.is_choice
            ORDER BY m.win_rate_low DESC, m.games DESC
        ),
        NULL
    ) AS choice_rank,
    COUNTIF(m.is_choice) OVER (
        PARTITION BY m.patch_key, m.team_position, m.champion_id
    ) AS choices_for_champion
FROM mesures AS m
LEFT JOIN {{ ref('stg_ddragon__champions') }} AS c
    ON m.patch_key = c.patch_key AND m.champion_id = c.champion_id
