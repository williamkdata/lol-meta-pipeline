"""Les infobulles des sorts, depuis le texte du jeu (CommunityDragon).

Le texte d'un sort entoure chaque nombre d'une balise qui dit ce qu'il est :
"<magicDamage>@TotalDamage@ magic damage</magicDamage>". La balise donne le
type de degats (physique, magique, brut) et dit si un nombre est un degat, un
bouclier, un soin... Verifie le 16/11/2026 : meme type que Data Dragon pour
1 028 formules sur 1 028, et 87 % des sorts infligent exactement ces types en
partie (recapitulatifs de mort).
"""

import re

# Une balise (<magicDamage>, </magicDamage>, <br />, <font color='...'>) OU un
# nombre (@TotalDamage@, @MovementSpeed*100@). Le nom du nombre s'arrete au
# premier caractere qui n'est ni lettre, ni chiffre, ni _ ; le reste jusqu'au
# @ suivant (un calcul comme *100) est ignore.
_JETON = re.compile(r"<(/?)(\w+)[^>]*?(/?)>|@(\w+)[^@<>]*@")

# Les mots qui suivent un nombre disent ce qu'il est ("% max Health magic
# damage") : 80 caracteres suffisent (mesure du 18/11/2026 sur les 69 formules
# de degats en pourcentage du 16.22).
LONGUEUR_SUITE = 80


def tooltip_number_tags(texte: str) -> list[dict]:
    """Chaque nombre de l'infobulle, avec la balise la plus proche qui l'entoure
    et les mots qui le suivent.

    Une ligne par couple (nom, balise) distinct, triee ; le nom en minuscules
    (comme nos formules) ; balise None si le nombre n'est dans aucune.
    following_text : les mots qui suivent sa PREMIERE apparition (voir _suite).

    La methode : une pile. On lit le texte de gauche a droite ; une balise
    ouvrante est empilee, une fermante depile jusqu'a la sienne (une balise
    jamais fermee, comme <li>, s'en va avec son parent) ; un nombre prend la
    balise du haut de la pile. <br> et les balises auto-fermantes (<br />) ne
    sont pas empilees.
    """
    pile = []
    couples = {}  # (nom, balise) -> mots qui suivent la premiere apparition
    for jeton in _JETON.finditer(texte):
        fermante, balise, auto_fermante, nombre = jeton.groups()
        if nombre is not None:
            cle = (nombre.lower(), pile[-1] if pile else None)
            if cle not in couples:
                couples[cle] = _suite(texte, jeton.end())
        elif auto_fermante or balise.lower() == "br":
            continue
        elif not fermante:
            pile.append(balise)
        elif balise in pile:
            while pile.pop() != balise:
                pass
    return [
        {"name": nom, "tag": balise, "following_text": couples[(nom, balise)]}
        for nom, balise in sorted(couples, key=lambda c: (c[0], c[1] or ""))
    ]


def _suite(texte: str, debut: int) -> str:
    """Les mots qui suivent un nombre : jusqu'au nombre suivant (le prochain @),
    sans les balises, espaces resserres, LONGUEUR_SUITE caracteres au plus.
    " ".join(x.split()) : decoupe aux espaces (et retours a la ligne) puis
    recolle avec un seul espace."""
    morceau = texte[debut:].split("@", 1)[0]
    morceau = re.sub(r"<[^>]*>", "", morceau)
    return " ".join(morceau.split())[:LONGUEUR_SUITE]


def spell_tooltip_key(slot: str, spell_name: str) -> str:
    """La cle de l'infobulle d'un sort dans le texte du jeu (lol.stringtable.json).

    Elle suit le NOM INTERNE du sort, pas la touche (le R de Vladimir s'appelle
    VladimirHemoplague). Au 16.22 : 685 sorts Q-R sur 688 trouves (Kayn Q, E, R
    manquent : il se transforme) ; les passifs ont leur propre forme de cle,
    169 sur 169.
    """
    nom = spell_name.lower()
    if slot == "P":
        return f"generatedtip_passive_{nom}_tooltip"
    return f"generatedtip_spell_{nom}_tooltipextended"
