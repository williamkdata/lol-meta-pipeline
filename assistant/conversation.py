"""La conversation avec le modele de langage local (Ollama), 23/11/2026.

La question part vers le modele, avec les consignes et la liste des outils
qu'il a le droit d'appeler (outils.py). S'il demande un outil, on l'execute et
on lui renvoie le resultat ; puis il repond. Le modele tourne sur le PC (Qwen3
4B, essai du 05/11) : aucun appel payant, aucune donnee ne sort du PC.
"""

import functools
import json
import sys

import requests
from google.cloud import bigquery

from outils import PROJET, builds_du_champion, changements_du_patch, dernier_patch

OLLAMA = "http://127.0.0.1:11434"
# Version officielle de Qwen, depuis Hugging Face : le stockage du registre
# Ollama est injoignable depuis ce reseau (essai du 05/11).
MODELE = "hf.co/Qwen/Qwen3-4B-GGUF:Q4_K_M"
# Une reponse d'un petit modele local peut prendre une minute (essai du 05/11).
TIMEOUT_S = 600
# Au plus 4 allers-retours avec les outils : un modele qui tourne en rond ne
# bloque pas tout.
TOURS_MAX = 4

CONSIGNES = (
    "Tu es un assistant pour joueurs de League of Legends, qui parle du ladder "
    "Challenger et Grandmaster d'EUW. Reponds en francais, en phrases courtes. "
    "N'invente aucun chiffre : utilise seulement les resultats des outils, et "
    "lis leurs definitions avant de citer un chiffre. Propose plusieurs options "
    "au joueur, ne lui impose pas un choix. Dis quand un chiffre repose sur peu "
    "de parties. La theorie ne tient compte que des ratios des sorts, pas des "
    "effets des objets : precise-le quand tu en parles. Si un outil renvoie une "
    "erreur, corrige ta demande ou explique ce qui manque. Le patch actuel est "
    "le {patch_actuel} : utilise-le si le joueur ne precise pas de patch. "
    # Les deux regles suivantes : essai du lanceur du 23/11 (Galio et LeBlanc
    # dits « confirmes », « Galio : survie et victoires ont augmente »).
    "Fais un resume court : le detail chiffre est affiche sous ta reponse. "
    "N'ecris « prouve » ou « confirme » que si la phrase dit « et c'est "
    "prouve » ; sinon ecris « pas encore prouve ». Les mots degats et survie "
    "sont des valeurs theoriques (calculees sur les sorts), jamais des mesures "
    "du ladder : le ladder mesure la part de jeu, la part d'achat et les victoires."
)

# Ce que le modele voit de chaque outil : son nom, a quoi il sert, ses
# parametres. Les noms des parametres sont exactement ceux des fonctions de
# outils.py (un test le verifie).
SCHEMAS_OUTILS = [
    {
        "type": "function",
        "function": {
            "name": "changements_du_patch",
            "description": (
                "Ce que la theorie a predit pour un patch (objets et champions "
                "changes par Riot), et ce que le ladder en a dit."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "patch": {"type": "string", "description": "ex. 16.23"},
                },
                "required": ["patch"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "builds_du_champion",
            "description": (
                "Les familles de builds d'un champion sur le ladder a un patch : "
                "parties, popularite, victoires avec leur fourchette."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "champion": {"type": "string", "description": "ex. Ezreal"},
                    "patch": {"type": "string", "description": "ex. 16.23"},
                    "poste": {
                        "type": "string",
                        "description": "facultatif : top, jungle, mid, adc, support",
                    },
                },
                "required": ["champion", "patch"],
            },
        },
    },
]


