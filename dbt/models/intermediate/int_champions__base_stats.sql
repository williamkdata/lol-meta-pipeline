-- Les stats de base de chaque champion : une ligne par patch et par champion,
-- une colonne par stat (simulateur de combat, etape 1).
--
-- Le staging (stg_kit__champion_record) donne une ligne par stat. Ici, PIVOT
-- les met cote a cote, comme la fiche d'un champion dans le client du jeu.
--
-- Un champ absent du fichier du jeu prend la valeur par defaut DU JEU, pas
-- toujours 0. Mesure du 09/11/2026 sur 22 patches, recoupee avec Data Dragon :
--   hp_regen_base       absent chez 8 champions (Zac, Kayle, Yuumi...) : 1 PV/s
--   resource_base       absent chez 8 champions (Tryndamere, Yasuo...) : 100
--   gains par niveau    absents chez quelques champions (Jhin, Thresh...) : 0
--   resource_type_code  absent chez 6 champions (Garen, Zac...) : aucune
-- Les autres stats n'ont PAS de valeur par defaut : si elles manquent, elles
-- restent vides et un test (not_null) echoue. C'est ce qui rendra bruyant un
-- nouveau renommage de Riot.
--
-- Unites du fichier du jeu : regenerations PAR SECONDE (Data Dragon : par
-- 5 secondes) ; as_per_level en pourcentage (2.5 = +2,5 % par niveau).

WITH fiche AS (
    SELECT *
    FROM (
        SELECT
            patch_key,
            patch,
            champion_id,
            champion_code,
            stat,
            -- Le fichier stocke 4.4 sous la forme 4.400000095... : arrondi a
            -- 6 decimales. Mesure du 16/11 : aucune vraie valeur n'est changee
            -- (a 4 decimales, l'AD par niveau de Vel'Koz, qui vaut pi, aurait
            -- perdu des chiffres).
            ROUND(value, 6) AS value
        FROM {{ ref('stg_kit__champion_record') }}
    )
    -- Une colonne par stat de la liste. MAX ne choisit rien : il n'y a qu'une
    -- valeur par case (test d'unicite du staging), mais PIVOT exige une
    -- fonction qui resume un groupe de lignes.
    PIVOT (MAX(value) FOR stat IN (
        'hp_base', 'hp_per_level', 'hp_regen_base', 'hp_regen_per_level',
        'armor_base', 'armor_per_level', 'mr_base', 'mr_per_level',
        'ad_base', 'ad_per_level', 'as_base', 'as_per_level', 'as_ratio',
        'attack_range', 'move_speed', 'crit_damage',
        'resource_base', 'resource_per_level', 'resource_regen_base',
        'resource_regen_per_level', 'resource_type_code'
    ))
)

SELECT
    patch_key,
    patch,
    champion_id,
    champion_code,

    -- PV
    hp_base,
    hp_per_level,
    COALESCE(hp_regen_base, 1.0) AS hp_regen_base,
    COALESCE(hp_regen_per_level, 0.0) AS hp_regen_per_level,

    -- Defenses
    armor_base,
    COALESCE(armor_per_level, 0.0) AS armor_per_level,
    mr_base,
    mr_per_level,

    -- Attaque
    ad_base,
    COALESCE(ad_per_level, 0.0) AS ad_per_level,
    as_base,
    COALESCE(as_per_level, 0.0) AS as_per_level,
    as_ratio,
    attack_range,
    crit_damage,

    move_speed,

    -- Ressource (mana, energie, fureur...)
    COALESCE(resource_base, 100.0) AS resource_base,
    COALESCE(resource_per_level, 0.0) AS resource_per_level,
    resource_regen_base,
    COALESCE(resource_regen_per_level, 0.0) AS resource_regen_per_level,
    CAST(resource_type_code AS INT64) AS resource_type_code,
    CASE
        WHEN resource_type_code IS NULL THEN 'aucune'
        WHEN resource_type_code = 0 THEN 'mana'
        WHEN resource_type_code = 1 THEN 'energie'
        ELSE 'autre'
    END AS resource_type

FROM fiche
