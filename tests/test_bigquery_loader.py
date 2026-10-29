import pytest
from google.cloud import bigquery

from bigquery_loader import load_rows
from fakes import FakeBigQuery

TABLE = "lol-meta-pipeline.lol_raw.ddragon_champions"

SCHEMA = [
    bigquery.SchemaField("champion_id", "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("champion_name", "STRING", mode="REQUIRED"),
]

ROWS = [
    {"champion_id": 103, "champion_name": "Ahri"},
    {"champion_id": 62, "champion_name": "Wukong"},
]


def test_load_rows_sends_the_rows_to_the_requested_table():
    client = FakeBigQuery()

    load_rows(ROWS, TABLE, SCHEMA, client)

    [(rows, destination, _)] = client.appels
    assert rows == ROWS
    assert destination == TABLE


def test_load_rows_uses_the_declared_schema():
    """Jamais de schema devine par BigQuery : deux chargements pourraient en
    deviner deux differents. Meme regle que le schema Parquet du projet 2."""
    client = FakeBigQuery()

    load_rows(ROWS, TABLE, SCHEMA, client)

    [(_, _, config)] = client.appels
    assert config.schema == SCHEMA
    assert not config.autodetect


def test_load_rows_appends_to_the_table():
    """Le brut accepte les doublons : c'est le staging dbt qui les retire.
    Remplacer la table effacerait les patches deja charges."""
    client = FakeBigQuery()

    load_rows(ROWS, TABLE, SCHEMA, client)

    [(_, _, config)] = client.appels
    assert config.write_disposition == bigquery.WriteDisposition.WRITE_APPEND


def test_load_rows_waits_for_the_load_to_finish():
    """Le chargement tourne chez Google. Sans attendre sa fin, la fonction
    rendrait la main avant de savoir s'il a reussi."""
    client = FakeBigQuery()

    load_rows(ROWS, TABLE, SCHEMA, client)

    assert client.job.attendu


def test_load_rows_returns_the_number_of_rows_loaded():
    assert load_rows(ROWS, TABLE, SCHEMA, FakeBigQuery()) == 2


def test_load_rows_refuses_a_count_mismatch():
    """BigQuery annonce combien de lignes il a chargees. Si ce n'est pas le
    nombre envoye, quelque chose s'est perdu en route : on s'arrete."""
    client = FakeBigQuery(lignes_annoncees=1)

    with pytest.raises(RuntimeError):
        load_rows(ROWS, TABLE, SCHEMA, client)


def test_load_rows_does_nothing_without_rows():
    """Aucune ligne : aucun chargement lance, inutile de deranger BigQuery."""
    client = FakeBigQuery()

    assert load_rows([], TABLE, SCHEMA, client) == 0
    assert client.appels == []
