-- Les nombres des infobulles des sorts (texte du jeu), chacun avec la balise la
-- plus proche qui l'entoure : le type de degats (physicalDamage, magicDamage,
-- trueDamage), ou bouclier, soin, vitesse... Une ligne par patch, champion,
-- touche, nom et balise. tag vide : le nombre n'est dans aucune balise.
--
-- Premier chargement verifie le 17/11/2026 : 767 303 lignes, 22 patches,
-- 0 doublon.

SELECT
    -- "16.4" -> 1604 : la meme cle que toutes les autres sources.
    CAST(SPLIT(patch, '.')[OFFSET(0)] AS INT64) * 100
    + CAST(SPLIT(patch, '.')[OFFSET(1)] AS INT64) AS patch_key,
    patch,
    champion_id,
    champion_code,
    slot,
    spell_name,
    name,
    tag,
    -- Les mots qui suivent le nombre ("% max Health magic damage") : ce qu'il
    -- est. Ajoutes le 18/11/2026 (table rechargee le jour meme).
    following_text

-- En mode apercu (cible pbe), les infobulles du PBE s'ajoutent comme un patch
-- ordinaire (20/11/2026) : la valeur survie du moteur theorique en a besoin.
FROM {{ source_avec_apercu_pbe('kit_spell_tooltips', 'pbe_kit_spell_tooltips') }}

-- Les entrees speciales Jade_ du 16.15 : meme filtre que pour les champions.
WHERE STRPOS(champion_code, '_') = 0
