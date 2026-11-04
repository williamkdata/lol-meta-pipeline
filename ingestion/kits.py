"""Base de connaissances des kits : les formules des sorts de chaque champion,
par patch, extraites des fichiers du jeu publies par CommunityDragon.

Data Dragon (source officielle) ne donne pas les ratios des sorts : champs
vides, descriptions a trous (verifie le 04/11/2026). CommunityDragon les donne,
un dossier par patch. Source communautaire, non officielle."""

import json
import logging

import requests
from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from bigquery_loader import load_rows
from ddragon import CDN_URL, LANGUE, fetch_versions, patch_of, season_versions

journal = logging.getLogger(__name__)

CDRAGON_URL = "https://raw.communitydragon.org"
TIMEOUT_S = 30
KIT_DATASET = "lol-meta-pipeline.lol_raw"
KIT_TABLES = {
    "formulas": f"{KIT_DATASET}.kit_formulas",
    "parts": f"{KIT_DATASET}.kit_formula_parts",
    "values": f"{KIT_DATASET}.kit_data_values",
}
# Charges dans cet ordre : kit_formulas EN DERNIER sert de marqueur, un patch
# qui y figure est complet.
ORDRE_CHARGEMENT = ("values", "parts", "formulas")


def _champ(nom, type_, mode="NULLABLE"):
    return bigquery.SchemaField(nom, type_, mode=mode)


_COMMUN = [
    _champ("patch", "STRING", "REQUIRED"),
    _champ("champion_id", "INTEGER", "REQUIRED"),
    _champ("champion_code", "STRING", "REQUIRED"),
    _champ("slot", "STRING", "REQUIRED"),
    _champ("spell_name", "STRING"),
]
KIT_SCHEMAS = {
    "formulas": [
        *_COMMUN,
        _champ("calc_name", "STRING", "REQUIRED"),
        # L'arbre entier, en JSON canonique : pour recalculer, et pour comparer
        # deux patches par simple egalite.
        _champ("formula", "STRING", "REQUIRED"),
    ],
    "parts": [
        *_COMMUN,
        _champ("calc_name", "STRING", "REQUIRED"),
        _champ("part_path", "STRING", "REQUIRED"),
        _champ("part_type", "STRING", "REQUIRED"),
        _champ("stat", "INTEGER"),
        _champ("stat_formula", "INTEGER"),
        _champ("coefficient", "FLOAT"),
        _champ("data_value", "STRING"),
        _champ("number", "FLOAT"),
        _champ("start_value", "FLOAT"),
        _champ("end_value", "FLOAT"),
        _champ("modified_calc", "STRING"),
    ],
    "values": [
        *_COMMUN,
        _champ("value_name", "STRING", "REQUIRED"),
        _champ("spell_rank", "INTEGER", "REQUIRED"),
        _champ("value", "FLOAT"),
    ],
}

TOUCHES = ("Q", "W", "E", "R")
SUFFIXE_FICHE = "/CharacterRecords/Root"


def spell_slots(fichier: dict) -> dict[str, str]:
    """Le sort derriere chaque touche : {"Q": chemin, ..., "P": chemin du passif}.
    Une touche dont le sort manque dans le fichier est absente du resultat.

    La POSITION dans spellNames est la touche (verifie sur les 173 champions du
    16.21 contre Data Dragon et le client du jeu). Les noms internes, eux, ne
    le sont pas : chez Naafiri, "NaafiriR" est sur W."""
    racine = next(cle for cle in fichier if cle.endswith(SUFFIXE_FICHE))
    fiche = fichier[racine]
    # "Characters/Ambessa/CharacterRecords/Root" -> "characters/ambessa/spells/"
    prefixe = (racine.removesuffix(SUFFIXE_FICHE) + "/Spells/").lower()
    # Les majuscules varient DANS un meme fichier (fiche "FiddleSticks", sorts
    # "Fiddlesticks") : on cherche les chemins en minuscules.
    par_minuscules = {cle.lower(): cle for cle in fichier}

    touches = {}
    for touche, nom in zip(TOUCHES, fiche.get("spellNames", []), strict=False):
        chemin = par_minuscules.get(prefixe + nom.lower())
        if chemin:
            touches[touche] = chemin

    passif = _passive_spell(fichier, fiche, prefixe, par_minuscules, touches)
    if passif:
        touches["P"] = passif
    return touches


