"""Chargement de lignes dans BigQuery, commun a toutes les sources."""

from google.cloud import bigquery


def load_rows(
    rows: list[dict],
    table_id: str,
    schema: list,
    client,
    partition_field=None,
    remplacer: bool = False,
) -> int:
    """Ajoute des lignes a une table BigQuery. Retourne le nombre de lignes chargees.

    partition_field : colonne date ou horodatage qui decoupe la table par jour.
    Ne compte qu'a la creation de la table (premier chargement).

    remplacer : vide la table avant d'ecrire (WRITE_TRUNCATE), au lieu
    d'ajouter. Pour une table qui ne garde qu'une version a la fois (l'apercu
    du PBE). Jamais pour le brut ordinaire : ce serait effacer l'historique.
    Sans ligne, rien n'est fait, meme avec remplacer : l'appelant doit refuser
    un chargement vide s'il veut vider la table."""
    if not rows:
        return 0

    partitions = None
    if partition_field:
        partitions = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY, field=partition_field
        )

    if remplacer:
        mode = bigquery.WriteDisposition.WRITE_TRUNCATE
    else:
        mode = bigquery.WriteDisposition.WRITE_APPEND

    config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition=mode,
        time_partitioning=partitions,
    )
    job = client.load_table_from_json(rows, table_id, job_config=config)
    job.result()

    if job.output_rows != len(rows):
        raise RuntimeError(
            f"{len(rows)} lignes envoyees, {job.output_rows} chargees dans {table_id}"
        )
    return job.output_rows
