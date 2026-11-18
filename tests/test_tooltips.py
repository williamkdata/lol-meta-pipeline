from tooltips import spell_tooltip_key, tooltip_number_tags

# Extraits du texte du jeu (16.22, lol.stringtable.json, en_us).
AHRI_Q = (
    "<mainText>Ahri throws then pulls back her orb, dealing <magicDamage>"
    "@TotalDamage@ magic damage</magicDamage> on the way out and <trueDamage>"
    "@TotalDamage@ true damage</trueDamage> on the way back."
    "@SpellModifierDescriptionAppend@</mainText>"
)
AHRI_W = (
    "<mainText>Ahri releases 3 fox-fires that seek nearby enemies and deal "
    "<magicDamage>@SingleFireDamage@ magic damage</magicDamage>, reduced to "
    "<magicDamage>@MultiFireDamage@ damage</magicDamage> beyond the first. She "
    "also gains <speed>@MovementSpeed*100@% Move Speed</speed> decaying over "
    "@MovementSpeedDuration@ seconds.</mainText>"
)


def noms_et_balises(texte):
    """Seulement le nom et la balise de chaque nombre (les tests d'avant les
    mots qui suivent, ajoutes le 18/11)."""
    return [
        {"name": ligne["name"], "tag": ligne["tag"]}
        for ligne in tooltip_number_tags(texte)
    ]


def test_ahri_q_une_formule_deux_types():
    # Magique a l'aller, brut au retour : la meme formule, deux balises.
    assert noms_et_balises(AHRI_Q) == [
        {"name": "spellmodifierdescriptionappend", "tag": "mainText"},
        {"name": "totaldamage", "tag": "magicDamage"},
        {"name": "totaldamage", "tag": "trueDamage"},
    ]


def test_ahri_w_la_balise_la_plus_proche_et_le_calcul_dans_le_nom():
    # @MovementSpeed*100@ : le nom est movementspeed. Un nombre sans balise
    # a lui prend celle qui l'entoure (mainText).
    assert noms_et_balises(AHRI_W) == [
        {"name": "movementspeed", "tag": "speed"},
        {"name": "movementspeedduration", "tag": "mainText"},
        {"name": "multifiredamage", "tag": "magicDamage"},
        {"name": "singlefiredamage", "tag": "magicDamage"},
    ]


def test_les_br_ne_cassent_pas_la_pile():
    texte = (
        "<mainText>a<br>b <shield>@ShieldAmount@</shield><br />@Duration@</mainText>"
    )
    assert noms_et_balises(texte) == [
        {"name": "duration", "tag": "mainText"},
        {"name": "shieldamount", "tag": "shield"},
    ]


def test_une_balise_avec_attributs():
    texte = "<font color='#FF0000'><magicDamage>@X@</magicDamage></font>"
    assert noms_et_balises(texte) == [{"name": "x", "tag": "magicDamage"}]


def test_une_balise_jamais_fermee_est_videe_avec_son_parent():
    # <li> n'est jamais ferme : quand </mainText> arrive, tout ce qui est
    # au-dessus de mainText dans la pile s'en va avec lui.
    texte = (
        "<mainText><li>un<li><physicalDamage>@Dmg@</physicalDamage></mainText>@After@"
    )
    assert noms_et_balises(texte) == [
        {"name": "after", "tag": None},
        {"name": "dmg", "tag": "physicalDamage"},
    ]


def test_une_fermante_orpheline_est_ignoree():
    assert noms_et_balises("</magicDamage>@X@") == [{"name": "x", "tag": None}]


def test_des_nombres_colles():
    texte = "<postScriptRight>@Cost1Prefix@@Cost1@@Cost1Postfix@</postScriptRight>"
    assert noms_et_balises(texte) == [
        {"name": "cost1", "tag": "postScriptRight"},
        {"name": "cost1postfix", "tag": "postScriptRight"},
        {"name": "cost1prefix", "tag": "postScriptRight"},
    ]


def test_un_doublon_ne_compte_qu_une_fois():
    texte = "<magicDamage>@D@</magicDamage> et <magicDamage>@D@</magicDamage>"
    assert noms_et_balises(texte) == [{"name": "d", "tag": "magicDamage"}]


def test_un_renvoi_vers_un_autre_texte_n_est_pas_un_nombre():
    # {{Spell_AhriSeduce_Name}} : le nom d'un autre sort, pas un nombre.
    texte = "<spellName>{{Spell_AhriSeduce_Name}}</spellName>"
    assert noms_et_balises(texte) == []


# --- spell_tooltip_key : ou trouver l'infobulle d'un sort ---


def test_la_cle_d_un_sort():
    assert spell_tooltip_key("Q", "AhriQ") == "generatedtip_spell_ahriq_tooltipextended"


def test_la_cle_suit_le_nom_interne_pas_la_touche():
    # Le R de Vladimir s'appelle VladimirHemoplague dans les fichiers du jeu.
    assert spell_tooltip_key("R", "VladimirHemoplague") == (
        "generatedtip_spell_vladimirhemoplague_tooltipextended"
    )


def test_la_cle_d_un_passif():
    # Les passifs ont leur propre forme de cle (169 sur 169 au 16.22).
    assert spell_tooltip_key("P", "AhriPassive") == (
        "generatedtip_passive_ahripassive_tooltip"
    )


# --- following_text : les mots qui suivent chaque nombre (18/11) ---
# Ils disent ce qu'est le nombre : "% max Health", "magic damage"...


def mots_apres(texte):
    return {
        (ligne["name"], ligne["tag"]): ligne["following_text"]
        for ligne in tooltip_number_tags(texte)
    }


def test_les_mots_qui_suivent_s_arretent_au_nombre_suivant():
    # Sans les balises, espaces resserres, jusqu'au @ du nombre suivant.
    mots = mots_apres(AHRI_Q)
    assert mots[("totaldamage", "magicDamage")] == "magic damage on the way out and"
    assert mots[("totaldamage", "trueDamage")] == "true damage on the way back."
    assert mots[("spellmodifierdescriptionappend", "mainText")] == ""


def test_les_mots_apres_un_calcul_dans_le_nom():
    mots = mots_apres(AHRI_W)
    assert mots[("movementspeed", "speed")] == "% Move Speed decaying over"
    assert mots[("movementspeedduration", "mainText")] == "seconds."


def test_un_pourcentage_des_pv_max():
    # Texte du jeu 16.22, passif de Brand (degats en % des PV max).
    brand = (
        "<mainText>... explodes, dealing <magicDamage>@ExplosionDamage@% max "
        "Health magic damage</magicDamage> to surrounding enemies.</mainText>"
    )
    assert mots_apres(brand)[("explosiondamage", "magicDamage")] == (
        "% max Health magic damage to surrounding enemies."
    )


def test_les_mots_qui_suivent_sont_coupes_a_80_caracteres():
    texte = "@X@ " + "a" * 200
    assert len(mots_apres(texte)[("x", None)]) == 80


def test_un_doublon_garde_les_mots_de_sa_premiere_apparition():
    texte = (
        "<magicDamage>@D@ premier</magicDamage> <magicDamage>@D@ second</magicDamage>"
    )
    assert mots_apres(texte)[("d", "magicDamage")] == "premier"
