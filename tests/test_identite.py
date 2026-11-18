import google.auth
from google.oauth2 import service_account

from identite import google_credentials

SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


def faux_fichier_cle(appels):
    """Remplace la lecture du fichier cle : note l'appel, rend un faux badge."""

    def lire(chemin, scopes=None):
        appels.append(("fichier", chemin, scopes))
        return "identite du fichier"

    return lire


def faux_defaut(appels):
    """Remplace les identifiants par defaut de Google (le badge du cloud)."""

    def defaut(scopes=None):
        appels.append(("defaut", scopes))
        return "identite par defaut", "lol-meta-pipeline"

    return defaut


def test_avec_le_fichier_cle_on_l_utilise(tmp_path, monkeypatch):
    # Sur le PC (Airflow) : le fichier cle est monte, on s'en sert.
    cle = tmp_path / "lol-pipeline-key.json"
    cle.write_text("{}")
    appels = []
    monkeypatch.setattr(
        service_account.Credentials,
        "from_service_account_file",
        faux_fichier_cle(appels),
    )
    monkeypatch.setattr(google.auth, "default", faux_defaut(appels))

    assert google_credentials(SCOPES, chemin_cle=str(cle)) == "identite du fichier"
    assert appels == [("fichier", str(cle), SCOPES)]


def test_sans_fichier_cle_on_prend_l_identite_par_defaut(tmp_path, monkeypatch):
    # Dans le cloud (Cloud Run) : aucun fichier ; Google fournit l'identite.
    appels = []
    monkeypatch.setattr(
        service_account.Credentials,
        "from_service_account_file",
        faux_fichier_cle(appels),
    )
    monkeypatch.setattr(google.auth, "default", faux_defaut(appels))

    absent = str(tmp_path / "pas-de-cle.json")
    assert google_credentials(SCOPES, chemin_cle=absent) == "identite par defaut"
    assert appels == [("defaut", SCOPES)]


def test_les_droits_demandes_sont_transmis(tmp_path, monkeypatch):
    # Oracle's Elixir demande aussi Google Drive : le droit doit arriver
    # jusqu'a l'identite, dans les deux cas.
    droits = [
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/cloud-platform",
    ]
    appels = []
    monkeypatch.setattr(google.auth, "default", faux_defaut(appels))

    google_credentials(droits, chemin_cle=str(tmp_path / "absent.json"))

    assert appels == [("defaut", droits)]
