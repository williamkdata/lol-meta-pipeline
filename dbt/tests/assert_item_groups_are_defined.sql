-- Un groupe cite par un objet mais introuvable dans le fichier du jeu : sa
-- limite est inconnue, et le moteur de build pourrait proposer un build
-- impossible. Avertissement (pas une erreur) : la collecte continue, on
-- regarde. 0 au 16.1-16.23 (mesure du 19/11/2026).
{{ config(severity='warn') }}

SELECT patch_key, item_id, item_group
FROM {{ ref('stg_item_groups') }}
WHERE NOT group_defined
