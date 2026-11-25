"""Les outils de l'assistant : ce que le modele de langage local (Ollama) peut
demander a nos marts (23/11/2026). Ils remplacent peu a peu le prototype
prototypes/essai_llm_local.py.

Trois regles, pour chaque outil :
- il lit la PROD (dataset lol_analytics), mise a jour chaque jour par le run ;
- le texte venu du modele n'est jamais colle dans le SQL : il passe par un
  parametre de requete (@patch), que BigQuery traite comme une valeur, jamais
  comme du code (pas d'injection SQL) ;
- chaque colonne renvoyee arrive avec sa definition (la couche semantique) :
  a l'essai du 05/11, sans elle, le modele a pris des points de ratio pour de
  l'or.
"""

import re

from google.cloud import bigquery

PROJET = "lol-meta-pipeline"
DATASET = "lol_analytics"

# "16.23" : des chiffres, un point, des chiffres. Rien avant, rien apres
# (fullmatch) : "16.23.1" ou "16" sont refuses.
_FORMAT_PATCH = re.compile(r"(\d+)\.(\d+)")

# Au plus 20 lignes : la memoire de travail du modele local est petite (8 192
# tokens, essai du 05/11). Les plus gros changements d'abord.
LIGNES_MAX = 20

DEFINITIONS_CHANGEMENTS = {
    "type": "objet (Riot a change ses stats ou son prix) ou champion (Riot a "
    "change les ratios de son kit)",
    "sujet": "le nom de l'objet ou du champion",
    "valeur": "la valeur theorique qui porte la prediction : degats, ou survie "
    "(boucliers, soins, vitesses) pour un champion dont seule la survie change",
    "sens_predit": "hausse = le moteur theorique predit que l'objet sera plus "
    "achete, ou le champion plus joue ou plus gagnant ; baisse = l'inverse",
    "ecart_theorique_pct": "variation moyenne, en %, de la valeur des objets "
    "pour 1 000 pieces d'or entre le patch precedent et celui-ci (pour un "
    "objet : moyenne sur les champions concernes). Une mesure theorique, "
    "calculee AVANT toute partie : ce n'est pas un taux de victoire",
    "champions_concernes": "le nombre de champions pour qui l'objet change de "
    "valeur (1 pour un champion : lui-meme)",
    "part_avant_pct": "en % : pour un objet, la part des joueurs des champions "
    "concernes qui l'achetent dans leurs 3 premiers objets ; pour un champion, "
    "la part des joueurs qui le jouent. Au patch precedent, sur le ladder "
    "(Challenger et Grandmaster EUW). Vide si pas encore juge",
    "part_apres_pct": "la meme part, au patch lui-meme",
    "victoires_avant_pct": "en % : le taux de victoire (quand l'objet est "
    "achete, ou du champion), au patch precedent. Vide si pas encore juge",
    "victoires_apres_pct": "le meme taux, au patch lui-meme",
    "verdict": "ce que le ladder a montre, deja interprete et verifie : "
    "reprends cette phrase telle quelle, sans la resumer en confirme ou "
    "contredit (prouve = les fourchettes de confiance des deux patches ne se "
    "touchent pas)",
}

# Ce que veut dire chaque code de verdict (macro dbt patch_verdict), en mots.
# {sens} = le sens predit ; {inverse} = l'autre sens.
_VERDICTS = {
    "confirme": "en {sens} comme predit, et c'est prouve",
    "meme_sens": "en {sens} comme predit, mais pas encore prouve",
    "sens_contraire": "en {inverse}, a l'inverse de la prediction, mais pas prouve",
    "contredit": "en {inverse}, a l'inverse de la prediction, et c'est prouve : "
    "la prediction est contredite",
    "stable": "sans changement",
    "sans_donnees": "pas assez de parties pour juger",
}
_INVERSE = {"hausse": "baisse", "baisse": "hausse"}


