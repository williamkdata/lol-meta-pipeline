-- Une ligne par joueur et par partie classee du ladder EUW : dedoublonnee,
-- avec la cle de patch commune, sans les parties qui ne disent rien de la
-- meta (remakes, abandons avant 15 minutes).

WITH dedoublonne AS (
    SELECT *
    FROM {{ source('lol_raw_ladder', 'participants') }}
    -- Un lot recharge apres une panne met une partie deux fois dans le brut.
    -- On garde la ligne la plus recente de chaque joueur de chaque partie.
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY match_id, participant_id
        ORDER BY ingested_at DESC
    ) = 1
)

SELECT
    match_id,
    game_start,
    game_duration_s,
    game_version,
    -- "16.21.834.2754" -> 1621 : la meme cle que Data Dragon et Oracle's Elixir.
    CAST(SPLIT(game_version, '.')[OFFSET(0)] AS INT64) * 100
    + CAST(SPLIT(game_version, '.')[OFFSET(1)] AS INT64) AS patch_key,
    participant_id,
    team_id,
    team_position,
    champion_id,
    champion_name,
    win AS is_win,
    kills,
    deaths,
    assists,
    gold_earned,
    damage_to_champions,
    minions_killed + neutral_minions_killed AS cs,
    champ_level,
    item_ids,
    trinket_id,
    summoner_spell_ids,
    primary_style,
    sub_style,
    keystone_id,
    rune_ids,
    stat_shard_ids

FROM dedoublonne
WHERE queue_id = 420
    AND NOT early_surrender
    -- Seuil justifie dans dbt_project.yml (var ladder_min_game_duration_s).
    AND game_duration_s >= {{ var('ladder_min_game_duration_s') }}
