-- Le prix en or de chaque stat, a chaque patch : la methode classique de la
-- « rentabilite en or ». La boutique vend des objets de base qui ne donnent
-- qu'une stat ; leur prix fixe la valeur d'un point de cette stat. Exemple :
-- l'Epee longue coute 350 or pour 10 d'AD -> 1 point d'AD vaut 35 or.
--
-- Regle : pour chaque stat, l'objet de BASE (fabrique a partir de rien) le
-- moins cher qui ne donne QUE cette stat. Les plus gros composants (B. F.
-- Sword) sont souvent un peu moins chers par point ; la convention retient le
-- plus petit, celui qu'on achete au premier retour a la base.
-- Recalcule a chaque patch : si Riot change le prix de l'Epee longue, la
-- valeur de l'AD change.
--
-- Les stats sans objet de base (vol de vie, ténacité, penetrations, % de
-- vitesse de deplacement...) n'ont pas de prix : elles ne sont pas
-- valorisees (limite connue du moteur theorique, version B).

WITH une_seule_stat AS (
    SELECT patch_key, item_id
    FROM {{ ref('stg_item_stats') }}
    GROUP BY patch_key, item_id
    HAVING COUNT(*) = 1
),

candidats AS (
    SELECT
        i.patch_key,
        s.stat,
        i.item_id,
        i.item_name,
        i.gold_total,
        s.value
    FROM {{ ref('stg_ddragon__items') }} AS i
    INNER JOIN une_seule_stat AS u
        ON i.patch_key = u.patch_key AND i.item_id = u.item_id
    INNER JOIN {{ ref('stg_item_stats') }} AS s
        ON i.patch_key = s.patch_key AND i.item_id = s.item_id
    WHERE i.purchasable
        AND i.on_summoners_rift
        AND ARRAY_LENGTH(i.builds_from) = 0
        -- Les variantes d'autres modes (identifiants a 6 chiffres).
        AND i.item_id < {{ var('mode_variant_min_item_id') }}
        AND i.gold_total > 0
        AND s.value > 0
)

SELECT
    patch_key,
    stat,
    item_id AS reference_item_id,
    item_name AS reference_item_name,
    gold_total AS reference_item_gold,
    value AS reference_item_value,
    -- La valeur est arrondie AVANT la division : 0,15 est stocke
    -- 0,15000000596 dans les fichiers du jeu (nombre a virgule), ce qui
    -- donnerait 3 999,9998 or au lieu de 4 000 pour le critique.
    ROUND(gold_total / ROUND(value, 4), 4) AS gold_per_unit
FROM candidats
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY patch_key, stat
    ORDER BY gold_total, item_id
) = 1
