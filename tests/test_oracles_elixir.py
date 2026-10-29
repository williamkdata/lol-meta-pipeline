from pathlib import Path

import pytest

from oe_columns import OE_COLUMNS
from oracles_elixir import check_header

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
