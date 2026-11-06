-- Chaque objet termine d'un patch joue en ladder doit avoir une famille dans
-- la seed item_families (relue par William le 06/11/2026). Au prochain patch,
-- un objet nouveau ou renumerote fait echouer ce test : il faut alors lui
-- donner une famille (et la faire relire).
--
-- Severite warn : un objet sans famille ne doit pas bloquer toute la chaine du
-- jour (collecte, autres marts) ; il ressort dans le bilan quotidien de dbt,
-- relu a chaque run.
--
-- Un test singulier passe quand cette requete ne renvoie AUCUNE ligne.

{{ config(severity='warn') }}

SELECT
    i.patch_key,
    i.item_id,
    i.item_name
FROM {{ ref('stg_ddragon__items') }} AS i
LEFT JOIN {{ ref('item_families') }} AS f
    ON i.item_id = f.item_id
WHERE i.is_completed
    AND f.item_id IS NULL
    AND i.patch_key IN (
        SELECT DISTINCT patch_key FROM {{ ref('stg_ladder__participants') }}
    )
