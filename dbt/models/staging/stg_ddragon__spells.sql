-- Les sorts des champions d'apres Data Dragon : temps de recharge et cout par
-- rang, rang maximum. Source OFFICIELLE pour ces chiffres (conforme aux notes
-- de patch) ; les formules viennent de CommunityDragon (stg_kit__*).

SELECT
    CAST(SPLIT(patch, '.')[OFFSET(0)] AS INT64) * 100
    + CAST(SPLIT(patch, '.')[OFFSET(1)] AS INT64) AS patch_key,
    patch,
    version,
    champion_id,
    champion_code,
    slot,
    spell_id,
    spell_name,
    max_rank,
    spell_rank,
    cooldown,
    cost

FROM {{ source('lol_raw', 'ddragon_spells') }}
WHERE STRPOS(champion_code, '_') = 0

-- Meme dedoublonnage que les champions : une ligne par patch et par rang.
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY champion_id, patch, slot, spell_rank
    ORDER BY version DESC
) = 1
