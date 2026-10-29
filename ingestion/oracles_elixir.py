"""Client Oracle's Elixir : les matchs pro de la saison, un fichier par an."""

from oe_columns import OE_COLUMNS


def check_header(contenu: str) -> None:
    """Verifie que le contenu telecharge est bien le CSV d'Oracle's Elixir."""
    premiere_ligne = contenu.split("\n", 1)[0].rstrip("\r")

    if premiere_ligne.startswith("<"):
        raise ValueError("page web recue au lieu du CSV : quota Google Drive ?")

    colonnes = premiere_ligne.split(",")
    if colonnes != OE_COLUMNS:
        ajoutees = sorted(set(colonnes) - set(OE_COLUMNS))
        disparues = sorted(set(OE_COLUMNS) - set(colonnes))
        raise ValueError(
            f"en-tete inattendu : ajoutees {ajoutees}, disparues {disparues}"
        )
