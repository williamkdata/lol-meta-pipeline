-- La meta du ladder EUW : par patch, poste et champion, parties, victoires,
-- taux de victoire AVEC SA FOURCHETTE (intervalle de Wilson a 95 %) et taux
-- de pick au poste. Le nom affiche vient de Data Dragon, joint par NUMERO de
-- champion (Riot ecrit "MonkeyKing" dans les parties, Data Dragon "Wukong").

WITH par_champion AS (
    SELECT
        patch_key,
        team_position,
        champion_id,
        COUNT(*) AS games,
        COUNTIF(is_win) AS wins
    FROM {{ ref('stg_ladder__participants') }}
    GROUP BY patch_key, team_position, champion_id
),

parties AS (
    -- Le denominateur du taux de pick : les parties du patch.
    SELECT
        patch_key,
        COUNT(DISTINCT match_id) AS matches
    FROM {{ ref('stg_ladder__participants') }}
    GROUP BY patch_key
)

SELECT
    c.patch_key,
    c.team_position,
    c.champion_id,
    d.champion_name,
    p.matches,
    c.games,
    c.wins,
    ROUND(c.wins / c.games, 4) AS win_rate,
    ROUND({{ wilson_bound('c.wins', 'c.games', '-') }}, 4) AS win_rate_low,
    ROUND({{ wilson_bound('c.wins', 'c.games', '+') }}, 4) AS win_rate_high,
    -- Un champion n'est pris qu'une fois par partie : a ce poste, il est dans
    -- `games` parties sur `matches`.
    ROUND(c.games / p.matches, 4) AS pick_rate

FROM par_champion AS c
INNER JOIN parties AS p USING (patch_key)
-- LEFT JOIN : un champion sorti le jour meme, avant le chargement de Data
-- Dragon, reste visible avec un nom vide ; le test not_null le signale.
LEFT JOIN {{ ref('stg_ddragon__champions') }} AS d
    ON c.patch_key = d.patch_key AND c.champion_id = d.champion_id
