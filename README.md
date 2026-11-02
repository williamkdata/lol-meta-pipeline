# lol-meta-pipeline

Pipeline de données sur la meta de *League of Legends* : quels champions, builds et runes performent par matchup et par patch, comment se jouent les timings d'avantage — et combien de temps met un pick vu en compétition professionnelle à descendre sur la ladder haut elo.

> **En construction — étapes 1 à 6 sur 9.** Les trois sources sont collectées chaque jour par Airflow et chargées dans BigQuery ; la meta pro par patch est modélisée en dbt. Prochaine étape : les marts du ladder (matchups, builds, runes, timings).

## Sources

| Flux | Source | Cadence | Accès |
|---|---|---|---|
| Ladder EUW | API Riot Games (Challenger + Grandmaster, classée solo) | quotidienne | clé *personal* |
| Compétition pro | Oracle's Elixir | quotidienne | fichier public, via l'API Google Drive |
| Référentiel | Data Dragon | à chaque patch | public, sans clé |

Le temps réel des matchs professionnels n'est pas accessible : il passe par un portail réservé aux équipes et partenaires de Riot. Oracle's Elixir en est lui-même en aval.

## Architecture

```
Data Dragon ──────┐
Oracle's Elixir ──┼──> Cloud Storage ──> BigQuery ─────────────> dbt ──────────────> BigQuery
API Riot ─────────┘    brut gzip,        lol_raw (permanent)      staging (vues)      lol_analytics
                       30 jours          lol_raw_ladder (60 j)    marts (tables)

                Airflow (local, Docker) : un DAG par jour à 14 h 30 UTC
       [Data Dragon, Oracle's Elixir, ladder Riot] en parallèle  ->  dbt deps  ->  dbt build
```

## Ce qui tourne aujourd'hui

| # | Étape | État |
|---|---|---|
| 1 | Terraform : bucket, 3 datasets, compte de service, IAM minimal | ✅ |
| 2 | Data Dragon → BigQuery, seulement les patches absents | ✅ |
| 3 | Oracle's Elixir → Cloud Storage → BigQuery (API Drive, MD5 vérifié) | ✅ |
| 4 | dbt : staging + mart de la meta pro par patch ; Airflow quotidien | ✅ |
| 5 | Client de l'API Riot : limiteur de débit, 429, clé hors du code | ✅ |
| 6 | Collecte du ladder, timelines aplaties, volume mesuré | ✅ |
| 7 | Marts du ladder : matchups, builds, runes, timings | à venir |
| 8 | Mart de diffusion de la meta, pro → ladder | à venir |
| 9 | Coûts mesurés sur la durée, limites, bilan | à venir |

## Choix notables

**Une clé de patch commune à toutes les sources.** Oracle's Elixir écrit `16.01`, Data Dragon `16.1`. Une jointure sur le texte ne plante pas : elle retrouve **50 890 picks sur 98 200** et en perd **47 310 en silence**. Le patch devient un entier, `majeur × 100 + mineur` (1601), qui joint toutes les sources (98 200 sur 98 200) et se trie correctement (`16.10` après `16.2`).

**Un limiteur de débit à fenêtre glissante.** La clé *personal* autorise 20 requêtes par seconde et 100 par 2 minutes, comptées séparément par hôte (`euw1` pour les ligues, `europe` pour les parties). Un *token bucket* se remplit en continu et peut dépasser ce que Riot compte sur une fenêtre ; la fenêtre glissante compte comme Riot. Vérifié sur 250 requêtes simulées : jamais plus de 20 par seconde ni de 100 par 2 minutes. Un 429 attend `Retry-After` ; une panne serveur est réessayée avec des attentes croissantes ; une clé refusée (403) arrête tout de suite.

