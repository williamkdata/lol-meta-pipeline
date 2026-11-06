"""Pre-classement des objets termines en familles, pour relecture par William.

Regles deterministes sur les etiquettes officielles (Data Dragon) et les stats
(fichiers du jeu). Chaque objet recoit une famille proposee, la regle qui l'a
choisie, et des doutes quand les indices se contredisent. Le brouillon ne
devient la seed dbt/seeds/item_families.csv qu'apres la relecture de William.

Lancement : uv run python prototypes/prefamilles.py
"""

import csv
import json
import urllib.request
from pathlib import Path

from google.cloud import bigquery

PATCH = 1622
VERSION = "16.22.1"
ICI = Path(__file__).parent
SORTIE_CSV = ICI / "item_families_brouillon.csv"
SORTIE_MD = ICI.parent.parent / "suivi" / "projets" / "relecture_familles_objets.md"

NOMS_FAMILLES = {
    "critique": "critique",
    "letalite": "létalité",
    "on_hit": "vitesse d'attaque / on-hit",
    "ap": "AP",
    "combattant": "combattant",
    "tank": "tank",
    "enchanteur": "enchanteur / support",
}

REQUETE = f"""
WITH stats AS (
  SELECT
    item_id,
    SUM(IF(stat = 'FlatPhysicalDamageMod', value, 0)) AS ad,
    SUM(IF(stat = 'FlatMagicDamageMod', value, 0)) AS ap,
    SUM(IF(stat = 'PercentAttackSpeedMod', value, 0)) AS vitesse_attaque,
    SUM(IF(stat = 'FlatCritChanceMod', value, 0)) AS critique,
    SUM(IF(stat = 'FlatHPPoolMod', value, 0)) AS pv,
    SUM(IF(stat = 'FlatArmorMod', value, 0)) AS armure,
    SUM(IF(stat = 'FlatSpellBlockMod', value, 0)) AS rm,
    SUM(IF(stat = 'AbilityHasteMod', value, 0)) AS acceleration
  FROM lol_analytics.stg_item_stats
  WHERE patch_key = {PATCH}
  GROUP BY item_id
),
usage AS (
  SELECT item_id, COUNT(*) AS fois
  FROM lol_analytics.stg_ladder__participants, UNNEST(item_ids) AS item_id
  WHERE patch_key >= 1621
  GROUP BY item_id
)
SELECT
  i.item_id, i.item_name, i.tags,
  IFNULL(s.ad, 0) AS ad, IFNULL(s.ap, 0) AS ap,
  IFNULL(s.vitesse_attaque, 0) AS vitesse_attaque,
  IFNULL(s.critique, 0) AS critique, IFNULL(s.pv, 0) AS pv,
  IFNULL(s.armure, 0) AS armure, IFNULL(s.rm, 0) AS rm,
  IFNULL(s.acceleration, 0) AS acceleration,
  IFNULL(u.fois, 0) AS fois_ladder
FROM lol_analytics.stg_ddragon__items AS i
LEFT JOIN stats AS s USING (item_id)
LEFT JOIN usage AS u USING (item_id)
WHERE i.patch_key = {PATCH}
  AND i.is_completed
  -- Variantes d'autres modes (05/11) : ecartees aussi en staging depuis.
  AND i.item_id < 100000
"""


