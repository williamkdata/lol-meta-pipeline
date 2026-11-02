-- Une partie classee, c'est 10 joueurs : 5 par equipe. Une partie qui n'a pas
-- exactement 5 joueurs dans chacune de ses 2 equipes a ete mal collectee ou
-- mal dedoublonnee, et fausserait les matchups.
--
-- Un test singulier passe quand cette requete ne renvoie AUCUNE ligne.

SELECT
    match_id,
    COUNT(*) AS joueurs,
    COUNTIF(team_id = 100) AS equipe_bleue,
    COUNTIF(team_id = 200) AS equipe_rouge
FROM {{ ref('stg_ladder__participants') }}
GROUP BY match_id
HAVING COUNT(*) != 10
    OR COUNTIF(team_id = 100) != 5
    OR COUNTIF(team_id = 200) != 5
