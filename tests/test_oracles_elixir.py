import hashlib
from pathlib import Path

import pytest
import requests

from fakes import FakeHttp, FakeResponse
from oe_columns import OE_COLUMNS
from oracles_elixir import check_header, download_file, find_season_file

FIXTURES = Path(__file__).resolve().parent / "fixtures"

ENTETE = ",".join(OE_COLUMNS)

# Une vraie ligne de donnees n'est pas necessaire : check_header ne lit que la
# premiere ligne. Celle-ci sert juste a montrer qu'il y a une suite.
SUITE = "\nLOLTMNT01_0001,complete,,LEC,2026,Winter,0,2026-01-17,1,16.01"


# --- check_header -----------------------------------------------------------


def test_check_header_accepts_the_real_header():
    check_header(ENTETE + SUITE)


def test_check_header_accepts_windows_line_endings():
    """Le vrai fichier termine ses lignes par \\r\\n. Sans retirer le \\r, la
    derniere colonne deviendrait 'opp_deathsat25\\r' et le vrai fichier serait
    refuse, avec un nom de colonne qui a l'air identique a l'ecran."""
    check_header(ENTETE + "\r" + SUITE.replace("\n", "\r\n"))


def test_check_header_refuses_the_real_drive_quota_page():
    """La page que Google Drive a VRAIMENT renvoyee le 29/10/2026, avec un
    statut 200. raise_for_status ne la voit pas : c'est ce test qui l'arrete."""
    page = (FIXTURES / "drive_quota_exceeded.html").read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="page web"):
        check_header(page)


def test_check_header_refuses_a_renamed_column():
    """Une colonne renommee en amont deviendrait une colonne vide chez nous."""
    renomme = ENTETE.replace(",patch,", ",game_patch,")

    with pytest.raises(ValueError):
        check_header(renomme + SUITE)


def test_check_header_refuses_an_added_column():
    with pytest.raises(ValueError):
        check_header(ENTETE + ",nouvelle_colonne" + SUITE)


def test_check_header_refuses_a_reordered_header():
    """Memes colonnes, autre ordre : BigQuery associe les colonnes d'un CSV par
    POSITION. Les valeurs de 'kills' iraient dans 'deaths', sans erreur."""
    colonnes = list(OE_COLUMNS)
    i, j = colonnes.index("kills"), colonnes.index("deaths")
    colonnes[i], colonnes[j] = colonnes[j], colonnes[i]

    with pytest.raises(ValueError):
        check_header(",".join(colonnes) + SUITE)


def test_check_header_refuses_empty_content():
    with pytest.raises(ValueError):
        check_header("")


# --- find_season_file -------------------------------------------------------

DOSSIER = "1gLSw0RLjBbtaNy0dgnGQDAZOHIgCe-HH"

# La vraie fiche renvoyee par l'API Drive le 29/10/2026. Attention : la taille
# arrive en TEXTE ("78814702"), pas en nombre.
FICHE_2026 = {
    "id": "1hnpbrUpBMS1TZI7IovfpKeZfWJH1Aptm",
    "name": "2026_LoL_esports_match_data_from_OraclesElixir.csv",
    "modifiedTime": "2026-10-29T13:05:04.895Z",
    "size": "78814702",
    "md5Checksum": "19f6c17f39cb13e65fdb318ee07c10e8",
}


def drive_qui_repond(fichiers):
    """Un faux Drive dont la recherche renvoie la liste `fichiers`."""
    http = FakeHttp()
    http.reponse = FakeResponse({"files": fichiers})
    return http


def test_find_season_file_returns_the_file_record():
    assert find_season_file(2026, drive_qui_repond([FICHE_2026])) == FICHE_2026


def test_find_season_file_searches_the_file_by_name_in_the_oe_folder():
    """On demande a Drive de filtrer lui-meme : un seul fichier en retour,
    au lieu de rapatrier la liste des 13 et de trier chez nous."""
    http = drive_qui_repond([FICHE_2026])

    find_season_file(2026, http)

    [(url, options)] = http.appels
    assert url == "https://www.googleapis.com/drive/v3/files"
    q = options["params"]["q"]
    assert f"'{DOSSIER}' in parents" in q
    assert "name = '2026_LoL_esports_match_data_from_OraclesElixir.csv'" in q
    assert "trashed = false" in q
    assert options["timeout"] > 0


