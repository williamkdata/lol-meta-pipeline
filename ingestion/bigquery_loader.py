"""Chargement de lignes dans BigQuery, commun a toutes les sources."""

from google.cloud import bigquery


def load_rows(
    rows: list[dict], table_id: str, schema: list, client, partition_field=None
) -> int:
    """Ajoute des lignes a une table BigQuery. Retourne le nombre de lignes chargees.

    partition_field : colonne date ou horodatage qui decoupe la table par jour.
    Ne compte qu'a la creation de la table (premier chargement)."""
    if not rows:
        return 0

    partitions = None
    if partition_field:
        partitions = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY, field=partition_field
        )

    config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        time_partitioning=partitions,
    )
    job = client.load_table_from_json(rows, table_id, job_config=config)
    job.result()

    if job.output_rows != len(rows):
        raise RuntimeError(
            f"{len(rows)} lignes envoyees, {job.output_rows} chargees dans {table_id}"
        )
    return job.output_rows
