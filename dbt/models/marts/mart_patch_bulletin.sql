-- Le bulletin de patch : une ligne par patch du ladder, qui resume les trois
-- mesures demandees par William le 06/11/2026 (« prouver les builds par les
-- chiffres, pas par l'avis ») :
--   1. fidelite : nos builds decrivent-ils ce que les joueurs possedent ?
--      (mart_ladder_build_fidelity) ;
--   2. duels : le build populaire gagne-t-il plus que ses alternatives ?
--      (mart_ladder_build_duels) ;
--   3. experiences : quand Riot change un objet ou un champion, le ladder
--      bouge-t-il dans le sens predit par le moteur theorique ?
--      (mart_patch_experiments, verdict sur la part d'achat ou de jeu).

WITH duels AS (
    SELECT
        patch_key,
        COUNTIF(level = 'famille') AS family_duels,
        COUNTIF(level = 'famille' AND verdict = 'populaire_confirme') AS family_confirmed,
        COUNTIF(level = 'famille' AND verdict = 'pepite') AS family_gems,
        COUNTIF(level = 'chemin') AS path_duels,
        COUNTIF(level = 'chemin' AND verdict = 'populaire_confirme') AS path_confirmed,
        COUNTIF(level = 'chemin' AND verdict = 'pepite') AS path_gems
    FROM {{ ref('mart_ladder_build_duels') }}
    GROUP BY patch_key
),

experiences AS (
    SELECT
        patch_key,
        COUNT(*) AS experiments,
        COUNTIF(share_verdict IN ('confirme', 'meme_sens')) AS experiments_predicted_direction,
        COUNTIF(share_verdict = 'confirme') AS experiments_confirmed,
        COUNTIF(share_verdict = 'contredit') AS experiments_contradicted
    FROM {{ ref('mart_patch_experiments') }}
    GROUP BY patch_key
)

SELECT
    f.patch_key,
    f.items_checked,
    f.fidelity_rate,
    COALESCE(d.family_duels, 0) AS family_duels,
    COALESCE(d.family_confirmed, 0) AS family_confirmed,
    COALESCE(d.family_gems, 0) AS family_gems,
    COALESCE(d.path_duels, 0) AS path_duels,
    COALESCE(d.path_confirmed, 0) AS path_confirmed,
    COALESCE(d.path_gems, 0) AS path_gems,
    COALESCE(e.experiments, 0) AS experiments,
    COALESCE(e.experiments_predicted_direction, 0) AS experiments_predicted_direction,
    COALESCE(e.experiments_confirmed, 0) AS experiments_confirmed,
    COALESCE(e.experiments_contradicted, 0) AS experiments_contradicted
FROM {{ ref('mart_ladder_build_fidelity') }} AS f
LEFT JOIN duels AS d
    ON f.patch_key = d.patch_key
LEFT JOIN experiences AS e
    ON f.patch_key = e.patch_key
