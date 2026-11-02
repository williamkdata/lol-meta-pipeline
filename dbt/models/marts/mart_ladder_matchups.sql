-- Les matchups du ladder : chaque champion contre son vis-a-vis (meme poste,
-- equipe adverse), par patch. Resultat, fourchette du taux de victoire, et
-- les TIMINGS D'AVANTAGE : ecart moyen d'or a 10 et 15 minutes, d'XP et de
-- sbires a 10 minutes. Chaque duel apparait dans les deux sens (Ahri contre
-- Syndra, et Syndra contre Ahri) : on lit la ligne du champion qui interesse.

WITH joueurs AS (
    SELECT
        match_id,
        patch_key,
        participant_id,
        team_id,
        team_position,
        champion_id,
        is_win
    FROM {{ ref('stg_ladder__participants') }}
),

photos AS (
    -- Une ligne par joueur et par partie, avec ses valeurs a 10 et 15 min.
    -- MAX(IF(...)) fait pivoter les lignes en colonnes : parmi les frames du
    -- joueur, seule celle de la minute 10 a une valeur, le MAX la recupere.
    SELECT
        match_id,
        participant_id,
        MAX(IF(frame_index = 10, total_gold, NULL)) AS gold_10,
        MAX(IF(frame_index = 15, total_gold, NULL)) AS gold_15,
        MAX(IF(frame_index = 10, xp, NULL)) AS xp_10,
        MAX(IF(frame_index = 10, cs, NULL)) AS cs_10
    FROM {{ ref('stg_ladder__frames') }}
    WHERE frame_index IN (10, 15)
    GROUP BY match_id, participant_id
),

duels AS (
    SELECT
        moi.patch_key,
        moi.team_position,
        moi.champion_id,
        lui.champion_id AS opponent_champion_id,
        moi.is_win,
        pm.gold_10 - pl.gold_10 AS gold_diff_10,
        pm.gold_15 - pl.gold_15 AS gold_diff_15,
        pm.xp_10 - pl.xp_10 AS xp_diff_10,
        pm.cs_10 - pl.cs_10 AS cs_diff_10
    FROM joueurs AS moi
    -- Le vis-a-vis : meme partie, meme poste, l'autre equipe.
    INNER JOIN joueurs AS lui
        ON moi.match_id = lui.match_id
        AND moi.team_position = lui.team_position
        AND moi.team_id != lui.team_id
    LEFT JOIN photos AS pm
        ON moi.match_id = pm.match_id AND moi.participant_id = pm.participant_id
    LEFT JOIN photos AS pl
        ON lui.match_id = pl.match_id AND lui.participant_id = pl.participant_id
)

SELECT
    patch_key,
    team_position,
    champion_id,
    opponent_champion_id,
    COUNT(*) AS games,
    COUNTIF(is_win) AS wins,
    ROUND(COUNTIF(is_win) / COUNT(*), 4) AS win_rate,
    ROUND({{ wilson_bound('COUNTIF(is_win)', 'COUNT(*)', '-') }}, 4) AS win_rate_low,
    ROUND({{ wilson_bound('COUNTIF(is_win)', 'COUNT(*)', '+') }}, 4) AS win_rate_high,
    ROUND(AVG(gold_diff_10)) AS avg_gold_diff_10,
    ROUND(AVG(gold_diff_15)) AS avg_gold_diff_15,
    ROUND(AVG(xp_diff_10)) AS avg_xp_diff_10,
    ROUND(AVG(cs_diff_10), 1) AS avg_cs_diff_10
FROM duels
GROUP BY patch_key, team_position, champion_id, opponent_champion_id
