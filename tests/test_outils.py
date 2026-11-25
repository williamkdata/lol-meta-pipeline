"""Les outils de l'assistant (23/11/2026) : ce que le modele de langage local
(Ollama) peut demander a nos marts. Chaque outil lit la prod avec des
parametres, jamais avec du texte du modele colle dans le SQL, et renvoie ses
chiffres avec leur definition (la couche semantique)."""

from pathlib import Path

import pytest
import yaml

from fakes import FakeBigQuery
from outils import (
    FAMILLES_EN_CLAIR,
    builds_du_champion,
    bulletin_du_patch,
    changements_du_patch,
    dernier_patch,
    phrase_du_verdict,
)

# Deux lignes comme celles du 16.23 en prod : une prediction jugee par le
# ladder (Annie, par sa survie) et une pas encore jugee.
LIGNES_16_23 = [
    {
        "type": "champion",
        "sujet": "Annie",
        "valeur": "survie",
        "sens_predit": "hausse",
        "ecart_theorique_pct": 974.2,
        "champions_concernes": 1,
        "part_avant_pct": 0.25,
        "part_apres_pct": 0.66,
        "victoires_avant_pct": 52.4,
        "victoires_apres_pct": 45.9,
        "verdict_part": "confirme",
        "verdict_victoires": "sens_contraire",
    },
    {
        "type": "objet",
        "sujet": "Bastionbreaker",
        "valeur": "degats",
        "sens_predit": "baisse",
        "ecart_theorique_pct": -18.2,
        "champions_concernes": 1,
        "part_avant_pct": None,
        "part_apres_pct": None,
        "victoires_avant_pct": None,
        "victoires_apres_pct": None,
        "verdict_part": "pas_encore_juge",
        "verdict_victoires": "pas_encore_juge",
    },
]


def parametre_patch(client):
    """La valeur du parametre @patch de la premiere requete envoyee."""
    (parametre,) = client.configs[0].query_parameters
    assert parametre.name == "patch"
    return parametre.value


def test_the_patch_becomes_its_key():
    client = FakeBigQuery()

    changements_du_patch("16.23", client)

    assert parametre_patch(client) == 1623


def test_a_single_digit_patch_keeps_its_zero():
    # Le prototype faisait int("16.4".replace(".", "")) = 164 : le 16.4 n'aurait
    # jamais ete trouve. La cle du projet est 16 x 100 + 4 = 1604.
    client = FakeBigQuery()

    changements_du_patch("16.4", client)

    assert parametre_patch(client) == 1604


@pytest.mark.parametrize("patch", ["seize", "16", "16.23.1", "", "16.x"])
def test_an_unreadable_patch_is_refused_before_any_query(patch):
    client = FakeBigQuery()

    with pytest.raises(ValueError, match="patch"):
        changements_du_patch(patch, client)
    assert client.requetes == []


def test_the_patch_goes_through_a_parameter_not_into_the_sql():
    # Le texte du modele n'est jamais colle dans le SQL : une question piegee
    # ne pourrait pas changer la requete (injection SQL).
    client = FakeBigQuery()

    changements_du_patch("16.23", client)

    (sql,) = client.requetes
    assert "@patch" in sql
    assert "1623" not in sql


def test_it_reads_the_predictions_and_their_experiments_in_prod():
    client = FakeBigQuery()

    changements_du_patch("16.23", client)

    (sql,) = client.requetes
    assert "lol-meta-pipeline.lol_analytics.mart_patch_predictions" in sql
    assert "lol-meta-pipeline.lol_analytics.mart_patch_experiments" in sql


