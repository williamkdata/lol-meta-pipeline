-- La famille du build de chaque joueur du ladder (decision 3 de William,
-- 05/11/2026 : autant de choix que de familles viables). On regarde la famille
-- PRINCIPALE (seed item_families, relue par William le 06/11) des 3 premiers
-- objets termines, ou de ceux qu'il a si la partie s'est finie avant (47 % des
-- joueurs du 16.22 n'ont pas 3 objets termines en fin de partie).
--
-- Le vote, dans cet ordre :
--   1. majorite : au moins 2 objets de la meme famille -> cette famille ;
--   2. hybride : pas de majorite, et des familles AD et AP melangees ;
--   3. premier objet : sinon, la famille du premier objet (l'objet central).
-- classification_rule garde la regle qui a joue, pour pouvoir la verifier.
--
-- Essayee puis retiree le 06/11/2026 (decision de William) : une regle "objet
-- signature" (Manamune -> build AD mana, pour Ezreal). Elle reclassait aussi
-- les builds letalite avec Manamune (Jayce 128 parties, Varus 45) et des
-- Kassadin AP. Ezreal reste donc "combattant" (Trinite, Faim insatiable).

WITH trois_premiers AS (
    SELECT
        a.match_id,
        a.participant_id,
        a.purchase_rank,
        a.item_id,
        -- Un objet absent de la seed reste visible au lieu d'etre perdu (le test
        -- assert_completed_items_have_a_family previent aussi).
        COALESCE(f.family, 'sans_famille') AS family
    FROM {{ ref('int_ladder__completed_purchases') }} AS a
    LEFT JOIN {{ ref('item_families') }} AS f
        ON a.item_id = f.item_id
    WHERE a.purchase_rank <= 3
),

par_joueur AS (
    SELECT
        match_id,
        participant_id,
        ARRAY_AGG(item_id ORDER BY purchase_rank) AS item_ids,
        ARRAY_AGG(family ORDER BY purchase_rank) AS families
    FROM trois_premiers
    GROUP BY match_id, participant_id
),

vote AS (
    SELECT
        match_id,
        participant_id,
        item_ids,
        families,
        ARRAY_LENGTH(families) AS items_counted,
        -- Sur 3 objets au plus, une seule famille peut en avoir 2 ou plus.
        (
            SELECT fam
            FROM UNNEST(families) AS fam
            GROUP BY fam
            HAVING COUNT(*) >= 2
        ) AS majority_family,
        -- Les cotes AD et AP. Tank et support ne sont d'aucun
        -- cote : un combattant avec un objet de tank n'est pas hybride.
        EXISTS (
            SELECT 1 FROM UNNEST(families) AS fam
            WHERE fam IN ('critique', 'letalite', 'on_hit', 'combattant', 'ad_mana')
        ) AS has_ad_side,
        EXISTS (
            SELECT 1 FROM UNNEST(families) AS fam
            WHERE fam IN ('ap', 'enchanteur')
        ) AS has_ap_side
    FROM par_joueur
)

SELECT
    p.patch_key,
    p.team_position,
    p.champion_id,
    p.match_id,
    p.participant_id,
    p.is_win,
    v.item_ids,
    v.families,
    v.items_counted,
    CASE
        WHEN v.majority_family IS NOT NULL THEN v.majority_family
        WHEN v.has_ad_side AND v.has_ap_side THEN 'hybride'
        ELSE v.families[OFFSET(0)]
    END AS build_family,
    CASE
        WHEN v.majority_family IS NOT NULL THEN 'majorite'
        WHEN v.has_ad_side AND v.has_ap_side THEN 'hybride'
        ELSE 'premier_objet'
    END AS classification_rule
FROM {{ ref('stg_ladder__participants') }} AS p
INNER JOIN vote AS v
    ON p.match_id = v.match_id AND p.participant_id = v.participant_id
