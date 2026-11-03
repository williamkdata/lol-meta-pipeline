# lol-meta-pipeline

Pipeline de données sur la meta de *League of Legends* : quels champions, builds et runes performent par matchup et par patch, comment se jouent les timings d'avantage — et combien de temps met un pick vu en compétition professionnelle à descendre sur la ladder haut elo.

> **Les 9 étapes sont terminées (03/11/2026), et la collecte continue chaque jour.** Les trois sources sont chargées dans BigQuery par Airflow ; dbt en tire la meta pro et la meta du ladder par patch (champions, matchups, timings d'avantage, builds, runes, chaque taux de victoire avec sa fourchette de confiance) et la diffusion de la meta entre les deux. Les seuils de volume par matchup et les premiers délais de diffusion seront mesurés quand un patch complet du ladder aura été collecté.

## Sources

| Flux | Source | Cadence | Accès |
|---|---|---|---|
| Ladder EUW | API Riot Games (Challenger + Grandmaster, classée solo) | quotidienne | clé *personal* |
| Compétition pro | Oracle's Elixir | quotidienne | fichier public, via l'API Google Drive |
| Référentiel | Data Dragon (champions, objets, runes) | à chaque patch | public, sans clé |

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
| 7 | Marts du ladder : matchups, builds, runes, timings | ✅ |
| 8 | Mart de diffusion de la meta, pro → ladder | ✅ |
| 9 | Coûts mesurés, limites, bilan | ✅ |

## Les marts

| Table | Question | Grain |
|---|---|---|
| `mart_pro_champion_patch` | Quels champions comptent en pro ? Picks, bans, présence, victoires | patch × champion |
| `mart_ladder_champion_patch` | Quels champions gagnent sur la ladder haut elo ? | patch × poste × champion |
| `mart_ladder_matchups` | Qui bat qui dans sa voie, et avec quelle avance d'or, d'XP et de sbires à 10 et 15 minutes ? | patch × poste × champion × adversaire |
| `mart_ladder_builds` | Quels deux premiers objets terminés, dans quel ordre, et avec quel résultat ? | patch × poste × champion × chemin |
| `mart_ladder_runes` | Quelle page de runes (rune principale + arbres) ? | patch × poste × champion × page |
| `mart_meta_diffusion` | Pro et ladder côte à côte : taux de pick, appartenance au cœur de la meta, évolution d'un patch à l'autre | patch × champion |
| `mart_meta_diffusion_lag` | Combien de patches entre l'entrée d'un champion dans la meta pro et son entrée dans la meta ladder ? | champion |

Chaque taux de victoire du ladder est accompagné de sa **fourchette à 95 %** (`win_rate_low`, `win_rate_high`).

## Choix notables

**Une clé de patch commune à toutes les sources.** Oracle's Elixir écrit `16.01`, Data Dragon `16.1`. Une jointure sur le texte ne plante pas : elle retrouve **50 890 picks sur 98 200** et en perd **47 310 en silence**. Le patch devient un entier, `majeur × 100 + mineur` (1601), qui joint toutes les sources (98 200 sur 98 200) et se trie correctement (`16.10` après `16.2`).

**Un limiteur de débit à fenêtre glissante.** La clé *personal* autorise 20 requêtes par seconde et 100 par 2 minutes, comptées séparément par hôte (`euw1` pour les ligues, `europe` pour les parties). Un *token bucket* se remplit en continu et peut dépasser ce que Riot compte sur une fenêtre ; la fenêtre glissante compte comme Riot. Vérifié sur 250 requêtes simulées : jamais plus de 20 par seconde ni de 100 par 2 minutes. Un 429 attend `Retry-After` ; une panne serveur est réessayée avec des attentes croissantes ; une clé refusée (403) arrête tout de suite.

**Un aplatissement sélectif des timelines.** Une timeline contient une photo par minute de chaque joueur et tous les événements de la partie. Sont gardés l'or, l'XP et les sbires par minute, ainsi que les événements qui répondent aux questions du projet : achats (l'ordre du build), montées de sorts, kills, objectifs, tourelles. Les poses de wards sont écartées. Environ 490 événements gardés par partie.

**Aucune donnée personnelle stockée.** L'analyse de la meta n'a pas besoin de savoir qui joue : ni identifiant Riot (puuid) ni pseudo n'arrivent dans BigQuery. Dans une partie, un joueur est désigné par son numéro de 1 à 10. Un test le vérifie.

**Le brut d'abord, dans le bucket.** Les requêtes à l'API Riot sont la ressource rare. Chaque partie et sa timeline sont déposées en JSON Lines compressé avant tout traitement : changer d'avis sur les champs gardés ne coûte aucune requête.

**Un chargement qui reprend proprement.** Les parties sont traitées par lots de 50 ; la table des joueurs est chargée en dernier et sert de marqueur de fin. Un run interrompu ne laisse aucune partie à moitié marquée comme collectée, et le run suivant ne retélécharge que ce qui manque.

**Des taux de victoire avec leur fourchette.** 3 victoires sur 4 font 75 %, mais ne disent presque rien. Chaque taux du ladder est accompagné de son intervalle de Wilson à 95 %, écrit une seule fois dans une macro dbt et figé par un test unitaire (3 sur 4 → [0,301 ; 0,954]). Un résultat est retenu comme significatif quand sa fourchette exclut 50 % ; le volume minimal découle de la largeur de fourchette acceptée, pas d'un nombre choisi au hasard.

**Des seuils tirés des distributions observées.**
- Une partie compte à partir de **15 minutes** : le vote d'abandon s'ouvre à 15 minutes, et les trois parties les plus courtes du premier échantillon durent 7 min 56 s, 9 min 09 s puis 15 min 23 s. Avant, c'est un remake ou un abandon après un AFK.
- Un objet compte dans un build à partir de **2 000 pièces d'or** : la distribution des prix des objets finaux montre un trou entre 1 750 et 2 000, qui sépare les légendaires des bottes et objets de départ.
- Les deux seuils sont des variables dbt, justifiées dans `dbt_project.yml`, et seront revérifiés sur un patch complet de données.

**L'ordre des builds vient de la timeline.** Une partie ne donne que l'inventaire final. L'ordre des achats vient des événements de la timeline, achats annulés exclus (6 annulations d'objets terminés dans les 28 premières parties). Un test unitaire dbt fige le cas : Lame d'infini achetée puis annulée, Collector, Lame rachetée → chemin « Collector puis Lame ».

**La diffusion de la meta, mesurée honnêtement.** Le « cœur de la meta » d'un patch est le plus petit groupe de champions qui fait la moitié des picks : 20 à 28 champions en pro, 37 sur la ladder haut elo au 16.21. Le délai de diffusion est l'écart en patches entre l'entrée d'un champion dans le cœur pro et son entrée dans le cœur ladder. La ladder n'étant collectée que depuis le patch 16.21, tout ce qui s'est passé avant est **inconnu, pas absent** : un champion déjà dans la meta au premier patch collecté, ou entré en pro avant le début de la collecte, reçoit un statut qui le dit, sans délai inventé. Au 03/11, aucun délai n'est encore mesurable ; les mesures apparaissent d'elles-mêmes au fil des patches.

**Un collecteur qui dit ce qu'il fait.** Le premier run complet a été cinq fois trop lent, et son journal était muet. Mesuré depuis le bucket (heure de dépôt de chaque lot), puis au niveau des connexions : une des deux adresses de l'API (Cloudflare) est injoignable depuis le réseau local, et chaque nouvelle connexion perdait jusqu'à 10 secondes à l'essayer. Trois hypothèses plus classiques (DNS, IPv6, réseaux Docker) ont été écartées par la mesure avant. Correction : une session HTTP qui réutilise la connexion (0,07 s par requête au lieu de 10). Le collecteur journalise désormais son avancement, chaque 429 avec les compteurs de Riot, et les limites que Riot annonce, comparées à celles que suppose le limiteur — sans jamais écrire d'identifiant de joueur.

Run du 03/11 après correction : **825 requêtes en 17 minutes** (contre plus de 2 heures avant), 261 parties, **un seul 429**, 0 panne. Riot annonce `100:120,20:1`, exactement les limites supposées par le limiteur. Le seul 429 venait d'un décalage d'horloge : le limiteur datait une requête à son départ, Riot à son arrivée, et la première connexion d'un run peut mettre 10 secondes à arriver ; le `Retry-After` imposé était de 11 secondes. Le limiteur date maintenant chaque requête au retour de sa réponse, ce qui le rend sûr quelle que soit la latence.

**Des tests sur les données, pas seulement sur le code.**
- `SAFE_CAST` ne plante jamais : une valeur non convertible devient `NULL` en silence. Un test singulier vérifie qu'aucune valeur non vide n'est perdue à la conversion (0 sur 10 colonnes).
- Data Dragon contient au patch 16.15 soixante entrées `Jade_<Champion>` qui dupliquent des noms de vrais champions. Elles sont écartées, et un test d'unicité du nom par patch protège la jointure par nom.
- Un `dbt build` a déjà affiché « réussi » avec zéro test lancé, à cause d'un cache d'analyse périmé : les runs d'Airflow utilisent `--no-partial-parse`.
- Une partie compte 10 picks : les taux de pick d'un patch font 10. Ce test a attrapé un taux calculé avec un numérateur et un dénominateur venus de deux tables d'âges différents (8,70 au lieu de 10).

## Coût et volume

**Le free tier GCP est calculé par compte de facturation, pas par projet.** Les 10 Gio de stockage et 1 Tio de requêtes BigQuery gratuits par mois sont donc **partagés** avec le projet [Vélib'](https://github.com/williamkdata/data-engineering-portfolio), sur le même compte.

**Cloud Storage a son propre free tier** (5 Go-mois), seulement dans `us-east1`, `us-west1` et `us-central1` : le projet est en `us-central1`.

D'où deux choix d'infrastructure :
- **un dataset par politique de rétention**, pas par source : le référentiel et les données pro n'expirent jamais ; le ladder vit dans des tables partitionnées par jour de partie, qui expirent après 60 jours ;
- **une durée de vie de 30 jours** sur le bucket de landing.

**Mesuré le 03/11/2026**, six jours après le début du projet (vues système `INFORMATION_SCHEMA.JOBS_BY_PROJECT` et `__TABLES__`, `gcloud storage du`) :

| | Mesuré | Free tier mensuel | Part utilisée |
|---|---|---|---|
| Requêtes BigQuery | 272 requêtes, **2,49 Gio facturés** | 1 Tio | 0,24 % |
| Chargements BigQuery | 28 | gratuits | — |
| Stockage BigQuery | ~111 Mio (`lol_raw` 87 Mio, `lol_raw_ladder` 23 Mio, marts < 1 Mio) | 10 Gio, partagés avec Vélib' | ~1 % |
| Cloud Storage | 92 Mo | 5 Go | ~2 % |

**Coût facturé : 0 €.** Les 272 requêtes ont lu 0,24 Gio mais en ont été facturées 2,49 : chaque requête est facturée au moins 10 Mio, quelle que soit sa taille. À cette échelle, c'est le **nombre** de requêtes qui coûte, pas leur volume.

Volume par partie du ladder, mesuré sur le premier run réel : ~70 Ko dans BigQuery, ~67 Ko compressés dans le bucket. À 400 parties par jour, la rétention de 60 jours tient en ~1,7 Go dans BigQuery, et celle de 30 jours en ~0,8 Go dans le bucket : toujours dans le free tier.

## Limites

- **Airflow tourne en local** : la collecte n'a lieu que si le PC est allumé à 14 h 30 UTC. La fenêtre de 2 jours absorbe un jour manqué ; au-delà, des parties sont perdues.
- **Un échantillon, pas tout le ladder.** La clé *personal* autorise 100 requêtes par 2 minutes : environ 400 nouvelles parties par jour, à partir des 300 premiers joueurs Challenger et Grandmaster. Les parties sont celles de joueurs du haut du classement, pas un tirage aléatoire.
- **La diffusion de la meta est censurée à gauche.** La ladder n'est collectée que depuis le patch 16.21 ; aucun délai n'est mesurable tant qu'un champion n'est pas entré dans la meta pendant la fenêtre observée. Le pro, lui, saute des patches (aucun match au 16.19) : un délai en patches se lit avec ça en tête.
- **Les seuils viennent d'un premier échantillon** (parties ≥ 15 min, objets ≥ 2 000 po) et seront revérifiés sur un patch complet. Aucun seuil de volume n'est encore imposé aux matchups : chaque taux est publié avec sa fourchette de confiance, qui dit elle-même quand un effectif est trop faible.
- **Une adresse de l'API injoignable** depuis le réseau local (cause inconnue) : contournée par une connexion réutilisée, pas résolue.
- **Les plaques de tourelle** ne suivent pas la règle connue (jusqu'à 15 par équipe et par voie, jusqu'à la minute 36) : collectées, mais utilisées par aucune mart tant que la mécanique n'est pas vérifiée.
- **Les données pro** dépendent d'Oracle's Elixir : certains matchs sont incomplets (écart d'or à 15 minutes manquant pour 1 740 lignes joueurs).
- **Un poste peut manquer.** Riot laisse le poste vide quand il ne sait pas déduire le rôle d'un joueur (1 ligne sur 2 890 au 03/11, dans une partie finie à 15 min 32 s). Un test le signale en avertissement ; la mart des matchups écarte d'elle-même le duel concerné.

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

lol-meta-pipeline isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc.

*(Mention légale imposée par les [règles du portail développeur de Riot](https://developer.riotgames.com/policies/general), reprise mot pour mot.)*

- Données de compétition : [Oracle's Elixir](https://oracleselixir.com/). Une partie du contenu provient de [Leaguepedia](https://lol.fandom.com/), sous licence CC BY-SA 3.0.
- Seuls le code et des agrégats sont publiés. Les données brutes ne sont pas redistribuées, et aucun identifiant de joueur (puuid, pseudo) n'est stocké.
