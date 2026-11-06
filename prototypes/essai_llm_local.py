"""Essai du 05/11/2026 : un LLM local (Ollama) appelle un outil qui lit nos marts.

Trois choses a verifier :
1. le modele tourne sur la carte graphique (et pas sur le processeur) ;
2. il comprend la question et appelle l'outil avec les bons arguments ;
3. sa reponse en francais reprend les chiffres de l'outil sans en inventer.
"""

import json
import time
import urllib.request

from google.cloud import bigquery

OLLAMA = "http://127.0.0.1:11434"
# Version officielle de Qwen, telechargee depuis Hugging Face : le stockage du
# registre Ollama (Cloudflare 172.64.x.x) est injoignable depuis ce reseau.
MODELE = "hf.co/Qwen/Qwen3-4B-GGUF:Q4_K_M"
# La prod n'aura ce mart qu'apres le dbt build du run de 14 h 30 (05/11).
DATASET = "lol_analytics_dev"

CONSIGNES = (
    "Tu es un assistant pour joueurs de League of Legends. Reponds en francais, "
    "en phrases courtes. N'invente aucun chiffre : utilise seulement les resultats "
    "des outils. Propose plusieurs options au joueur, ne lui impose pas un choix. "
    "La valeur theorique ne tient compte que des ratios des sorts du champion, pas "
    "des passifs des objets : precise-le."
)

OUTILS = [
    {
        "type": "function",
        "function": {
            "name": "objets_du_champion",
            "description": (
                "Valeur theorique des objets pour un champion a un patch donne "
                "(d'apres les ratios de ses sorts), et les objets dont la valeur a "
                "le plus change par rapport au patch precedent."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "champion": {
                        "type": "string",
                        "description": "Nom du champion, ex. Pyke",
                    },
                    "patch": {"type": "string", "description": "Patch au format 16.22"},
                },
                "required": ["champion", "patch"],
            },
        },
    }
]


def appeler(chemin, corps=None):
    """Appelle le serveur Ollama local et renvoie sa reponse JSON."""
    donnees = json.dumps(corps).encode() if corps is not None else None
    requete = urllib.request.Request(
        OLLAMA + chemin, data=donnees, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(requete, timeout=600) as reponse:
        return json.loads(reponse.read())


def objets_du_champion(champion: str, patch: str) -> dict:
    """L'outil : lit mart_item_theory_value avec des parametres (pas de SQL libre)."""
    client = bigquery.Client(project="lol-meta-pipeline")
    cle_patch = int(patch.replace(".", ""))  # "16.22" -> 1622
    config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("champion", "STRING", champion),
            bigquery.ScalarQueryParameter("patch", "INT64", cle_patch),
        ]
    )
    base = (
        f"FROM `lol-meta-pipeline.{DATASET}.mart_item_theory_value` "
        "WHERE LOWER(champion_code) = LOWER(@champion) AND patch_key = @patch"
    )
    meilleurs = (
        "SELECT item_name AS objet, rank_for_champion AS rang, "
        f"theory_value_per_1000_gold AS valeur_pour_1000_or {base} "
        "ORDER BY rang LIMIT 5"
    )
    changements = (
        "SELECT item_name AS objet, "
        "change_vs_previous_patch AS ecart_avec_patch_precedent "
        f"{base} AND change_vs_previous_patch != 0 "
        "ORDER BY ABS(change_vs_previous_patch) DESC LIMIT 3"
    )
    return {
        "champion": champion,
        "patch": patch,
        # La couche semantique : chaque chiffre arrive avec sa definition et son unite
        # (essai 1 : sans elles, le modele a pris des points de ratio pour de l'or).
        "definitions": {
            "valeur_pour_1000_or": (
                "points de ratio (stats de l'objet x ratios des sorts du champion) "
                "obtenus pour 1 000 pieces d'or depensees. Ce n'est PAS de l'or."
            ),
            "rang": "1 = l'objet le plus rentable pour ce champion, d'apres la theorie",
            "ecart_avec_patch_precedent": (
                "variation de la valeur de l'objet (en points de ratio) depuis "
                "le patch precedent ; positif = l'objet est devenu meilleur "
                "pour ce champion"
            ),
        },
        "meilleurs_objets_en_theorie": [
            dict(r) for r in client.query(meilleurs, job_config=config).result()
        ],
        "plus_grands_changements": [
            dict(r) for r in client.query(changements, job_config=config).result()
        ],
    }


def discuter(messages):
    debut = time.perf_counter()
    r = appeler(
        "/api/chat",
        # think=False : Qwen3 sait "reflechir a voix haute" avant de repondre ;
        # coupe ici pour une reponse rapide (a comparer plus tard).
        # num_ctx : la memoire de travail du modele. Par defaut 40 960 tokens -> 8,9 Go,
        # dont 48 % seulement sur la carte graphique (essai 1). 8 192 suffisent ici.
        {
            "model": MODELE,
            "messages": messages,
            "tools": OUTILS,
            "stream": False,
            "think": False,
            "options": {"num_ctx": 8192},
        },
    )
    duree = time.perf_counter() - debut
    secondes = r.get("eval_duration", 0) / 1e9
    vitesse = r["eval_count"] / secondes if secondes else 0
    print(
        f"  [{duree:.1f} s ; {r.get('prompt_eval_count')} tokens lus, "
        f"{r.get('eval_count')} ecrits, {vitesse:.0f} tokens/s]"
    )
    return r["message"]


question = (
    "Avec le patch 16.22, quels objets sont devenus plus interessants pour Pyke ?"
)
# "/no_think" : interrupteur documente par Qwen3 pour couper la reflexion a voix
# haute (essai 1 : think=False n'a pas suffi avec le modele venu de Hugging Face).
messages = [
    {"role": "system", "content": CONSIGNES},
    {"role": "user", "content": question + " /no_think"},
]
print("QUESTION :", question)

print("\n1) Le modele lit la question :")
reponse = discuter(messages)
appels = reponse.get("tool_calls") or []
print("  Appels d'outil demandes :", [c["function"] for c in appels] or "aucun")
messages.append(reponse)

for appel in appels:
    nom = appel["function"]["name"]
    arguments = appel["function"]["arguments"]
    resultat = objets_du_champion(**arguments) if nom == "objets_du_champion" else {}
    print("\n2) L'outil renvoie :", json.dumps(resultat, ensure_ascii=False, indent=1))
    messages.append(
        {
            "role": "tool",
            "tool_name": nom,
            "content": json.dumps(resultat, ensure_ascii=False),
        }
    )

if appels:
    print("\n3) Le modele repond avec les chiffres :")
    reponse = discuter(messages)
texte = reponse.get("content", "")
# Une balise de reflexion vide peut rester en tete : on la retire.
texte = texte.split("</think>")[-1].strip()
print("\nREPONSE :\n" + texte)

print("\nCarte graphique :")
for m in appeler("/api/ps").get("models", []):
    part = m["size_vram"] / m["size"] if m.get("size") else 0
    print(
        f"  {m['name']} : {m['size'] / 1e9:.1f} Go en memoire, "
        f"dont {part:.0%} sur la carte graphique"
    )