def phrase_du_verdict(ligne: dict) -> str:
    """Une prediction et ce que le ladder en a dit, en une phrase deja
    interpretee. Essai du 23/11 : le modele confondait les codes (le verdict de
    la part et celui des victoires, confirme et meme_sens) ; ce qui doit etre
    juste se calcule ici, le modele ne fait que reprendre la phrase. Leve
    ValueError pour un code de verdict inconnu."""
    sens = ligne["sens_predit"]
    debut = f"{ligne['sujet']} ({ligne['type']}) : la theorie predit une {sens}"
    if ligne["type"] == "objet":
        n = ligne["champions_concernes"]
        if n == 1:
            debut += " pour l'unique champion concerne"
        else:
            debut += f" pour les {n} champions concernes"
    debut += "."
    if ligne["verdict_part"] == "pas_encore_juge":
        return (
            f"{debut} Pas encore juge : il faut des parties de ladder au patch "
            "precedent et a celui-ci."
        )

    def taux(nom, avant, apres, decimales, code):
        """Une moitie de la phrase : "Victoires : 52,4 % -> 45,9 %, ..."."""
        if code not in _VERDICTS:
            raise ValueError(f"verdict inconnu : {code!r}")
        texte = _VERDICTS[code].format(sens=sens, inverse=_INVERSE[sens])
        if avant is None or apres is None:
            return f"{nom} : {texte}."
        # 0.25 -> "0,25 %" : la virgule francaise.
        avant_txt = f"{avant:.{decimales}f}".replace(".", ",")
        apres_txt = f"{apres:.{decimales}f}".replace(".", ",")
        return f"{nom} : {avant_txt} % -> {apres_txt} %, {texte}."

    nom_part = "Part d'achat" if ligne["type"] == "objet" else "Part de jeu"
    return " ".join(
        [
            debut,
            taux(
                nom_part,
                ligne["part_avant_pct"],
                ligne["part_apres_pct"],
                2,
                ligne["verdict_part"],
            ),
            taux(
                "Victoires",
                ligne["victoires_avant_pct"],
                ligne["victoires_apres_pct"],
                1,
                ligne["verdict_victoires"],
            ),
        ]
    )


def _cle_du_patch(patch: str) -> int:
    """ "16.23" -> 1623, la cle de tout le projet. Leve ValueError si le texte
    n'est pas un patch."""
    morceaux = _FORMAT_PATCH.fullmatch(patch)
    if morceaux is None:
        raise ValueError(f"patch illisible : {patch!r} (format attendu : 16.23)")
    # "16.4" -> 16 x 100 + 4 = 1604. (Le prototype enlevait le point :
    # "16.4" -> 164, un patch introuvable.)
    return int(morceaux[1]) * 100 + int(morceaux[2])


def changements_du_patch(patch: str, client) -> dict:
    """Ce que le moteur theorique a predit pour un patch, et ce que le ladder en
    a dit. Une ligne par objet ou champion change par Riot, les plus gros
    changements d'abord. Leve ValueError si le patch est illisible."""
    cle = _cle_du_patch(patch)

    sql = f"""
        SELECT
            p.subject_type AS type,
            p.subject_name AS sujet,
            p.value_kind AS valeur,
            p.predicted_direction AS sens_predit,
            p.theory_change_pct AS ecart_theorique_pct,
            p.concerned_champions AS champions_concernes,
            ROUND(e.old_share * 100, 2) AS part_avant_pct,
            ROUND(e.new_share * 100, 2) AS part_apres_pct,
            ROUND(e.old_win_rate * 100, 1) AS victoires_avant_pct,
            ROUND(e.new_win_rate * 100, 1) AS victoires_apres_pct,
            COALESCE(e.share_verdict, 'pas_encore_juge') AS verdict_part,
            COALESCE(e.win_verdict, 'pas_encore_juge') AS verdict_victoires
        FROM `{PROJET}.{DATASET}.mart_patch_predictions` AS p
        LEFT JOIN `{PROJET}.{DATASET}.mart_patch_experiments` AS e
            ON e.patch_key = p.patch_key
            AND e.subject_type = p.subject_type
            AND e.subject_id = p.subject_id
        WHERE p.patch_key = @patch
        ORDER BY ABS(p.theory_change_pct) DESC
        LIMIT {LIGNES_MAX}
    """
    config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("patch", "INT64", cle)]
    )
    predictions = []
    for lue in client.query(sql, job_config=config).result():
        # Une copie : la ligne lue reste intacte.
        prediction = dict(lue)
        prediction["verdict"] = phrase_du_verdict(prediction)
        # Les codes bruts ne partent pas vers le modele : il les confondait
        # (essai du 23/11). La phrase dit tout.
        del prediction["verdict_part"], prediction["verdict_victoires"]
        predictions.append(prediction)

    resultat = {
        "patch": patch,
        "definitions": DEFINITIONS_CHANGEMENTS,
        "predictions": predictions,
    }
    if not predictions:
        # Une liste vide, sans explication, pourrait pousser le modele a
        # inventer des changements.
        resultat["remarque"] = (
            "aucune prediction pour ce patch : il n'est pas encore charge, ou le "
            "moteur theorique n'y voit aucun changement de ratio ni de stat d'objet"
        )
    return resultat


