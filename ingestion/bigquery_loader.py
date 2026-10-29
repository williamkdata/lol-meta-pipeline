"""Chargement de lignes dans BigQuery, commun a toutes les sources."""

from google.cloud import bigquery


def load_rows(rows: list[dict], table_id: str, schema: list, client) -> int:
    """Ajoute des lignes a une table BigQuery. Retourne le nombre de lignes chargees."""
    if not rows:
        return 0

    config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    job = client.load_table_from_json(rows, table_id, job_config=config)
    job.result()

    if job.output_rows != len(rows):
        raise RuntimeError(
            f"{len(rows)} lignes envoyees, {job.output_rows} chargees dans {table_id}"
        )
    return job.output_rows