def classer(o):
    """Renvoie (famille, regle, doutes) pour un objet."""
    t = set(o["tags"])
    degats_ad = o["ad"] > 0 or "Damage" in t
    degats_ap = o["ap"] > 0 or "SpellDamage" in t
    resistant = o["pv"] > 0 or o["armure"] > 0 or o["rm"] > 0
    solide = o["pv"] >= 300 or o["armure"] >= 50 or o["rm"] >= 50

    if o["critique"] > 0 or "CriticalStrike" in t:
        return "critique", "chance de coup critique", []
    if degats_ap:
        doutes = []
        if o["vitesse_attaque"] > 0:
            doutes.append("AP et vitesse d'attaque : AP ou on-hit ?")
        if o["ad"] > 0:
            doutes.append("AP et AD : AP ou hybride ?")
        if "ManaRegen" in t and o["ap"] <= 60 and o["pv"] < 300:
            if o["ap"] >= 50:
                doutes.append("assez d'AP pour un mage : AP ou enchanteur ?")
            return "enchanteur", "AP modeste + regeneration de mana", doutes
        return "ap", "puissance (AP)", doutes
    if o["vitesse_attaque"] > 0:
        if o["pv"] >= 300:
            return "combattant", "vitesse d'attaque + au moins 300 PV", []
        return "on_hit", "vitesse d'attaque sans critique ni AP", []
    if degats_ad and "ArmorPenetration" in t:
        if o["pv"] >= 300:
            return "combattant", "penetration d'armure + au moins 300 PV", []
        return "letalite", "degats physiques + penetration d'armure", []
    if degats_ad and resistant:
        return "combattant", "degats physiques + PV ou resistances", []
    if degats_ad:
        doute = (
            "ni PV, ni penetration, ni critique : combattant, letalite ou critique ?"
        )
        return "combattant", "degats physiques seuls", [doute]
    if resistant:
        if t & {"Aura", "Active", "ManaRegen"} and o["pv"] <= 250:
            doute = "objet de support : tank ou enchanteur ?"
            return "tank", "resistances, sans degats", [doute]
        if solide:
            return "tank", "PV ou resistances, sans degats", []
        return (
            "tank",
            "resistances legeres, sans degats",
            ["peu de resistances : tank ?"],
        )
    return "enchanteur", "ni degats ni resistances", ["a classer"]


def stats_lisibles(o):
    """Les stats non nulles, en clair : 'AD 60, VA 25%, PV 300'."""
    morceaux = []
    for cle, libelle, pourcent in [
        ("ad", "AD", False),
        ("ap", "AP", False),
        ("vitesse_attaque", "VA", True),
        ("critique", "crit", True),
        ("pv", "PV", False),
        ("armure", "armure", False),
        ("rm", "RM", False),
        ("acceleration", "accél.", False),
    ]:
        if o[cle]:
            valeur = round(o[cle] * 100) if pourcent else round(o[cle])
            morceaux.append(f"{libelle} {valeur}{'%' if pourcent else ''}")
    return ", ".join(morceaux) or "—"


def tableau(liste, avec_doute):
    """Un tableau Markdown, une ligne par objet."""
    colonnes = ["Objet (FR)", "Objet (EN)", "Famille proposée", "Stats"]
    colonnes += ["Étiquettes Riot", "Vu en ladder"]
    if avec_doute:
        colonnes.append("Le doute")
    lignes = ["| " + " | ".join(colonnes) + " |", "|" + "---|" * len(colonnes)]
    for li in liste:
        cellules = [
            li["nom_fr"],
            li["item_name"],
            f"**{NOMS_FAMILLES[li['famille']]}**",
            stats_lisibles(li),
            ", ".join(li["tags"]),
            str(li["fois_ladder"]),
        ]
        if avec_doute:
            cellules.append(" ; ".join(li["doutes"]))
        lignes.append("| " + " | ".join(cellules) + " |")
    return "\n".join(lignes)