# Les noms des postes que le modele peut ecrire -> le code de Riot dans nos
# marts (team_position). En minuscules : la recherche ignore les majuscules.
POSTES = {
    "top": "TOP",
    "jungle": "JUNGLE",
    "jungler": "JUNGLE",
    "mid": "MIDDLE",
    "middle": "MIDDLE",
    "adc": "BOTTOM",
    "bot": "BOTTOM",
    "bottom": "BOTTOM",
    "support": "UTILITY",
    "supp": "UTILITY",
    "utility": "UTILITY",
}

# Le nom de chaque famille en clair, pour le modele (essai du 23/11 : il
# decrivait « hybride » comme « equilibre degats et survie »). Tire de la seed
# item_families, relue par William le 06/11 ; hybride vient de la regle du
# vote (int_ladder__build_families). Un test verifie que chaque famille de la
# seed a son nom ici.
FAMILLES_EN_CLAIR = {
    "ap": "ap (objets de puissance)",
    "critique": "critique (objets de chances de critique)",
    "tank": "tank (objets de PV et de resistances)",
    "combattant": "combattant (objets de combattant : attaque et PV)",
    "letalite": "letalite (objets de letalite, d'assassin)",
    "enchanteur": "enchanteur (objets de soins et de boucliers pour les allies)",
    "on_hit": "on_hit (objets d'effets a l'impact)",
    "support": "support (objet de support)",
    "ad_mana": "ad_mana (objets d'attaque et de mana)",
    "hybride": "hybride (ni majorite AD ni majorite AP : objets AD et AP melanges)",
}

DEFINITIONS_BUILDS = {
    "poste": "le poste de Riot : TOP, JUNGLE, MIDDLE (mid), BOTTOM (adc), "
    "UTILITY (support)",
    "famille": "la famille du build, votee sur ses 3 premiers objets termines "
    "(chaque objet a une famille : critique, letalite, ap, tank, combattant...) : "
    "la famille d'au moins 2 des 3 premiers objets ; sinon hybride, si des "
    "objets AD et AP melanges ; sinon la famille du premier objet. Ne decris "
    "pas une famille au-dela de ses objets_principaux",
    "objets_principaux": "les 3 objets les plus frequents de la famille (parmi "
    "les 3 premiers objets termines des joueurs), avec pct_des_parties : la "
    "part des parties de la famille ou l'objet est present",
    "parties": "le nombre de parties jouees avec cette famille, sur le ladder "
    "(Challenger et Grandmaster EUW), a ce patch",
    "part_des_parties_pct": "en % : la part des parties du champion a ce poste "
    "jouees avec cette famille (sa popularite, pas sa qualite)",
    "victoires_pct": "en % : le taux de victoire de la famille",
    "victoires_bas_pct": "en % : le bas de la fourchette de Wilson a 95 % du "
    "taux de victoire. Peu de parties = fourchette large = taux peu sur",
    "victoires_haut_pct": "en % : le haut de cette fourchette",
    "vrai_choix": "vrai si la famille a au moins 10 parties : assez pour la "
    "comparer aux autres. Une famille sous 10 parties reste affichee, mais "
    "n'est pas un choix",
    "rang_parmi_les_choix": "1 = le choix au meilleur bas de fourchette (un "
    "80 % sur 10 parties ne passe pas devant un 54 % sur 500) ; vide si ce "
    "n'est pas un vrai choix",
}


