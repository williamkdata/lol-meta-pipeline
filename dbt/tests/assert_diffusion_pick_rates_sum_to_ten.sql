-- Une partie compte 10 picks, en pro comme sur la ladder : les taux de pick
-- d'un patch couvert font donc 10 au total. Si la somme s'en ecarte, des picks
-- se sont perdus en route (un champion absent de la grille Data Dragon, une
-- jointure ratee). Tolerance 0,01 : les taux sont arrondis a 4 decimales.
--
-- Un test singulier passe quand cette requete ne renvoie AUCUNE ligne.

SELECT
    patch_key,
    SUM(pro_pick_rate) AS somme_pro,
    SUM(ladder_pick_rate) AS somme_ladder
FROM {{ ref('mart_meta_diffusion') }}
GROUP BY patch_key
HAVING (COUNT(pro_matches) > 0 AND ABS(SUM(pro_pick_rate) - 10) > 0.01)
    OR (COUNT(ladder_matches) > 0 AND ABS(SUM(ladder_pick_rate) - 10) > 0.01)