def _passive_spell(fichier, fiche, prefixe, par_minuscules, touches):
    """Le chemin du sort du passif, ou None.

    1. Par son nom court (passiveSpell : "AmbessaPassive"), quand la fiche le donne.
    2. Par elimination : la capacite de mAbilities qui reste quand on a retire
       les sorts Q, W, E, R. mAbilities n'est PAS range par touche (85 champions
       sur 173 dans le desordre au 16.21) : seule l'elimination est sure.
    3. Si plusieurs capacites restent (champions qui se transforment), par le
       nom "...PassiveAbility" ; sinon None plutot qu'un mauvais passif."""
    nom = fiche.get("passiveSpell")
    if nom:
        fin = "/" + nom.lower()
        for minuscule, cle in par_minuscules.items():
            if minuscule.startswith(prefixe) and minuscule.endswith(fin):
                return cle

    deja_pris = {chemin.lower() for chemin in touches.values()}
    restants = []
    for capacite in fiche.get("mAbilities", []):
        objet = fichier.get(par_minuscules.get(capacite.lower(), ""), {})
        sort_principal = (objet.get("mRootSpell") or "").lower()
        if sort_principal in par_minuscules and sort_principal not in deja_pris:
            restants.append(par_minuscules[sort_principal])
    if len(restants) == 1:
        return restants[0]

    for cle, valeur in fichier.items():
        if cle.lower().endswith("passiveability") and isinstance(valeur, dict):
            sort_principal = valeur.get("mRootSpell")
            if sort_principal and sort_principal.lower() in par_minuscules:
                return par_minuscules[sort_principal.lower()]
    return None


# Les champs utiles d'un morceau de formule, et leur colonne.
CHAMPS_MORCEAU = {
    "mCoefficient": "coefficient",
    "mDataValue": "data_value",
    "mNumber": "number",
    "mStartValue": "start_value",
    "mEndValue": "end_value",
    "mModifiedGameCalculation": "modified_calc",
}


def flatten_formula(calcul: dict) -> list[dict]:
    """Une formule de sort (un arbre de morceaux) -> une ligne par morceau,
    avec son chemin dans l'arbre ("mFormulaParts.0.mSubparts.1")."""
    lignes = []
    _parcourir(calcul, "", lignes)
    return lignes


def _parcourir(noeud, chemin: str, lignes: list) -> None:
    """Note le morceau s'il en est un, puis descend dans TOUT ce qu'il contient :
    un type jamais vu n'est pas perdu (parcours generique, pas 19 cas prevus)."""
    if isinstance(noeud, list):
        for i, enfant in enumerate(noeud):
            _parcourir(enfant, _joindre(chemin, str(i)), lignes)
        return
    if not isinstance(noeud, dict):
        return

    type_ = noeud.get("__type")
    if type_:
        ligne = {"part_path": chemin, "part_type": type_}
        for champ, colonne in CHAMPS_MORCEAU.items():
            ligne[colonne] = noeud.get(champ)
        if type_.startswith("StatBy"):
            # Morceau "par stat" : le fichier omet les valeurs par defaut.
            # Code absent = 0 = puissance (AP), formule 0 = totale (Ahri Q).
            ligne["stat"] = noeud.get("mStat", 0)
            ligne["stat_formula"] = noeud.get("mStatFormula", 0)
        else:
            ligne["stat"] = noeud.get("mStat")
            ligne["stat_formula"] = noeud.get("mStatFormula")
        lignes.append(ligne)

    for cle, valeur in noeud.items():
        if isinstance(valeur, dict | list):
            _parcourir(valeur, _joindre(chemin, cle), lignes)


def _joindre(chemin: str, etape: str) -> str:
    return f"{chemin}.{etape}" if chemin else etape


def flatten_data_values(sort: dict) -> list[dict]:
    """Les valeurs par rang d'un sort (mSpell) -> une ligne par (valeur, rang).

    Chaque liste a 7 cases : la case 0 est le rang 0 (sort pas encore appris),
    les cases 1 a 6 les rangs 1 a 6. Une valeur SANS liste est ignoree : on
    n'invente pas de zeros (102 cas au 16.21, "Test", "URFManaCost"...)."""
    lignes = []
    for valeur in sort.get("DataValues") or []:
        # Jusqu'au 16.5 : mName / mValues ; depuis le 16.6 : name / values.
        nom = valeur.get("name", valeur.get("mName"))
        nombres = valeur.get("values", valeur.get("mValues"))
        if nombres is None:
            continue
        for rang, nombre in enumerate(nombres):
            if rang == 0:
                continue
            lignes.append({"value_name": nom, "spell_rank": rang, "value": nombre})
    return lignes


