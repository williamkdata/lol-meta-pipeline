"""Ce qui ne doit JAMAIS etre versionne, verifie par git lui-meme.

Deux exigences du projet passent par le .gitignore : aucun secret dans le depot,
et aucune rediffusion des donnees brutes de Riot (CGU). Or un .gitignore se
modifie sans bruit : une ligne supprimee par erreur, et la cle du compte de
service part au prochain `git add -A`.

`git check-ignore` repond pour un chemin donne, meme s'il n'existe pas encore :
code 0 s'il est ignore, code 1 s'il ne l'est pas.
"""

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

NE_DOIT_PAS_ETRE_VERSIONNE = [
    ".env",  # cle API Riot en local
    "secrets/lol-pipeline-key.json",  # cle du compte de service GCP
    "infra/terraform/terraform.tfvars",  # valeurs propres au compte
    "infra/terraform/terraform.tfstate",  # identifiants en clair possibles
    "infra/terraform/terraform.tfstate.backup",
    "infra/terraform/step1.tfplan",  # un plan peut contenir des valeurs sensibles
    "data/riot/match_EUW1_1234567890.json",  # brut Riot : rediffusion interdite
    "data/oracles_elixir/2026.csv",  # brut pro : idem
]


def is_ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", path],
        cwd=REPO_ROOT,
        check=False,
    )
    return result.returncode == 0


@pytest.mark.parametrize("path", NE_DOIT_PAS_ETRE_VERSIONNE)
def test_path_is_ignored_by_git(path):
    assert is_ignored(path), f"{path} n'est pas ignore par git"


def test_terraform_example_stays_versioned():
    """L'exemple doit rester visible : sans lui, personne ne sait quoi renseigner.

    Il est exclu de la regle *.tfvars par une exception (!*.tfvars.example).
    Ce test casse si l'exception disparait.
    """
    assert not is_ignored("infra/terraform/terraform.tfvars.example")
