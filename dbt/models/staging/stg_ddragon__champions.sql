-- Les vrais champions, un par patch, avec une cle de patch commune a toutes
-- les sources.

SELECT
    -- "16.21" -> 1621, "16.1" -> 1601. Un entier sert a la fois a JOINDRE
    -- (Oracle's Elixir ecrit "16.01", Data Dragon "16.1") et a TRIER
    -- (en texte, "16.10" passe avant "16.2").
    CAST(SPLIT(patch, '.')[OFFSET(0)] AS INT64) * 100
    + CAST(SPLIT(patch, '.')[OFFSET(1)] AS INT64) AS patch_key,
    patch,
    version,
    champion_id,
    champion_code,
    champion_name,
    title,
    tags

FROM {{ source('lol_raw', 'ddragon_champions') }}

-- Les 60 entrees speciales du patch 16.15 (Jade_Ahri, Jade_Wukong...) ont un
-- _ dans leur code ; aucun vrai champion n'en a. STRPOS cherche le caractere
-- tel quel. PAS de LIKE '%_%' : dans un LIKE, _ est un joker qui vaut
-- n'importe quel caractere, et le filtre ecarterait TOUS les champions.
WHERE STRPOS(champion_code, '_') = 0

-- Le brut accepte les doublons : si la saison a ete chargee deux fois, chaque
-- champion y est deux fois par patch. On n'en garde qu'un. Les lignes en
-- double sont identiques, l'ordre choisi n'a donc pas d'importance pour le
-- resultat ; il rend seulement le choix deterministe.
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY champion_id, patch
    ORDER BY version DESC
) = 1
