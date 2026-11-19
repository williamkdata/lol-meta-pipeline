-- Bulletin de patch, mesure 3 (1/2) : ce que le moteur THEORIQUE predit pour
-- un patch, avant que les joueurs reagissent. Une ligne par patch et par
-- « sujet » qui change :
--   - objet : Riot a change ses stats ou son prix (Bloodmail : 30 -> 40 d'AD
--     au 16.22). Prediction : il vaut plus (hausse) ou moins (baisse) pour les
--     champions concernes, donc il devrait etre plus ou moins achete ;
--   - champion : les ratios de son kit ont change, ses objets (inchanges)
--     valent plus ou moins pour lui. Prediction : il est renforce ou affaibli.
-- Les deux causes sont SEPAREES : un champion dont le kit a change est ecarte
-- des concernes d'un objet change (sinon on ne saurait pas laquelle des deux
-- explique l'ecart).
--
-- Deux valeurs (19/11/2026, value_kind) : degats et survie (boucliers, soins,
-- vitesse). Pour un champion, sa prediction suit les degats s'ils bougent,
-- sinon la survie : un changement qui ne touche que son bouclier (Galio au
-- 16.23) est predit, sans melanger deux mesures differentes. Pour un objet,
-- seuls les degats comptent (comme avant). Un kit qui change d'un cote OU de
-- l'autre ecarte le champion des concernes d'un objet change.
--
-- Calculable des la sortie d'un patch (il ne faut que les fichiers du jeu) :
-- c'est une prediction, pas une observation. mart_patch_experiments la
-- confronte ensuite aux parties jouees.
-- Limites : les passifs des objets et les temps de recharge sont ignores par
-- le moteur (version A) ; un changement qu'il ne voit pas n'est pas predit.

WITH patches AS (
    -- Le patch precedent = le precedent dans la liste des patches calcules
    -- (les cles ne se suivent pas de 1 en 1 : 1601 vient apres 1524).
    SELECT
        patch_key,
        LAG(patch_key) OVER (ORDER BY patch_key) AS previous_patch_key
    FROM (SELECT DISTINCT patch_key FROM {{ ref('mart_item_theory_value') }})
),

paires AS (
    SELECT patch_key, previous_patch_key
    FROM patches
    WHERE previous_patch_key IS NOT NULL
),

stats_nouvelles AS (
    SELECT pp.patch_key, s.item_id, s.stat, s.value
    FROM paires AS pp
    INNER JOIN {{ ref('stg_item_stats') }} AS s
        ON s.patch_key = pp.patch_key
),

stats_anciennes AS (
    SELECT pp.patch_key, s.item_id, s.stat, s.value
    FROM paires AS pp
    INNER JOIN {{ ref('stg_item_stats') }} AS s
        ON s.patch_key = pp.previous_patch_key
),

objets_changes AS (
    -- Une stat changee, ajoutee ou retiree...
    SELECT DISTINCT
        COALESCE(n.patch_key, a.patch_key) AS patch_key,
        COALESCE(n.item_id, a.item_id) AS item_id
    FROM stats_nouvelles AS n
    FULL OUTER JOIN stats_anciennes AS a
        ON n.patch_key = a.patch_key AND n.item_id = a.item_id AND n.stat = a.stat
    WHERE n.value IS DISTINCT FROM a.value

    UNION DISTINCT

    -- ... ou un prix change.
    SELECT pp.patch_key, n.item_id
    FROM paires AS pp
    INNER JOIN {{ ref('stg_ddragon__items') }} AS n
        ON n.patch_key = pp.patch_key
    INNER JOIN {{ ref('stg_ddragon__items') }} AS a
        ON a.patch_key = pp.previous_patch_key AND a.item_id = n.item_id
    WHERE n.gold_total != a.gold_total
),

