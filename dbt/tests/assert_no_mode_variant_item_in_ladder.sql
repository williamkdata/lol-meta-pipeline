-- Les variantes d'autres modes (identifiant >= mode_variant_min_item_id) sont
-- ecartees des objets termines (stg_ddragon__items). Ce choix repose sur une
-- mesure : aucune n'apparait dans les achats du ladder (0 sur 403 603 le
-- 05/11/2026). Si Riot donne un jour un identifiant a 6 chiffres a un vrai
-- objet de la Faille, ce test le signale au lieu de le perdre en silence.
--
-- Un test singulier passe quand cette requete ne renvoie AUCUNE ligne.

SELECT
    match_id,
    participant_id,
    item_id,
    timestamp_ms
FROM {{ ref('stg_ladder__events') }}
WHERE event_type = 'ITEM_PURCHASED'
    AND item_id >= {{ var('mode_variant_min_item_id') }}