def test_each_prediction_gets_its_verdict_sentence_instead_of_the_codes():
    # Essai du 23/11 : le modele confondait les codes (part / victoires,
    # confirme / meme_sens). Il recoit la phrase, calculee et testee ici.
    client = FakeBigQuery(resultat_requete=LIGNES_16_23)

    resultat = changements_du_patch("16.23", client)

    assert resultat["patch"] == "16.23"
    for recue, lue in zip(resultat["predictions"], LIGNES_16_23, strict=True):
        assert recue["verdict"] == phrase_du_verdict(lue)
        assert "verdict_part" not in recue
        assert "verdict_victoires" not in recue
        assert recue["sujet"] == lue["sujet"]
        assert recue["part_apres_pct"] == lue["part_apres_pct"]


def test_the_rows_read_in_bigquery_are_not_modified():
    # La phrase s'ajoute a une COPIE : les lignes lues restent intactes.
    client = FakeBigQuery(resultat_requete=LIGNES_16_23)

    changements_du_patch("16.23", client)

    assert "verdict_part" in LIGNES_16_23[0]
    assert "verdict" not in LIGNES_16_23[0]


def test_the_win_rates_are_read_too():
    client = FakeBigQuery()

    changements_du_patch("16.23", client)

    (sql,) = client.requetes
    assert "AS victoires_avant_pct" in sql
    assert "AS victoires_apres_pct" in sql


def test_every_column_comes_with_its_definition():
    # Essai du 05/11 : sans definition, le modele a pris des points de ratio
    # pour de l'or. Chaque colonne renvoyee doit etre expliquee.
    resultat = changements_du_patch(
        "16.23", FakeBigQuery(resultat_requete=LIGNES_16_23)
    )

    colonnes = {colonne for ligne in resultat["predictions"] for colonne in ligne}
    assert colonnes <= set(resultat["definitions"])


def test_a_patch_without_prediction_says_so():
    # Sans remarque, une liste vide pourrait pousser le modele a inventer.
    resultat = changements_du_patch("16.23", FakeBigQuery())

    assert resultat["predictions"] == []
    assert "aucune prediction" in resultat["remarque"]


# --- builds_du_champion ------------------------------------------------------

# Deux familles d'Ezreal au 16.23, comme dans mart_ladder_build_families : un
# vrai choix (10 parties ou plus) et une famille trop rare.
FAMILLES_EZREAL = [
    {
        "poste": "BOTTOM",
        "famille": "manamune",
        "parties": 220,
        "part_des_parties_pct": 81.5,
        "victoires_pct": 50.9,
        "victoires_bas_pct": 44.3,
        "victoires_haut_pct": 57.5,
        "vrai_choix": True,
        "rang_parmi_les_choix": 1,
        "objets_principaux": [
            {"objet": "Manamune", "pct_des_parties": 99},
            {"objet": "Horizon Focus", "pct_des_parties": 69},
            {"objet": "Essence Reaver", "pct_des_parties": 51},
        ],
    },
    {
        "poste": "BOTTOM",
        "famille": "critique",
        "parties": 6,
        "part_des_parties_pct": 2.2,
        "victoires_pct": 66.7,
        "victoires_bas_pct": 30.0,
        "victoires_haut_pct": 90.3,
        "vrai_choix": False,
        "rang_parmi_les_choix": None,
        "objets_principaux": [{"objet": "Essence Reaver", "pct_des_parties": 100}],
    },
]


def parametres(client):
    """Les parametres de la premiere requete : {nom: valeur}."""
    return {p.name: p.value for p in client.configs[0].query_parameters}


def test_builds_reads_the_patch_like_the_other_tools():
    client = FakeBigQuery()

    builds_du_champion("Ezreal", "16.4", client)

    assert parametres(client)["patch"] == 1604


def test_builds_refuses_an_unreadable_patch_before_any_query():
    client = FakeBigQuery()

    with pytest.raises(ValueError, match="patch"):
        builds_du_champion("Ezreal", "16", client)
    assert client.requetes == []