**Un aplatissement sélectif des timelines.** Une timeline contient une photo par minute de chaque joueur et tous les événements de la partie. Sont gardés l'or, l'XP et les sbires par minute, ainsi que les événements qui répondent aux questions du projet : achats (l'ordre du build), montées de sorts, kills, objectifs, tourelles. Les poses de wards sont écartées. Environ 490 événements gardés par partie.

**Aucune donnée personnelle stockée.** L'analyse de la meta n'a pas besoin de savoir qui joue : ni identifiant Riot (puuid) ni pseudo n'arrivent dans BigQuery. Dans une partie, un joueur est désigné par son numéro de 1 à 10. Un test le vérifie.

**Le brut d'abord, dans le bucket.** Les requêtes à l'API Riot sont la ressource rare. Chaque partie et sa timeline sont déposées en JSON Lines compressé avant tout traitement : changer d'avis sur les champs gardés ne coûte aucune requête.

**Un chargement qui reprend proprement.** Les parties sont traitées par lots de 50 ; la table des joueurs est chargée en dernier et sert de marqueur de fin. Un run interrompu ne laisse aucune partie à moitié marquée comme collectée, et le run suivant ne retélécharge que ce qui manque.

**Des tests sur les données, pas seulement sur le code.**
- `SAFE_CAST` ne plante jamais : une valeur non convertible devient `NULL` en silence. Un test singulier vérifie qu'aucune valeur non vide n'est perdue à la conversion (0 sur 10 colonnes).
- Data Dragon contient au patch 16.15 soixante entrées `Jade_<Champion>` qui dupliquent des noms de vrais champions. Elles sont écartées, et un test d'unicité du nom par patch protège la jointure par nom.
- Un `dbt build` a déjà affiché « réussi » avec zéro test lancé, à cause d'un cache d'analyse périmé : les runs d'Airflow utilisent `--no-partial-parse`.

## Coût et volume

**Le free tier GCP est calculé par compte de facturation, pas par projet.** Les 10 Gio de stockage et 1 Tio de requêtes BigQuery gratuits par mois sont donc **partagés** avec le projet [Vélib'](https://github.com/williamkdata/data-engineering-portfolio), sur le même compte.

**Cloud Storage a son propre free tier** (5 Go-mois), seulement dans `us-east1`, `us-west1` et `us-central1` : le projet est en `us-central1`.

D'où deux choix d'infrastructure :
- **un dataset par politique de rétention**, pas par source : le référentiel et les données pro n'expirent jamais ; le ladder vit dans des tables partitionnées par jour de partie, qui expirent après 60 jours ;
- **une durée de vie de 30 jours** sur le bucket de landing.

Volume mesuré sur un premier run réel (30 parties) :

| | par partie | 400 parties par jour, sur la durée de rétention |
|---|---|---|
| Cloud Storage (gzip) | ~67 Ko | ~0,8 Go sur 30 jours |
| BigQuery | ~70 Ko | ~1,7 Go sur 60 jours |

Les deux restent dans le free tier. Une requête Riot prend environ 2 secondes : un run quotidien d'environ 1 100 requêtes dure une trentaine de minutes, sous le quota de la clé.

## Structure

```
ingestion/        Data Dragon, Oracle's Elixir, client Riot (limiteur), collecteur du ladder
infra/terraform/  bucket, datasets, compte de service, IAM minimal
airflow/          image, docker-compose, DAG quotidien lol_daily
dbt/              staging (vues) -> marts (tables), tests de données
tests/            pytest hors ligne : faux clients HTTP, BigQuery et Storage
```

## Lancer le projet

Prérequis : Python 3.12 et [uv](https://docs.astral.sh/uv/), un projet GCP créé par `infra/terraform`, la clé du compte de service dans `secrets/` et une clé Riot dans `.env` (`RIOT_API_KEY=...`). Ces deux fichiers sont ignorés par git.

```bash
uv sync
uv run pytest
uv run python ingestion/ladder.py --max-joueurs 20 --max-parties 30
```

Orchestration : depuis `airflow/`, `docker compose up -d`, puis l'interface sur `http://localhost:8081`. La clé Riot est montée dans les conteneurs en lecture seule, jamais copiée.

## Attribution et conditions d'utilisation

- Données de compétition : [Oracle's Elixir](https://oracleselixir.com/). Une partie du contenu provient de [Leaguepedia](https://lol.fandom.com/), sous licence CC BY-SA 3.0.
- Les statistiques de jeu sont la propriété de Riot Games. Ce projet n'est ni approuvé ni sponsorisé par Riot Games, et ne reflète pas ses positions.
- Seuls le code et des agrégats sont publiés. Les données brutes ne sont pas redistribuées.
