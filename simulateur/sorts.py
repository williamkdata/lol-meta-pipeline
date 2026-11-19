"""Les sorts du simulateur : calculer la valeur d'une formule de sort.

Une formule (mSpellCalculations, dans les fichiers du jeu) est un arbre de
morceaux : une valeur par rang, un ratio x une stat, un nombre, une somme, un
produit... Les formules sont dans stg_kit__formulas (texte JSON), les valeurs
par rang dans stg_kit__values.
"""

# Les stats qu'un morceau "par stat" peut demander : (code de stat, code de
# formule) -> cle de stats_with_items. Codes decodes et verifies par deux
# sources le 04/11/2026 (seed stat_codes) : 0 = AP, 2 = attaque, 12 = PV,
# 1 = armure, 6 = RM ; formule 0 = totale, 2 = bonus. L'AP n'a pas de part de
# base : AP bonus = AP totale. Les autres codes (4, 7, 8, 9...) ne sont pas
# encore decodes : ils levent une erreur au lieu d'etre devines.
STATS_DES_CODES = {
    (0, 0): "ap",
    (0, 2): "ap",
    (2, 0): "ad",
    (2, 2): "ad_bonus",
    (12, 0): "hp",
    (12, 2): "hp_bonus",
    (1, 0): "armor",
    (1, 2): "armor_bonus",
    (6, 0): "mr",
    (6, 2): "mr_bonus",
    # Decodes le 18/11/2026 : le nom des formules (ecrit par Riot) et les mots
    # des infobulles, deux indices independants, puis la forme des calculs.
    # Vitesse d'attaque BONUS, en fraction (0.5 = +50 %) : passif de Varus,
    # 42 x ce code = 21 d'AD a +50 % (en %, 2 100 : absurde).
    (4, 2): "as_bonus",
    # Chances de critique (fraction) et degats critiques (multiplicateur total,
    # 2.0 en general) : le Q de Sivir et le E de Garen multiplient leurs degats
    # par 1 + X x (code 9 - 1), la forme exacte du critique en moyenne.
    (8, 0): "crit_chance",
    (9, 0): "crit_damage",
    # Letalite : seul Pyke l'utilise ; son R s'appelle "RLethalityDamage".
    (29, 0): "lethality",
    # PAS encore relies (une erreur plutot qu'un faux nombre) :
    #   (4, 0) vitesse d'attaque totale, probable, unite non verifiable ;
    #   (7, x) vitesse de deplacement (DashSpeed x 6, Janna, Hecarim) : le
    #          mannequin n'a pas cette stat ;
    #   (9, 2) degats critiques bonus : le mannequin ne garde que le total ;
    #   (10, 13, 14, 15, 16, 18, 31) : un ou deux exemples, sens incertain.
}


def evaluate_formula(
    nom: str,
    formules: dict,
    valeurs: dict,
    rang: int,
    stats: dict,
    niveau: int | None = None,
    cumuls: dict[str, float] | None = None,
) -> float:
    """La valeur de la formule `nom` d'un sort, a un rang et avec des stats donnes.

    formules : toutes les formules du sort, {nom: arbre} (une formule peut en
    reprendre une autre du meme sort).
    valeurs : les valeurs par rang du sort, {nom: [rang 1, rang 2, ...]}.
    stats : les stats du champion (cles de stats_with_items : ap, ad, ad_bonus...).
    niveau : le niveau du champion (1 a 20), pour les morceaux qui en dependent.
    cumuls : le nombre de cumuls de chaque effet, {nom du cumul: nombre}, pour
    les morceaux "compteur de cumuls" (Q de Nasus, E de Cho'Gath...). Ce nombre
    n'est pas dans les fichiers du jeu : c'est un reglage de scenario. Les noms
    sont ceux du fichier, souvent chiffres ("{1b1d7345}" pour Nasus).

    Un morceau pas encore gere, un code de stat pas encore decode ou une valeur
    par rang absente levent une erreur qui les nomme : jamais de chiffre faux
    en silence.
    """
    return _calcul(formules[nom], formules, valeurs, rang, stats, niveau, cumuls)