def test_the_champion_goes_through_a_parameter_not_into_the_sql():
    # Un nom de champion vient du modele : jamais colle dans le SQL. La
    # comparaison ignore les majuscules (le modele peut ecrire "ezreal").
    client = FakeBigQuery()

    builds_du_champion("Ezreal' OR 1=1 --", "16.23", client)

    (sql,) = client.requetes
    assert "OR 1=1" not in sql
    assert "LOWER(champion_name) = LOWER(@champion)" in sql
    assert parametres(client)["champion"] == "Ezreal' OR 1=1 --"


@pytest.mark.parametrize(
    ("ecrit", "poste"),
    [
        ("top", "TOP"),
        ("Jungle", "JUNGLE"),
        ("mid", "MIDDLE"),
        ("adc", "BOTTOM"),
        ("bot", "BOTTOM"),
        ("support", "UTILITY"),
        ("UTILITY", "UTILITY"),
    ],
)
def test_the_usual_names_of_the_roles_are_understood(ecrit, poste):
    client = FakeBigQuery()

    builds_du_champion("Ezreal", "16.23", client, poste=ecrit)

    assert parametres(client)["poste"] == poste


def test_without_a_role_every_role_is_returned():
    client = FakeBigQuery()

    builds_du_champion("Ezreal", "16.23", client)

    assert parametres(client)["poste"] is None
    (sql,) = client.requetes
    assert "@poste IS NULL OR team_position = @poste" in sql


def test_an_unknown_role_is_refused_before_any_query():
    client = FakeBigQuery()

    with pytest.raises(ValueError, match="poste"):
        builds_du_champion("Ezreal", "16.23", client, poste="roamer")
    assert client.requetes == []


def test_builds_reads_the_build_families_in_prod():
    client = FakeBigQuery()

    builds_du_champion("Ezreal", "16.23", client)

    (sql,) = client.requetes
    assert "lol-meta-pipeline.lol_analytics.mart_ladder_build_families" in sql


def test_builds_reads_the_first_three_items_of_each_player():
    # Le contenu d'une famille : les 3 premiers objets termines de chaque
    # joueur (int_ladder__build_families), nommes par la seed item_families.
    client = FakeBigQuery()

    builds_du_champion("Ezreal", "16.23", client)

    (sql,) = client.requetes
    assert "lol-meta-pipeline.lol_analytics.int_ladder__build_families" in sql
    assert "UNNEST(b.item_ids)" in sql
    assert "lol-meta-pipeline.lol_analytics.item_families" in sql
    # Le SELECT final reprend la liste calculee (sabotage du 23/11 : un NULL a
    # sa place passait, le faux BigQuery n'executant pas le SQL).
    select_final = sql.rsplit("SELECT", 1)[1]
    assert "p.objets_principaux" in select_final


def test_the_family_definition_explains_the_vote():
    # Essai du 23/11 : le modele inventait (« hybride = degats et survie »).
    # La regle du vote (int_ladder__build_families) est dans la definition.
    definition = builds_du_champion("Ezreal", "16.23", FakeBigQuery())["definitions"][
        "famille"
    ]

    assert "au moins 2 des 3 premiers objets" in definition
    assert "hybride" in definition
    assert "AD et AP melanges" in definition


def test_the_families_are_returned_with_a_definition_for_each_column():
    client = FakeBigQuery(resultat_requete=FAMILLES_EZREAL)

    resultat = builds_du_champion("Ezreal", "16.23", client, poste="adc")

    assert resultat["champion"] == "Ezreal"
    assert resultat["patch"] == "16.23"
    # Tout est rendu tel que lu, sauf le nom de la famille (en clair).
    for recue, lue in zip(resultat["familles"], FAMILLES_EZREAL, strict=True):
        assert {k: v for k, v in recue.items() if k != "famille"} == {
            k: v for k, v in lue.items() if k != "famille"
        }
    colonnes = {colonne for ligne in resultat["familles"] for colonne in ligne}
    assert colonnes <= set(resultat["definitions"])


SEEDS = Path(__file__).resolve().parents[1] / "dbt" / "seeds" / "_seeds.yml"


