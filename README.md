# lol-meta-pipeline

Pipeline de données sur la meta de *League of Legends* : quels champions, builds et runes performent par matchup et par patch, comment se jouent les timings d'avantage — et combien de temps met un pick vu en compétition professionnelle à descendre sur la ladder haut elo.

> **En construction — étape 1 sur 9** (squelette et infrastructure).

## Sources

| Flux | Source | Cadence | Accès |
|---|---|---|---|
| Ladder EUW | API Riot Games (Challenger + Grandmaster) | quasi temps réel | clé *personal* |
| Compétition pro | Oracle's Elixir | quotidienne | CSV publics |
| Référentiel | Data Dragon | à chaque patch | public, sans clé |

Le temps réel des matchs professionnels n'est pas accessible : il passe par un portail réservé aux équipes et partenaires de Riot. Oracle's Elixir en est lui-même en aval.

## Stack

GCP — Cloud Storage, BigQuery — Airflow (local, Docker), dbt, Terraform, GitHub Actions. Même socle que le projet [Vélib'](https://github.com/williamkdata/data-engineering-portfolio), recyclé volontairement : le temps d'ingénierie va dans l'ingestion Python et la modélisation, pas dans l'infrastructure.

## Coût : deux contraintes vérifiées avant d'écrire le Terraform

**Le free tier GCP est calculé par compte de facturation, pas par projet.** Les 10 Gio de stockage et 1 Tio de requêtes BigQuery gratuits par mois sont donc **partagés** avec le projet Vélib', qui tourne sur le même compte. Mesuré au démarrage : Vélib' occupe 0,012 Gio.

**Cloud Storage n'est pas couvert par le free tier BigQuery.** Il a le sien — 5 Go-mois — mais seulement dans trois régions : `us-east1`, `us-west1` et `us-central1`. Or le JSON brut des timelines atterrit dans un bucket.

D'où deux choix d'infrastructure :

- **un dataset par politique de rétention**, pas par source. Le référentiel et les données pro n'expirent jamais ; les événements de ladder vivent dans une fenêtre glissante par partition.
- **une durée de vie sur le bucket de landing**, à recalibrer une fois le volume réel mesuré.

## Structure

```
ingestion/        clients Riot (rate limiter), Oracle's Elixir, Data Dragon ; aplatisseur de timeline
infra/terraform/  bucket, datasets, compte de service, IAM minimal
airflow/          DAGs
dbt/              staging -> intermediate -> marts
tests/            pytest hors ligne, sans identifiant
```

## Attribution et conditions d'utilisation

- Données de compétition : [Oracle's Elixir](https://oracleselixir.com/). Une partie du contenu provient de [Leaguepedia](https://lol.fandom.com/), sous licence CC BY-SA.
- Les statistiques de jeu sont la propriété de Riot Games. Ce projet n'est ni approuvé ni sponsorisé par Riot Games, et ne reflète pas ses positions.
- Seuls le code et des agrégats sont publiés. Les données brutes ne sont pas redistribuées.
