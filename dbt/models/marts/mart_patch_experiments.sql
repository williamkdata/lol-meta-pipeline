-- Bulletin de patch, mesure 3 (2/2) : l'experience naturelle du patch. Les
-- predictions du moteur theorique (mart_patch_predictions), faites sans
-- regarder les parties, confrontees au ladder du patch precedent et du patch
-- nouveau. C'est le juge le plus fort : il teste la CAUSE (Riot a change
-- quelque chose), pas l'effet de troupeau (tout le monde copie tout le monde).
--
-- Deux taux par experience, chacun avec sa fourchette de Wilson :
--   - part (share) :
--       objet    -> parmi les joueurs des champions concernes, la part qui
--                   l'achete dans ses 3 premiers objets termines ;
--       champion -> parmi tous les joueurs du patch, la part qui le joue ;
--   - victoires (win_rate) :
--       objet    -> le taux de victoire quand l'objet est achete ;
--       champion -> le taux de victoire du champion.
-- Le verdict (macro patch_verdict) dit si chaque taux a bouge dans le sens
-- predit, et si c'est prouve (fourchettes separees).
-- Seules les predictions dont les DEUX patches ont des parties de ladder sont
-- testables.

WITH patches_ladder AS (
    SELECT DISTINCT patch_key FROM {{ ref('stg_ladder__participants') }}
),

testables AS (
    SELECT *
    FROM {{ ref('mart_patch_predictions') }}
    WHERE patch_key IN (SELECT patch_key FROM patches_ladder)
        AND previous_patch_key IN (SELECT patch_key FROM patches_ladder)
),

periodes AS (
    -- Chaque experience regardee deux fois : avant (ancien patch) et apres.
    SELECT
        t.patch_key,
        t.subject_type,
        t.subject_id,
        t.concerned_champion_ids,
        periode.observed_patch_key,
        periode.is_new
    FROM testables AS t,
        UNNEST([
            STRUCT(t.previous_patch_key AS observed_patch_key, FALSE AS is_new),
            STRUCT(t.patch_key AS observed_patch_key, TRUE AS is_new)
        ]) AS periode
),

achats AS (
    SELECT DISTINCT match_id, participant_id, item_id
    FROM {{ ref('int_ladder__completed_purchases') }}
    WHERE purchase_rank <= 3
),

observations AS (
    -- Objets : les joueurs des champions concernes ; « touche » = achete.
    SELECT
        pe.patch_key,
        pe.subject_type,
        pe.subject_id,
        pe.is_new,
        COUNT(*) AS population,
        COUNTIF(a.item_id IS NOT NULL) AS hits,
        COUNTIF(a.item_id IS NOT NULL AND p.is_win) AS hit_wins
    FROM periodes AS pe
    CROSS JOIN UNNEST(pe.concerned_champion_ids) AS champion_concerne
    INNER JOIN {{ ref('stg_ladder__participants') }} AS p
        ON p.patch_key = pe.observed_patch_key AND p.champion_id = champion_concerne
    LEFT JOIN achats AS a
        ON a.match_id = p.match_id
        AND a.participant_id = p.participant_id
        AND a.item_id = pe.subject_id
    WHERE pe.subject_type = 'objet'
    GROUP BY pe.patch_key, pe.subject_type, pe.subject_id, pe.is_new

    UNION ALL

    -- Champions : tous les joueurs du patch ; « touche » = joue ce champion.
    SELECT
        pe.patch_key,
        pe.subject_type,
        pe.subject_id,
        pe.is_new,
        COUNT(*) AS population,
        COUNTIF(p.champion_id = pe.subject_id) AS hits,
        COUNTIF(p.champion_id = pe.subject_id AND p.is_win) AS hit_wins
    FROM periodes AS pe
    INNER JOIN {{ ref('stg_ladder__participants') }} AS p
        ON p.patch_key = pe.observed_patch_key
    WHERE pe.subject_type = 'champion'
    GROUP BY pe.patch_key, pe.subject_type, pe.subject_id, pe.is_new
),

