-- La fiche du champion (fichier du jeu) : une stat par patch, champion et stat,
-- sous un nom stable.
--
-- Le meme chiffre change de nom selon le patch : Riot a renomme les champs au
-- 16.5 (baseHP -> baseHPModifiable), et certains noms arrivent haches
-- ({01262a25}) tant que CommunityDragon ne les a pas decodes. La seed
-- champion_record_fields traduit chaque orthographe connue vers une stat.
--
-- Un champ absent de la seed est ignore ICI (la fiche contient aussi la taille
-- de la zone cliquable, la meute de Naafiri...). Si Riot renomme un champ
-- utile, son nouveau nom sera donc ignore : ce sont les tests du modele
-- suivant (stat obligatoire manquante, stat qui disparait d'un patch a
-- l'autre) qui le rendront bruyant.

SELECT
    -- "16.4" -> 1604 : la meme cle que toutes les autres sources.
    CAST(SPLIT(r.patch, '.')[OFFSET(0)] AS INT64) * 100
    + CAST(SPLIT(r.patch, '.')[OFFSET(1)] AS INT64) AS patch_key,
    r.patch,
    r.champion_id,
    r.champion_code,
    f.stat,
    r.value,
    -- Le nom lu dans le fichier : pour savoir d'ou vient chaque chiffre.
    r.field AS source_field

FROM {{ source('lol_raw', 'kit_champion_record') }} AS r

-- INNER JOIN : seuls les champs connus de la seed passent.
INNER JOIN {{ ref('champion_record_fields') }} AS f
    ON r.field = f.field

-- Les 60 entrees speciales Jade_ du 16.15 : meme filtre que pour les champions.
WHERE STRPOS(r.champion_code, '_') = 0