def builds_du_champion(
    champion: str, patch: str, client, poste: str | None = None
) -> dict:
    """Les familles de builds d'un champion sur le ladder, a un patch, pour un
    poste ou pour tous : parties, popularite, victoires avec leur fourchette.
    Plusieurs options, jamais un ordre : c'est au joueur de choisir. Leve
    ValueError si le patch ou le poste est illisible."""
    cle = _cle_du_patch(patch)
    code_poste = None
    if poste is not None:
        code_poste = POSTES.get(poste.lower())
        if code_poste is None:
            raise ValueError(
                f"poste inconnu : {poste!r} (postes acceptes : {sorted(POSTES)})"
            )

    # Trois etapes : les familles du champion (la mart) ; les objets de leurs
    # joueurs (les 3 premiers objets termines de chacun, une ligne par objet
    # grace a UNNEST) ; les 3 plus frequents par famille. La vue
    # int_ladder__build_families refait son calcul a chaque appel : ~450 Mo lus
    # (mesure du 23/11), 0,04 % du gratuit mensuel de BigQuery.
    sql = f"""
        WITH familles AS (
            SELECT *
            FROM `{PROJET}.{DATASET}.mart_ladder_build_families`
            WHERE patch_key = @patch
                AND LOWER(champion_name) = LOWER(@champion)
                AND (@poste IS NULL OR team_position = @poste)
        ),

        objets AS (
            SELECT b.team_position, b.build_family, item_id, COUNT(*) AS parties
            FROM `{PROJET}.{DATASET}.int_ladder__build_families` AS b,
                UNNEST(b.item_ids) AS item_id
            WHERE b.patch_key = @patch
                AND b.champion_id IN (SELECT champion_id FROM familles)
            GROUP BY b.team_position, b.build_family, item_id
        ),

        principaux AS (
            SELECT
                o.team_position,
                o.build_family,
                ARRAY_AGG(
                    STRUCT(
                        -- Un objet absent de la seed garde son numero.
                        COALESCE(n.item_name, CAST(o.item_id AS STRING)) AS objet,
                        CAST(ROUND(100 * o.parties / f.games) AS INT64)
                            AS pct_des_parties
                    )
                    ORDER BY o.parties DESC, o.item_id
                    LIMIT 3
                ) AS objets_principaux
            FROM objets AS o
            INNER JOIN familles AS f
                ON o.team_position = f.team_position
                AND o.build_family = f.build_family
            LEFT JOIN `{PROJET}.{DATASET}.item_families` AS n
                ON o.item_id = n.item_id
            GROUP BY o.team_position, o.build_family
        )

        SELECT
            f.team_position AS poste,
            f.build_family AS famille,
            f.games AS parties,
            ROUND(f.share_of_champion_games * 100, 1) AS part_des_parties_pct,
            ROUND(f.win_rate * 100, 1) AS victoires_pct,
            ROUND(f.win_rate_low * 100, 1) AS victoires_bas_pct,
            ROUND(f.win_rate_high * 100, 1) AS victoires_haut_pct,
            f.is_choice AS vrai_choix,
            IF(f.is_choice, f.choice_rank, NULL) AS rang_parmi_les_choix,
            p.objets_principaux
        FROM familles AS f
        LEFT JOIN principaux AS p
            ON f.team_position = p.team_position
            AND f.build_family = p.build_family
        ORDER BY poste, vrai_choix DESC, rang_parmi_les_choix, parties DESC
        LIMIT {LIGNES_MAX}
    """
    config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("patch", "INT64", cle),
            bigquery.ScalarQueryParameter("champion", "STRING", champion),
            bigquery.ScalarQueryParameter("poste", "STRING", code_poste),
        ]
    )
    familles = []
    for lue in client.query(sql, job_config=config).result():
        # Une copie : la ligne lue reste intacte.
        famille = dict(lue)
        # Le nom en clair ; une famille inconnue garde son code (visible, pas
        # perdue).
        famille["famille"] = FAMILLES_EN_CLAIR.get(
            famille["famille"], famille["famille"]
        )
        familles.append(famille)

    resultat = {
        "champion": champion,
        "patch": patch,
        "definitions": DEFINITIONS_BUILDS,
        "familles": familles,
    }
    if not familles:
        resultat["remarque"] = (
            "aucun build trouve : le nom du champion est peut-etre mal ecrit, ou "
            "il a trop peu de parties a ce patch et a ce poste sur le ladder"
        )
    return resultat


