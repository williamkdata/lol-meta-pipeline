-- Bulletin de patch, mesure 2 : le build POPULAIRE contre la meilleure
-- ALTERNATIVE (demande de William du 06/11/2026 : « populaire » ne veut pas
-- dire « bon », tout le monde copie tout le monde). Une ligne par patch,
-- poste, champion et niveau de build :
--   - famille : critique, letalite, AP... (mart_ladder_build_families) ;
--   - chemin : les deux premiers objets termines (mart_ladder_builds).
-- Seules les options jouees au moins build_family_min_games fois comptent
-- (decision 4 de William : 10 parties minimum pour un choix). Un champion qui
-- n'a qu'une option n'a pas de duel, donc pas de ligne.
--
-- Le verdict compare les fourchettes de Wilson (95 %) :
--   - populaire_confirme : le BAS du populaire depasse le HAUT de toutes les
--     autres options -> il gagne plus, et c'est prouve ;
--   - pepite : le BAS d'une alternative depasse le HAUT du populaire -> une
--     option moins jouee qui gagne nettement plus ;
--   - non_departage : les fourchettes se chevauchent -> pas assez de parties
--     pour trancher (le cas le plus frequent tant que le volume est faible).

WITH options AS (
    SELECT
        patch_key,
        team_position,
        champion_id,
        'famille' AS level,
        build_family AS option_label,
        games,
        win_rate,
        win_rate_low,
        win_rate_high
    FROM {{ ref('mart_ladder_build_families') }}
    WHERE games >= {{ var('build_family_min_games') }}

    UNION ALL

    SELECT
        patch_key,
        team_position,
        champion_id,
        'chemin' AS level,
        CONCAT(first_item_name, ' > ', second_item_name) AS option_label,
        games,
        win_rate,
        win_rate_low,
        win_rate_high
    FROM {{ ref('mart_ladder_builds') }}
    -- Un « chemin » d'un seul objet (partie finie avant le deuxieme) n'est pas
    -- un build que l'on peut conseiller.
    WHERE second_item_id IS NOT NULL
        AND games >= {{ var('build_family_min_games') }}
),

classees AS (
    SELECT
        *,
        -- La plus jouee ; a egalite de parties, la meilleure fourchette, puis
        -- l'ordre alphabetique, pour que le resultat ne change pas d'un run a
        -- l'autre.
        ROW_NUMBER() OVER (
            PARTITION BY patch_key, team_position, champion_id, level
            ORDER BY games DESC, win_rate_low DESC, option_label
        ) AS popularity_rank,
        COUNT(*) OVER (
            PARTITION BY patch_key, team_position, champion_id, level
        ) AS options
    FROM options
),

alternatives AS (
    -- Pour chaque champion : le plus haut des hauts de fourchette parmi les
    -- alternatives (pour « confirme »), et la meilleure alternative par le bas
    -- de sa fourchette (la challengeuse, et la pepite eventuelle).
    SELECT
        patch_key,
        team_position,
        champion_id,
        level,
        MAX(win_rate_high) AS max_other_win_rate_high,
        ARRAY_AGG(
            STRUCT(option_label, games, win_rate, win_rate_low, win_rate_high)
            ORDER BY win_rate_low DESC, games DESC, option_label
            LIMIT 1
        )[OFFSET(0)] AS challenger
    FROM classees
    WHERE popularity_rank > 1
    GROUP BY patch_key, team_position, champion_id, level
)

SELECT
    p.patch_key,
    p.team_position,
    p.champion_id,
    c.champion_name,
    p.level,
    p.options,
    p.option_label AS popular_option,
    p.games AS popular_games,
    p.win_rate AS popular_win_rate,
    p.win_rate_low AS popular_win_rate_low,
    p.win_rate_high AS popular_win_rate_high,
    a.challenger.option_label AS challenger_option,
    a.challenger.games AS challenger_games,
    a.challenger.win_rate AS challenger_win_rate,
    a.challenger.win_rate_low AS challenger_win_rate_low,
    a.challenger.win_rate_high AS challenger_win_rate_high,
    CASE
        WHEN p.win_rate_low > a.max_other_win_rate_high THEN 'populaire_confirme'
        WHEN a.challenger.win_rate_low > p.win_rate_high THEN 'pepite'
        ELSE 'non_departage'
    END AS verdict
FROM classees AS p
INNER JOIN alternatives AS a
    ON p.patch_key = a.patch_key
    AND p.team_position = a.team_position
    AND p.champion_id = a.champion_id
    AND p.level = a.level
LEFT JOIN {{ ref('stg_ddragon__champions') }} AS c
    ON p.patch_key = c.patch_key AND p.champion_id = c.champion_id
WHERE p.popularity_rank = 1