def _calcul(noeud, formules, valeurs, rang, stats, niveau, cumuls):
    """La valeur d'un morceau : on descend dans l'arbre (fonction recursive)."""

    def sous(morceau):
        # Raccourci : la valeur d'un sous-morceau, avec le meme contexte.
        return _calcul(morceau, formules, valeurs, rang, stats, niveau, cumuls)

    type_ = noeud["__type"]
    if type_ == "GameCalculation":
        total = sum(sous(m) for m in noeud.get("mFormulaParts", []))
        multiplicateur = noeud.get("mMultiplier")
        return total * sous(multiplicateur) if multiplicateur else total
    if type_ == "GameCalculationModified":
        # Une autre formule du meme sort, multipliee (Ahri W : MultiFireDamage
        # = SingleFireDamage x RepeatDamageMod).
        reprise = formules[noeud["mModifiedGameCalculation"]]
        return sous(reprise) * sous(noeud["mMultiplier"])
    if type_ == "NamedDataValueCalculationPart":
        return _valeur(noeud["mDataValue"], valeurs, rang)
    if type_ == "NumberCalculationPart":
        # Absent : le defaut du format, 0 (7 morceaux au 16.22, tous des
        # formules d'affichage "tooltipOnly").
        return noeud.get("mNumber", 0.0)
    if type_ == "StatByCoefficientCalculationPart":
        return noeud["mCoefficient"] * _stat(noeud, stats)
    if type_ == "StatByNamedDataValueCalculationPart":
        return _valeur(noeud["mDataValue"], valeurs, rang) * _stat(noeud, stats)
    if type_ == "StatBySubPartCalculationPart":
        return sous(noeud["mSubpart"]) * _stat(noeud, stats)
    if type_ == "SumOfSubPartsCalculationPart":
        return sum(sous(m) for m in noeud.get("mSubparts", []))
    if type_ == "ProductOfSubPartsCalculationPart":
        return sous(noeud["mPart1"]) * sous(noeud["mPart2"])
    if type_ == "ByCharLevelFormulaCalculationPart":
        # Une liste de 31 valeurs (niveaux 0 a 30) : la valeur du niveau N est
        # a la position N (wiki : Leona 32 - 151, Lux 30 - 200, Braum 26 - 196).
        return noeud["values"][_niveau(niveau)]
    if type_ == "ByCharLevelInterpolationCalculationPart":
        return _interpolation(noeud, _niveau(niveau))
    if type_ == "ByCharLevelBreakpointsCalculationPart":
        return _paliers(noeud, _niveau(niveau))
    if type_ == "{ee18a47b}":
        # Nom de classe chiffre (non retrouve). Une valeur de depart et une
        # d'arrivee, par rang : une LIGNE DROITE du niveau 1 au niveau 18. Le
        # wiki l'ecrit ainsi pour l'eclair d'Udyr Q ("1.5 + (3-1.5)/17*(x-1)
        # for 20", lu le 18/11/2026), et la prolonge apres 18 (non mesure).
        debut = _valeur(noeud["StartDataValue"], valeurs, rang)
        fin = _valeur(noeud["EndDataValue"], valeurs, rang)
        return debut + (fin - debut) * (_niveau(niveau) - 1) / 17
    if type_ == "AbilityResourceByCoefficientCalculationPart":
        return noeud["mCoefficient"] * _ressource(noeud, stats)
    if type_ == "BuffCounterByCoefficientCalculationPart":
        return noeud["mCoefficient"] * _cumuls(noeud, cumuls)
    if type_ == "BuffCounterByNamedDataValueCalculationPart":
        return _valeur(noeud["mDataValue"], valeurs, rang) * _cumuls(noeud, cumuls)
    raise ValueError(f"morceau de formule pas encore gere : {type_}")


# Le mana dans les stats du simulateur : total (formule absente) ou bonus (2),
# la meme regle que pour l'AD ou les PV. Ryze : % du mana BONUS ; Kassadin et
# Blitzcrank : % du mana MAX (ce que disent leurs infobulles en jeu).
RESSOURCE_PAR_FORMULE = {0: "resource", 2: "resource_bonus"}


def _ressource(noeud: dict, stats: dict) -> float:
    formule = noeud.get("mStatFormula", 0)
    if formule not in RESSOURCE_PAR_FORMULE:
        raise ValueError(f"formule de ressource pas encore decodee : {formule}")
    return stats[RESSOURCE_PAR_FORMULE[formule]]