def familles_de_la_seed():
    """Les familles acceptees par la seed item_families (son test dbt)."""
    seeds = yaml.safe_load(SEEDS.read_text(encoding="utf-8"))["seeds"]
    (seed,) = [s for s in seeds if s["name"] == "item_families"]
    (colonne,) = [c for c in seed["columns"] if c["name"] == "family"]
    (test,) = [t for t in colonne["data_tests"] if isinstance(t, dict)]
    return set(test["accepted_values"]["arguments"]["values"])


def test_every_family_has_a_name_in_clear():
    # Une famille ajoutee un jour a la seed sans son nom en clair : ce test
    # echoue. hybride n'est pas dans la seed : c'est un resultat du vote.
    familles = familles_de_la_seed() | {"hybride"}

    assert familles <= set(FAMILLES_EN_CLAIR)
    assert len(familles) >= 10, "la lecture de la seed n'a rien trouve"


def test_the_model_receives_the_family_name_in_clear():
    # Essai du 23/11 : « hybride = equilibre degats et survie ». Le nom en
    # clair ne laisse plus de place a l'idee toute faite du modele.
    ligne = {**FAMILLES_EZREAL[1], "famille": "hybride"}

    (famille,) = builds_du_champion(
        "Ezreal", "16.23", FakeBigQuery(resultat_requete=[ligne])
    )["familles"]

    assert famille["famille"] == FAMILLES_EN_CLAIR["hybride"]
    assert "objets AD et AP melanges" in famille["famille"]


def test_an_unknown_family_keeps_its_code():
    ligne = {**FAMILLES_EZREAL[1], "famille": "nouvelle"}

    (famille,) = builds_du_champion(
        "Ezreal", "16.23", FakeBigQuery(resultat_requete=[ligne])
    )["familles"]

    assert famille["famille"] == "nouvelle"


def test_the_rows_read_for_the_builds_are_not_modified():
    builds_du_champion(
        "Ezreal", "16.23", FakeBigQuery(resultat_requete=FAMILLES_EZREAL)
    )

    assert FAMILLES_EZREAL[1]["famille"] == "critique"


def test_no_build_says_so():
    resultat = builds_du_champion("Ezreal", "16.23", FakeBigQuery())

    assert resultat["familles"] == []
    assert "aucun build" in resultat["remarque"]


# --- dernier_patch -------------------------------------------------------------


def test_the_last_patch_is_written_like_a_patch():
    client = FakeBigQuery(resultat_requete=[{"cle": 1623}])

    assert dernier_patch(client) == "16.23"


def test_a_single_digit_last_patch_has_no_leading_zero():
    # 1604 -> "16.4", comme Riot l'ecrit (et comme _cle_du_patch le relit).
    assert dernier_patch(FakeBigQuery(resultat_requete=[{"cle": 1604}])) == "16.4"


def test_the_last_patch_is_the_last_one_with_ladder_games_in_prod():
    client = FakeBigQuery(resultat_requete=[{"cle": 1623}])

    dernier_patch(client)

    (sql,) = client.requetes
    assert "MAX(patch_key)" in sql
    assert "lol-meta-pipeline.lol_analytics.mart_ladder_champion_patch" in sql


def test_no_ladder_game_at_all_is_an_error():
    # Une table vide donne MAX = NULL : mieux vaut le dire que d'inventer un patch.
    with pytest.raises(ValueError, match="aucun patch"):
        dernier_patch(FakeBigQuery(resultat_requete=[{"cle": None}]))


# --- phrase_du_verdict -----------------------------------------------------------


def ligne(**changements):
    """Une prediction de champion (Annie au 16.23), modifiee au besoin."""
    return {**LIGNES_16_23[0], **changements}