avant_apres AS (
    -- Une ligne par experience : l'ancien patch et le nouveau cote a cote.
    -- COALESCE : sans aucun joueur concerne, la periode n'a pas de ligne.
    SELECT
        patch_key,
        subject_type,
        subject_id,
        COALESCE(MAX(IF(NOT is_new, population, NULL)), 0) AS old_population,
        COALESCE(MAX(IF(NOT is_new, hits, NULL)), 0) AS old_hits,
        COALESCE(MAX(IF(NOT is_new, hit_wins, NULL)), 0) AS old_hit_wins,
        COALESCE(MAX(IF(is_new, population, NULL)), 0) AS new_population,
        COALESCE(MAX(IF(is_new, hits, NULL)), 0) AS new_hits,
        COALESCE(MAX(IF(is_new, hit_wins, NULL)), 0) AS new_hit_wins
    FROM observations
    GROUP BY patch_key, subject_type, subject_id
),

taux AS (
    -- Les IF protegent la formule de Wilson d'une division par zero.
    SELECT
        *,
        IF(old_population > 0, old_hits / old_population, NULL) AS old_share,
        IF(old_population > 0, {{ wilson_bound('old_hits', 'old_population', '-') }}, NULL) AS old_share_low,
        IF(old_population > 0, {{ wilson_bound('old_hits', 'old_population', '+') }}, NULL) AS old_share_high,
        IF(new_population > 0, new_hits / new_population, NULL) AS new_share,
        IF(new_population > 0, {{ wilson_bound('new_hits', 'new_population', '-') }}, NULL) AS new_share_low,
        IF(new_population > 0, {{ wilson_bound('new_hits', 'new_population', '+') }}, NULL) AS new_share_high,
        IF(old_hits > 0, old_hit_wins / old_hits, NULL) AS old_win_rate,
        IF(old_hits > 0, {{ wilson_bound('old_hit_wins', 'old_hits', '-') }}, NULL) AS old_win_rate_low,
        IF(old_hits > 0, {{ wilson_bound('old_hit_wins', 'old_hits', '+') }}, NULL) AS old_win_rate_high,
        IF(new_hits > 0, new_hit_wins / new_hits, NULL) AS new_win_rate,
        IF(new_hits > 0, {{ wilson_bound('new_hit_wins', 'new_hits', '-') }}, NULL) AS new_win_rate_low,
        IF(new_hits > 0, {{ wilson_bound('new_hit_wins', 'new_hits', '+') }}, NULL) AS new_win_rate_high
    FROM avant_apres
)

SELECT
    t.patch_key,
    p.previous_patch_key,
    t.subject_type,
    t.subject_id,
    p.subject_name,
    p.predicted_direction,
    p.theory_change_pct,
    p.concerned_champions,
    t.old_population,
    t.old_hits,
    t.old_hit_wins,
    t.new_population,
    t.new_hits,
    t.new_hit_wins,
    ROUND(t.old_share, 4) AS old_share,
    ROUND(t.old_share_low, 4) AS old_share_low,
    ROUND(t.old_share_high, 4) AS old_share_high,
    ROUND(t.new_share, 4) AS new_share,
    ROUND(t.new_share_low, 4) AS new_share_low,
    ROUND(t.new_share_high, 4) AS new_share_high,
    {{ patch_verdict('p.predicted_direction', 't.old_share', 't.old_share_low', 't.old_share_high',
                     't.new_share', 't.new_share_low', 't.new_share_high') }} AS share_verdict,
    ROUND(t.old_win_rate, 4) AS old_win_rate,
    ROUND(t.new_win_rate, 4) AS new_win_rate,
    {{ patch_verdict('p.predicted_direction', 't.old_win_rate', 't.old_win_rate_low', 't.old_win_rate_high',
                     't.new_win_rate', 't.new_win_rate_low', 't.new_win_rate_high') }} AS win_verdict
FROM taux AS t
INNER JOIN testables AS p
    ON p.patch_key = t.patch_key
    AND p.subject_type = t.subject_type
    AND p.subject_id = t.subject_id
