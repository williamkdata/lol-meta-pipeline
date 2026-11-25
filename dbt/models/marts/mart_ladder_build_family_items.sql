-- Les objets de chaque famille de builds (25/11/2026) : pour un champion a son
-- poste et par patch, les objets presents dans les 3 premiers objets termines
-- des joueurs de la famille, dans combien de parties, et quelle part des
-- parties de la famille. « hybride » chez Ezreal au 16.23 : Manamune (99 %),
-- Horizon Focus (69 %), Essence Reaver (51 %).
--
-- Precalcule chaque jour par le run : l'assistant (outil builds_du_champion)
-- le lit en quelques Mo au lieu de refaire le calcul de la vue
-- int_ladder__build_families a chaque question (~450 Mo, mesure du 23/11).

WITH objets AS (
    SELECT
        b.patch_key,
        b.team_position,
        b.champion_id,
        b.build_family,
        item_id,
        -- Les joueurs distincts (une partie + un participant) : un objet achete
        -- deux fois parmi les 3 premiers ne compte qu'une fois.
        COUNT(DISTINCT CONCAT(b.match_id, '-', CAST(b.participant_id AS STRING)))
            AS games_with_item
    FROM {{ ref('int_ladder__build_families') }} AS b,
        UNNEST(b.item_ids) AS item_id
    GROUP BY b.patch_key, b.team_position, b.champion_id, b.build_family, item_id
)

SELECT
    o.patch_key,
    o.team_position,
    o.champion_id,
    o.build_family,
    o.item_id,
    -- Un objet absent de la seed garde son numero (visible, pas perdu).
    COALESCE(n.item_name, CAST(o.item_id AS STRING)) AS item_name,
    o.games_with_item,
    f.games AS family_games,
    ROUND(o.games_with_item / f.games, 4) AS share_of_family_games,
    -- 1 = l'objet le plus frequent de la famille ; egalite departagee par le
    -- numero de l'objet (un ordre stable d'un run a l'autre).
    ROW_NUMBER() OVER (
        PARTITION BY o.patch_key, o.team_position, o.champion_id, o.build_family
        ORDER BY o.games_with_item DESC, o.item_id
    ) AS item_rank
FROM objets AS o
INNER JOIN {{ ref('mart_ladder_build_families') }} AS f
    ON o.patch_key = f.patch_key
    AND o.team_position = f.team_position
    AND o.champion_id = f.champion_id
    AND o.build_family = f.build_family
LEFT JOIN {{ ref('item_families') }} AS n
    ON o.item_id = n.item_id