def repondre(
    question: str,
    session,
    outils: dict,
    patch_actuel: str,
    journal: list | None = None,
) -> str:
    """La reponse du modele a une question, apres les appels d'outils qu'il a
    demandes. outils : {nom: fonction}, les fonctions deja pretes a lire
    BigQuery. journal (facultatif) : une liste ou noter chaque appel d'outil,
    (nom, arguments, resultat), pour le detail verifie. Leve RuntimeError si le
    modele demande encore des outils apres TOURS_MAX tours."""
    messages = [
        {"role": "system", "content": CONSIGNES.format(patch_actuel=patch_actuel)},
        # "/no_think" : l'interrupteur de Qwen3 pour couper sa reflexion a voix
        # haute (essai du 05/11 : think=False ne suffisait pas seul).
        {"role": "user", "content": question + " /no_think"},
    ]
    # Le modele ne voit que les outils qu'on lui donne vraiment.
    schemas = [s for s in SCHEMAS_OUTILS if s["function"]["name"] in outils]

    for _ in range(TOURS_MAX):
        reponse = session.post(
            f"{OLLAMA}/api/chat",
            json={
                "model": MODELE,
                "messages": messages,
                "tools": schemas,
                "stream": False,
                "think": False,
                # La memoire de travail : 8 192 tokens tiennent sur la carte
                # graphique (essai du 05/11 : par defaut, 48 % seulement).
                # temperature 0 : toujours le mot le plus probable ; la meme
                # question donne la meme reponse, deux essais se comparent.
                "options": {"num_ctx": 8192, "temperature": 0},
            },
            timeout=TIMEOUT_S,
        )
        reponse.raise_for_status()
        message = reponse.json()["message"]
        messages.append(message)

        appels = message.get("tool_calls") or []
        if not appels:
            # Une balise de reflexion vide peut rester en tete : on la retire.
            return message.get("content", "").split("</think>")[-1].strip()

        for appel in appels:
            nom = appel["function"]["name"]
            try:
                arguments = appel["function"].get("arguments") or {}
                # Certains modeles ecrivent les arguments en texte JSON.
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                if nom not in outils:
                    raise ValueError(f"outil inconnu : {nom}")
                resultat = outils[nom](**arguments)
            except (ValueError, TypeError) as erreur:
                # Demande refusee (patch illisible, poste inconnu, nom
                # d'argument invente) : le modele lit l'erreur et peut corriger.
                resultat = {"erreur": str(erreur)}
            if journal is not None:
                journal.append((nom, arguments, resultat))
            messages.append(
                {
                    "role": "tool",
                    "tool_name": nom,
                    # default=str : une date ou un nombre decimal de BigQuery
                    # devient du texte au lieu de faire planter l'envoi.
                    "content": json.dumps(resultat, ensure_ascii=False, default=str),
                }
            )

    raise RuntimeError(f"pas de reponse du modele apres {TOURS_MAX} tours d'outils")


def detail_verifie(journal: list) -> str:
    """Le detail des resultats des outils, mis en forme par le PROGRAMME, pas
    par le modele : les phrases de verdict recopiees mot pour mot, une ligne par
    famille de builds. Affiche sous le resume du modele, qui peut resumer de
    travers (essai du 23/11 : « victoires stables » pour Galio, 49 % -> 53 %).
    journal : les (nom, arguments, resultat) notes par repondre."""

    def pct(valeur):
        # 60.2 -> "60,2 %" : la virgule francaise.
        return f"{valeur:.1f}".replace(".", ",") + " %"

    lignes = []
    vus = set()
    for nom, arguments, resultat in journal:
        # Le meme appel deux fois (le modele redemande parfois) : une seule fois.
        cle = (nom, json.dumps(arguments, sort_keys=True, default=str))
        if cle in vus:
            continue
        vus.add(cle)

        if "erreur" in resultat:
            lignes.append(f"{nom} : erreur : {resultat['erreur']}")
            continue
        if nom == "changements_du_patch":
            lignes.append(f"Changements du patch {resultat['patch']} :")
            lignes.extend(f"- {p['verdict']}" for p in resultat["predictions"])
        elif nom == "builds_du_champion":
            lignes.append(
                f"Builds de {resultat['champion']} au patch {resultat['patch']} :"
            )
            for f in resultat["familles"]:
                if f["vrai_choix"]:
                    choix = f"rang {f['rang_parmi_les_choix']} parmi les choix"
                else:
                    choix = "moins de 10 parties : pas un choix"
                ligne = (
                    f"- {f['poste']}, {f['famille']} : {f['parties']} parties "
                    f"({pct(f['part_des_parties_pct'])} des parties), victoires "
                    f"{pct(f['victoires_pct'])} [{pct(f['victoires_bas_pct'])} ; "
                    f"{pct(f['victoires_haut_pct'])}], {choix}"
                )
                # Ce que contient la famille : ses objets les plus frequents
                # (absents si aucun objet connu).
                if f.get("objets_principaux"):
                    objets = ", ".join(
                        f"{o['objet']} ({o['pct_des_parties']} %)"
                        for o in f["objets_principaux"]
                    )
                    ligne += f" ; objets : {objets}"
                lignes.append(ligne)
        else:
            lignes.append(f"{nom} : pas de detail pour cet outil")
            continue
        if "remarque" in resultat:
            lignes.append(f"- {resultat['remarque']}")
    return "\n".join(lignes)


if __name__ == "__main__":
    # A lancer a la main, depuis la racine du depot :
    #   python assistant/conversation.py "Quels builds pour Ezreal en adc ?"
    client = bigquery.Client(project=PROJET)
    # functools.partial : chaque outil avec son client BigQuery deja rempli ; le
    # modele ne fournit que ses propres arguments (patch, champion, poste).
    outils_prets = {
        "changements_du_patch": functools.partial(changements_du_patch, client=client),
        "builds_du_champion": functools.partial(builds_du_champion, client=client),
    }
    question = " ".join(sys.argv[1:]) or "Qu'est-ce qui a change au dernier patch ?"
    journal = []
    resume = repondre(
        question, requests.Session(), outils_prets, dernier_patch(client), journal
    )
    # Deux blocs : le resume redige par le modele, puis le detail calcule et
    # recopie par le programme (les chiffres garantis).
    print(resume)
    detail = detail_verifie(journal)
    if detail:
        print("\n--- Detail verifie (calcule par le programme, pas par le modele) ---")
        print(detail)
