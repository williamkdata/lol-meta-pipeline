"""Le chef d'orchestre du run quotidien, hors d'Airflow (job Cloud Run, 18/11/2026).

Il refait ce que fait le DAG lol_daily : les collectes, chacune avec ses
relances, puis dbt seulement si toutes ont reussi. Le DAG reste dans le depot
(il tourne encore sur le PC tant que la bascule n'est pas faite).
"""

import logging
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass

journal = logging.getLogger(__name__)


@dataclass
class Etape:
    """Une etape du run : un nom, une commande, et sa politique de relance.

    essais : le nombre total d'essais (3 = 1 essai + 2 relances, comme le
    reglage par defaut du DAG) ; attente_s : la pause entre deux essais
    (10 min par defaut). delai_max_s : au-dela, l'essai est arrete et compte
    comme un echec (le ladder : 2 h, comme dans le DAG).
    """

    nom: str
    commande: list[str]
    essais: int = 3
    attente_s: int = 600
    delai_max_s: int | None = None


# Les collectes, avec les memes commandes et relances que le DAG lol_daily.
# Dans le cloud, elles tournent l'une APRES l'autre (pas en parallele) : les
# rapides d'abord, puis le ladder (le plus long et le plus important), et
# Oracle's Elixir en DERNIER, pour que ses pauses de 2 h ne retardent personne.
# sys.executable : le Python qui lance ce script (celui de l'image).
COLLECTES = [
    Etape("ingest_ddragon", [sys.executable, "ingestion/ddragon.py"]),
    Etape("ingest_kits", [sys.executable, "ingestion/kits.py"]),
    Etape("ingest_item_stats", [sys.executable, "ingestion/item_stats.py"]),
    # Arrete au-dela de 2 h, comme dans le DAG (~52 min un jour normal).
    Etape("ingest_ladder", [sys.executable, "ingestion/ladder.py"], delai_max_s=7200),
    # Google Drive peut refuser un fichier tres demande pendant des heures :
    # 3 relances espacees de 2 h, comme dans le DAG.
    Etape(
        "ingest_oracles_elixir",
        [sys.executable, "ingestion/oracles_elixir.py"],
        essais=4,
        attente_s=2 * 3600,
    ),
]

# dbt deps n'est pas ici : les paquets dbt sont installes une fois, a la
# fabrication de l'image Docker. --no-partial-parse : un cache d'analyse
# perime a deja fait passer un build "reussi" sans lancer aucun test (02/11).
FINALES = [
    Etape(
        "dbt_build",
        [
            "dbt",
            "build",
            "--project-dir",
            "dbt",
            "--profiles-dir",
            "dbt/profiles",
            "--target",
            "prod",
            "--no-partial-parse",
            "--no-use-colors",
        ],
    ),
]


def run_pipeline(
    collectes: list[Etape],
    finales: list[Etape],
    lancer: Callable[[Etape], bool],
    attendre: Callable[[float], None],
) -> dict[str, str]:
    """Lance les collectes, puis les etapes finales (dbt) si toutes ont reussi.

    lancer(etape) lance UN essai et dit s'il a reussi ; attendre(secondes) fait
    la pause entre deux essais. Les recevoir en parametre permet de tester sans
    rien lancer ni attendre pour de vrai.

    Rend le bilan {nom de l'etape: "reussie" | "echouee" | "pas lancee"}.
    - Toutes les collectes sont lancees, meme si l'une echoue (dans le DAG,
      elles tournent en parallele).
    - Les etapes finales ne sont lancees que si toutes les collectes ont reussi,
      et s'arretent au premier echec (dbt build a besoin de dbt deps).
    """
    bilan = {}
    for etape in collectes:
        bilan[etape.nom] = _avec_relances(etape, lancer, attendre)

    peut_continuer = all(etat == "reussie" for etat in bilan.values())
    for etape in finales:
        if peut_continuer:
            bilan[etape.nom] = _avec_relances(etape, lancer, attendre)
            peut_continuer = bilan[etape.nom] == "reussie"
        else:
            bilan[etape.nom] = "pas lancee"
    return bilan


def _avec_relances(etape: Etape, lancer, attendre) -> str:
    """Les essais d'une etape : on s'arrete au premier qui reussit ; une pause
    entre deux essais, jamais apres le dernier."""
    for essai in range(1, etape.essais + 1):
        if lancer(etape):
            return "reussie"
        if essai < etape.essais:
            attendre(etape.attente_s)
    return "echouee"


def lancer_commande(etape: Etape) -> bool:
    """Lance UN essai de l'etape, pour de vrai ; vrai si la commande a reussi.

    Reussie = code de sortie 0 (la convention des programmes : 0 veut dire
    "tout va bien"). Au-dela de delai_max_s, la commande est arretee : echec.
    Une commande introuvable compte aussi comme un echec : le chef d'orchestre
    ne doit jamais planter, il doit finir et rendre son bilan.
    La sortie de la commande s'affiche telle quelle : dans le cloud, elle part
    dans le journal du job.
    """
    journal.info("%s : lancement de %s", etape.nom, " ".join(etape.commande))
    debut = time.monotonic()
    try:
        resultat = subprocess.run(etape.commande, timeout=etape.delai_max_s)
    except subprocess.TimeoutExpired:
        journal.error(
            "%s : arretee apres %d s (delai maximum)", etape.nom, etape.delai_max_s
        )
        return False
    except OSError as erreur:
        journal.error("%s : impossible de lancer la commande (%s)", etape.nom, erreur)
        return False
    duree = time.monotonic() - debut
    if resultat.returncode == 0:
        journal.info("%s : reussie en %.0f s", etape.nom, duree)
        return True
    journal.error(
        "%s : echec, code de sortie %d, apres %.0f s",
        etape.nom,
        resultat.returncode,
        duree,
    )
    return False


def code_de_sortie(bilan: dict[str, str]) -> int:
    """0 si toutes les etapes ont reussi, 1 sinon (echec ou etape pas lancee).
    Un code non nul fait marquer le run "en echec" par Cloud Run : c'est ce qui
    declenchera l'alerte."""
    return 0 if all(etat == "reussie" for etat in bilan.values()) else 1


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s : %(message)s"
    )
    bilan = run_pipeline(COLLECTES, FINALES, lancer_commande, time.sleep)
    for nom, etat in bilan.items():
        journal.info("bilan : %s %s", nom, etat)
    sys.exit(code_de_sortie(bilan))
