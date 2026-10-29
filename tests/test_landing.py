import gzip

import pytest

from fakes import FakeStorage
from landing import upload_to_gcs

BUCKET = "lol-meta-pipeline-landing"
CHEMIN = "oracles_elixir/2026/2026-10-29.csv.gz"

# Un CSV repetitif, comme le vrai : il se compresse bien.
CONTENU = b"gameid,league,patch\nLOLTMNT01_0001,LEC,16.01\n" * 1000


def depose(client=None):
    """Lance un depot et renvoie l'objet tel que le faux bucket l'a recu."""
    client = client or FakeStorage()
    upload_to_gcs(CONTENU, CHEMIN, client)
    return client.objets[(BUCKET, CHEMIN)]


def test_upload_to_gcs_returns_the_gs_address():
    adresse = upload_to_gcs(CONTENU, CHEMIN, FakeStorage())

    assert adresse == f"gs://{BUCKET}/{CHEMIN}"


def test_upload_to_gcs_writes_into_the_landing_bucket_at_the_given_path():
    client = FakeStorage()

    upload_to_gcs(CONTENU, CHEMIN, client)

    assert list(client.objets) == [(BUCKET, CHEMIN)]


def test_upload_to_gcs_compresses_without_losing_anything():
    """Un fichier gzip commence toujours par les octets 1f 8b. Et il doit se
    decompresser EXACTEMENT a l'identique : une compression qui perd des
    donnees serait pire que pas de compression du tout."""
    objet = depose()

    assert objet.data[:2] == b"\x1f\x8b"
    assert gzip.decompress(objet.data) == CONTENU
    assert len(objet.data) < len(CONTENU)


def test_upload_to_gcs_declares_a_gzip_file():
    assert depose().content_type == "application/gzip"


def test_upload_to_gcs_refuses_a_size_mismatch():
    """Le bucket annonce combien d'octets il a recus. Si ce n'est pas ce qui a
    ete envoye, l'objet depose est incomplet : on s'arrete."""
    with pytest.raises(RuntimeError):
        depose(FakeStorage(taille_annoncee=1))