def dernier_patch(client) -> str:
    """Le patch le plus recent qui a des parties de ladder en prod, ecrit comme
    Riot ("16.23"). Le modele ne le connait pas : le lanceur le lui donne dans
    ses consignes. Leve ValueError si le ladder est vide."""
    sql = f"""
        SELECT MAX(patch_key) AS cle
        FROM `{PROJET}.{DATASET}.mart_ladder_champion_patch`
    """
    (ligne,) = client.query(sql).result()
    cle = ligne["cle"]
    if cle is None:
        raise ValueError("aucun patch avec des parties de ladder")
    # 1623 -> 1623 // 100 = 16 (division entiere) et 1623 % 100 = 23 (le
    # reste) : "16.23". Et 1604 -> "16.4", comme Riot l'ecrit.
    return f"{cle // 100}.{cle % 100}"


DEFINITIONS_BULLETIN = {
    "resume": "le bulletin du patch en une phrase, deja calculee et verifiee : "
    "reprends-la telle quelle",
    "objets_controles": "le nombre de premiers objets achetes controles (les 3 "
    "premiers objets termines de chaque joueur du ladder)",
    "fidelite_pct": "en % : la part de ces objets retrouves dans l'inventaire "
    "de fin de partie. Pres de 100 % = nos builds decrivent bien ce que les "
    "joueurs possedent. Ne dit rien de la theorie",
    "duels_familles": "le nombre de duels de familles : pour un champion a son "
    "poste, le build le plus joue contre sa meilleure alternative (10 parties "
    "ou plus)",
    "familles_populaire_prouve": "les duels ou le build populaire est prouve "
    "meilleur (fourchettes de Wilson separees)",
    "familles_pepites": "les duels ou une alternative est prouvee meilleure que "
    "le build populaire (une pepite) ; a confirmer au patch suivant",
    "duels_chemins": "la meme chose au niveau du chemin (les 2 premiers objets)",
    "chemins_populaire_prouve": "les duels de chemins ou le populaire est prouve",
    "chemins_pepites": "les pepites au niveau du chemin",
    "experiences": "le nombre de changements de Riot (objets ou champions) juges "
    "sur le ladder a ce patch",
    "experiences_sens_predit": "les experiences dont la part de jeu ou d'achat "
    "a bouge dans le sens predit par la theorie (prouve ou non)",
    "experiences_prouvees": "les experiences prouvees dans le sens predit",
    "experiences_contredites": "les experiences prouvees dans l'autre sens",
}


