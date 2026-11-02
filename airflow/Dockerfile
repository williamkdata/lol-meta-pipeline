FROM apache/airflow:3.3.0

# Ce dont les taches ont besoin pour lancer l'ingestion et dbt. Recopie depuis
# pyproject.toml : seulement l'execution, pas les outils de developpement
# (pytest, ruff) inutiles dans Airflow.
RUN pip install --no-cache-dir \
    "dbt-bigquery>=1.12.0" \
    "dbt-core>=1.12.0" \
    "google-cloud-bigquery>=3.46.2" \
    "google-cloud-storage>=3.1.1" \
    "requests>=2.34.2"