def test_the_verdict_sentence_of_annie():
    assert phrase_du_verdict(ligne()) == (
        "Annie (champion) : la theorie predit une hausse. "
        "Part de jeu : 0,25 % -> 0,66 %, en hausse comme predit, et c'est prouve. "
        "Victoires : 52,4 % -> 45,9 %, en baisse, a l'inverse de la prediction, "
        "mais pas prouve."
    )


def test_same_direction_not_yet_proven():
    phrase = phrase_du_verdict(ligne(verdict_part="meme_sens"))

    assert "0,25 % -> 0,66 %, en hausse comme predit, mais pas encore prouve." in (
        phrase
    )


def test_a_proven_opposite_is_called_a_contradiction():
    phrase = phrase_du_verdict(ligne(sens_predit="baisse", verdict_part="contredit"))

    assert "la theorie predit une baisse" in phrase
    assert (
        "0,25 % -> 0,66 %, en hausse, a l'inverse de la prediction, et c'est "
        "prouve : la prediction est contredite." in phrase
    )


def test_an_item_speaks_of_purchases_and_of_its_champions():
    phrase = phrase_du_verdict(
        ligne(type="objet", sujet="Overlord's Bloodmail", champions_concernes=94)
    )

    assert phrase.startswith(
        "Overlord's Bloodmail (objet) : la theorie predit une hausse pour les 94 "
        "champions concernes."
    )
    assert "Part d'achat : 0,25 % -> 0,66 %" in phrase


def test_a_prediction_not_yet_judged_says_so_without_numbers():
    assert phrase_du_verdict(LIGNES_16_23[1]) == (
        "Bastionbreaker (objet) : la theorie predit une baisse pour l'unique "
        "champion concerne. Pas encore juge : il faut des parties de ladder au "
        "patch precedent et a celui-ci."
    )


def test_a_rate_without_games_says_so():
    phrase = phrase_du_verdict(
        ligne(
            victoires_avant_pct=None,
            victoires_apres_pct=None,
            verdict_victoires="sans_donnees",
        )
    )

    assert phrase.endswith("Victoires : pas assez de parties pour juger.")


def test_a_stable_rate():
    phrase = phrase_du_verdict(ligne(verdict_part="stable", part_apres_pct=0.25))

    assert "Part de jeu : 0,25 % -> 0,25 %, sans changement." in phrase


def test_an_unknown_verdict_code_is_refused():
    # Un nouveau code dans dbt, oublie ici : mieux vaut planter dans les tests
    # que donner au modele une phrase fausse.
    with pytest.raises(ValueError, match="verdict inconnu"):
        phrase_du_verdict(ligne(verdict_part="presque"))


# --- bulletin_du_patch -----------------------------------------------------------

# La ligne du 16.23 en prod (23/11), colonnes renommees en francais par le SQL.
BULLETIN_16_23 = {
    "objets_controles": 94103,
    "fidelite_pct": 99.83,
    "duels_familles": 82,
    "familles_populaire_prouve": 1,
    "familles_pepites": 2,
    "duels_chemins": 164,
    "chemins_populaire_prouve": 0,
    "chemins_pepites": 5,
    "experiences": 8,
    "experiences_sens_predit": 8,
    "experiences_prouvees": 3,
    "experiences_contredites": 0,
}


def test_the_bulletin_reads_its_patch_through_a_parameter_in_prod():
    client = FakeBigQuery()

    bulletin_du_patch("16.4", client)

    assert parametres(client)["patch"] == 1604
    (sql,) = client.requetes
    assert "lol-meta-pipeline.lol_analytics.mart_patch_bulletin" in sql
    assert "WHERE patch_key = @patch" in sql


def test_the_bulletin_refuses_an_unreadable_patch_before_any_query():
    client = FakeBigQuery()

    with pytest.raises(ValueError, match="patch"):
        bulletin_du_patch("16", client)
    assert client.requetes == []


