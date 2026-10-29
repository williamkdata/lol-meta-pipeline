"""Depot de fichiers bruts dans le bucket de landing, commun aux sources."""

import gzip

LANDING_BUCKET = "lol-meta-pipeline-landing"


def upload_to_gcs(contenu: bytes, chemin: str, client) -> str:
    """Compresse le contenu et le depose dans le bucket. Retourne son adresse gs://."""
    compresse = gzip.compress(contenu)

    blob = client.bucket(LANDING_BUCKET).blob(chemin)
    blob.upload_from_string(compresse, content_type="application/gzip")

    if blob.size != len(compresse):
        raise RuntimeError(
            f"{len(compresse)} octets envoyes, {blob.size} recus par le bucket"
        )
    return f"gs://{LANDING_BUCKET}/{chemin}"
