"""Le banc d'essai de l'assistant (25/11/2026).

Des questions fixes, posees au vrai modele, et pour chacune l'outil et les
arguments attendus. On ne juge pas le texte de la reponse (il peut varier), on
juge l'APPEL d'outil (il doit etre exact). Ne de l'incident du 25/11 : une mise
a jour automatique d'Ollama (0.40.16 -> 0.40.18) avait casse l'appel d'outils
(outils pas appeles, patch « 11.23 » invente) sans qu'aucun test le voie.

A lancer avant toute mise a jour d'Ollama ou de modele, depuis la racine :
    python assistant/evaluation.py
Code de sortie 0 si toutes les questions passent, 1 sinon.
"""

import sys

import requests
from google.cloud import bigquery

from conversation import outils_prets, repondre
from outils import POSTES, PROJET, dernier_patch

# "{patch}" est remplace par le patch actuel au moment de l'essai.
ESSAIS = [
    {
        "question": "Que dit le bulletin du dernier patch ?",
        "outil": "bulletin_du_patch",
        "arguments": {"patch": "{patch}"},
    },
    {
        "question": "Qu'est-ce qui a change au dernier patch ?",
        "outil": "changements_du_patch",
        "arguments": {"patch": "{patch}"},
    },
    {
        "question": "Quels objets sont les plus rentables en theorie pour Annie ?",
        "outil": "objets_du_champion",
        "arguments": {"champion": "Annie", "patch": "{patch}"},
    },
    {
        "question": "Quels builds pour Ezreal en adc ?",
        "outil": "builds_du_champion",
        "arguments": {"champion": "Ezreal", "patch": "{patch}", "poste": "adc"},
    },
]


def evaluer(essais: list, session, outils: dict, patch_actuel: str) -> list:
    """Pose chaque question au modele et dit si l'outil attendu a ete appele
    avec les arguments attendus (majuscules ignorees ; un poste compare comme
    l'outil le comprend : « adc » = « ADC » = « bottom »). Un modele bloque
    dans les outils compte comme un echec, et l'essai continue."""

    def normalise(nom, valeur):
        texte = str(valeur).strip().lower()
        return POSTES.get(texte, texte) if nom == "poste" else texte

    resultats = []
    for essai in essais:
        attendus = {
            nom: valeur.format(patch=patch_actuel)
            for nom, valeur in essai["arguments"].items()
        }
        journal = []
        try:
            reponse = repondre(
                essai["question"], session, outils, patch_actuel, journal
            )
        except RuntimeError as erreur:
            reponse = f"erreur : {erreur}"
        appels = [(nom, arguments) for nom, arguments, _ in journal]
        ok = any(
            nom == essai["outil"]
            and isinstance(arguments, dict)
            and all(
                normalise(cle, arguments.get(cle, "")) == normalise(cle, valeur)
                for cle, valeur in attendus.items()
            )
            for nom, arguments in appels
        )
        resultats.append(
            {
                "question": essai["question"],
                "attendu": (essai["outil"], attendus),
                "appels": appels,
                "ok": ok,
                "reponse": reponse,
            }
        )
    return resultats


if __name__ == "__main__":
    client = bigquery.Client(project=PROJET)
    patch = dernier_patch(client)
    resultats = evaluer(ESSAIS, requests.Session(), outils_prets(client), patch)
    for r in resultats:
        etat = "OK   " if r["ok"] else "ECHEC"
        print(f"{etat} {r['question']}")
        print(f"      attendu {r['attendu']}")
        print(f"      appels  {r['appels']}")
    reussies = sum(r["ok"] for r in resultats)
    print(f"{reussies} / {len(resultats)} questions reussies (patch {patch})")
    sys.exit(0 if reussies == len(resultats) else 1)
