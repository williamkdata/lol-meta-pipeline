# L'image du job quotidien (Cloud Run, 18/11/2026) : Python, nos scripts
# d'ingestion et dbt. Pas d'Airflow : le chef d'orchestre est
# ingestion/quotidien.py.
#
# A fabriquer depuis la racine du depot (le .dockerignore y est), puis
# deposer sur l'etagere (N = la version, celle de job_image_tag dans Terraform) :
#   docker build --provenance=false -f job/Dockerfile \
#     -t us-central1-docker.pkg.dev/lol-meta-pipeline/lol-job/lol-job:N .
#   docker push us-central1-docker.pkg.dev/lol-meta-pipeline/lol-job/lol-job:N
# --provenance=false : sans lui, Docker Desktop ajoute une "attestation" et
# l'etagere compte 3 versions par image ; la regle "garder les 3 dernieres"
# n'en garderait qu'une (constate le 18/11/2026).
#
# Fabrication en deux temps ("multi-stage") : un atelier installe les
# dependances avec uv ; l'image finale ne garde que le resultat (.venv), pas
# l'outil. Premiere version a un seul temps, avec les fichiers Python
# pre-compiles : 1,49 Go ; le stockage gratuit de l'etagere d'images est de
# 0,5 Gio.

# --- 1. L'atelier -------------------------------------------------------------
FROM python:3.12-slim AS atelier

# uv, a la meme version que sur le PC : il installe les versions exactes du
# fichier uv.lock (les memes que le PC et la CI).
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-cache

# --- 2. L'image finale ----------------------------------------------------------
FROM python:3.12-slim

# PYTHONUNBUFFERED : les journaux partent tout de suite, sans attendre qu'un
# tampon se remplisse. Dans Cloud Run, on les lit pendant le run.
ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app

# Seulement l'environnement Python fabrique dans l'atelier.
COPY --from=atelier /app/.venv /app/.venv

# Le code : seulement ce dont le job a besoin (.dockerignore ecarte le reste).
COPY ingestion/ ingestion/
COPY dbt/ dbt/

# Les paquets dbt (dbt_utils), une fois pour toutes, puis deux verifications
# pendant la fabrication : dbt lit tout le projet (sans se connecter a
# BigQuery), et chaque script s'importe. Si l'une echoue, pas d'image.
RUN dbt deps --project-dir dbt \
    && dbt parse --project-dir dbt --profiles-dir dbt/profiles --target prod --no-partial-parse \
    && python -c "import sys; sys.path.insert(0, 'ingestion'); import quotidien, ddragon, kits, item_stats, ladder, oracles_elixir"

# Un utilisateur sans droits d'administration. dbt ecrit dans dbt/ (target,
# logs) : il en devient proprietaire.
RUN useradd --create-home job && chown -R job /app/dbt
USER job

ENTRYPOINT ["python", "ingestion/quotidien.py"]