def test_find_season_file_asks_for_the_date_and_the_checksum():
    """Sans les demander explicitement, Drive ne renvoie ni la date de
    modification ni l'empreinte MD5 : les deux etapes suivantes en ont besoin."""
    http = drive_qui_repond([FICHE_2026])

    find_season_file(2026, http)

    [(_, options)] = http.appels
    for champ in ("id", "modifiedTime", "size", "md5Checksum"):
        assert champ in options["params"]["fields"]


def test_find_season_file_follows_the_year():
    """En janvier, le meme code cherchera le fichier 2027, sans modification."""
    http = drive_qui_repond([FICHE_2026])

    find_season_file(2027, http)

    [(_, options)] = http.appels
    assert (
        "name = '2027_LoL_esports_match_data_from_OraclesElixir.csv'"
        in (options["params"]["q"])
    )


def test_find_season_file_refuses_a_missing_file():
    """Le 1er janvier, le fichier de la nouvelle annee n'existe pas encore."""
    with pytest.raises(ValueError):
        find_season_file(2027, drive_qui_repond([]))


def test_find_season_file_refuses_two_files_with_the_same_name():
    """Deux fichiers du meme nom : on ne devine pas lequel est le bon."""
    double = [FICHE_2026, {**FICHE_2026, "id": "un-autre-identifiant"}]

    with pytest.raises(ValueError):
        find_season_file(2026, drive_qui_repond(double))


def test_find_season_file_raises_on_a_drive_error():
    """Avec l'API, un quota depasse est un vrai statut d'erreur (403) :
    raise_for_status l'attrape, contrairement a la page web de tout a l'heure."""
    http = FakeHttp()
    http.reponse = FakeResponse(None, status_code=403)

    with pytest.raises(requests.HTTPError):
        find_season_file(2026, http)


# --- download_file ----------------------------------------------------------

# Un petit CSV valide : le vrai en-tete et une ligne, en octets.
CSV = (ENTETE + SUITE).encode("utf-8")


def fiche_de(contenu):
    """La fiche que Drive donnerait pour ce contenu : vraie taille, vraie
    empreinte. La taille est en TEXTE, comme dans la vraie API."""
    return {
        "id": FICHE_2026["id"],
        "name": FICHE_2026["name"],
        "size": str(len(contenu)),
        "md5Checksum": hashlib.md5(contenu).hexdigest(),
    }


def drive_qui_envoie(contenu):
    http = FakeHttp()
    http.reponse = FakeResponse(content=contenu)
    return http


def test_download_file_returns_the_bytes():
    assert download_file(fiche_de(CSV), drive_qui_envoie(CSV)) == CSV


def test_download_file_requests_the_content_of_the_right_file():
    """alt=media : sans lui, Drive renvoie la fiche du fichier, pas son contenu."""
    http = drive_qui_envoie(CSV)

    download_file(fiche_de(CSV), http)

    [(url, options)] = http.appels
    assert url == f"https://www.googleapis.com/drive/v3/files/{FICHE_2026['id']}"
    assert options["params"]["alt"] == "media"
    assert options["timeout"] > 0


def test_download_file_refuses_a_truncated_download():
    """Le telechargement s'est arrete en route : il manque la fin du fichier."""
    tronque = CSV[:-10]

    with pytest.raises(ValueError, match="taille"):
        download_file(fiche_de(CSV), drive_qui_envoie(tronque))


def test_download_file_refuses_a_corrupted_download():
    """Meme taille, un seul octet different : seule l'empreinte le voit."""
    abime = CSV[:-1] + b"9"

    with pytest.raises(ValueError, match="empreinte"):
        download_file(fiche_de(CSV), drive_qui_envoie(abime))


def test_download_file_still_checks_the_header():
    """Un fichier intact peut quand meme avoir change d'en-tete en amont."""
    renomme = CSV.replace(b",patch,", b",game_patch,")

    with pytest.raises(ValueError, match="en-tete"):
        download_file(fiche_de(renomme), drive_qui_envoie(renomme))


def test_download_file_raises_on_a_drive_error():
    http = FakeHttp()
    http.reponse = FakeResponse(status_code=403)

    with pytest.raises(requests.HTTPError):
        download_file(fiche_de(CSV), http)
