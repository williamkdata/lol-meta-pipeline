-- Une photo par joueur et par minute, pour les seules parties gardees par
-- stg_ladder__participants. frame_index = numero de la minute, sauf la
-- derniere frame, prise a la fin de la partie (voir timestamp_ms).

SELECT
    f.match_id,
    f.game_start,
    f.frame_index,
    f.timestamp_ms,
    f.participant_id,
    f.total_gold,
    f.xp,
    f.level,
    f.minions_killed + f.jungle_minions_killed AS cs

FROM {{ source('lol_raw_ladder', 'timeline_frames') }} AS f
WHERE f.match_id IN (
    SELECT DISTINCT match_id FROM {{ ref('stg_ladder__participants') }}
)
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY f.match_id, f.frame_index, f.participant_id
    ORDER BY f.ingested_at DESC
) = 1
