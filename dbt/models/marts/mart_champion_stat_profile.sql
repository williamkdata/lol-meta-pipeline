-- Le profil de sensibilite de chaque champion, par patch : pour chaque stat, la
-- somme de ses ratios sur ses sorts (Q, W, E, R, passif). Ambessa au 16.22 :
-- surtout l'attaque bonus (1,5 sur le bouclier du W, 0,2 sur son passif...).
-- Version A du moteur theorique (choix de William, 04/11).
--
-- Trois regles, chacune justifiee par une mesure (projet3_explications.md) :
--   ratios IDENTIQUES dans un meme sort comptes une seule fois : les formules
--     d'affichage repetent les vrais ratios. (Premiere version : ecarter les
--     formules nommees "Tooltip". Abandonnee : le vrai ratio d'Orianna etait
--     dans une formule "Tooltip" au 16.21, renommee au 16.22 -> faux buff.
--     Un nom peut mentir ; un ratio identique, non.) Revers assume : deux
--     instances reelles au meme ratio (Q d'Ahri aller-retour) comptent une fois ;
--   ratios sous 0,01 ecartes : une autre unite (% des PV de la cible, vitesse,
--     duree de ralentissement... par point de stat), 64 ratios sur 1 109 ;
--   ratios par rang lus au rang maximum du sort (Data Dragon), rang 1 pour le
--     passif : c'est quand on a ses objets qu'on a ses sorts au maximum.
-- Seuls les codes de stats decodes (seed stat_codes) comptent.
--
-- Quatrieme regle, "sans la survie" (decision de William, 19/11/2026) : les
-- ratios des formules que l'infobulle designe CLAIREMENT comme de la survie
-- (bouclier, soin ou PV "healing", vitesse) ne comptent plus, sauf si la meme
-- formule est aussi balisee degats (un drain). Une formule absente des
-- infobulles reste comptee : retirer ce qu'on ne sait pas classer cassait une
-- vingtaine de champions (Gnar, Jayce...). Mesure du 19/11 au 16.23 : 151 tops
-- 5 sur 173 inchanges ; corrige Annie (les PV de Tibbers en faisaient une
-- acheteuse d'objets PV), Mordekaiser, Maitre Yi, Gangplank, K'Sante.
--
-- Puis la valeur survie SEPAREE (19/11/2026) : ces ratios ne sont plus jetes,
-- ils forment un second profil. value_kind = 'degats' (tout le reste, y compris
-- les formules sans infobulle) ou 'survie'. Les trois premieres regles
-- s'appliquent a chaque profil separement. Sans la survie, un changement qui ne
-- touche qu'elle (bouclier de Galio, PV de Tibbers) n'etait plus predit : 6
-- champions perdus depuis le 16.19 (Fiora, Vi, Diana, Viktor, Annie, Galio).

WITH rangs_max AS (
    SELECT patch_key, champion_id, slot, MAX(max_rank) AS max_rank
    FROM {{ ref('stg_ddragon__spells') }}
    GROUP BY patch_key, champion_id, slot
),

formules_de_survie AS (
    -- Les formules dont TOUTES les balises sont de la survie (au moins une), et
    -- aucune de degats. Les noms des infobulles sont en minuscules.
    SELECT patch_key, champion_id, slot, spell_name, name
    FROM {{ ref('stg_kit__spell_tooltips') }}
    GROUP BY patch_key, champion_id, slot, spell_name, name
    HAVING
        LOGICAL_OR(
            LOWER(tag) LIKE '%shield%' OR LOWER(tag) LIKE '%heal%' OR LOWER(tag) = 'speed'
        )
        AND NOT LOGICAL_OR(tag IN ('physicalDamage', 'magicDamage', 'trueDamage'))
),

ratios AS (
    SELECT
        p.patch_key,
        p.champion_id,
        p.champion_code,
        p.slot,
        p.stat,
        p.stat_formula,
        -- Une formule de survie (trouvee dans la liste) va dans le profil survie.
        IF(s.name IS NULL, 'degats', 'survie') AS value_kind,
        -- Ratio fixe (StatByCoefficient) ou ratio par rang (StatByNamedDataValue).
        COALESCE(p.coefficient, v.value) AS coefficient
    FROM {{ ref('stg_kit__parts') }} AS p
    LEFT JOIN rangs_max AS r
        ON p.patch_key = r.patch_key AND p.champion_id = r.champion_id AND p.slot = r.slot
    LEFT JOIN {{ ref('stg_kit__values') }} AS v
        ON p.patch_key = v.patch_key
        AND p.champion_id = v.champion_id
        AND p.slot = v.slot
        AND p.data_value = v.value_name
        AND COALESCE(r.max_rank, 1) = v.spell_rank
    LEFT JOIN formules_de_survie AS s
        ON p.patch_key = s.patch_key
        AND p.champion_id = s.champion_id
        AND p.slot = s.slot
        AND p.spell_name = s.spell_name
        AND LOWER(p.calc_name) = s.name
    WHERE p.part_type IN (
        'StatByCoefficientCalculationPart', 'StatByNamedDataValueCalculationPart'
    )
),

ratios_distincts AS (
    -- Une seule fois chaque ratio identique d'un meme sort, quel que soit le
    -- nom de la formule qui le porte, dans chaque profil.
    SELECT DISTINCT
        patch_key,
        champion_id,
        champion_code,
        value_kind,
        slot,
        stat,
        stat_formula,
        ROUND(coefficient, 6) AS coefficient
    FROM ratios
)

SELECT
    r.patch_key,
    r.champion_id,
    r.champion_code,
    r.value_kind,
    c.stat_label,
    c.item_stat,
    COUNT(*) AS ratios,
    -- L'arrondi n'est pas cosmetique : une somme de nombres a virgule depend
    -- de l'ordre des additions (1,7999999 ou 1,8000001). Sans lui, la valeur
    -- survie de Locke bougeait de 0,01 d'un patch a l'autre sans rien changer
    -- (mesure du 19/11) : une fausse prediction.
    ROUND(SUM(r.coefficient), 4) AS total_coefficient
FROM ratios_distincts AS r
INNER JOIN {{ ref('stat_codes') }} AS c
    ON r.stat = c.stat AND r.stat_formula = c.stat_formula
WHERE ABS(r.coefficient) >= 0.01
GROUP BY r.patch_key, r.champion_id, r.champion_code, r.value_kind, c.stat_label, c.item_stat