def kit_rows(patch: str, champion_id: int, champion_code: str, fichier: dict) -> dict:
    """Tout le kit d'un champion pour un patch, en trois listes de lignes :
    formulas (une par formule, arbre entier en texte canonique), parts (une par
    morceau de formule), values (une par valeur et par rang). Seuls les sorts
    des touches Q, W, E, R et du passif comptent."""
    commun = {
        "patch": patch,
        "champion_id": champion_id,
        "champion_code": champion_code,
    }
    lignes = {"formulas": [], "parts": [], "values": []}

    for touche, chemin in spell_slots(fichier).items():
        sort = fichier[chemin].get("mSpell") or {}
        base = {**commun, "slot": touche, "spell_name": chemin.split("/")[-1]}

        for nom, calcul in (sort.get("mSpellCalculations") or {}).items():
            # sort_keys : meme formule = meme texte, quel que soit l'ordre des
            # cles. Comparer deux patches devient une simple egalite.
            texte = json.dumps(calcul, sort_keys=True)
            lignes["formulas"].append({**base, "calc_name": nom, "formula": texte})
            for morceau in flatten_formula(calcul):
                lignes["parts"].append({**base, "calc_name": nom, **morceau})

        for valeur in flatten_data_values(sort):
            lignes["values"].append({**base, **valeur})
    return lignes


def champion_file_url(patch: str, code: str) -> str:
    """Le fichier d'un champion pour un patch, sur CommunityDragon. Les dossiers
    sont en minuscules ; un dossier par patch (16.1 ... 16.21)."""
    dossier = code.lower()
    return f"{CDRAGON_URL}/{patch}/game/data/characters/{dossier}/{dossier}.bin.json"


def champions_of(version: str, session) -> list[tuple[int, str]]:
    """Les champions d'une version, d'apres Data Dragon : (numero, code)."""
    url = f"{CDN_URL}/{version}/data/{LANGUE}/champion.json"
    reponse = session.get(url, timeout=TIMEOUT_S)
    reponse.raise_for_status()
    return [(int(c["key"]), c["id"]) for c in reponse.json()["data"].values()]


def load_patch_kits(
    patch: str, champions, session, client, tables=ORDRE_CHARGEMENT
) -> dict:
    """Telecharge le kit de chaque champion pour un patch, l'aplatit et le charge.
    Un champion absent (404) est saute et compte. Retourne le bilan.

    tables : les tables a charger, dans l'ordre. Par defaut les trois, kit_formulas
    en dernier ; une partie seulement pour completer un patch sans rien effacer."""
    lignes = {table: [] for table in KIT_TABLES}
    absents = []
    for champion_id, code in champions:
        reponse = session.get(champion_file_url(patch, code), timeout=TIMEOUT_S)
        if reponse.status_code == 404:
            absents.append(code)
            continue
        reponse.raise_for_status()
        kit = kit_rows(patch, champion_id, code, reponse.json())
        for table, nouvelles in kit.items():
            lignes[table].extend(nouvelles)

    for table in tables:
        load_rows(lignes[table], KIT_TABLES[table], KIT_SCHEMAS[table], client)

    bilan = {
        "patch": patch,
        "champions": len(champions) - len(absents),
        "absents": absents,
        **{table: len(nouvelles) for table, nouvelles in lignes.items()},
    }
    journal.info("kits %s : %s", patch, bilan)
    return bilan


def loaded_kit_patches(client) -> set[str]:
    """Les patches deja complets en base. Vide si la table n'existe pas encore."""
    sql = f"SELECT DISTINCT patch FROM `{KIT_TABLES['formulas']}`"
    try:
        lignes = client.query(sql).result()
    except NotFound:
        return set()
    return {ligne["patch"] for ligne in lignes}


def season_patches(versions: list[str]) -> dict[str, str]:
    """Les patches de la saison, chacun avec sa version la plus recente.
    Data Dragon liste les versions de la plus recente a la plus ancienne."""
    patches = {}
    for version in season_versions(versions):
        patches.setdefault(patch_of(version), version)
    return patches


def load_kits_season(versions: list[str], session, client) -> list[dict]:
    """Charge les kits des patches de la saison PAS ENCORE en base."""
    deja = loaded_kit_patches(client)
    bilans = []
    for patch, version in season_patches(versions).items():
        if patch in deja:
            continue
        champions = champions_of(version, session)
        bilans.append(load_patch_kits(patch, champions, session, client))
    return bilans


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s : %(message)s"
    )
    client = bigquery.Client(project="lol-meta-pipeline")
    bilans = load_kits_season(fetch_versions(), requests.Session(), client)
    journal.info("%d patches charges", len(bilans))