def _cumuls(noeud: dict, cumuls: dict | None) -> float:
    """Le nombre de cumuls que demande un morceau "compteur". Absent : une
    erreur qui nomme le cumul, jamais un 0 silencieux (un Nasus a 0 cumul et
    un Nasus a 600 ne sont pas le meme champion)."""
    nom = noeud["mBuffName"]
    if not cumuls or nom not in cumuls:
        raise ValueError(f"nombre de cumuls requis pour {nom}")
    return cumuls[nom]


def _niveau(niveau: int | None) -> int:
    if niveau is None:
        raise ValueError("niveau du champion requis pour un morceau par niveau")
    return niveau


def _courbe(niveau: int) -> float:
    """La courbe de croissance des stats de LoL (la meme que la macro dbt
    level_growth) : 0 au niveau 1, 17 au niveau 18."""
    return (niveau - 1) * (0.7025 + 0.0175 * (niveau - 1))


def _interpolation(noeud: dict, niveau: int) -> float:
    """De mStartValue (niveau 1) a mEndValue (niveau 18). En ligne droite (wiki,
    passif de Hwei : 40 ; 54,41 ; ...), ou sur la courbe des stats si le
    fichier le dit (wiki, bouclier de Yasuo : 125 ; 145,12 ; ...). Bloquee au
    niveau 18, sauf si le fichier dit de continuer (mScalePastDefaultMaxLevel :
    sens tire du nom du champ, pas mesure). Champ absent : 0."""
    if not noeud.get("mScalePastDefaultMaxLevel"):
        niveau = min(niveau, 18)
    if noeud.get("mScaleByStatProgressionMultiplier"):
        pas = _courbe(niveau)
    else:
        pas = niveau - 1
    debut = noeud.get("mStartValue", 0.0)
    fin = noeud.get("mEndValue", 0.0)
    return debut + (fin - debut) * pas / 17


def _paliers(noeud: dict, niveau: int) -> float:
    """mLevel1Value au niveau 1, puis un bonus par niveau (mInitialBonusPerLevel).
    A chaque palier : un bonus une seule fois (mAdditionalBonusAtThisLevel), et
    un NOUVEAU bonus par niveau a partir de ce niveau, qui REMPLACE l'ancien
    (mBonusPerLevelAtAndAfter ; absent = 0 : la progression s'arrete, Camille Q
    plafonne a 100 % au niveau 16). Verifie sur les vrais coups d'Ekko (19,6 %
    des coups contre 1,2 % si le bonus s'ajoutait) et sur le wiki (30 - 140)."""
    paliers = {p.get("mLevel"): p for p in noeud.get("mBreakpoints", [])}
    valeur = noeud.get("mLevel1Value", 0.0)
    par_niveau = noeud.get("mInitialBonusPerLevel", 0.0)
    for niv in range(1, niveau + 1):
        palier = paliers.get(niv)
        if palier:
            par_niveau = palier.get("mBonusPerLevelAtAndAfter", 0.0)
            valeur += palier.get("mAdditionalBonusAtThisLevel", 0.0)
        if niv >= 2:
            valeur += par_niveau
    return valeur


def _valeur(nom: str, valeurs: dict, rang: int) -> float:
    """La valeur par rang `nom`, au rang voulu (rang 1 = premier element).

    Le nom exact d'abord ; sinon le meme nom SANS tenir compte de la casse : le
    jeu chiffre ses noms en minuscules (FNV-1a), BADRatio et bADRatio sont le
    meme nom pour lui (12 formules de degats au 16.23 : Fiora Q, Morgana W...).
    Deux valeurs qui ne different que par la casse (2 sorts au 16.23) : une
    erreur, jamais un choix au hasard."""
    if nom in valeurs:
        return valeurs[nom][rang - 1]
    memes = [cle for cle in valeurs if cle.lower() == nom.lower()]
    if len(memes) > 1:
        raise ValueError(f"valeur par rang ambigue : {nom} ({memes})")
    if not memes:
        raise ValueError(f"valeur par rang absente : {nom}")
    return valeurs[memes[0]][rang - 1]


def _stat(noeud: dict, stats: dict) -> float:
    """La stat que demande un morceau "par stat". Le fichier omet les codes par
    defaut : code absent = 0 (AP), formule absente = 0 (totale)."""
    code = (noeud.get("mStat", 0), noeud.get("mStatFormula", 0))
    if code not in STATS_DES_CODES:
        raise ValueError(f"code de stat pas encore decode : {code}")
    return stats[STATS_DES_CODES[code]]
