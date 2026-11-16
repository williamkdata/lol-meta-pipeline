-- La fidelite des builds, premiere mesure du bulletin de patch (demande de
-- William du 06/11/2026 : prouver les builds par les chiffres, pas par l'avis).
-- Les objets que nous placons en tete d'un build (les 3 premiers objets
-- termines, achats annules exclus) sont-ils vraiment dans l'inventaire du
-- joueur en fin de partie ? Deux sources de Riot independantes : les achats
-- horodates de la timeline, et l'inventaire du resume de la partie.
--
-- Un objet qui se TRANSFORME (Manamune -> Muramana) n'est plus dans
-- l'inventaire sous son nom d'achat : il compte comme retrouve s'il y est sous
-- sa forme transformee (seed item_transformations). Les vrais absents sont
-- surtout des objets revendus.
--
-- Ce que la mesure prouve : les objets du build sont les bons. Ce qu'elle ne
-- prouve pas : l'ORDRE, qui vient directement de l'horodatage de Riot.

WITH controles AS (
    SELECT
        p.patch_key,
        a.item_id,
        CASE
            WHEN a.item_id IN UNNEST(p.item_ids) THEN 'trouve'
            WHEN t.transformed_item_id IN UNNEST(p.item_ids) THEN 'transforme'
            ELSE 'absent'
        END AS outcome
    FROM {{ ref('int_ladder__completed_purchases') }} AS a
    INNER JOIN {{ ref('stg_ladder__participants') }} AS p
        ON a.match_id = p.match_id AND a.participant_id = p.participant_id
    LEFT JOIN {{ ref('item_transformations') }} AS t
        ON a.item_id = t.item_id
    WHERE a.purchase_rank <= 3
),

absents AS (
    -- Les objets absents les plus frequents de chaque patch : si l'alerte se
    -- declenche, ils disent ou chercher (une transformation nouvelle ?).
    SELECT
        c.patch_key,
        STRING_AGG(
            FORMAT('%s (%d)', COALESCE(i.item_name, CAST(c.item_id AS STRING)), c.n),
            ', '
            ORDER BY c.n DESC, c.item_id
            LIMIT 3
        ) AS most_missing_items
    FROM (
        SELECT patch_key, item_id, COUNT(*) AS n
        FROM controles
        WHERE outcome = 'absent'
        GROUP BY patch_key, item_id
    ) AS c
    LEFT JOIN {{ ref('stg_ddragon__items') }} AS i
        ON c.patch_key = i.patch_key AND c.item_id = i.item_id
    GROUP BY c.patch_key
),

par_patch AS (
    SELECT
        patch_key,
        COUNT(*) AS items_checked,
        COUNTIF(outcome = 'trouve') AS items_found,
        COUNTIF(outcome = 'transforme') AS items_transformed,
        COUNTIF(outcome = 'absent') AS items_missing
    FROM controles
    GROUP BY patch_key
)

SELECT
    p.patch_key,
    p.items_checked,
    p.items_found,
    p.items_transformed,
    p.items_missing,
    ROUND((p.items_found + p.items_transformed) / p.items_checked, 4) AS fidelity_rate,
    a.most_missing_items
FROM par_patch AS p
LEFT JOIN absents AS a
    ON p.patch_key = a.patch_key
