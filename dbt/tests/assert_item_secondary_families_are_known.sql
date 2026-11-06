-- Les familles secondaires de la seed item_families sont du texte libre separe
-- par "|" : une faute de frappe ("on-hit" au lieu de "on_hit") passerait sans
-- bruit. Chaque famille secondaire doit etre une famille connue, ou "hybride"
-- (objet des builds AD + AP, notes de William du 06/11/2026), et differente de
-- la famille principale.
--
-- Un test singulier passe quand cette requete ne renvoie AUCUNE ligne.

SELECT
    f.item_id,
    f.family,
    secondaire
FROM {{ ref('item_families') }} AS f,
    UNNEST(SPLIT(f.secondary_families, '|')) AS secondaire
WHERE f.secondary_families IS NOT NULL
    AND f.secondary_families != ''
    AND (
        secondaire NOT IN (
            'critique', 'letalite', 'on_hit', 'ap', 'combattant', 'tank',
            'enchanteur', 'support', 'ad_mana', 'hybride'
        )
        OR secondaire = f.family
    )
