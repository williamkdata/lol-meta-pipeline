-- Une stat presente dans la fiche d'un champion a un patch ne doit pas
-- disparaitre au patch suivant.
--
-- Pourquoi : si Riot renomme un champ (comme au 16.5), le nouveau nom est
-- inconnu de la seed champion_record_fields et la ligne disparait du staging.
-- Pour une stat sans valeur par defaut, le not_null du modele
-- int_champions__base_stats echoue. Mais pour une stat AVEC valeur par defaut
-- (un gain par niveau...), la valeur par defaut boucherait le trou en silence :
-- c'est ce test qui le voit.
--
-- Mesure du 16/11/2026 sur 22 patches : 0 stat disparue, 0 stat apparue.
-- Avertissement seulement : une disparition peut etre un vrai choix de Riot.
-- Elle demande un regard humain avant d'utiliser le patch.

{{ config(severity='warn') }}

WITH presences AS (
    SELECT patch_key, champion_id, champion_code, stat
    FROM {{ ref('stg_kit__champion_record') }}
),

-- Pour chaque champion et chaque patch, son patch precedent.
champion_patches AS (
    SELECT
        patch_key,
        champion_id,
        LAG(patch_key) OVER (
            PARTITION BY champion_id ORDER BY patch_key
        ) AS previous_patch_key
    FROM (SELECT DISTINCT patch_key, champion_id FROM presences)
)

-- Les stats du patch precedent qu'on ne retrouve pas a ce patch.
SELECT
    cp.patch_key,
    avant.champion_code,
    avant.stat
FROM champion_patches AS cp
INNER JOIN presences AS avant
    ON avant.champion_id = cp.champion_id
    AND avant.patch_key = cp.previous_patch_key
LEFT JOIN presences AS apres
    ON apres.champion_id = cp.champion_id
    AND apres.patch_key = cp.patch_key
    AND apres.stat = avant.stat
WHERE apres.stat IS NULL
