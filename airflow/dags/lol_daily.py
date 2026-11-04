"""Pipeline LoL quotidien : Data Dragon + Oracle's Elixir + ladder EUW + kits, puis dbt.

    [ingest_ddragon, ingest_oracles_elixir, ingest_ladder, ingest_kits]
        >> dbt_deps >> dbt_build

Cadence : une fois par jour, a 14 h 30 UTC. Oracle's Elixir publie son fichier
une fois par jour (observe : 13 h 05 UTC le 29/10/2026) et demande de ne pas
le telecharger plus souvent. Data Dragon ne charge que les nouveaux patches :
les jours sans patch, la tache ne fait rien.

dbt tourne sur la cible prod (dataset lol_analytics), avec le compte de
service, et --no-partial-parse : un cache d'analyse perime a deja fait passer
un build "reussi" sans lancer aucun test (02/11/2026).
"""

from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

DBT_DIR = "/opt/airflow/dbt"
DBT_OPTIONS = f"--project-dir {DBT_DIR} --profiles-dir {DBT_DIR}/profiles --target prod"

with DAG(
    dag_id="lol_daily",
    description="Data Dragon + Oracle's Elixir + ladder EUW -> dbt build (prod)",
    schedule="30 14 * * *",
    start_date=datetime(2026, 11, 1),
    # Pas de rattrapage : rejouer les jours manques n'a pas de sens, les deux
    # sources renvoient toujours l'etat le plus recent.
    catchup=False,
    # Jamais deux executions en meme temps : vecu sur Velib', deux runs
    # simultanes avaient duplique 1 518 lignes.
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=10)},
    tags=["lol"],
) as dag:
    ingest_ddragon = BashOperator(
        task_id="ingest_ddragon",
        bash_command="cd /opt/airflow && python ingestion/ddragon.py",
    )

    # Google Drive peut refuser un fichier tres demande pendant des heures :
    # les nouvelles tentatives sont espacees de 2 h, pas de quelques minutes.
    ingest_oracles_elixir = BashOperator(
        task_id="ingest_oracles_elixir",
        bash_command="cd /opt/airflow && python ingestion/oracles_elixir.py",
        retries=3,
        retry_delay=timedelta(hours=2),
    )

    # Le ladder EUW par l'API Riot (cle personal) : 1 000 joueurs (Challenger +
    # Grandmaster), ~1 800 requetes, ~36 min au rythme du quota (mesure du
    # 03/11 : 825 requetes en 17 min avec la session). Un nouvel essai ne
    # recollecte rien : les parties deja en base sont ecartees. Le plafond de
    # 2 h evite qu'un run bloque tienne la place du suivant.
    ingest_ladder = BashOperator(
        task_id="ingest_ladder",
        bash_command="cd /opt/airflow && python ingestion/ladder.py",
        execution_timeout=timedelta(hours=2),
    )

    # Les kits des champions (formules des sorts) depuis CommunityDragon : seuls
    # les patches absents de BigQuery sont charges. Les jours sans nouveau patch,
    # rien n'est telecharge ; le jour d'un patch (~1 min, 173 fichiers), le dbt
    # build qui suit produit la liste des changements (mart_kit_*_changes).
    ingest_kits = BashOperator(
        task_id="ingest_kits",
        bash_command="cd /opt/airflow && python ingestion/kits.py",
    )

    # dbt_packages/ n'est pas versionne : on l'installe a chaque run.
    dbt_deps = BashOperator(
        task_id="dbt_deps",
        bash_command=f"dbt deps --project-dir {DBT_DIR}",
    )

    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=f"dbt build {DBT_OPTIONS} --no-partial-parse --no-use-colors",
    )

    (
        [ingest_ddragon, ingest_oracles_elixir, ingest_ladder, ingest_kits]
        >> dbt_deps
        >> dbt_build
    )
