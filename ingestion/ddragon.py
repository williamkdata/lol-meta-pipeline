"""Client Data Dragon : le referentiel des champions, objets et runes, par patch."""


def patch_of(version: str) -> str:
    """Le patch d'une version : ses deux premiers nombres. 16.21.1 -> 16.21."""
    parties = version.split(".")
    if len(parties) < 2:
        raise ValueError(f"version illisible : {version}")

    for partie in parties:
        if not partie.isdigit():
            raise ValueError(f"version illisible : {version}")

    return f"{parties[0]}.{parties[1]}"


def flatten_champions(payload: dict) -> list[dict]:
    """Une ligne par champion, a partir du fichier champion.json d'une version."""
    version = payload["version"]
    patch = patch_of(version)

    lignes = []
    for champion in payload["data"].values():
        lignes.append(
            {
                "patch": patch,
                "version": version,
                "champion_id": int(champion["key"]),
                "champion_code": champion["id"],
                "champion_name": champion["name"],
                "title": champion["title"],
                "tags": champion["tags"],
            }
        )
    return lignes