def test_the_bulletin_summary_of_16_23():
    resultat = bulletin_du_patch(
        "16.23", FakeBigQuery(resultat_requete=[BULLETIN_16_23])
    )

    assert resultat["bulletin"]["resume"] == (
        "Bulletin du patch 16.23. Fidelite des builds (dit si nous lisons bien "
        "les builds, rien sur la theorie) : 99,83 % des 94 103 premiers objets "
        "achetes sont dans l'inventaire de fin de partie. Duels (le build le plus "
        "joue contre sa meilleure alternative : ils comparent les builds entre "
        "eux, rien sur la theorie) : de familles, 82, dont populaire prouve "
        "meilleur : 1, pepites (alternative prouvee meilleure) : 2, non "
        "departages : 79 ; de chemins, 164, dont populaire prouve meilleur : 0, "
        "pepites : 5, non departages : 159. Une pepite de debut de patch reste a "
        "confirmer au patch suivant. Experiences (seules a juger la theorie : un "
        "changement de Riot, une prediction, ce que le ladder a fait) : 8 "
        "changements de Riot juges. Prouves dans le sens predit : 3 sur 8. Dans "
        "le sens predit, mais sans preuve : 5. Contredits (prouves dans l'autre "
        "sens) : 0. Autres (sens contraire non prouve, stables ou sans donnees) : "
        "0."
    )


def test_the_experiments_are_split_so_that_nothing_adds_up_by_itself():
    # Essai du 25/11 : « la theorie a vu juste 8 fois sur 8 », alors que 4
    # seulement etaient prouvees. Chaque groupe est compte ici. Le 16.22 : 9
    # experiences, 5 dans le sens predit dont 2 prouvees, 2 contredites.
    ligne = {**BULLETIN_16_23, "experiences": 9, "experiences_sens_predit": 5}
    ligne.update(experiences_prouvees=2, experiences_contredites=2)

    resume = bulletin_du_patch("16.22", FakeBigQuery(resultat_requete=[ligne]))[
        "bulletin"
    ]["resume"]

    assert resume.endswith(
        "9 changements de Riot juges. Prouves dans le sens predit : 2 sur 9. "
        "Dans le sens predit, mais sans preuve : 3. Contredits (prouves dans "
        "l'autre sens) : 2. Autres (sens contraire non prouve, stables ou sans "
        "donnees) : 2."
    )


def test_the_summary_says_which_measure_judges_the_theory():
    # Essai du 23/11 : « la theorie a vu juste : les builds suivent les ratios
    # des sorts (99,83 % de fidelite) ». La fidelite et les duels ne disent rien
    # de la theorie ; seules les experiences la jugent. La phrase le dit.
    resume = bulletin_du_patch(
        "16.23", FakeBigQuery(resultat_requete=[BULLETIN_16_23])
    )["bulletin"]["resume"]

    assert resume.count("rien sur la theorie") == 2
    assert "Experiences (seules a juger la theorie" in resume


def test_a_patch_without_experiment_says_so_plainly():
    ligne = {**BULLETIN_16_23, "experiences": 0, "experiences_sens_predit": 0}
    ligne.update(experiences_prouvees=0, experiences_contredites=0)

    resume = bulletin_du_patch("16.21", FakeBigQuery(resultat_requete=[ligne]))[
        "bulletin"
    ]["resume"]

    assert resume.endswith(
        "Experiences (seules a juger la theorie) : aucun changement de Riot "
        "jugeable a ce patch."
    )


def test_the_bulletin_keeps_its_numbers_with_a_definition_each():
    resultat = bulletin_du_patch(
        "16.23", FakeBigQuery(resultat_requete=[BULLETIN_16_23])
    )

    assert {k: v for k, v in resultat["bulletin"].items() if k != "resume"} == (
        BULLETIN_16_23
    )
    assert set(resultat["bulletin"]) <= set(resultat["definitions"])


def test_a_patch_without_bulletin_says_so():
    resultat = bulletin_du_patch("16.99", FakeBigQuery())

    assert resultat["bulletin"] is None
    assert "aucun bulletin" in resultat["remarque"]
