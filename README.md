# lol-meta-pipeline

Pipeline de données sur la meta de *League of Legends* : quels champions, builds et runes performent par matchup et par patch, comment se jouent les timings d'avantage — et combien de temps met un pick vu en compétition professionnelle à descendre sur la ladder haut elo.

> **Les 9 étapes sont terminées (03/11/2026), et la collecte continue chaque jour.** Les trois sources sont chargées dans BigQuery par Airflow ; dbt en tire la meta pro et la meta du ladder par patch (champions, matchups, timings d'avantage, builds, runes, chaque taux de victoire avec sa fourchette de confiance) et la diffusion de la meta entre les deux. Les seuils de volume par matchup et les premiers délais de diffusion seront mesurés quand un patch complet du ladder aura été collecté.
>
> **Depuis le 04/11/2026 : vers un assistant pour les joueurs.** Le projet devient la base d'un outil d'aide aux joueurs, dans l'esprit de Blitz. Premier moteur construit : un **moteur théorique** qui lit les formules des sorts dans les fichiers du jeu et détecte, le jour même d'un patch, **ce qui a changé** — validé contre les notes de patch officielles.
>
> **Depuis le 06/11/2026 : les familles de builds.** Chaque objet terminé a une famille (critique, létalité, on-hit, AP, combattant, tank…), relue par un joueur expérimenté ; chaque build du ladder est classé par le vote de ses trois premiers objets. Le nombre de choix proposés pour un champion **sort des données** : un mage n'a qu'une famille, Varus en a deux (on-hit ou létalité).
>
> **Depuis le 06/11/2026 : un bulletin de patch.** Trois mesures, recalculées à chaque patch, disent si l'on peut croire les builds : la fidélité de notre lecture des achats, le duel entre le build le plus joué et sa meilleure alternative, et l'« expérience naturelle » du patch (le moteur théorique prédit le sens d'un changement de Riot, le ladder confirme ou contredit).
>
> **Depuis le 09/11/2026 : vers un simulateur de combat.** Le but : proposer un build à partir des stats des champions et des objets (stats pures, effets, coût). Étape 1 terminée (16/11) : les stats de chaque champion à chaque niveau, lues dans les fichiers du jeu et vérifiées sur les vraies parties. Étape 2 en cours : le mannequin (attaques de base simulées ; **99 % des formules de dégâts des sorts calculées** ; le coup de sort entier, vérifié sur 3 875 vrais coups).
>
> **Depuis le 18/11/2026 : la collecte ne dépend plus du PC.** Un job Cloud Run, réveillé chaque jour par Cloud Scheduler, fait tout le run quotidien (collectes puis `dbt build`), décrit en Terraform, sans fichier de clé de compte de service, pour environ 0 € par mois. Un courriel part si le run échoue.
>
> **Depuis le 18/11/2026 : prédire un patch avant sa sortie.** Le serveur de test de Riot (PBE) prépare le patch suivant pendant deux semaines. Un aperçu de ses fichiers, chargé à part, passe dans le moteur théorique : les prédictions sont écrites et **datées** dans [`predictions/`](predictions/) avant la sortie, avec la façon dont elles seront jugées. Nom retenu pour le futur produit : **Farsight** (l'altération de longue-vue : voir loin, avant les statistiques).

## Sources

| Flux | Source | Cadence | Accès |
|---|---|---|---|
| Ladder EUW | API Riot Games (Challenger + Grandmaster, classée solo) | quotidienne | clé *personal* |
| Compétition pro | Oracle's Elixir | quotidienne | fichier public, via l'API Google Drive |
| Référentiel | Data Dragon (champions, objets, runes, temps de recharge et coûts des sorts) | à chaque patch | public, sans clé |
| Formules des sorts, stats des champions et des objets | CommunityDragon (fichiers du jeu extraits, **source communautaire, non officielle**) | à chaque patch | public, sans clé |

Le temps réel des matchs professionnels n'est pas accessible : il passe par un portail réservé aux équipes et partenaires de Riot. Oracle's Elixir en est lui-même en aval.

## Architecture

```
Data Dragon ──────┐
Oracle's Elixir ──┼──> Cloud Storage ──> BigQuery ─────────────> dbt ──────────────> BigQuery
API Riot ─────────┘    brut gzip,        lol_raw (permanent)      staging (vues)      lol_analytics
                       30 jours          lol_raw_ladder (60 j)    intermédiaire (vues)
                                                                 marts (tables), seeds relues

     Cloud Scheduler (14 h 30 UTC) -> job Cloud Run lol-quotidien (image Docker)
  ingestion/quotidien.py : Data Dragon, kits, stats d'objets, ladder Riot, Oracle's Elixir
           (chacune avec ses relances)  ->  dbt build (cible prod)
           clé Riot lue dans Secret Manager ; courriel d'alerte si un run échoue

  (Airflow, en local, est gardé en pause : retour possible au PC si besoin.)

  À la main : ingestion/pbe.py -> lol_raw.pbe_*  ->  dbt (cible pbe) -> lol_analytics_pbe
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
| 10 | Collecte sortie du PC : job Cloud Run + Cloud Scheduler + Secret Manager + alerte, en Terraform | ✅ 18/11 |
| 11 | Aperçu du PBE et prédictions datées avant la sortie d'un patch | ✅ 18/11 (première prédiction) |
| 12 | Assistant local (modèle de langage sur le PC, Ollama) branché sur les marts par des outils testés | ✅ 23/11 (premiers essais) |

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
| `mart_champion_stat_profile` | Avec quelles stats chaque champion grandit-il, et dans quelle proportion ? Pour ses dégâts, et pour sa survie ? | patch × champion × valeur × stat |
| `mart_item_theory_value` | Que vaut chaque objet pour chaque champion, d'après ses ratios, en dégâts et en survie ? Qu'est-ce que le patch a changé ? | patch × champion × valeur × objet |
| `mart_ladder_build_families` | Quelles familles de builds (critique, létalité, AP, hybride…) pour ce champion, combien de parties, quel résultat ? Lesquelles sont de vrais choix ? | patch × poste × champion × famille |
| `mart_ladder_build_fidelity` | Lit-on bien les builds ? Les 3 premiers objets achetés sont-ils dans l'inventaire de fin de partie ? | patch |
| `mart_ladder_build_duels` | Le build le plus joué gagne-t-il plus que sa meilleure alternative ? Confirmé, pépite ou non départagé | patch × poste × champion × niveau (famille ou chemin) |
| `mart_patch_predictions` | Que prédit la théorie, le jour du patch et avant toute partie, pour chaque objet ou champion changé ? | patch × sujet |
| `mart_patch_experiments` | Le ladder a-t-il bougé dans le sens prédit (part de jeu, victoires) ? | patch × sujet |
| `mart_patch_bulletin` | Le résumé des trois mesures du bulletin | patch |

Chaque taux de victoire du ladder est accompagné de sa **fourchette à 95 %** (`win_rate_low`, `win_rate_high`).

## Le moteur théorique : ce qui change d'un patch à l'autre

Le jour d'un nouveau patch, il n'existe encore aucune partie : un outil fondé sur les statistiques de jeu n'a rien de fiable à dire. Le moteur théorique part des **chiffres du jeu** eux-mêmes.

- **Les formules des sorts viennent des fichiers du jeu** (CommunityDragon) : Data Dragon, la source officielle, ne donne pas les ratios (champs vides, descriptions à trous). Chaque formule est un **arbre** (une somme de morceaux, un morceau multiplié par un autre…), aplati par une fonction récursive : 2 019 formules et 173 champions par patch, 0 morceau perdu (contrôle : autant de lignes que de nœuds typés dans le texte de chaque formule).
- **Les codes internes sont décodés et vérifiés** par une seconde source, avant d'être utilisés : `(2, 2)` = attaque bonus (le bouclier du W d'Ambessa : 50 → 320 selon le niveau, + 150 % de l'attaque bonus), code absent = puissance (le fichier omet les valeurs par défaut), `12` = PV, `1` = armure, `6` = résistance magique. Depuis le 19/11, aussi la **vitesse d'attaque bonus** `(4, 2)`, les **chances** `(8, 0)` et **dégâts critiques** `(9, 0)` et la **létalité** `(29, 0)`, décodés pour le simulateur (noms des formules, infobulles, forme des calculs) : +50 lignes au profil des champions au 16.23, et trois changements de Riot jusque-là invisibles sont prédits (Caitlyn et Bastionbreaker au 16.21, Varus au 16.22 : son passif « vitesse d'attaque → AD » passe de 33 à 42). Les autres codes restent marqués inconnus.
- **Chaque chiffre vient de la meilleure source pour lui** : formules et ratios depuis CommunityDragon, temps de recharge et coûts depuis Data Dragon. Le champ de temps de recharge le plus évident des fichiers du jeu (`cooldownTime`) **n'est plus à jour** : seule la confrontation aux notes de patch l'a révélé.
- **Validé contre les notes de patch officielles du 16.22 : les 14 champions annoncés sont détectés**, chiffre par chiffre (par exemple Kayle, Q : 12/11/10/9/8 s → 10/9,5/9/8,5/8 s, les rangs inchangés n'apparaissant pas). Le moteur relève aussi un changement **non annoncé** (le passif de Varus) et un faux positif connu (des formules d'Orianna renommées dans les fichiers), désormais reconnu quand le contenu est identique (54 renommages sur la saison).
- **22 patches de la saison chargés** (40 377 formules, 133 157 morceaux, 719 610 valeurs par rang, ~73 Mio) ; chaque jour, seuls les patches absents sont téléchargés.

**La valeur théorique des objets (version A)** : pour chaque champion, un **profil de sensibilité** — la somme de ses ratios par stat (ratios identiques d'un même sort comptés une fois ; ratios sous 0,01, d'une autre unité, écartés ; ratios par rang au rang maximum) — multiplié par les **stats de chaque objet** (lues dans les fichiers du jeu, plus complètes que Data Dragon : 1 174 recoupements, 0 écart), pour 1 000 pièces d'or. Le moteur traduit ainsi un changement d'objet en « pour qui il devient meilleur » : au 16.22, le Lien de sang du suzerain passe de 30 à 40 d'attaque (annoncé dans les notes), et ressort comme la plus forte variation, pour Pyke, Naafiri, Corki… Limite assumée : seules les stats des ratios comptent (pas encore les PV, l'accélération de compétence ni les passifs des objets) ; les classements sont donc naïfs pour les combattants.

**Sans la survie (depuis le 19/11)** : le profil ne compte plus les ratios des formules que l'infobulle désigne **clairement** comme de la survie (bouclier, soin, PV de soin, vitesse), sauf si la même formule est aussi balisée dégâts (un drain reste compté). Les PV de Tibbers, à ratio d'AP, faisaient d'Annie une acheteuse d'objets PV. Une formule absente des infobulles reste comptée : retirer tout ce qui n'est pas clairement des dégâts cassait une vingtaine de champions (Gnar, Jayce, Nidalee… : formules des deux formes, absentes des infobulles). Mesuré au 16.23 : **151 top 5 sur 173 inchangés** ; Annie, Mordekaiser, Maître Yi, Gangplank et K'Santé corrigés. Test unitaire écrit d'abord (Annie au 16.23 : dégâts, PV de Tibbers, bouclier, drain, vitesse, formule sans infobulle), 5 sabotages attrapés.

**Deux valeurs, dégâts et survie (19/11)** : ces ratios de survie ne sont plus jetés, ils forment un **second profil**. Chaque objet a donc deux valeurs pour chaque champion, jamais additionnées, chacune avec son classement : au 16.23, Annie appelle Rabadon et l'Écho de Luden pour ses dégâts, Warmog et Cœuracier pour sa survie (les PV de Tibbers). 80 champions ont un profil de survie. Une prédiction de champion suit ses dégâts s'ils bougent, **sinon sa survie** : **13 changements de Riot qui ne touchent que la survie sont de nouveau prédits**, à part, sur la saison, dont Annie et Galio au 16.23 (Annie : part de jeu de 0,25 % à 0,66 %, confirmée par le ladder sur les premières parties du patch ; Galio dans le sens prédit, pas encore prouvé). Un objet reste jugé sur les dégâts. Les arrondis du profil (4 décimales) ne sont pas cosmétiques : sans eux, une somme de nombres à virgule calculée dans un autre ordre faisait bouger la survie de Locke de 0,01 sans que rien ne change, soit une fausse prédiction (vu en mesurant). **En prod depuis le run du 21/11** (image `4`) : 167 prédictions, dont les 13 « survie », identiques à celles mesurées en dev ; runs des 21 et 22/11 réussis (779 et 759 parties, `dbt build` 244 PASS, 2 avertissements connus, 0 erreur).

**La version B, la valeur en or utile (en dev seulement, 09/11)** : une seule unité, l'or. Le prix d'un point de chaque stat vient de la boutique : l'objet de base le moins cher qui ne donne que cette stat (Épée longue : 35 or le point d'AD ; Cristal de saphir : 1 or le point de mana). Ce prix est en prod. Chaque stat d'un objet compte ensuite **seulement si elle sert au champion**, selon sa classe et ses ratios. Les top 5 s'améliorent nettement (Ambessa : Couperet noir au lieu d'objets de tireur ; Malphite et Leona : Convergence de Zeke au lieu de Rabadon). Mais la relecture par un joueur expérimenté a montré les limites d'une addition de stats : la classe est trop grossière (un combattant peut être AD ou AP), et les effets des objets ne comptent pas. D'où le simulateur, plus bas. Ce brouillon reste en dev : une règle de `dbt_project.yml` l'exclut de la prod, qui lit le dossier dbt tel quel.

## Le bulletin de patch : prouver les builds par les chiffres

La popularité s'auto-entretient : beaucoup de joueurs copient la même tier list, et « populaire » ne veut pas dire « bon ». Le bulletin cherche des juges qui ne copient personne. Il est recalculé à chaque patch, une ligne par patch dans `mart_patch_bulletin`.

1. **La fidélité des builds.** Deux sources de Riot indépendantes : les achats horodatés de la timeline (d'où vient l'ordre d'achat) et l'inventaire de fin de partie. Sur les 3 premiers objets terminés : **99,84 % retrouvés au 16.21, 99,79 % au 16.22** (36 571 objets, mesure du 06/11). Les objets qui se transforment (Manamune → Muramana…) comptent comme retrouvés, grâce à une seed de 3 lignes tirée du champ `specialRecipe` de Data Dragon ; sans elle, ~98 %. Un test avertit sous 99 % (à partir de 1 000 objets) et la mart nomme les objets les plus souvent absents : Manamune retiré exprès de la seed, l'alerte sonne et désigne « Manamune (450) ».
2. **Le build populaire contre la meilleure alternative.** Pour chaque champion à son poste, au niveau de la famille et du chemin, le build le plus joué affronte la meilleure alternative jouée au moins 10 fois. Trois verdicts, avec les fourchettes de Wilson : **confirmé** (le bas de la fourchette du populaire dépasse le haut de toutes les autres), **pépite** (le bas d'une alternative dépasse le haut du populaire), **non départagé** (les fourchettes se chevauchent).
3. **L'expérience naturelle du patch.** Quand Riot change un objet ou un kit, le moteur théorique prédit le sens (la valeur monte ou baisse) **le jour du patch, avant toute partie**. Le ladder dit ensuite si la part de jeu et les victoires ont suivi. C'est le juge le plus fort : il teste la cause (le changement de Riot), pas l'effet de troupeau. Les deux causes sont séparées : un champion dont le kit a changé est écarté des concernés d'un objet changé. Depuis la valeur survie (19/11), un kit qui ne change que la survie compte aussi : trois expériences d'objets de la saison contenaient un champion dont seul le bouclier ou le soin avait changé (Hubris au 16.05 avec Nunu, Mandat impérial au 16.11 avec Diana, Ceinture-roquette au 16.14 avec Senna) ; il en est retiré.

**Ce que les premiers patches ont appris :**
- **La plupart des duels ne sont pas encore départagés**, faute de parties. Au 16.22 (run du 06/11), 3 duels sur 117 seulement l'étaient (Jhin BOTTOM : critique 208 parties à 54 %, contre létalité 41 parties à 32 %).
- **Les verdicts bougent beaucoup en début de patch.** Entre les runs du 07 et du 08/11, 3 « confirmés » sur 4 sont redevenus non départagés, et deux pépites se sont évaporées (Renata Glasc : 10 victoires sur 11, puis 12 sur 17 ; c'est le retour vers la moyenne). Règle recommandée, pas encore décidée : n'afficher un verdict aux joueurs que s'il tient au patch suivant.
- **Le bulletin montre où la théorie est aveugle.** Au 16.22, le moteur prédisait une baisse de Mel ; le ladder montre une forte hausse, prouvée. La cause : Riot a baissé ses coûts en mana et ses temps de recharge, que la version A ne voit pas, et a restructuré les formules de son Q. Ce n'est pas un échec du bulletin, c'est son rôle.

## Vers un simulateur de combat

Additionner des stats ne suffit pas : un objet a des effets, et un champion n'a pas les mêmes stats au niveau 1 et au niveau 11. Le but fixé : un moteur qui propose un build à partir des stats des champions et des objets, **stats pures, effets et coût**. Le plan : simuler un combat contre un mannequin, comme dans l'outil d'entraînement, mais en calcul. Quatre étapes : les données ; un mannequin sans effets ; les effets des objets, **lus automatiquement** dans les textes de Riot (un catalogue écrit à la main vieillirait à chaque saison) ; puis des scénarios tirés du ladder et un build construit objet par objet. Le ladder sert de juge.

**Étape 1, terminée (16/11) : les stats de chaque champion, à chaque niveau.**
- **La source** : la fiche du champion dans le fichier du jeu (CommunityDragon), déjà téléchargé pour les kits. Data Dragon, la source officielle, n'a pas le ratio de vitesse d'attaque (0 pour Jhin, dont la vitesse d'attaque ne grandit pas comme celle des autres), et **donne 0 d'AD par niveau à tous les champions depuis le 16.5**.
- **Riot a renommé les champs au 16.5** (`baseHP` → `baseHPModifiable`, `baseSpellBlock` → `baseMR`…), et certains arrivent **hachés** (`{01262a25}`). Un nom haché est l'empreinte FNV-1a 32 bits du nom en minuscules : FNV-1a(`mrperlevel`) = `01262a25`, vérifié en calculant. CommunityDragon remplace l'empreinte par le nom quand il le trouve (au 16.16 pour celui-ci). Le 16.5 est aussi le patch où l'AD par niveau de Data Dragon tombe à 0 : son générateur cherchait probablement encore l'ancien nom.
- **Le brut garde tout, sous le nom du fichier** (186 282 nombres, 22 patches). Une seed traduit chaque orthographe connue (45) vers 21 stats, et prévoit déjà le nom en clair des 4 empreintes pas encore décodées.
- **Recoupé avec Data Dragon sur les 22 patches** (~60 000 comparaisons) : identique à 3 exceptions près, en début de saison, sauf l'AD par niveau.
- **Un champ absent n'est pas toujours 0** : il prend la valeur par défaut du jeu. Mettre 0 partout aurait donné 0 régénération de PV à Zac (le jeu : 1 PV par seconde) et 0 de fureur maximale à Tryndamere (le jeu : 100), sans aucune erreur visible.
- **La fiche complète** (`int_champions__base_stats`, une ligne par champion et par patch, 3 794 lignes) : les stats en colonnes, les valeurs par défaut du jeu. **Un nouveau renommage de Riot ne passera pas en silence** : une stat obligatoire vide fait échouer un test ; une stat qui disparaît d'un patch au suivant déclenche un avertissement. C'est le seul test qui voit le renommage d'une stat à valeur par défaut, car le 0 boucherait le trou sans laisser de case vide (vérifié par sabotage : 171 champions signalés).
- **Les stats à chaque niveau** (`int_champions__stats_by_level`, 75 880 lignes, niveaux 1 à 20) : la croissance de LoL n'est pas une ligne droite. Le gain arrive plus tard : Ahri au niveau 6 a 1 000,8 PV, et non 1 110.
  - **La formule est vérifiée sur les vraies parties, pas sur la parole du wiki.** Les timelines brutes donnent, chaque minute, les vraies stats de chaque joueur. Sur 1 500 parties, la valeur la plus fréquente par champion et par niveau tombe sur la courbe de LoL dans 94 % des cas (armure et RM), contre moins de 1 % pour une ligne droite ; 140 champions sur 164 n'ont aucun écart.
  - L'écart le plus net (Jhin, +8 d'armure et de RM à tous les niveaux) venait d'un objet de départ, trouvé dans les achats : 75 % des Jhin commencent par le Heaume de Doran.
  - **Les niveaux 19 et 20 existent** pour les joueurs du haut (1 984 fins de partie au 16.22), et la courbe continue après 18 : mesuré, pas supposé.

**Étape 2, en cours : le mannequin sans effets** (Python, dossier `simulateur/`). Un combat se déroule dans le temps (coups, temps de recharge, mana) : il est simulé en Python, à partir des données que dbt prépare. Des fonctions pures, testées une à une (tests écrits d'abord, sabotages vus échouer) :
- **la part des dégâts qui passe l'armure**, 100 / (100 + armure) : vérifiée sur 31 160 attaques de base réelles (les récapitulatifs de mort donnent chaque coup reçu). La formule gagne dans toutes les tranches d'armure, loin devant les autres essayées ;
- **la pénétration** (le % d'abord, puis la létalité, jamais sous 0) : tirée du wiki, **pas mesurable avec nos données**, car l'API ne montre pas la létalité. Le code le dit ;
- **les stats avec objets** : 12 stats additionnées, les % de pénétration multipliés, 11 stats ignorées exprès ; **une stat d'objet inconnue lève une erreur** au lieu d'être perdue ;
- **le critique, mesuré** : les coups critiques ont leur propre nom dans le récapitulatif de mort. Le pic est à 200 % (et vers 230 % avec la Lame d'infini, qui donne +30 %). Le fichier du jeu le dit aussi, et connaît le cas d'Ashe (100 %) ;
- **les dégâts par seconde et le temps pour tuer** avec les attaques de base : les coups tombent un par un, le premier tout de suite. Jinx niveau 11 (Lame d'infini, Lord Dominik, Dague) tue Zed niveau 11 sans objet en 7 coups, 8,1 s.

- **les formules des sorts, évaluées** (`simulateur/sorts.py`) : une fonction récursive parcourt l'arbre de chaque formule (sommes, produits, ratios de stats, valeurs par rang, valeurs selon le niveau, paliers) ; un morceau inconnu lève une erreur. **99 % des formules de dégâts sont calculables au 16.23** (90 % le 17/11 ; détail ci-dessous) ;
- **lesquels des calculs d'un sort sont des dégâts, et de quel type** : lus dans le **texte du jeu** (les infobulles, CommunityDragon), où chaque nombre est entouré d'une balise (`magicDamage`, `physicalDamage`, `trueDamage`, ou bouclier, soin…). La balise **la plus proche** compte (une pile, pas une expression régulière : la première version prenait la balise extérieure et trouvait 962 faux désaccords). Même type que Data Dragon pour **1 028 formules sur 1 028** ; une formule peut avoir deux types (Ahri Q : magique à l'aller, brut au retour) ;
- **« 9 % de quoi ? »** : pour une formule affichée en pourcentage, les mots qui suivent le nombre dans l'infobulle disent ce qu'il multiplie (`scales_with`) : **PV max, PV manquants, PV actuels** de la cible, ou autre chose. Au 16.22 et au 16.23 : 69 formules en pourcentage, **47 PV max, 7 PV manquants, 5 PV actuels, 10 autres** (AD bonus de Jhin, Grit de Sett…). Une erreur connue : Udyr Q2, dont l'infobulle dit « max Health damage » **avant** le nombre.

- **de 90 % à 99 % en une soirée (18/11)**, chaque ajout prouvé avant d'être écrit :
  - **quatre codes de stats décodés** (vitesse d'attaque bonus, chances et dégâts critiques, létalité) par deux indices indépendants (le nom des formules, écrit par Riot, et les mots des infobulles), puis par la forme des calculs : le Q de Sivir multiplie ses dégâts par 1 + X × chances × (dégâts critiques − 1), la formule exacte du critique en moyenne ; le passif de Varus prouve que la vitesse d'attaque bonus est une fraction (en %, il donnerait 2 100 d'AD). Les codes douteux restent des erreurs, jamais de faux nombres ;
  - **les compteurs de cumuls** (Q de Nasus, âmes de Thresh…) : le nombre de cumuls n'est pas dans les fichiers du jeu, c'est un réglage de scénario ; absent, il lève une erreur qui le nomme ;
  - **le mana**, total ou bonus (Ryze : % du mana bonus ; Kassadin : % du mana max) ;
  - **la casse des noms** : le jeu chiffre ses noms en minuscules, `BADRatio` et `bADRatio` sont le même nom pour lui ; deux valeurs qui ne diffèrent que par la casse lèvent une erreur ;
  - **une progression du niveau 1 au niveau 18 entre deux valeurs** (un type de morceau au nom chiffré) : en ligne droite, d'après le texte source du wiki (« 1.5 + (3-1.5)/17*(x-1) » pour l'éclair d'Udyr) ;
- **le coup de sort entier** (`simulateur/degats.py`) : la valeur de la formule, multipliée par ce qu'elle vise (PV max, manquants ou actuels de la cible), puis par la part qui passe l'armure ou la RM après pénétration ; les dégâts bruts passent tout. **Vérifié sur 3 875 vrais coups** (récapitulatifs de mort de 300 parties du 16.22 ; stats de l'attaquant et de la victime identiques dans les photos d'avant et d'après le coup) : le pic du rapport observé / prédit est à 0,99–1,00, et les sorts simples collent (R de Leona : 73 % des coups à ±2 %). Le léger décalage vient du jeu, qui **tronque** les dégâts affichés : pour **506 coups, la prédiction tronquée est exacte au point près**. Les grands écarts ont des causes nommées : dégâts sur la durée (comptés tick par tick), attaques renforcées, cumuls. **Depuis le 23/11, un coup est reconnu par le nom de son sort, pas par son emplacement** : le récapitulatif de Riot range parfois un sort dans le mauvais emplacement (le W de Kennen, `KennenBringTheLight`, dans celui du Q), alors que le nom est exactement celui du kit. Sur les mêmes parties : 3 097 coups retenus, **28,3 % à ±2 %** (23,3 % avant), et 5,3 % sur un multiple exact de la prédiction (plusieurs coups additionnés dans une même ligne du récapitulatif).

Reste à faire pour l'étape 2 : les anciennes « valeurs d'effet » (5 formules), les sorts à plusieurs coups et sur la durée, puis les effets des objets.

## Prédire un patch avant sa sortie : le PBE

Le bulletin juge le moteur théorique **après** un patch. Le PBE, le serveur de test de Riot, permet de prédire **avant** : le patch suivant y est testé environ deux semaines, et CommunityDragon publie ses fichiers dans un dossier `pbe`.

- **Un aperçu, jamais dans les vraies tables.** `ingestion/pbe.py` (lancé à la main) lit le numéro du patch que prépare le PBE, télécharge les valeurs et formules des sorts, leurs infobulles (depuis le 20/11) et les stats des objets **avec les mêmes fonctions que la collecte normale**, et les charge dans des tables à part (`lol_raw.pbe_*`), **remplacées** à chaque fois. Charger le PBE sous le nom « 16.24 » dans les vraies tables aurait été un piège : la collecte saute les patches déjà en base, le vrai 16.24 aurait été ignoré à sa sortie. Il refuse un patch déjà sorti, et un aperçu vide avant tout chargement.
- **Un mode aperçu dans dbt, à part.** Une macro (`source_avec_apercu_pbe`), appelée dans le `FROM` de 7 modèles de staging, renvoie la vraie table seule en dev et en prod. Avec la cible dbt `pbe` (son propre dataset, `lol_analytics_pbe`), elle ajoute l'aperçu comme un patch ordinaire ; le vrai patch, une fois sorti, gagne toujours. Data Dragon ne publiant un patch qu'à sa sortie, son dernier patch est emprunté — le dernier **par numéro** (16.23 > 16.9), pas par texte. Les tables sont collées **par nom de colonne** (`UNION ALL CORRESPONDING`), pas par position.
- **Des prédictions datées, jugées d'après une règle fixée d'avance.** Chaque aperçu ajoute une section à `predictions/<patch>.md` : date, version exacte du PBE, ce qui change, la prédiction, et ce qu'on peut espérer trancher. Le juge est `mart_patch_experiments` (part de jeu et victoires, fourchettes de Wilson séparées, référence « rien ne change »). On ne réécrit jamais une prédiction passée.
- **Premier aperçu (18/11, 16.24)** : le cycle de test commence, **un seul champion change** (Akshan : ratio d'AD du Q 0,70 → 0,80), aucun objet. Contrôle dans BigQuery : formules et objets identiques au 16.23, 6 valeurs de plus (Akshan). **Prédiction : Akshan en hausse (+3,7 % de valeur pour ses objets).** Akshan est rare (0,35 % des joueurs au 16.22) : sa part de jeu pourra se juger (fourchette ~±0,03 point sur un patch complet), son taux de victoire probablement pas (~±5 points).
- **Deuxième aperçu (20/11, nouvelle version du PBE)** : toujours le seul Q d'Akshan. **Prédiction : hausse, +4,3 %** : même changement, mais le moteur a changé entre-temps (nouveaux codes de stats, survie à part), la base de sa valeur dégâts est plus petite. **Un défaut trouvé avant d'écrire la prédiction** : le premier calcul donnait 77 prédictions, presque toutes en hausse (Shen +1 402 %), sur les champions à boucliers et soins. L'aperçu ne chargeait pas les infobulles du PBE (inutiles avant la valeur survie) : aucune formule n'était reconnue comme de la survie, toute la survie passait dans les dégâts, et le build restait vert. Corrigé : l'aperçu charge les infobulles du PBE (34 659 lignes), tests d'abord, 4 sabotages attrapés. Et un **garde-fou** fait maintenant échouer le build si un patch a des formules sans infobulles (vérifié : il attrape l'aperçu fautif ; en prod, 23 patches sur 23 ont leurs infobulles). **En prod depuis le 23/11 (image `5`)**, avant la sortie du 16.24 : si les infobulles d'un nouveau patch manquaient, le run échouerait et l'alerte partirait, au lieu de publier des prédictions fausses.
- **Aperçus des 23 et 25/11** (deux nouvelles versions du PBE) : contrôle complet, ligne par ligne contre le 16.23 (valeurs, morceaux de formules, infobulles, stats des objets) : **toujours le seul Akshan**, prédiction inchangée. À une semaine environ de la sortie, le 16.24 semble un patch calme : une seule prédiction sera jugée.

## Un assistant local qui lit les marts

Un modèle de langage tourne **sur le PC** (Qwen3 4B, via Ollama, 3,9 Go, entièrement sur la carte graphique) : aucun appel payant, aucune donnée ne sort. Il répond aux questions d'un joueur en appelant des **outils** (`assistant/outils.py`), des fonctions Python testées qui lisent les marts de prod :

- `changements_du_patch(patch)` : ce que le moteur théorique a prédit pour un patch, et ce que le ladder en a dit ;
- `builds_du_champion(champion, patch, poste)` : les familles de builds (parties, popularité, victoires avec leur fourchette, objets les plus fréquents) ;
- `bulletin_du_patch(patch)` : le bulletin du patch, en une phrase de bilan calculée qui dit **ce que juge chaque mesure** (la fidélité dit si nous lisons bien les builds, les duels comparent les builds entre eux, **seules les expériences jugent la théorie**) et **compte chaque groupe à part** (prouvées dans le sens prédit, dans le sens prédit sans preuve, contredites, autres) ;
- `objets_du_champion(champion, patch)` : les objets les plus rentables **en théorie** (les ratios des sorts), pour les dégâts et pour la survie, et ce que le patch a changé ; le champion est trouvé par son nom ou par son code du jeu (Wukong = `MonkeyKing`).

**La version d'Ollama est fixée (0.40.16, mise à jour automatique coupée)** : le 25/11, Ollama s'est mis à jour seul en 0.40.18, et le modèle n'appelait plus ses outils (il « réfléchissait à voix haute » en anglais, inventait des noms d'outils et un patch « 11.23 »). Les notes de version officielles expliquent pourquoi : la consigne de ne pas réfléchir et la description des outils ne lui parviennent plus de la même façon. Retour à la 0.40.16 (installateur officiel, empreinte et signature vérifiées) : les outils sont de nouveau appelés. Comme uv et dbt, un outil dont dépend le projet a sa version fixée ; « même question, même réponse » (température 0) n'est vrai qu'à version égale.

Les règles, chacune née d'un essai mesuré (23-25/11) :
- **le texte du modèle n'entre jamais dans le SQL** : le patch, le champion, le poste passent par des paramètres de requête (un nom piégé reste une valeur) ;
- **chaque chiffre arrive avec sa définition** ; une liste vide arrive avec une remarque (sinon le modèle comble le vide) ;
- **ce qui doit être juste se calcule, le modèle ne fait que rédiger** : il confondait les codes de verdict (la part de jeu et les victoires, « confirmé » et « même sens ») ; il reçoit maintenant une phrase déjà interprétée et testée (« Part de jeu : 1,57 % -> 2,47 %, en hausse comme prédit, et c'est prouvé ») ; les familles arrivent avec leur nom en clair et leurs objets (il décrivait « hybride » comme « dégâts et survie » ; c'est Manamune + Horizon Focus pour Ezreal) ;
- **deux blocs** : le résumé du modèle, puis le **détail vérifié**, mis en forme et recopié par le programme ; **température 0** : la même question donne la même réponse, deux essais se comparent ;
- une erreur d'outil (patch illisible, poste inconnu) revient au modèle, qui peut corriger sa demande ; au plus 4 tours d'outils.

Mesuré sur la même question (« qu'est-ce qui a changé au 16.23 ? »), chaque résumé relu phrase par phrase contre les chiffres : **4 erreurs** avec les codes bruts, **1** avec les phrases de verdict, puis **1, et une réponse identique d'un essai à l'autre** avec la température à 0. Sur les builds d'Ezreal : objets et taux justes, plus aucune description inventée après le nom des familles en clair. Sur le bulletin (« la théorie a-t-elle vu juste ? ») : d'abord « oui, 99,83 % de fidélité » (la fidélité ne juge pas la théorie), puis « 8 sur 8, elle est correcte » (4 seulement prouvées), enfin, avec la phrase qui compte chaque groupe et une consigne (« ne conclus jamais que la théorie est correcte »), **un résumé juste de bout en bout** : « 4 sur 8 prouvées, 4 autres dans le bon sens sans preuve ». 15 à 47 s par question.

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

**Les familles de builds : une seed relue, un vote simple.** Les étiquettes officielles des objets sont imprécises (le Couperet noir est étiqueté comme un objet de létalité et d'on-hit), et la létalité manquait alors aux stats chargées depuis les fichiers du jeu (un bug du chargeur, corrigé le 09/11 : voir plus bas). La famille de chaque objet est donc une **seed** : pré-remplie par des règles sur les étiquettes et les stats, puis **relue en entier par un joueur expérimenté**, qui a corrigé 17 cas douteux et montré qu'un objet peut avoir plusieurs familles (une principale, des secondaires). Un build est classé par la famille majoritaire de ses trois premiers objets terminés ; sans majorité, « hybride » s'il mélange AD et AP, sinon la famille du premier objet. Une famille devient un **choix** à partir de 10 parties ; le nombre de parties est toujours affiché, et les choix sont classés par le **bas de leur fourchette**, pour qu'un 80 % sur 10 parties ne passe pas devant un 54 % sur 500. Une règle d'« objet signature » a été essayée puis retirée : elle corrigeait un champion (Ezreal) mais en reclassait deux autres à tort (173 builds de Jayce et de Varus) — mesuré sur tous les builds réels, pas seulement sur le cas qui l'avait fait naître.

**Une couche intermédiaire, pour écrire une règle une seule fois.** L'ordre d'achat des objets (achats annulés exclus) sert à deux marts : il vit dans un modèle intermédiaire partagé. Après ce déplacement, `mart_ladder_builds` a été comparé à sa version précédente : 5 533 lignes de chaque côté, **0 différence**.

**Des tests qu'on a vus échouer.** Les nouveaux tests ont d'abord été lancés contre une version sabotée exprès (une famille retirée, une faute de frappe, une majorité à 3 objets au lieu de 2) : chacun a échoué là où il devait, puis est passé sur la version juste. Un test qu'on n'a jamais vu échouer ne prouve pas qu'il détecte le problème. Un sabotage a même révélé un trou : pour le prix des stats, retirer le filtre « objet de base » laissait le test vert, parce que l'objet fabriqué du test était de toute façon plus cher. Le test a reçu un objet fabriqué moins cher, et le sabotage échoue maintenant.

**Un recensement fait après le filtre.** Le chargeur des stats d'objets ne gardait que les champs dont le nom commence par « m » (`mFlatHPPoolMod`). Le mana, la régénération de mana, la létalité et l'omnivampirisme s'écrivent sans ce « m » : ils n'étaient **jamais chargés** (72, 61, 40 et 16 objets au 16.22). Le code annonçait « 24 sortes de stats recensées », mais le recensement avait été fait sur les données déjà filtrées : il ne pouvait pas voir ce que le filtre jetait. Le bug est apparu à la relecture d'un résultat (« Ahri commence par un objet qui donne du mana » : 0 objet avec du mana dans la base). Correction testée, puis toute la saison rechargée (sauvegarde, vidage, rechargement) et vérifiée par différence : **0 ancienne ligne perdue ou changée**, 4 097 lignes nouvelles, exactement les 5 sortes attendues ; mana identique à Data Dragon pour les 72 objets. Effet de bord : un nerf de létalité au 16.21 (Bastionbreaker, 22 → 18), invisible jusque-là, est maintenant vu par le bulletin.

**Un chargement des kits table par table.** Un patch était « déjà chargé » s'il figurait dans une seule table, celle des formules. Une nouvelle table (la fiche des champions) serait restée vide pour les 22 patches déjà là. Chaque table complète maintenant ses propres patches manquants : la fiche de toute la saison s'est remplie au run suivant, sans lancement à la main, et les autres tables sont restées identiques à la ligne près. Au passage, un risque de double chargement après une panne en cours de patch a disparu.

**Des tests sur les données, pas seulement sur le code.**
- `SAFE_CAST` ne plante jamais : une valeur non convertible devient `NULL` en silence. Un test singulier vérifie qu'aucune valeur non vide n'est perdue à la conversion (0 sur 10 colonnes).
- Data Dragon contient au patch 16.15 soixante entrées `Jade_<Champion>` qui dupliquent des noms de vrais champions. Elles sont écartées, et un test d'unicité du nom par patch protège la jointure par nom.
- Un `dbt build` a déjà affiché « réussi » avec zéro test lancé, à cause d'un cache d'analyse périmé : les runs d'Airflow utilisent `--no-partial-parse`.
- Une partie compte 10 picks : les taux de pick d'un patch font 10. Ce test a attrapé un taux calculé avec un numérateur et un dénominateur venus de deux tables d'âges différents (8,70 au lieu de 10).

**Un run dans le cloud, sans fichier de clé.** Le job Cloud Run tourne sous l'identité du compte de service du pipeline, fournie par Google (« Application Default Credentials ») : aucun fichier de clé à créer, copier ou faire fuiter. Le même code garde le fichier de clé en local (Airflow) : une seule fonction (`ingestion/identite.py`) choisit. Drive (Oracle's Elixir) l'accepte, vérifié au premier run. La clé Riot est dans Secret Manager, **collée à la main dans la console** : sa valeur ne passe jamais par Terraform (elle finirait en clair dans l'état de Terraform).

**Un chef d'orchestre en Python plutôt qu'Airflow dans le cloud.** `ingestion/quotidien.py` lance chaque collecte avec ses relances (Oracle's Elixir : 4 essais à 2 h d'intervalle, son quota Drive se libère lentement), toutes même si l'une échoue, puis `dbt build` seulement si toutes ont réussi, et sort avec un code d'erreur si une étape a échoué. Cloud Run ne relance pas le job entier : il recollecterait tout et consommerait le quota Riot pour rien.

**Une image fabriquée en deux temps.** Un atelier installe les dépendances avec uv, l'image finale ne garde que le résultat : **1,49 Go → 1,2 Go, ~250 Mo compressée**, sous les 0,5 Gio gratuits de l'étagère d'images. Un `.dockerignore` écarte `.env`, `secrets/` et tout ce dont le job n'a pas besoin ; l'image tourne sans droits d'administrateur. Fabriquée avec `--provenance=false` : sinon Docker Desktop ajoute une attestation, l'étagère compte 3 versions par image, et la règle « garder les 3 dernières » n'en garderait qu'une (vu en listant l'étagère).

**Une bascule dans un ordre sûr.** Jamais deux collectes en même temps : elles partagent la clé, et verraient les mêmes nouvelles parties comme absentes de la base. Le premier run dans le cloud a été lancé après celui du PC (relance vérifiée sans doublon : 2 275 parties, 10 lignes chacune) ; puis le DAG du PC a été mis en pause **avant** que le réveil du cloud soit activé.

**Après un `apply`, un `plan`.** Juste après la création du réveil, Terraform voulait encore lui ajouter « 0 relance » : Google ne renvoie pas un réglage qui vaut sa valeur par défaut. Le bloc inutile a été retiré (0 relance est le défaut, vérifié dans la documentation de l'API). « Apply complete » dit que la création a marché, pas que le code et le cloud disent la même chose.

**Une alerte testée de bout en bout.** Un courriel part si le bilan du run dit qu'une étape a échoué, si le conteneur sort en erreur, ou si le réveil ne lance pas le job ; une étape échouée puis réussie à la relance ne déclenche rien. Vérifié : 0 ligne du run réussi ne la déclenche ; une fausse ligne d'échec, écrite par l'API du journal, a bien envoyé le courriel — au deuxième essai : le premier, écrit 2 minutes après la création de la règle, était arrivé trop tôt.

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

**Les runs des 10 et 11/11** : 771 et 776 parties, 1 et 3 refus 429 ; `dbt build` **186 PASS, 2 avertissements connus, 0 erreur** (bulletin de patch et fiche des champions compris).

**Le premier run dans le cloud, le 18/11/2026** (après celui du PC, donc 47 parties nouvelles seulement) : **25 minutes**, 1 096 requêtes à Riot, 0 refus 429 ; Oracle's Elixir 119 232 lignes ; `dbt build` **225 PASS, 2 avertissements connus, 0 erreur**. Soit ~1 500 vCPU-secondes et ~3 000 Gio-secondes : **moins de 1 %** du niveau gratuit mensuel des jobs Cloud Run (240 000 vCPU-s et 450 000 Gio-s par compte de facturation). Un run complet (~1 h, 1 vCPU, 2 Gio) en prendrait environ la moitié sur un mois. Le réveil fait partie des 3 gratuits ; l'image pèse 261 Mo sur 0,5 Gio gratuits ; l'alerte est gratuite jusqu'au 31/08/2027, puis 0,35 $ par mois (prix vérifiés sur les pages officielles le 18/11).

**Le premier run complet dans le cloud, le 19/11/2026** (image `2`) : **53 min 21 s**, 747 parties nouvelles (sur 747 disponibles), 0 introuvable ; stats d'objets : rien à charger (pas de nouveau patch) ; `dbt build` **236 PASS, 2 avertissements connus, 0 erreur** ; aucune alerte. Soit ~3 200 vCPU-secondes et ~6 400 Gio-secondes : un mois de runs pareils prendrait ~40 % du niveau gratuit, comme estimé.

**Le déploiement se fait par étiquette** : chaque image porte un numéro (`1`, `2`, `3`…), le job lance celle que nomme `job_image_tag` dans Terraform, et l'étagère garde les 3 dernières. Revenir en arrière : remettre l'ancien numéro, `terraform apply`.

## Limites

- **Le run quotidien tourne dans le cloud depuis le 18/11** ; avant, il dépendait du PC (environ 2 200 parties perdues pendant une mise en veille). Il reste des limites : un jour manqué au-delà de la fenêtre de 2 jours fait perdre des parties ; les pauses de 2 h des relances d'Oracle's Elixir sont facturées comme du temps de calcul (toujours dans le gratuit).
- **L'aperçu du PBE est un brouillon de Riot** : ses valeurs changent avant la sortie, d'où une prédiction finale le jour du patch. Un champion nouveau, présent au PBE mais pas encore dans Data Dragon, manquerait à l'aperçu ; un prix ou un nom d'objet changé au PBE n'est pas vu (Data Dragon est emprunté au dernier patch publié).
- **Un échantillon, pas tout le ladder.** La clé *personal* autorise 100 requêtes par 2 minutes : jusqu'à 800 nouvelles parties par jour (environ 52 minutes de collecte), à partir des 1 000 joueurs Challenger et Grandmaster. Les parties sont celles de joueurs du haut du classement, pas un tirage aléatoire.
- **La diffusion de la meta est censurée à gauche.** La ladder n'est collectée que depuis le patch 16.21 ; aucun délai n'est mesurable tant qu'un champion n'est pas entré dans la meta pendant la fenêtre observée. Le pro, lui, saute des patches (aucun match au 16.19) : un délai en patches se lit avec ça en tête.
- **Les seuils viennent d'un premier échantillon** (parties ≥ 15 min, objets ≥ 2 000 po) et seront revérifiés sur un patch complet. Aucun seuil de volume n'est encore imposé aux matchups : chaque taux est publié avec sa fourchette de confiance, qui dit elle-même quand un effectif est trop faible.
- **Une adresse de l'API injoignable** depuis le réseau local (cause inconnue) : contournée par une connexion réutilisée, pas résolue.
- **Les plaques de tourelle** ne suivent pas la règle connue (jusqu'à 15 par équipe et par voie, jusqu'à la minute 36) : collectées, mais utilisées par aucune mart tant que la mécanique n'est pas vérifiée.
- **Les données pro** dépendent d'Oracle's Elixir : certains matchs sont incomplets (écart d'or à 15 minutes manquant pour 1 740 lignes joueurs).
- **Les formules des sorts viennent d'une source communautaire** (CommunityDragon), non officielle : à valider avant toute demande de clé de production. Une formule seulement renommée (contenu identique) est reconnue comme telle ; si Riot la renomme **et** en change la structure, elle reste signalée comme un retrait plus un ajout.
- **La létalité n'a pas encore de prix** : elle est chargée depuis le 09/11, mais aucun objet de base ne donne que de la létalité, donc la règle du prix d'un point ne s'applique pas. Un prix dérivé est prévu. Même chose pour le vol de vie, la ténacité, les pénétrations, les soins et boucliers : non valorisés.
- **Le moteur théorique ne voit ni les coûts en mana, ni les temps de recharge, ni les dégâts de base, ni les effets des objets** : c'est l'angle mort que le bulletin a révélé (Mel au 16.22), et que le simulateur doit combler.
- **La valeur survie ne voit que les ratios des boucliers, soins et vitesses**, pas la solidité générale qu'apportent les PV ou l'armure. Un changement d'objet n'est jugé que sur les dégâts. Un champion qui reçoit son **tout premier** ratio de survie n'a pas de valeur précédente à comparer : ce changement n'est pas vu, s'il ne bouge rien d'autre.
- **Le simulateur ne connaît pas encore les effets des objets**, ni les sorts à plusieurs coups ou sur la durée ; dégâts moyens (le critique compte en moyenne), sans le temps d'armer le premier coup ni la régénération de la cible. La pénétration suit le wiki, sans mesure possible avec nos données. Restent non décodés : la vitesse d'attaque totale (4, 0), la vitesse de déplacement (7) et quelques codes rares. L'anomalie du Q de Lissandra et de Kennen (~0,27 du prédit) venait de la vérification, pas du simulateur : elle comparait au Q d'autres effets rangés dans le même emplacement (corrigé le 23/11). Reconnu par son nom, le Q de Lissandra est à 0,90 sur 3 coups seulement, et celui de Kennen n'a aucun coup sans pénétration : ni l'un ni l'autre n'est encore validé. Le mana bonus et la progression par niveau ne sont pas encore validés sur de vrais coups (trop peu de coups simples).
- **Les groupes d'objets sont chargés, mais aucun build ne les vérifie encore** : le jeu interdit certains cumuls. Au 16.23, le groupe « Dernier souffle » (un seul objet) compte 7 objets, dont le **Couperet noir**, exclusif avec Lord Dominik ; une seule paire de bottes parmi 22. Chargés depuis le 19/11 avec les stats des objets (table par table : 23 patches, 42 129 lignes, 0 groupe introuvable), dans `stg_item_groups`. Un groupe dont CommunityDragon ne connaît pas encore le nom porte son empreinte : `{321e09b4}` jusqu'au 16.19, puis `PrismaticTankItems` (vérifié : c'est bien l'empreinte de ce chemin). Le moteur de build devra s'en servir pour ne jamais proposer un build impossible.
- **Les verdicts du bulletin sont instables en début de patch** : beaucoup de duels se renversent en un ou deux jours. Ils ne doivent pas être montrés aux joueurs avant d'avoir tenu dans la durée.
- **Le résumé de l'assistant peut encore se tromper** (1 erreur sur 8 champions à la dernière mesure, une phrase de raisonnement fausse sur les builds) : c'est le **détail vérifié** qui fait foi. L'assistant ne tourne que sur le PC (Ollama), pas dans le cloud. Une question sur les builds lit ~450 Mo dans BigQuery (une vue refait son calcul) : ~0,04 % du gratuit mensuel ; une table précalculée le ramènerait à quelques Mo.
- **La famille d'un objet ne dépend pas de qui l'achète.** La Force de la trinité est un objet de combattant : le build d'Ezreal (Trinité, Manamune, Faim insatiable) est donc classé « combattant », alors qu'un joueur dirait « Ezreal Manamune ». Choix assumé (la règle qui corrigeait ce cas en cassait d'autres).
- **Peu de choix par champion pour l'instant** : au 16.22, après le run du 06/11, 42 couples champion × poste ont deux familles à 10 parties ou plus, et 2 en ont trois (Jax TOP : combattant, AP, hybride ; Sona support : enchanteur, tank, AP). La veille, 16 couples en avaient deux et aucun trois. Ce n'est pas l'algorithme mais le volume : il grandit chaque jour.
- **Un poste peut manquer.** Riot laisse le poste vide quand il ne sait pas déduire le rôle d'un joueur (1 ligne sur 2 890 au 03/11, dans une partie finie à 15 min 32 s). Un test le signale en avertissement ; la mart des matchups écarte d'elle-même le duel concerné.

## Structure

```
ingestion/        Data Dragon, Oracle's Elixir, client Riot (limiteur), collecteur du ladder,
                  kits des champions (formules des sorts, fiche des stats, texte du jeu)
                  et stats des objets (CommunityDragon) ; quotidien.py (le chef
                  d'orchestre du job) ; identite.py ; pbe.py (aperçu du PBE)
infra/terraform/  bucket, datasets, compte de service, IAM minimal ; job.tf (job Cloud
                  Run, réveil, étagère d'images, coffre de la clé) ; alerte.tf
job/              Dockerfile du job quotidien (fabrication en deux temps)
predictions/      prédictions datées, faites avant la sortie d'un patch
airflow/          image, docker-compose, DAG quotidien lol_daily
dbt/              staging (vues) -> intermédiaire (vues) -> marts (tables), seeds
                  relues (codes de stats, familles d'objets, objets transformés,
                  noms des champs de la fiche), macros, tests de données
simulateur/       simulateur de combat (Python pur) : degats, stats avec objets,
                  temps pour tuer le mannequin, formules des sorts, coup de sort entier
assistant/        l'assistant local : outils.py (les outils qui lisent les marts, avec
                  leurs définitions et les phrases de verdict) ; conversation.py (la
                  boucle avec Ollama, le détail vérifié, le lanceur)
tests/            pytest hors ligne : faux clients HTTP, BigQuery, Storage et Ollama ;
                  fonctions du simulateur
prototypes/       essais : le premier LLM local du 05/11 (remplacé par assistant/) ;
                  pré-classement des familles d'objets avant relecture
```

## Lancer le projet

Prérequis : Python 3.12 et [uv](https://docs.astral.sh/uv/), un projet GCP créé par `infra/terraform`, la clé du compte de service dans `secrets/` et une clé Riot dans `.env` (`RIOT_API_KEY=...`). Ces deux fichiers sont ignorés par git.

```bash
uv sync
uv run pytest
uv run python ingestion/ladder.py --max-joueurs 20 --max-parties 30
```

Orchestration dans le cloud : `infra/terraform` crée le job, son réveil, l'étagère d'images, le coffre de la clé et l'alerte (sur un projet neuf, d'abord avec `-var deployer_le_job=false` : le job ne peut naître sans son image ni sa clé). L'image se fabrique et se dépose avec les deux commandes écrites en tête de `job/Dockerfile` ; la clé Riot se colle à la main dans Secret Manager.

Orchestration locale (en pause depuis le 18/11, gardée pour revenir au PC si besoin) : depuis `airflow/`, `docker compose up -d`, puis l'interface sur `http://localhost:8081`. La clé Riot est montée dans les conteneurs en lecture seule, jamais copiée.

Prédire le prochain patch (à la main) :

```bash
uv run python ingestion/pbe.py
cd dbt && uv run dbt build --target pbe --select +mart_patch_predictions --exclude "test_type:unit" --indirect-selection cautious --profiles-dir profiles
```

Poser une question à l'assistant (Ollama **0.40.16** lancé sur le PC, mise à jour automatique coupée, avec le modèle `hf.co/Qwen/Qwen3-4B-GGUF:Q4_K_M`) :

```bash
uv run python assistant/conversation.py "Quels builds pour Ezreal en adc ?"
```

## Attribution et conditions d'utilisation

lol-meta-pipeline isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc.

*(Mention légale imposée par les [règles du portail développeur de Riot](https://developer.riotgames.com/policies/general), reprise mot pour mot.)*

- Données de compétition : [Oracle's Elixir](https://oracleselixir.com/). Une partie du contenu provient de [Leaguepedia](https://lol.fandom.com/), sous licence CC BY-SA 3.0.
- Seuls le code et des agrégats sont publiés. Les données brutes ne sont pas redistribuées, et aucun identifiant de joueur (puuid, pseudo) n'est stocké.
