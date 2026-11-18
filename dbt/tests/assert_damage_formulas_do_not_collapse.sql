-- Le nombre de formules de degats d'un patch ne doit pas chuter de plus de
-- 10 % par rapport au patch precedent.
--
-- Pourquoi : le type de degats vient des balises des infobulles
-- (<magicDamage>...). Si Riot change le format du texte (une balise renommee
-- a la nouvelle saison), les formules de degats disparaitraient en silence.
-- Mesure du 17/11/2026 sur les 22 patches de la saison : de 885 a 912 lignes
-- par patch, jamais plus de 1 % d'ecart d'un patch au suivant.
-- Avertissement : une vraie baisse (champions retires) reste possible.

{{ config(severity='warn') }}

WITH par_patch AS (
    SELECT patch_key, COUNT(*) AS formules
    FROM {{ ref('int_kit__damage_formulas') }}
    GROUP BY patch_key
),

avec_precedent AS (
    SELECT
        patch_key,
        formules,
        LAG(formules) OVER (ORDER BY patch_key) AS formules_avant
    FROM par_patch
)

SELECT patch_key, formules, formules_avant
FROM avec_precedent
WHERE formules < 0.9 * formules_avant