ecarts AS (
    -- Chaque valeur theorique qui bouge (pour 1 000 pieces d'or : un prix
    -- plus cher fait baisser la valeur), avec sa cause.
    SELECT
        pp.patch_key,
        pp.previous_patch_key,
        n.champion_id,
        n.value_kind,
        n.item_id,
        SAFE_DIVIDE(
            n.theory_value_per_1000_gold - a.theory_value_per_1000_gold,
            a.theory_value_per_1000_gold
        ) AS change_ratio,
        oc.item_id IS NOT NULL AS is_item_change
    FROM paires AS pp
    INNER JOIN {{ ref('mart_item_theory_value') }} AS n
        ON n.patch_key = pp.patch_key
    INNER JOIN {{ ref('mart_item_theory_value') }} AS a
        ON a.patch_key = pp.previous_patch_key
        AND a.champion_id = n.champion_id
        AND a.value_kind = n.value_kind
        AND a.item_id = n.item_id
    LEFT JOIN objets_changes AS oc
        ON oc.patch_key = pp.patch_key AND oc.item_id = n.item_id
    WHERE n.theory_value_per_1000_gold != a.theory_value_per_1000_gold
),

kits_changes AS (
    -- Un champion dont un objet INCHANGE vaut plus ou moins, en degats OU en
    -- survie : son kit a change. value_kind = la valeur qui portera sa
    -- prediction : les degats s'ils bougent, sinon la survie.
    SELECT
        patch_key,
        champion_id,
        IF(LOGICAL_OR(value_kind = 'degats'), 'degats', 'survie') AS value_kind
    FROM ecarts
    WHERE NOT is_item_change
    GROUP BY patch_key, champion_id
),

predictions AS (
    SELECT
        e.patch_key,
        e.previous_patch_key,
        'objet' AS subject_type,
        e.item_id AS subject_id,
        'degats' AS value_kind,
        AVG(e.change_ratio) AS change_ratio,
        ARRAY_AGG(e.champion_id ORDER BY e.champion_id) AS concerned_champion_ids
    FROM ecarts AS e
    LEFT JOIN kits_changes AS k
        ON k.patch_key = e.patch_key AND k.champion_id = e.champion_id
    WHERE e.is_item_change
        AND e.value_kind = 'degats'
        AND k.champion_id IS NULL
    GROUP BY e.patch_key, e.previous_patch_key, e.item_id

    UNION ALL

    SELECT
        e.patch_key,
        e.previous_patch_key,
        'champion' AS subject_type,
        e.champion_id AS subject_id,
        k.value_kind,
        AVG(e.change_ratio) AS change_ratio,
        [e.champion_id] AS concerned_champion_ids
    FROM ecarts AS e
    -- Seulement les ecarts de la valeur retenue pour ce champion.
    INNER JOIN kits_changes AS k
        ON k.patch_key = e.patch_key
        AND k.champion_id = e.champion_id
        AND k.value_kind = e.value_kind
    WHERE NOT e.is_item_change
    GROUP BY e.patch_key, e.previous_patch_key, e.champion_id, k.value_kind
)

SELECT
    p.patch_key,
    p.previous_patch_key,
    p.subject_type,
    p.subject_id,
    COALESCE(i.item_name, c.champion_name) AS subject_name,
    IF(p.change_ratio > 0, 'hausse', 'baisse') AS predicted_direction,
    ROUND(p.change_ratio * 100, 1) AS theory_change_pct,
    ARRAY_LENGTH(p.concerned_champion_ids) AS concerned_champions,
    p.concerned_champion_ids,
    -- La valeur qui porte la prediction : degats ou survie.
    p.value_kind
FROM predictions AS p
LEFT JOIN {{ ref('stg_ddragon__items') }} AS i
    ON p.subject_type = 'objet' AND i.patch_key = p.patch_key AND i.item_id = p.subject_id
LEFT JOIN {{ ref('stg_ddragon__champions') }} AS c
    ON p.subject_type = 'champion' AND c.patch_key = p.patch_key AND c.champion_id = p.subject_id
-- Des ecarts qui se compensent exactement ne predisent rien.
WHERE p.change_ratio != 0
