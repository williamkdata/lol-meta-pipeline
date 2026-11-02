-- SAFE_CAST ne plante jamais : une valeur qu'il ne sait pas convertir devient
-- NULL, sans aucun message. Ce test cherche les valeurs NON VIDES du brut qui
-- seraient devenues NULL apres conversion. Mesure le 02/11/2026 : zero.
-- Il cassera le jour ou Oracle's Elixir changera un format ("1,234" au lieu
-- de "1234", une date dans un autre format...).
--
-- Un test singulier passe quand cette requete ne renvoie AUCUNE ligne.

{% set colonnes = {
    "participantid": "INT64",
    "gamelength": "INT64",
    "kills": "INT64",
    "deaths": "INT64",
    "assists": "INT64",
    "damagetochampions": "FLOAT64",
    "earnedgold": "FLOAT64",
    "golddiffat10": "FLOAT64",
    "golddiffat15": "FLOAT64",
    "date": "TIMESTAMP",
} %}

{% for colonne, type in colonnes.items() %}
SELECT
    gameid,
    participantid,
    '{{ colonne }}' AS colonne,
    {{ colonne }} AS valeur_brute
FROM {{ source('lol_raw', 'oe_matches') }}
WHERE {{ colonne }} IS NOT NULL
  AND TRIM({{ colonne }}) != ''
  AND SAFE_CAST({{ colonne }} AS {{ type }}) IS NULL
{% if not loop.last %}UNION ALL{% endif %}
{% endfor %}
