{#
  Une table brute de lol_raw, avec ou sans l'apercu du PBE (18/11/2026).

  Le PBE est le serveur de test de Riot : le prochain patch y est teste deux
  semaines avant sa sortie. ingestion/pbe.py (lance a la main) en charge un
  apercu dans des tables a part (pbe_*), etiquete du vrai numero ("16.24").

  HORS MODE APERCU (le cas normal : dev, prod, run quotidien) : la table brute,
  rien d'autre. Les tables pbe_* ne sont meme pas lues.

  EN MODE APERCU (cible pbe, ou var pbe_preview: true pour les tests) :
    - table_pbe donnee (kits, objets) : on ajoute les lignes de l'apercu, sauf
      si leur patch est deja dans la vraie table. Le vrai patch est sorti : il
      gagne, un vieil apercu ne doit pas s'y melanger ;
    - sans table_pbe (Data Dragon, qui ne publie un patch qu'a sa sortie) : on
      recopie le DERNIER patch publie sous le nom du patch du PBE (lu dans la
      table des formules du PBE). Le dernier par NUMERO (16.23 > 16.9), pas par
      texte ('16.9' > '16.23'). La version (16.23.1) garde sa valeur : on voit
      que c'est un emprunt. Limite : un prix ou un nom change au PBE n'est pas
      vu par ce biais (les stats des objets, elles, viennent du PBE).

  UNION ALL CORRESPONDING : colonnes associees par leur NOM, pas par leur
  position. Si une colonne est ajoutee un jour a une seule des deux tables,
  rien ne se decale en silence (verifie sur BigQuery le 18/11/2026).
#}
{% macro source_avec_apercu_pbe(nom_table, table_pbe=none) -%}
    {%- set vraie = source('lol_raw', nom_table) -%}
    {%- if not var('pbe_preview', target.name == 'pbe') -%}
        {{ vraie }}
    {%- elif table_pbe -%}
        (
            SELECT * FROM {{ vraie }}
            UNION ALL CORRESPONDING
            SELECT * FROM {{ source('lol_raw', table_pbe) }}
            WHERE patch NOT IN (SELECT DISTINCT patch FROM {{ vraie }})
        )
    {%- else -%}
        (
            SELECT * FROM {{ vraie }}
            UNION ALL CORRESPONDING
            SELECT publiee.* REPLACE (apercu.patch AS patch)
            FROM {{ vraie }} AS publiee
            CROSS JOIN (
                SELECT DISTINCT patch
                FROM {{ source('lol_raw', 'pbe_kit_formula_parts') }}
            ) AS apercu
            WHERE publiee.patch = (
                SELECT ARRAY_AGG(
                    patch
                    ORDER BY
                        CAST(SPLIT(patch, '.')[OFFSET(0)] AS INT64) * 100
                        + CAST(SPLIT(patch, '.')[OFFSET(1)] AS INT64) DESC
                    LIMIT 1
                )[OFFSET(0)]
                FROM {{ vraie }}
            )
                AND apercu.patch NOT IN (SELECT DISTINCT patch FROM {{ vraie }})
        )
    {%- endif -%}
{%- endmacro %}
