import logging
import sys
import time
from pathlib import Path

from quotidien import (
    COLLECTES,
    Etape,
    code_de_sortie,
    lancer_commande,
    run_pipeline,
)

DD = Etape("ingest_ddragon", ["python", "ingestion/ddragon.py"])
OE = Etape(
    "ingest_oracles_elixir",
    ["python", "ingestion/oracles_elixir.py"],
    essais=4,
    attente_s=2 * 3600,
)
LADDER = Etape("ingest_ladder", ["python", "ingestion/ladder.py"])
DEPS = Etape("dbt_deps", ["dbt", "deps"])
BUILD = Etape("dbt_build", ["dbt", "build"])


class FauxLanceur:
    """Lance pour de faux : rend les resultats prevus, essai par essai, et
    note chaque lancement et chaque attente."""

    def __init__(self, resultats=None):
        # {nom de l'etape: [resultat du 1er essai, du 2e, ...]} ; absent = reussi.
        self.resultats = resultats or {}
        self.lancements = []
        self.attentes = []

    def lancer(self, etape):
        self.lancements.append(etape.nom)
        prevus = self.resultats.get(etape.nom, [])
        essai = self.lancements.count(etape.nom)
        return prevus[essai - 1] if essai <= len(prevus) else True

    def attendre(self, secondes):
        self.attentes.append(secondes)


def test_tout_reussit_du_premier_coup():
    faux = FauxLanceur()
    bilan = run_pipeline([DD, OE, LADDER], [DEPS, BUILD], faux.lancer, faux.attendre)

    assert faux.lancements == [
        "ingest_ddragon",
        "ingest_oracles_elixir",
        "ingest_ladder",
        "dbt_deps",
        "dbt_build",
    ]
    assert faux.attentes == []
    assert set(bilan.values()) == {"reussie"}


def test_un_echec_puis_une_relance_qui_reussit():
    # Le 12/11 : le reseau n'etait pas pret au reveil du PC, la 2e tentative
    # du ladder est passee.
    faux = FauxLanceur({"ingest_ladder": [False, True]})
    bilan = run_pipeline([DD, LADDER], [DEPS, BUILD], faux.lancer, faux.attendre)

    assert faux.lancements.count("ingest_ladder") == 2
    assert faux.attentes == [600]  # 10 min, comme les relances d'Airflow
    assert bilan["ingest_ladder"] == "reussie"
    assert bilan["dbt_build"] == "reussie"


def test_chaque_etape_a_son_attente():
    # Oracle's Elixir : 2 h entre deux essais (Google Drive refuse parfois un
    # fichier tres demande pendant des heures).
    faux = FauxLanceur({"ingest_oracles_elixir": [False, False, True]})
    run_pipeline([OE], [BUILD], faux.lancer, faux.attendre)

    assert faux.attentes == [7200, 7200]


def test_une_collecte_qui_echoue_n_arrete_pas_les_autres_mais_bloque_dbt():
    # Comme Airflow : les collectes tournent toutes ; dbt ne tourne que si
    # toutes ont reussi.
    faux = FauxLanceur({"ingest_ddragon": [False, False, False]})
    bilan = run_pipeline([DD, LADDER], [DEPS, BUILD], faux.lancer, faux.attendre)

    assert faux.lancements.count("ingest_ddragon") == 3  # 1 essai + 2 relances
    assert "ingest_ladder" in faux.lancements
    assert "dbt_deps" not in faux.lancements
    assert bilan == {
        "ingest_ddragon": "echouee",
        "ingest_ladder": "reussie",
        "dbt_deps": "pas lancee",
        "dbt_build": "pas lancee",
    }


def test_pas_d_attente_apres_le_dernier_essai():
    faux = FauxLanceur({"ingest_ddragon": [False, False, False]})
    run_pipeline([DD], [], faux.lancer, faux.attendre)

    assert faux.attentes == [600, 600]  # entre les essais, pas apres le dernier


def test_dbt_s_arrete_au_premier_echec():
    # dbt build a besoin des paquets installes par dbt deps.
    faux = FauxLanceur({"dbt_deps": [False, False, False]})
    bilan = run_pipeline([DD], [DEPS, BUILD], faux.lancer, faux.attendre)

    assert "dbt_build" not in faux.lancements
    assert bilan["dbt_deps"] == "echouee"
    assert bilan["dbt_build"] == "pas lancee"


# --- lancer_commande : un vrai essai d'une etape ---
# De vraies petites commandes Python (sys.executable : le Python qui lance les
# tests, sur le PC comme dans la CI).


def commande_python(code):
    return [sys.executable, "-c", code]


def test_une_commande_qui_reussit():
    etape = Etape("essai", commande_python("print('ok')"))
    assert lancer_commande(etape) is True


def test_une_commande_qui_echoue():
    etape = Etape("essai", commande_python("raise SystemExit(3)"))
    assert lancer_commande(etape) is False


def test_une_commande_trop_longue_est_arretee():
    # Le ladder est arrete au-dela de 2 h ; ici, au-dela de 1 s.
    etape = Etape("essai", commande_python("import time; time.sleep(3)"), delai_max_s=1)
    debut = time.monotonic()
    assert lancer_commande(etape) is False
    assert time.monotonic() - debut < 2.5


def test_une_commande_introuvable_ne_fait_pas_planter():
    etape = Etape("essai", ["commande-qui-n-existe-pas-du-tout"])
    assert lancer_commande(etape) is False


def test_l_echec_est_ecrit_dans_le_journal(caplog):
    # Dans le cloud, le journal est le seul endroit ou l'on voit ce qui s'est
    # passe : le nom de l'etape et le code de sortie doivent y etre.
    caplog.set_level(logging.INFO)
    lancer_commande(Etape("ingest_ladder", commande_python("raise SystemExit(3)")))
    assert "ingest_ladder" in caplog.text
    assert "code de sortie 3" in caplog.text


# --- code_de_sortie et la liste des etapes ---


def test_code_de_sortie_zero_si_tout_a_reussi():
    assert code_de_sortie({"ingest_ladder": "reussie", "dbt_build": "reussie"}) == 0


def test_code_de_sortie_un_si_une_etape_a_echoue():
    assert code_de_sortie({"ingest_ladder": "echouee", "dbt_build": "pas lancee"}) == 1


def test_code_de_sortie_un_si_une_etape_n_a_pas_ete_lancee():
    assert code_de_sortie({"ingest_ladder": "reussie", "dbt_build": "pas lancee"}) == 1


def test_chaque_collecte_pointe_vers_un_script_qui_existe():
    # Une faute de frappe dans un chemin ne se verrait qu'au premier run dans
    # le cloud : on la voit ici.
    racine = Path(__file__).resolve().parents[1]
    for etape in COLLECTES:
        script = etape.commande[1]
        assert (racine / script).is_file(), (etape.nom, script)


def test_les_collectes_du_dag_sont_toutes_la():
    # Les memes 5 collectes que le DAG lol_daily.
    assert {etape.nom for etape in COLLECTES} == {
        "ingest_ddragon",
        "ingest_oracles_elixir",
        "ingest_ladder",
        "ingest_kits",
        "ingest_item_stats",
    }


def test_oracles_elixir_passe_en_dernier():
    # Ses relances attendent 2 h : en dernier, elles ne retardent personne.
    assert COLLECTES[-1].nom == "ingest_oracles_elixir"
