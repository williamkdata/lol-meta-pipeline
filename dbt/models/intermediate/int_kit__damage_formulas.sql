-- Les formules de sorts qui sont des DEGATS, avec leur type (physique,
-- magique, brut), d'apres la balise de l'infobulle qui les cite.
--
-- Une ligne par patch, champion, touche, formule et type : une meme formule
-- peut avoir deux types (Ahri Q : magique a l'aller, brut au retour).
-- Verifie le 16/11/2026 : meme type que Data Dragon pour 1 028 formules sur
-- 1 028 ; en partie (recapitulatifs de mort), 87 % des sorts infligent
-- exactement ces types, le reste vient d'effets (passifs, objets).
--
-- Une formule absente de l'infobulle, ou citee hors d'une balise de degats
-- (bouclier, soin, duree...), n'est pas ici.
--
-- Mesure du 17/11/2026 : de 885 a 912 lignes par patch (911 au 16.22).

SELECT
    f.patch_key,
    f.patch,
    f.champion_id,
    f.champion_code,
    f.slot,
    f.spell_name,
    f.calc_name,
    CASE t.tag
        WHEN 'physicalDamage' THEN 'physical'
        WHEN 'magicDamage' THEN 'magic'
        WHEN 'trueDamage' THEN 'true'
    END AS damage_type,

    -- Ce que la valeur multiplie. Une formule affichee en pourcentage
    -- (mDisplayAsPercent) donne une fraction (0,09 = 9 %) : de QUOI ? Les mots
    -- qui suivent le nombre dans l'infobulle le disent. L'ordre des WHEN
    -- compte : "missing health" avant "max health". Mesure du 18/11/2026 sur
    -- les 69 formules en pourcentage (16.22 et 16.23) : 47 PV max, 7 PV
    -- manquants, 5 PV actuels, 10 autres (% d'AD bonus de Jhin, Grit de
    -- Sett, seuil d'execution de Smolder...). Limite connue : Udyr Q2 dit
    -- "max Health damage" AVANT son nombre ; il tombe dans 'other'.
    CASE
        WHEN COALESCE(JSON_VALUE(f.formula, '$.mDisplayAsPercent'), 'false') != 'true'
            THEN 'flat'
        WHEN REGEXP_CONTAINS(LOWER(t.following_text), r'missing health')
            THEN 'target_missing_hp'
        WHEN REGEXP_CONTAINS(LOWER(t.following_text), r'current health')
            THEN 'target_current_hp'
        WHEN REGEXP_CONTAINS(LOWER(t.following_text), r'max(imum)? health')
            THEN 'target_max_hp'
        ELSE 'other'
    END AS scales_with,
    t.following_text

FROM {{ ref('stg_kit__formulas') }} AS f

-- Les noms des infobulles sont en minuscules (TotalDamage -> totaldamage).
INNER JOIN {{ ref('stg_kit__spell_tooltips') }} AS t
    ON t.patch_key = f.patch_key
    AND t.champion_id = f.champion_id
    AND t.slot = f.slot
    AND t.spell_name = f.spell_name
    AND t.name = LOWER(f.calc_name)

WHERE t.tag IN ('physicalDamage', 'magicDamage', 'trueDamage')
