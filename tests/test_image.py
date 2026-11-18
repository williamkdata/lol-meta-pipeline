"""L'image Docker du job quotidien : rien de secret dedans, et le bon point d'entree.

Ces tests lisent les fichiers (Dockerfile, .dockerignore) : ils ne fabriquent
pas l'image. La fabrication, elle, verifie dbt et les imports.
"""

from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
DOCKERFILE = RACINE / "job" / "Dockerfile"
DOCKERIGNORE = RACINE / ".dockerignore"


def lignes_utiles(chemin):
    """Les lignes d'un fichier, sans les commentaires ni les lignes vides."""
    return [
        ligne.strip()
        for ligne in chemin.read_text(encoding="utf-8").splitlines()
        if ligne.strip() and not ligne.strip().startswith("#")
    ]


def test_les_secrets_sont_ecartes_de_l_image():
    # .env (la cle Riot) et secrets/ (la cle du compte de service) ne doivent
    # JAMAIS entrer dans l'image : elle part sur une etagere chez Google.
    ecartes = lignes_utiles(DOCKERIGNORE)
    assert ".env" in ecartes
    assert "secrets/" in ecartes


def test_le_dockerfile_ne_copie_que_le_necessaire():
    # Pas de "COPY . ." : il copierait tout, y compris ce qu'on oublierait
    # d'ecarter. On nomme ce qu'on copie.
    copies = [ligne for ligne in lignes_utiles(DOCKERFILE) if ligne.startswith("COPY ")]
    assert copies, "aucune ligne COPY"
    for ligne in copies:
        sources = ligne.split()[1:-1]
        assert "." not in sources, ligne
        assert not any(".env" in s or "secrets" in s for s in sources), ligne


def test_le_point_d_entree_est_le_chef_d_orchestre():
    entree = [
        ligne for ligne in lignes_utiles(DOCKERFILE) if ligne.startswith("ENTRYPOINT")
    ]
    assert entree == ['ENTRYPOINT ["python", "ingestion/quotidien.py"]']
    assert (RACINE / "ingestion" / "quotidien.py").is_file()


def test_l_image_ne_tourne_pas_en_administrateur():
    assert any(ligne.startswith("USER ") for ligne in lignes_utiles(DOCKERFILE))