def bulletin_du_patch(patch: str, client) -> dict:
    """Le bulletin d'un patch (mart_patch_bulletin) : la fidelite des builds,
    les duels du build populaire contre ses alternatives, les experiences
    naturelles. Les chiffres, et une phrase de bilan calculee ici : ce qui doit
    etre juste ne passe pas par le modele (essais du 23/11). Leve ValueError si
    le patch est illisible."""
    cle = _cle_du_patch(patch)
    sql = f"""
        SELECT
            items_checked AS objets_controles,
            ROUND(fidelity_rate * 100, 2) AS fidelite_pct,
            family_duels AS duels_familles,
            family_confirmed AS familles_populaire_prouve,
            family_gems AS familles_pepites,
            path_duels AS duels_chemins,
            path_confirmed AS chemins_populaire_prouve,
            path_gems AS chemins_pepites,
            experiments AS experiences,
            experiments_predicted_direction AS experiences_sens_predit,
            experiments_confirmed AS experiences_prouvees,
            experiments_contradicted AS experiences_contredites
        FROM `{PROJET}.{DATASET}.mart_patch_bulletin`
        WHERE patch_key = @patch
    """
    config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("patch", "INT64", cle)]
    )
    lignes = list(client.query(sql, job_config=config).result())
    if not lignes:
        return {
            "patch": patch,
            "definitions": DEFINITIONS_BULLETIN,
            "bulletin": None,
            "remarque": "aucun bulletin pour ce patch : pas encore de parties "
            "de ladder (ou patch inconnu)",
        }

    # Une copie : la ligne lue reste intacte.
    b = dict(lignes[0])
    # 94103 -> "94 103" (separateur de milliers a la francaise) ; 99.83 ->
    # "99,83 %".
    objets = f"{b['objets_controles']:,}".replace(",", " ")
    fidelite = f"{b['fidelite_pct']:.2f}".replace(".", ",")
    # Les duels ni prouves pour le populaire ni pepites : non departages.
    familles_non_departagees = (
        b["duels_familles"] - b["familles_populaire_prouve"] - b["familles_pepites"]
    )
    chemins_non_departages = (
        b["duels_chemins"] - b["chemins_populaire_prouve"] - b["chemins_pepites"]
    )
    # Chaque mesure dit ce qu'elle juge (essai du 23/11 : le modele prenait la
    # fidelite pour une preuve de la theorie). Seules les experiences jugent la
    # theorie.
    phrases = [
        f"Bulletin du patch {patch}.",
        "Fidelite des builds (dit si nous lisons bien les builds, rien sur la "
        f"theorie) : {fidelite} % des {objets} premiers objets achetes sont dans "
        "l'inventaire de fin de partie.",
        "Duels (le build le plus joue contre sa meilleure alternative : ils "
        "comparent les builds entre eux, rien sur la theorie) : de familles, "
        f"{b['duels_familles']}, dont populaire prouve meilleur : "
        f"{b['familles_populaire_prouve']}, pepites (alternative prouvee "
        f"meilleure) : {b['familles_pepites']}, non departages : "
        f"{familles_non_departagees} ; de chemins, {b['duels_chemins']}, dont "
        f"populaire prouve meilleur : {b['chemins_populaire_prouve']}, pepites : "
        f"{b['chemins_pepites']}, non departages : {chemins_non_departages}.",
        "Une pepite de debut de patch reste a confirmer au patch suivant.",
    ]
    if b["experiences"] == 0:
        phrases.append(
            "Experiences (seules a juger la theorie) : aucun changement de Riot "
            "jugeable a ce patch."
        )
    else:
        # Chaque groupe compte a part (essai du 25/11 : « la theorie a vu juste
        # 8 fois sur 8 », 4 seulement prouvees). Les « sans preuve » et les
        # « autres » se calculent ici, pas dans la tete du modele.
        n = b["experiences"]
        prouvees = b["experiences_prouvees"]
        sans_preuve = b["experiences_sens_predit"] - prouvees
        contredites = b["experiences_contredites"]
        autres = n - b["experiences_sens_predit"] - contredites
        phrases.append(
            "Experiences (seules a juger la theorie : un changement de Riot, une "
            f"prediction, ce que le ladder a fait) : {n} changements de Riot "
            f"juges. Prouves dans le sens predit : {prouvees} sur {n}. Dans le "
            f"sens predit, mais sans preuve : {sans_preuve}. Contredits (prouves "
            f"dans l'autre sens) : {contredites}. Autres (sens contraire non "
            f"prouve, stables ou sans donnees) : {autres}."
        )
    b["resume"] = " ".join(phrases)
    return {"patch": patch, "definitions": DEFINITIONS_BULLETIN, "bulletin": b}


DEFINITIONS_OBJETS = {
    "resume": "les objets les plus rentables en theorie pour ce champion, deja "
    "mis en phrase : reprends-la telle quelle",
    "degats": "les 5 objets les plus rentables pour les degats du champion, en "
    "theorie (les ratios de ses sorts)",
    "survie": "les 5 objets les plus rentables pour sa survie (ses boucliers, "
    "soins et vitesses), en theorie ; vide s'il n'a aucun ratio de survie",
    "changements": "les 3 plus gros changements de valeur depuis le patch "
    "precedent (un ratio ou une stat d'objet a change)",
    "objet": "le nom de l'objet",
    "rang": "1 = l'objet le plus rentable pour ce champion, dans cette valeur",
    "points_pour_1000_or": "points de ratio (stats de l'objet x ratios des "
    "sorts du champion) pour 1 000 pieces d'or. Ce n'est PAS de l'or, ni un "
    "taux de victoire. Les effets des objets ne comptent pas",
    "valeur": "degats ou survie",
    "ecart_avec_patch_precedent": "variation de la valeur de l'objet, en "
    "points de ratio (pas pour 1 000 po), depuis le patch precedent ; positif = "
    "l'objet est devenu meilleur pour ce champion",
}


