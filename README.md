# lol-meta-pipeline

Pipeline de données sur la meta de *League of Legends* : quels champions, builds et runes performent par matchup et par patch, comment se jouent les timings d'avantage — et combien de temps met un pick vu en compétition professionnelle à descendre sur la ladder haut elo.

> **Les 9 étapes sont terminées (03/11/2026), et la collecte continue chaque jour.** Les trois sources sont chargées dans BigQuery par Airflow ; dbt en tire la meta pro et la meta du ladder par patch (champions, matchups, timings d'avantage, builds, runes, chaque taux de victoire avec sa fourchette de confiance) et la diffusion de la meta entre les deux. Les seuils de volume par matchup et les premiers délais de diffusion seront mesurés quand un patch complet du ladder aura été collecté.
>
> **Depuis le 04/11/2026 : vers un assistant pour les joueurs.** Le projet devient la base d'un outil d'aide aux joueurs, dans l'esprit de Blitz. Premier moteur construit : un **moteur théorique** qui lit les formules des sorts dans les fichiers du jeu et détecte, le jour même d'un patch, **ce qui a changé** — validé contre les notes de patch officielles.
>
> **Depuis le 06/11/2026 : les familles de builds.** Chaque objet terminé a une famille (critique, létalité, on-hit, AP, combattant, tank…), relue par un joueur expérimenté ; chaque build du ladder est classé par le vote de ses trois premiers objets. Le nombre de choix proposés pour un champion **sort des données** : un mage n'a qu'une famille, Varus en a deux (on-hit ou létalité).

## Sources

| Flux | Source | Cadence | Accès |
|---|---|---|---|
| Ladder EUW | API Riot Games (Challenger + Grandmaster, classée solo) | quotidienne | clé *personal* |
| Compétition pro | Oracle's Elixir | quotidienne | fichier public, via l'API Google Drive |
| Référentiel | Data Dragon (champions, objets, runes, temps de recharge et coûts des sorts) | à chaque patch | public, sans clé |
| Formules des sorts | CommunityDragon (fichiers du jeu extraits, **source communautaire, non officielle**) | à chaque patch | public, sans clé |

Le temps réel des matchs professionnels n'est pas accessible : il passe par un portail réservé aux équipes et partenaires de Riot. Oracle's Elixir en est lui-même en aval.

## Architecture

```
Data Dragon ──────┐
Oracle's Elixir ──┼──> Cloud Storage ──> BigQuery ─────────────> dbt ──────────────> BigQuery
API Riot ─────────┘    brut gzip,        lol_raw (permanent)      staging (vues)      lol_analytics
                       30 jours          lol_raw_ladder (60 j)    intermédiaire (vues)
                                                                 marts (tables), seeds relues

                Airflow (local, Docker) : un DAG par jour à 14 h 30 UTC
  [Data Dragon, Oracle's Elixir, ladder Riot, kits, stats d'objets] en parallèle
                                ->  dbt deps  ->  dbt build
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
| `mart_kit_value_changes` | Quels chiffres de sorts ont changé avec le patch (dégâts, temps de recharge, coûts) ? | patch × champion × touche × chiffre × rang |
| `mart_kit_part_changes` | Quels ratios et morceaux de formule ont été modifiés, ajoutés ou retirés ? | patch × champion × touche × morceau de formule |
| `mart_champion_stat_profile` | Avec quelles stats chaque champion grandit-il, et dans quelle proportion ? | patch × champion × stat |
| `mart_item_theory_value` | Que vaut chaque objet pour chaque champion, d'après ses ratios ? Qu'est-ce que le patch a changé ? | patch × champion × objet |
| `mart_ladder_build_families` | Quelles familles de builds (critique, létalité, AP, hybride…) pour ce champion, combien de parties, quel résultat ? Lesquelles sont de vrais choix ? | patch × poste × champion × famille |

Chaque taux de victoire du ladder est accompagné de sa **fourchette à 95 %** (`win_rate_low`, `win_rate_high`).

## Le moteur théorique : ce qui change d'un patch à l'autre

Le jour d'un nouveau patch, il n'existe encore aucune partie : un outil fondé sur les statistiques de jeu n'a rien de fiable à dire. Le moteur théorique part des **chiffres du jeu** eux-mêmes.

- **Les formules des sorts viennent des fichiers du jeu** (CommunityDragon) : Data Dragon, la source officielle, ne donne pas les ratios (champs vides, descriptions à trous). Chaque formule est un **arbre** (une somme de morceaux, un morceau multiplié par un autre…), aplati par une fonction récursive : 2 019 formules et 173 champions par patch, 0 morceau perdu (contrôle : autant de lignes que de nœuds typés dans le texte de chaque formule).
- **Les codes internes sont décodés et vérifiés** par une seconde source, avant d'être utilisés : `(2, 2)` = attaque bonus (le bouclier du W d'Ambessa : 50 → 320 selon le niveau, + 150 % de l'attaque bonus), code absent = puissance (le fichier omet les valeurs par défaut), `12` = PV, `1` = armure, `6` = résistance magique. Les autres codes restent marqués inconnus.
- **Chaque chiffre vient de la meilleure source pour lui** : formules et ratios depuis CommunityDragon, temps de recharge et coûts depuis Data Dragon. Le champ de temps de recharge le plus évident des fichiers du jeu (`cooldownTime`) **n'est plus à jour** : seule la confrontation aux notes de patch l'a révélé.
- **Validé contre les notes de patch officielles du 16.22 : les 14 champions annoncés sont détectés**, chiffre par chiffre (par exemple Kayle, Q : 12/11/10/9/8 s → 10/9,5/9/8,5/8 s, les rangs inchangés n'apparaissant pas). Le moteur relève aussi un changement **non annoncé** (le passif de Varus) et un faux positif connu (des formules d'Orianna renommées dans les fichiers), désormais reconnu quand le contenu est identique (54 renommages sur la saison).
- **22 patches de la saison chargés** (40 377 formules, 133 157 morceaux, 719 610 valeurs par rang, ~73 Mio) ; chaque jour, seuls les patches absents sont téléchargés.

**La valeur théorique des objets (version A)** : pour chaque champion, un **profil de sensibilité** — la somme de ses ratios par stat (ratios identiques d'un même sort comptés une fois ; ratios sous 0,01, d'une autre unité, écartés ; ratios par rang au rang maximum) — multiplié par les **stats de chaque objet** (lues dans les fichiers du jeu, plus complètes que Data Dragon : 1 174 recoupements, 0 écart), pour 1 000 pièces d'or. Le moteur traduit ainsi un changement d'objet en « pour qui il devient meilleur » : au 16.22, le Lien de sang du suzerain passe de 30 à 40 d'attaque (annoncé dans les notes), et ressort comme la plus forte variation, pour Pyke, Naafiri, Corki… Limite assumée : seules les stats des ratios comptent (pas encore les PV, l'accélération de compétence ni les passifs des objets) ; les classements sont donc naïfs pour les combattants.

Prochaines étapes : valoriser les stats « universelles » selon le rôle du champion ; combiner théorie et parties jouées (la théorie pèse le plus au début d'un patch, quand les parties manquent et que beaucoup de joueurs gardent leurs anciens builds) ; puis confronter la théorie aux parties réellement jouées.

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

**Des objets fantômes.** Data Dragon marque 33 objets à identifiant à 6 chiffres (323003 pour le Bâton de l'archange 3003…) comme achetables sur la Faille. Ce sont des variantes d'autres modes : **0 achat sur 403 603** dans le ladder. Ils faisaient pourtant 21 % des lignes de la valeur théorique au 16.22, et occupaient 149 places dans des top 5 (le n° 1 théorique de Jinx en était un). Ils sont écartés, et un test refait la mesure à chaque build : si un vrai objet de la Faille recevait un jour un identifiant à 6 chiffres, il serait signalé au lieu d'être perdu.

**Les familles de builds : une seed relue, un vote simple.** Les étiquettes officielles des objets sont imprécises (le Couperet noir est étiqueté comme un objet de létalité et d'on-hit), et la létalité n'apparaît pas dans les stats des fichiers du jeu. La famille de chaque objet est donc une **seed** : pré-remplie par des règles sur les étiquettes et les stats, puis **relue en entier par un joueur expérimenté**, qui a corrigé 17 cas douteux et montré qu'un objet peut avoir plusieurs familles (une principale, des secondaires). Un build est classé par la famille majoritaire de ses trois premiers objets terminés ; sans majorité, « hybride » s'il mélange AD et AP, sinon la famille du premier objet. Une famille devient un **choix** à partir de 10 parties ; le nombre de parties est toujours affiché, et les choix sont classés par le **bas de leur fourchette**, pour qu'un 80 % sur 10 parties ne passe pas devant un 54 % sur 500. Une règle d'« objet signature » a été essayée puis retirée : elle corrigeait un champion (Ezreal) mais en reclassait deux autres à tort (173 builds de Jayce et de Varus) — mesuré sur tous les builds réels, pas seulement sur le cas qui l'avait fait naître.

**Une couche intermédiaire, pour écrire une règle une seule fois.** L'ordre d'achat des objets (achats annulés exclus) sert à deux marts : il vit dans un modèle intermédiaire partagé. Après ce déplacement, `mart_ladder_builds` a été comparé à sa version précédente : 5 533 lignes de chaque côté, **0 différence**.

**Des tests qu'on a vus échouer.** Les nouveaux tests ont d'abord été lancés contre une version sabotée exprès (une famille retirée, une faute de frappe, une majorité à 3 objets au lieu de 2) : chacun a échoué là où il devait, puis est passé sur la version juste. Un test qu'on n'a jamais vu échouer ne prouve pas qu'il détecte le problème.

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

Volume par partie du ladder, mesuré sur le premier run réel : ~70 Ko dans BigQuery, ~67 Ko compressés dans le bucket. À 800 parties par jour (le plafond actuel), la rétention de 60 jours tient en ~3,4 Go dans BigQuery, et celle de 30 jours en ~1,6 Go dans le bucket : toujours dans le free tier.

**Le run quotidien, mesuré le 06/11/2026** : 800 parties (le plafond ; 844 disponibles), **2 602 requêtes à Riot, 0 refus 429, 0 panne**. La collecte dure 51 min 52 s, dont 2 300 s d'attente du limiteur sur la route `europe` : c'est le quota de la clé, pas le code, qui fixe la durée. Puis `dbt build` : 3 min 17 s, 129 nœuds, **127 PASS, 2 avertissements connus, 0 erreur**.

## Limites

- **Airflow tourne en local** : la collecte n'a lieu que si le PC est allumé à 14 h 30 UTC. La fenêtre de 2 jours absorbe un jour manqué ; au-delà, des parties sont perdues.
- **Un échantillon, pas tout le ladder.** La clé *personal* autorise 100 requêtes par 2 minutes : jusqu'à 800 nouvelles parties par jour (environ 52 minutes de collecte), à partir des 1 000 joueurs Challenger et Grandmaster. Les parties sont celles de joueurs du haut du classement, pas un tirage aléatoire.
- **La diffusion de la meta est censurée à gauche.** La ladder n'est collectée que depuis le patch 16.21 ; aucun délai n'est mesurable tant qu'un champion n'est pas entré dans la meta pendant la fenêtre observée. Le pro, lui, saute des patches (aucun match au 16.19) : un délai en patches se lit avec ça en tête.
- **Les seuils viennent d'un premier échantillon** (parties ≥ 15 min, objets ≥ 2 000 po) et seront revérifiés sur un patch complet. Aucun seuil de volume n'est encore imposé aux matchups : chaque taux est publié avec sa fourchette de confiance, qui dit elle-même quand un effectif est trop faible.
- **Une adresse de l'API injoignable** depuis le réseau local (cause inconnue) : contournée par une connexion réutilisée, pas résolue.
- **Les plaques de tourelle** ne suivent pas la règle connue (jusqu'à 15 par équipe et par voie, jusqu'à la minute 36) : collectées, mais utilisées par aucune mart tant que la mécanique n'est pas vérifiée.
- **Les données pro** dépendent d'Oracle's Elixir : certains matchs sont incomplets (écart d'or à 15 minutes manquant pour 1 740 lignes joueurs).
- **Les formules des sorts viennent d'une source communautaire** (CommunityDragon), non officielle : à valider avant toute demande de clé de production. Une formule seulement renommée (contenu identique) est reconnue comme telle ; si Riot la renomme **et** en change la structure, elle reste signalée comme un retrait plus un ajout.
- **La létalité n'est pas valorisée par le moteur théorique** : elle n'apparaît pas dans les stats des objets des fichiers du jeu (seulement sur d'anciens objets d'Arena). Les objets de létalité ne sont reconnus que par l'étiquette de Riot, pour les familles.
- **La famille d'un objet ne dépend pas de qui l'achète.** La Force de la trinité est un objet de combattant : le build d'Ezreal (Trinité, Manamune, Faim insatiable) est donc classé « combattant », alors qu'un joueur dirait « Ezreal Manamune ». Choix assumé (la règle qui corrigeait ce cas en cassait d'autres).
- **Peu de choix par champion pour l'instant** : au 16.22, après le run du 06/11, 42 couples champion × poste ont deux familles à 10 parties ou plus, et 2 en ont trois (Jax TOP : combattant, AP, hybride ; Sona support : enchanteur, tank, AP). La veille, 16 couples en avaient deux et aucun trois. Ce n'est pas l'algorithme mais le volume : il grandit chaque jour.
- **Un poste peut manquer.** Riot laisse le poste vide quand il ne sait pas déduire le rôle d'un joueur (1 ligne sur 2 890 au 03/11, dans une partie finie à 15 min 32 s). Un test le signale en avertissement ; la mart des matchups écarte d'elle-même le duel concerné.

## Structure

```
ingestion/        Data Dragon, Oracle's Elixir, client Riot (limiteur), collecteur du ladder,
                  kits des champions (formules des sorts, CommunityDragon)
infra/terraform/  bucket, datasets, compte de service, IAM minimal
airflow/          image, docker-compose, DAG quotidien lol_daily
dbt/              staging (vues) -> intermédiaire (vues) -> marts (tables), seeds
                  relues (codes de stats, familles d'objets), tests de données
tests/            pytest hors ligne : faux clients HTTP, BigQuery et Storage
prototypes/       essais : LLM local (Ollama) qui appelle un outil sur un mart ;
                  pré-classement des familles d'objets avant relecture
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
