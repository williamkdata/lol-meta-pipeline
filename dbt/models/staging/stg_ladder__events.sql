-- Les evenements utiles des parties gardees par stg_ladder__participants.
-- event_index = rang de l'evenement dans toute la timeline : avec match_id,
-- il identifie chaque evenement (Riot ne leur donne pas d'identifiant).

SELECT
    e.match_id,
    e.game_start,
    e.event_index,
    e.timestamp_ms,
    DIV(e.timestamp_ms, 60000) AS minute,
    e.event_type,
    e.participant_id,
    e.item_id,
    e.before_item_id,
    e.after_item_id,
    e.skill_slot,
    e.killer_id,
    e.victim_id,
    e.assisting_ids,
    e.killer_team_id,
    e.team_id,
    e.monster_type,
    e.monster_sub_type,
    e.building_type,
    e.lane_type,
    e.tower_type

FROM {{ source('lol_raw_ladder', 'timeline_events') }} AS e
WHERE e.match_id IN (
    SELECT DISTINCT match_id FROM {{ ref('stg_ladder__participants') }}
)
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY e.match_id, e.event_index
    ORDER BY e.ingested_at DESC
) = 1
