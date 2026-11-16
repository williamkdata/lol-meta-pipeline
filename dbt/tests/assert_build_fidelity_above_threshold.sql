-- Bulletin de patch, mesure 1 : l'alerte de fidelite des builds. Renvoie les
-- patches ou moins de build_fidelity_min_rate (99 %) des 3 premiers objets
-- termines se retrouvent dans l'inventaire de fin de partie (objets
-- transformes compris). Mesure du 06/11/2026 : 99,84 % au 16.21, 99,79 % au
-- 16.22.
--
-- Une baisse veut dire que nos builds ne decrivent plus ce que les joueurs
-- possedent vraiment. Causes possibles : un objet qui se transforme, nouveau
-- au patch (a ajouter a la seed item_transformations : most_missing_items le
-- nomme), ou un changement de la logique des achats annules.
--
-- Pas d'alerte sous build_fidelity_min_items objets (premier jour d'un patch).
-- Severite warn, comme la couverture des familles : un probleme a corriger,
-- qui ne doit pas bloquer la collecte du jour.

{{ config(severity='warn') }}

SELECT
    patch_key,
    items_checked,
    fidelity_rate,
    most_missing_items
FROM {{ ref('mart_ladder_build_fidelity') }}
WHERE items_checked >= {{ var('build_fidelity_min_items') }}
    AND fidelity_rate < {{ var('build_fidelity_min_rate') }}