def objets_du_champion(champion: str, patch: str, client) -> dict:
    """Les objets les plus rentables EN THEORIE pour un champion (la valeur
    theorique : les stats de l'objet x les ratios de ses sorts), pour ses degats
    et pour sa survie, et les plus gros changements depuis le patch precedent.
    Reprend l'outil du prototype du 05/11 (qui lisait la dev, et les degats
    seuls). Leve ValueError si le patch est illisible."""
    cle = _cle_du_patch(patch)
    # Le champion est trouve par son code (Wukong = MonkeyKing dans les
    # fichiers du jeu) ou par son nom affiche (Data Dragon).
    sql = f"""
        WITH valeurs AS (
            SELECT
                t.value_kind,
                t.item_name,
                t.rank_for_champion,
                t.theory_value_per_1000_gold,
                t.change_vs_previous_patch
            FROM `{PROJET}.{DATASET}.mart_item_theory_value` AS t
            INNER JOIN `{PROJET}.{DATASET}.stg_ddragon__champions` AS c
                ON c.patch_key = t.patch_key AND c.champion_id = t.champion_id
            WHERE t.patch_key = @patch
                AND LOWER(@champion) IN (LOWER(t.champion_code), LOWER(c.champion_name))
        )

        SELECT
            'meilleurs' AS liste,
            value_kind AS valeur,
            item_name AS objet,
            rank_for_champion AS rang,
            theory_value_per_1000_gold AS points_pour_1000_or,
            change_vs_previous_patch AS ecart_avec_patch_precedent
        FROM valeurs
        WHERE rank_for_champion <= 5

        UNION ALL

        SELECT
            'changements',
            value_kind,
            item_name,
            rank_for_champion,
            theory_value_per_1000_gold,
            change_vs_previous_patch
        FROM valeurs
        WHERE change_vs_previous_patch != 0
        QUALIFY ROW_NUMBER() OVER (
            ORDER BY ABS(change_vs_previous_patch) DESC, item_name
        ) <= 3

        ORDER BY liste DESC, valeur, rang, objet
    """
    config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("patch", "INT64", cle),
            bigquery.ScalarQueryParameter("champion", "STRING", champion),
        ]
    )
    lignes = [dict(ligne) for ligne in client.query(sql, job_config=config).result()]

    def meilleurs(valeur):
        return [
            {
                "objet": ligne["objet"],
                "rang": ligne["rang"],
                "points_pour_1000_or": ligne["points_pour_1000_or"],
            }
            for ligne in lignes
            if ligne["liste"] == "meilleurs" and ligne["valeur"] == valeur
        ]

    resultat = {
        "champion": champion,
        "patch": patch,
        "definitions": DEFINITIONS_OBJETS,
        "degats": meilleurs("degats"),
        "survie": meilleurs("survie"),
        "changements": [
            {
                "valeur": ligne["valeur"],
                "objet": ligne["objet"],
                "ecart_avec_patch_precedent": ligne["ecart_avec_patch_precedent"],
            }
            for ligne in lignes
            if ligne["liste"] == "changements"
        ],
    }
    if not lignes:
        resultat["remarque"] = (
            "aucune valeur theorique : le nom du champion est peut-etre mal ecrit, "
            "ou ce patch n'est pas charge"
        )
        return resultat

    def points(valeur):
        # 107.34 -> "107,34" : la virgule sur le NOMBRE seul (un point dans un
        # nom d'objet doit rester un point).
        return f"{valeur:.2f}".replace(".", ",")

    def liste_txt(objets):
        # "Rabadon's Deathcap (107,34 points pour 1 000 po), ..."
        return ", ".join(
            f"{o['objet']} ({points(o['points_pour_1000_or'])} points pour 1 000 po)"
            for o in objets
        )

    degats = liste_txt(resultat["degats"]) or "aucun ratio de degats"
    survie = liste_txt(resultat["survie"]) or "aucun ratio de survie"
    changements = (
        ", ".join(
            f"{c['objet']} ({c['valeur']}, "
            + f"{c['ecart_avec_patch_precedent']:+.1f}".replace(".", ",")
            + " points)"
            for c in resultat["changements"]
        )
        or "aucun"
    )
    resultat["resume"] = (
        "En theorie (les ratios des sorts seulement : ni les effets des objets, "
        f"ni les parties du ladder), pour {champion} au patch {patch}. Pour ses "
        f"degats : {degats}. Pour sa survie : {survie}. "
        "Plus gros changements depuis le patch precedent : "
        f"{changements}. Ce ne sont pas des taux de victoire : ce que jouent "
        "vraiment les joueurs est dans leurs builds."
    )
    return resultat