def main():
    client = bigquery.Client(project="lol-meta-pipeline")
    objets = [dict(r) for r in client.query(REQUETE).result()]
    url = f"https://ddragon.leagueoflegends.com/cdn/{VERSION}/data/fr_FR/item.json"
    with urllib.request.urlopen(url, timeout=60) as reponse:
        donnees = json.loads(reponse.read())["data"]
    noms_fr = {int(k): v["name"] for k, v in donnees.items()}

    lignes = []
    for o in objets:
        famille, regle, doutes = classer(o)
        nom_fr = noms_fr.get(o["item_id"], "?")
        lignes.append(
            {
                **o,
                "nom_fr": nom_fr,
                "famille": famille,
                "regle": regle,
                "doutes": doutes,
            }
        )

    with SORTIE_CSV.open("w", newline="", encoding="utf-8") as f:
        ecrivain = csv.writer(f)
        ecrivain.writerow(["item_id", "item_name", "family"])
        for li in sorted(lignes, key=lambda x: x["item_id"]):
            ecrivain.writerow([li["item_id"], li["item_name"], li["famille"]])

    douteux = sorted(
        (li for li in lignes if li["doutes"]), key=lambda x: -x["fois_ladder"]
    )
    surs = sorted(
        (li for li in lignes if not li["doutes"]),
        key=lambda x: (x["famille"], -x["fois_ladder"]),
    )
    compte = {}
    for li in lignes:
        compte[li["famille"]] = compte.get(li["famille"], 0) + 1
    repartition = ", ".join(
        f"{NOMS_FAMILLES[k]} {v}"
        for k, v in sorted(compte.items(), key=lambda kv: -kv[1])
    )

    texte = "\n".join(
        [
            f"# Relecture : la famille de chaque objet terminé (patch {VERSION[:5]})",
            "",
            "*Préparé par Claude le 05/11/2026 (`prototypes/prefamilles.py`), "
            "à relire par William (décision du 05/11). Brouillon de seed : "
            "`lol-meta-pipeline/prototypes/item_families_brouillon.csv` ; il deviendra "
            "`dbt/seeds/item_families.csv` après relecture.*",
            "",
            "**Comment relire** : pour chaque objet, la famille proposée est-elle "
            "celle que tu choisirais en jeu ? Réponds simplement « objet → famille » "
            "pour ceux à changer. Les **cas douteux** sont en premier. Dans chaque "
            "tableau, les objets **les plus joués en ladder** (16.21-16.22, "
            "inventaires de fin de partie) sont en tête : ce sont ceux qui comptent "
            "le plus.",
            "",
            "**Les 7 familles** : critique, létalité, vitesse d'attaque / on-hit, AP, "
            "combattant (dégâts + PV), tank, enchanteur / support. Un build qui "
            "mélange AD et AP sera « hybride » (au niveau du build, pas de l'objet).",
            "",
            "**Comment les propositions sont faites** (règles, dans cet ordre) :",
            "- chance de critique → critique ;",
            "- puissance (AP) → AP, ou enchanteur si 60 AP au plus, de la "
            "régénération de mana et moins de 300 PV ;",
            "- vitesse d'attaque → on-hit, ou combattant avec au moins 300 PV ;",
            "- dégâts physiques + étiquette « pénétration d'armure » → létalité, ou "
            "combattant avec au moins 300 PV ;",
            "- dégâts physiques + PV ou résistances → combattant ;",
            "- PV ou résistances sans dégâts → tank.",
            "",
            "**La létalité n'est pas dans les stats des fichiers du jeu** : elle "
            "n'est repérée que par l'étiquette de Riot. **Les variantes d'autres "
            "modes** (identifiants à 6 chiffres) sont écartées : jamais achetées en "
            "ladder.",
            "",
            f"**Bilan** : {len(lignes)} objets ; {len(douteux)} cas douteux. "
            f"Par famille proposée : {repartition}.",
            "",
            f"## 1. Les cas douteux ({len(douteux)})",
            "",
            tableau(douteux, True),
            "",
            f"## 2. Les autres objets ({len(surs)})",
            "",
            tableau(surs, False),
            "",
        ]
    )
    SORTIE_MD.write_text(texte, encoding="utf-8")
    print(len(lignes), "objets ;", len(douteux), "douteux ;", compte)
    print(
        "sans nom francais :", [li["item_id"] for li in lignes if li["nom_fr"] == "?"]
    )
    print(
        "jamais vus en ladder :",
        [li["item_name"] for li in lignes if not li["fois_ladder"]],
    )


if __name__ == "__main__":
    main()
