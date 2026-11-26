import pytest

from tooltips import (
    spell_tooltip_key,
    tooltip_number_tags,
    unfold_tooltip_references,
)

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


# Les nombres qualifies (26/11) : dans les textes nommes par les renvois, un
# nombre peut nommer son sort, @spell.GnarQ:MiniTotalDamage@ (le sort, deux
# points, le calcul). 799 au 16.23. Avant, le motif s'arretait au point et
# lisait le nom "spell".
GNAR_Q = (
    "<mainText>Gnar throws a boomerang that deals <physicalDamage>"
    "@spell.GnarQ:MiniTotalDamage@ physical damage</physicalDamage> and "
    "<status>Slows</status> by @spell.GnarQ:SlowAmount*100@% for "
    "@spell.GnarQ:SlowDuration@ seconds.</mainText>"
)


def sorts_et_noms(texte):
    """Le sort, le nom et la balise de chaque nombre."""
    return [
        (ligne["spell"], ligne["name"], ligne["tag"])
        for ligne in tooltip_number_tags(texte)
    ]


def test_un_nombre_qualifie_donne_son_calcul_et_son_sort():
    assert sorts_et_noms(GNAR_Q) == [
        ("gnarq", "minitotaldamage", "physicalDamage"),
        ("gnarq", "slowamount", "mainText"),
        ("gnarq", "slowduration", "mainText"),
    ]


def test_spell_avec_une_majuscule():
    # 35 nombres sur 799 au 16.23 ecrivent "Spell." (le Q de Karma).
    texte = "<magicDamage>@Spell.KarmaMantra:TotalDamage@</magicDamage>"

    assert sorts_et_noms(texte) == [("karmamantra", "totaldamage", "magicDamage")]


def test_les_mots_apres_un_nombre_qualifie_avec_un_calcul():
    mots = {
        ligne["name"]: ligne["following_text"] for ligne in tooltip_number_tags(GNAR_Q)
    }

    assert mots["minitotaldamage"] == "physical damage and Slows by"
    assert mots["slowamount"] == "% for"


def test_un_nombre_simple_n_a_pas_de_sort():
    assert {ligne["spell"] for ligne in tooltip_number_tags(AHRI_Q)} == {None}


def test_le_meme_calcul_de_deux_sorts_donne_deux_lignes():
    texte = (
        "<magicDamage>@spell.KarmaQ:TotalDamage@</magicDamage> ou "
        "<magicDamage>@spell.KarmaMantra:TotalDamage@</magicDamage>"
    )

    assert sorts_et_noms(texte) == [
        ("karmamantra", "totaldamage", "magicDamage"),
        ("karmaq", "totaldamage", "magicDamage"),
    ]


def test_un_nombre_decimal_n_est_pas_qualifie():
    # @MovementSpeed.0*100@ : un point, mais ni "spell" ni deux-points.
    assert sorts_et_noms("<speed>@MovementSpeed.0*100@%</speed>") == [
        (None, "movementspeed", "speed")
    ]


# --- unfold_tooltip_references : suivre les renvois {{...}} ---
#
# Au 16.23, 173 infobulles sur 1 568 ne contiennent que des renvois vers
# d'autres textes du jeu : celle de Gnar Q dit seulement
# "{{spell_GnarQ_Tooltip}}<br><br>{{spell_GnarBigQ_Tooltip}}". Les balises de
# degats sont dans les textes nommes.


def test_un_renvoi_est_remplace_par_le_texte_qu_il_nomme():
    # Les cles du texte du jeu sont en minuscules ; le renvoi, non.
    textes = {
        "spell_gnarq_tooltip": "boomerang",
        "spell_gnarbigq_tooltip": "rocher",
    }
    texte = "{{spell_GnarQ_Tooltip}}<br><br>{{spell_GnarBigQ_Tooltip}}"

    assert unfold_tooltip_references(texte, textes) == "boomerang<br><br>rocher"


def test_un_renvoi_dans_un_renvoi_est_suivi():
    textes = {"a": "debut {{B}} fin", "b": "milieu"}

    assert unfold_tooltip_references("{{A}}", textes) == "debut milieu fin"


def test_des_espaces_dans_les_accolades():
    assert unfold_tooltip_references("{{ Spell_X }}", {"spell_x": "ok"}) == "ok"


def test_un_renvoi_introuvable_disparait():
    # Rien a lire (0 cas au 16.23 : les 185 cibles existent).
    assert unfold_tooltip_references("avant{{Inconnu}}apres", {}) == "avantapres"


def test_un_renvoi_construit_pendant_la_partie_reste_tel_quel():
    # Le nom depend d'une variable de la partie (@f1@ : l'arme d'Aphelios) :
    # impossible a suivre ici. 15 cas dans les infobulles au 16.23.
    texte = "{{ Spell_ApheliosP_GunShortDesc_@f1@ }}"

    assert unfold_tooltip_references(texte, {}) == texte


def test_cinq_niveaux_de_renvois_passent():
    textes = {"a": "{{b}}", "b": "{{c}}", "c": "{{d}}", "d": "{{e}}", "e": "fin"}

    assert unfold_tooltip_references("{{a}}", textes) == "fin"


def test_six_niveaux_de_renvois_sont_refuses():
    # La frontiere par le haut (sabotage du 26/11 : la limite decalee d'un
    # niveau passait, le message annoncant pourtant 5).
    textes = {
        "a": "{{b}}",
        "b": "{{c}}",
        "c": "{{d}}",
        "d": "{{e}}",
        "e": "{{f}}",
        "f": "fin",
    }

    with pytest.raises(ValueError, match=r"\{\{f\}\}"):
        unfold_tooltip_references("{{a}}", textes)


def test_une_boucle_de_renvois_est_une_erreur_qui_nomme_le_renvoi():
    # Sans limite, a -> b -> a tournerait sans fin. 2 niveaux au plus au 16.23.
    textes = {"a": "{{B}}", "b": "{{A}}"}

    with pytest.raises(ValueError, match=r"\{\{[AB]\}\}.*5 niveaux"):
        unfold_tooltip_references("{{A}}", textes)


def test_un_texte_sans_renvoi_ressort_intact():
    texte = "<magicDamage>@TotalDamage@ magic damage</magicDamage>"

    assert unfold_tooltip_references(texte, {}) == texte


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
