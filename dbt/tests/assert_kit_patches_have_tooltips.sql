-- Chaque patch qui a des formules de sorts a aussi des infobulles (20/11/2026).
--
-- Les infobulles disent quelle formule est un bouclier ou un soin. Sans elles,
-- la valeur survie du moteur theorique est vide, et toute la survie passe dans
-- les degats EN SILENCE : vu sur l'apercu du PBE du 16.24 (pbe.py ne chargeait
-- pas le texte du jeu), 77 predictions fausses (Shen +1 402 %), avec un build
-- pourtant vert. Une erreur, pas un avertissement : en prod, le run echoue et
-- l'alerte part, au lieu de publier des predictions fausses.
--
-- Mesure du 20/11/2026 en prod : 23 patches sur 23, et 3 967 champions x
-- patch sur 3 967, ont leurs infobulles.

SELECT f.patch_key
FROM (SELECT DISTINCT patch_key FROM {{ ref('stg_kit__parts') }}) AS f
LEFT JOIN (SELECT DISTINCT patch_key FROM {{ ref('stg_kit__spell_tooltips') }}) AS i
    ON f.patch_key = i.patch_key
WHERE i.patch_key IS NULL
