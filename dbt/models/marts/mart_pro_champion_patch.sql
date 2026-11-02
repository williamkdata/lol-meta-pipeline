-- La meta pro : par patch et par champion, picks, victoires, bans, presence.
-- Premier croisement des deux sources : chaque champion pro retrouve son
-- numero Data Dragon par (nom, patch_key).

WITH picks AS (
    -- Un pick = une ligne joueur. Un champion ne peut etre joue qu'une fois
    -- par match (draft), donc picks <= nombre de matchs.
    SELECT
        patch_key,
        champion_name,
        COUNT(*) AS picks,
        COUNTIF(is_win) AS wins
    FROM {{ ref('stg_oe__players') }}
    GROUP BY patch_key, champion_name
),

bans AS (
    -- Les 5 colonnes de bans de chaque equipe deviennent 5 lignes : UNNEST
    -- deplie le tableau [ban1, ..., ban5]. Les bans vides sont ecartes.
    SELECT
        t.patch_key,
        ban AS champion_name,
        COUNT(*) AS bans
    FROM {{ ref('stg_oe__teams') }} AS t,
        UNNEST([t.ban1, t.ban2, t.ban3, t.ban4, t.ban5]) AS ban
    WHERE ban IS NOT NULL AND TRIM(ban) != ''
    GROUP BY t.patch_key, ban
),

games AS (
    SELECT
        patch_key,
        COUNT(DISTINCT game_id) AS games
    FROM {{ ref('stg_oe__teams') }}
    GROUP BY patch_key
),

meta AS (
    -- FULL OUTER JOIN : un champion peut etre banni sans jamais etre joue
    -- (Evelynn, en 2026), ou joue sans etre banni. Aucun des deux ne doit
    -- disparaitre.
    SELECT
        patch_key,
        champion_name,
        COALESCE(p.picks, 0) AS picks,
        COALESCE(p.wins, 0) AS wins,
        COALESCE(b.bans, 0) AS bans
    FROM picks AS p
    FULL OUTER JOIN bans AS b USING (patch_key, champion_name)
)

SELECT
    m.patch_key,
    d.champion_id,
    m.champion_name,
    g.games,
    m.picks,
    m.wins,
    m.bans,
    -- SAFE_DIVIDE renvoie NULL au lieu de planter sur une division par zero :
    -- un champion banni mais jamais joue n'a pas de taux de victoire (inconnu,
    -- pas 0 %).
    SAFE_DIVIDE(m.wins, m.picks) AS win_rate,
    SAFE_DIVIDE(m.picks, g.games) AS pick_rate,
    SAFE_DIVIDE(m.bans, g.games) AS ban_rate,
    SAFE_DIVIDE(m.picks + m.bans, g.games) AS presence

FROM meta AS m
INNER JOIN games AS g USING (patch_key)
-- LEFT JOIN : un champion pro sans ligne Data Dragon reste visible, avec un
-- champion_id vide. C'est le test not_null ci-contre qui le signale.
LEFT JOIN {{ ref('stg_ddragon__champions') }} AS d
    ON m.patch_key = d.patch_key AND m.champion_name = d.champion_name
