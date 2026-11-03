-- La diffusion de la meta, patch par patch : pour chaque champion, sa place
-- en pro et sur la ladder haut elo EUW, cote a cote.
--
-- Les deux taux de pick mesurent la meme chose : la part des parties ou le
-- champion est joue. Une partie compte 10 picks des deux cotes, donc les taux
-- d'un patch font 10 au total (verifie par un test).
--
-- Le COEUR DE LA META d'un patch : le plus petit groupe de champions qui fait
-- la moitie des picks, du plus joue au moins joue. Meme definition des deux
-- cotes, sans seuil arbitraire.

WITH grille AS (
    -- Tous les vrais champions de chaque patch. Un champion jamais joue a un
    -- taux de pick de 0, pas un taux inconnu.
    SELECT patch_key, champion_id, champion_name
    FROM {{ ref('stg_ddragon__champions') }}
),

patches_pro AS (
    -- Le nombre de matchs vient de la MEME table que les picks : un taux prend
    -- numerateur et denominateur dans la meme source. (Le 03/11, en dev, les
    -- matchs pris dans la vue stg_oe__teams, a jour, et les picks dans la table
    -- de la veille donnaient 8,70 picks par match au lieu de 10.)
    SELECT patch_key, MAX(games) AS pro_matches
    FROM {{ ref('mart_pro_champion_patch') }}
    GROUP BY patch_key
),

picks_pro AS (
    SELECT patch_key, champion_id, picks
    FROM {{ ref('mart_pro_champion_patch') }}
    WHERE champion_id IS NOT NULL
),

patches_ladder AS (
    SELECT patch_key, COUNT(DISTINCT match_id) AS ladder_matches
    FROM {{ ref('stg_ladder__participants') }}
    GROUP BY patch_key
),

picks_ladder AS (
    SELECT patch_key, champion_id, COUNT(*) AS picks
    FROM {{ ref('stg_ladder__participants') }}
    GROUP BY patch_key, champion_id
),

taux AS (
    SELECT
        g.patch_key,
        g.champion_id,
        g.champion_name,
        pp.pro_matches,
        -- Patch sans match pro : NULL (inconnu). Patch couvert mais champion
        -- jamais pris : 0. SAFE_DIVIDE(x, NULL) donne NULL.
        SAFE_DIVIDE(COALESCE(kp.picks, 0), pp.pro_matches) AS pro_pick_rate,
        pl.ladder_matches,
        SAFE_DIVIDE(COALESCE(kl.picks, 0), pl.ladder_matches) AS ladder_pick_rate
    FROM grille AS g
    LEFT JOIN patches_pro AS pp
        ON g.patch_key = pp.patch_key
    LEFT JOIN picks_pro AS kp
        ON g.patch_key = kp.patch_key AND g.champion_id = kp.champion_id
    LEFT JOIN patches_ladder AS pl
        ON g.patch_key = pl.patch_key
    LEFT JOIN picks_ladder AS kl
        ON g.patch_key = kl.patch_key AND g.champion_id = kl.champion_id
),

parts_cumulees AS (
    -- La part des picks du patch faite par les champions PLUS joues que celui-ci
    -- (10 picks par partie : part = somme des taux / 10). ROWS BETWEEN ... AND
    -- 1 PRECEDING : toutes les lignes avant celle-ci, sans elle.
    SELECT
        *,
        SUM(pro_pick_rate) OVER (
            PARTITION BY patch_key
            ORDER BY pro_pick_rate DESC, champion_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) / 10 AS pro_share_before,
        SUM(ladder_pick_rate) OVER (
            PARTITION BY patch_key
            ORDER BY ladder_pick_rate DESC, champion_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) / 10 AS ladder_share_before
    FROM taux
)

SELECT
    patch_key,
    -- Le rang du patch dans la saison (1, 2, 3...) : les ecarts en patches se
    -- calculent sur ce rang, pas sur patch_key (1601 - 1524 ne vaut pas 1).
    DENSE_RANK() OVER (ORDER BY patch_key) AS patch_index,
    champion_id,
    champion_name,
    pro_matches,
    ROUND(pro_pick_rate, 4) AS pro_pick_rate,
    -- Dans le coeur si les champions plus joues font moins de la moitie des
    -- picks : il fait partie de ceux qui atteignent 50 %. NULL si non couvert.
    IF(
        pro_matches IS NULL,
        NULL,
        pro_pick_rate > 0 AND COALESCE(pro_share_before, 0) < 0.5
    ) AS in_pro_core,
    ROUND(
        pro_pick_rate - LAG(pro_pick_rate) OVER (PARTITION BY champion_id ORDER BY patch_key),
        4
    ) AS pro_pick_rate_change,
    ladder_matches,
    ROUND(ladder_pick_rate, 4) AS ladder_pick_rate,
    IF(
        ladder_matches IS NULL,
        NULL,
        ladder_pick_rate > 0 AND COALESCE(ladder_share_before, 0) < 0.5
    ) AS in_ladder_core,
    ROUND(
        ladder_pick_rate
        - LAG(ladder_pick_rate) OVER (PARTITION BY champion_id ORDER BY patch_key),
        4
    ) AS ladder_pick_rate_change

FROM parts_cumulees
