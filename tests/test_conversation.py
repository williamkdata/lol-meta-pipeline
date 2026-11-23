"""La conversation avec le modele local (Ollama), 23/11/2026 : la question part,
le modele demande des outils, leurs resultats lui reviennent, puis il repond.
Aucun vrai modele ici : un faux Ollama rejoue des reponses preparees."""

import copy
import inspect
import json

import pytest
import requests

import outils as module_outils
from conversation import (
    MODELE,
    OLLAMA,
    SCHEMAS_OUTILS,
    TOURS_MAX,
    detail_verifie,
    repondre,
)
from fakes import FakeResponse


class FakeOllama:
    """Le serveur Ollama : chaque POST recoit la reponse suivante de la liste
    (un message du modele). On garde ce qui a ete envoye."""

    def __init__(self, messages, status_code=200):
        self._messages = list(messages)
        self._status_code = status_code
        self.envois = []

    def post(self, url, json=None, timeout=None):
        # Une COPIE de ce qui part : un vrai envoi HTTP fige les messages au
        # moment de l'appel, alors que la liste continue de grandir ensuite.
        self.envois.append((url, copy.deepcopy(json)))
        return FakeResponse({"message": self._messages.pop(0)}, self._status_code)


def texte(contenu):
    return {"role": "assistant", "content": contenu}


def appel(nom, arguments):
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": nom, "arguments": arguments}}],
    }


class Outil:
    """Un faux outil : note ses appels et renvoie un resultat fixe, ou leve
    l'erreur donnee."""

    def __init__(self, resultat=None, erreur=None):
        self.resultat = resultat if resultat is not None else {"ok": True}
        self.erreur = erreur
        self.appels = []

    def __call__(self, **arguments):
        self.appels.append(arguments)
        if self.erreur:
            raise self.erreur
        return self.resultat


def message_outil(ollama, envoi):
    """Le dernier message de role "tool" d'un envoi au modele."""
    messages = ollama.envois[envoi][1]["messages"]
    return [m for m in messages if m["role"] == "tool"][-1]


def test_an_answer_without_tool_is_returned_after_one_exchange():
    ollama = FakeOllama([texte("Bonjour.")])

    reponse = repondre("Salut ?", ollama, {}, patch_actuel="16.23")

    assert reponse == "Bonjour."
    ((url, corps),) = ollama.envois
    assert url == f"{OLLAMA}/api/chat"
    assert corps["model"] == MODELE
    assert corps["stream"] is False


def test_the_question_and_the_current_patch_are_sent():
    ollama = FakeOllama([texte("ok")])

    repondre("Quoi de neuf ?", ollama, {}, patch_actuel="16.23")

    systeme, question = ollama.envois[0][1]["messages"]
    assert systeme["role"] == "system"
    assert "16.23" in systeme["content"]
    assert question["role"] == "user"
    assert question["content"].startswith("Quoi de neuf ?")


def test_a_tool_asked_by_the_model_is_called_and_its_result_sent_back():
    outil = Outil(resultat={"patch": "16.23", "predictions": []})
    ollama = FakeOllama(
        [appel("changements_du_patch", {"patch": "16.23"}), texte("Rien de neuf.")]
    )

    reponse = repondre(
        "Le 16.23 ?", ollama, {"changements_du_patch": outil}, patch_actuel="16.23"
    )

    assert reponse == "Rien de neuf."
    assert outil.appels == [{"patch": "16.23"}]
    assert len(ollama.envois) == 2
    retour = message_outil(ollama, 1)
    assert retour["tool_name"] == "changements_du_patch"
    assert json.loads(retour["content"]) == {"patch": "16.23", "predictions": []}


def test_only_the_schemas_of_the_given_tools_are_offered():
    ollama = FakeOllama([texte("ok")])

    repondre("?", ollama, {"builds_du_champion": Outil()}, patch_actuel="16.23")

    noms = [schema["function"]["name"] for schema in ollama.envois[0][1]["tools"]]
    assert noms == ["builds_du_champion"]


def test_a_refused_request_goes_back_to_the_model_as_an_error():
    # Patch illisible, poste inconnu... : le modele lit l'erreur et peut
    # corriger sa demande, au lieu d'un plantage.
    outil = Outil(erreur=ValueError("poste inconnu : 'roamer'"))
    ollama = FakeOllama(
        [
            appel("builds_du_champion", {"champion": "Bard", "patch": "16.23"}),
            texte("Je n'ai pas compris le poste."),
        ]
    )

    reponse = repondre(
        "Bard roamer ?", ollama, {"builds_du_champion": outil}, patch_actuel="16.23"
    )

    assert reponse == "Je n'ai pas compris le poste."
    assert json.loads(message_outil(ollama, 1)["content"]) == {
        "erreur": "poste inconnu : 'roamer'"
    }


def test_a_wrong_argument_name_goes_back_as_an_error():
    def outil_strict(patch):
        return {"patch": patch}

    ollama = FakeOllama(
        [appel("changements_du_patch", {"version": "16.23"}), texte("ok")]
    )

    repondre("?", ollama, {"changements_du_patch": outil_strict}, patch_actuel="16.23")

    assert "erreur" in json.loads(message_outil(ollama, 1)["content"])


def test_an_unknown_tool_goes_back_as_an_error():
    ollama = FakeOllama([appel("pirater_riot", {}), texte("ok")])

    repondre("?", ollama, {}, patch_actuel="16.23")

    assert json.loads(message_outil(ollama, 1)["content"]) == {
        "erreur": "outil inconnu : pirater_riot"
    }


def test_arguments_written_as_text_are_read():
    # Certains modeles envoient les arguments en texte JSON plutot qu'en objet.
    outil = Outil()
    ollama = FakeOllama(
        [appel("changements_du_patch", '{"patch": "16.22"}'), texte("ok")]
    )

    repondre("?", ollama, {"changements_du_patch": outil}, patch_actuel="16.23")

    assert outil.appels == [{"patch": "16.22"}]


def test_an_empty_thinking_tag_is_removed_from_the_answer():
    ollama = FakeOllama([texte("<think>\n\n</think>\n\nAkshan monte.")])

    assert repondre("?", ollama, {}, patch_actuel="16.24") == "Akshan monte."


def test_a_model_that_never_stops_calling_tools_is_stopped():
    outil = Outil()
    ollama = FakeOllama(
        [appel("changements_du_patch", {"patch": "16.23"})] * (TOURS_MAX + 1)
    )

    with pytest.raises(RuntimeError, match="tours"):
        repondre("?", ollama, {"changements_du_patch": outil}, patch_actuel="16.23")
    assert len(ollama.envois) == TOURS_MAX


def test_an_unreachable_model_raises():
    ollama = FakeOllama([texte("ok")], status_code=500)

    with pytest.raises(requests.HTTPError):
        repondre("?", ollama, {}, patch_actuel="16.23")


@pytest.mark.parametrize("schema", SCHEMAS_OUTILS, ids=lambda s: s["function"]["name"])
def test_every_schema_matches_its_python_function(schema):
    # Ce que le modele croit pouvoir envoyer doit etre exactement ce que la
    # fonction accepte : un nom de parametre en trop ou en moins, et l'outil
    # echouerait a chaque appel.
    fonction = getattr(module_outils, schema["function"]["name"])
    parametres = inspect.signature(fonction).parameters
    proprietes = schema["function"]["parameters"]["properties"]
    obligatoires = set(schema["function"]["parameters"]["required"])

    attendus = {nom for nom in parametres if nom != "client"}
    assert set(proprietes) == attendus
    sans_defaut = {
        nom
        for nom, p in parametres.items()
        if nom != "client" and p.default is inspect.Parameter.empty
    }
    assert obligatoires == sans_defaut


# --- le journal des appels, et le detail verifie -------------------------------


def test_the_journal_keeps_each_tool_call_and_its_result():
    outil = Outil(resultat={"patch": "16.23", "predictions": []})
    ollama = FakeOllama(
        [appel("changements_du_patch", {"patch": "16.23"}), texte("ok")]
    )
    journal = []

    repondre(
        "?",
        ollama,
        {"changements_du_patch": outil},
        patch_actuel="16.23",
        journal=journal,
    )

    assert journal == [
        (
            "changements_du_patch",
            {"patch": "16.23"},
            {"patch": "16.23", "predictions": []},
        )
    ]


def test_the_journal_keeps_a_refused_call_as_an_error():
    outil = Outil(erreur=ValueError("patch illisible : '16'"))
    ollama = FakeOllama([appel("changements_du_patch", {"patch": "16"}), texte("ok")])
    journal = []

    repondre(
        "?",
        ollama,
        {"changements_du_patch": outil},
        patch_actuel="16.23",
        journal=journal,
    )

    assert journal == [
        ("changements_du_patch", {"patch": "16"}, {"erreur": "patch illisible : '16'"})
    ]


ANNIE = (
    "Annie (champion) : la theorie predit une hausse. Part de jeu : 0,25 % -> "
    "0,52 %, en hausse comme predit, et c'est prouve."
)
GALIO = (
    "Galio (champion) : la theorie predit une hausse. Part de jeu : 0,64 % -> "
    "0,70 %, en hausse comme predit, mais pas encore prouve."
)
CHANGEMENTS = {
    "patch": "16.23",
    "predictions": [{"sujet": "Annie", "verdict": ANNIE}, {"verdict": GALIO}],
}
BUILDS = {
    "champion": "Ezreal",
    "patch": "16.23",
    "familles": [
        {
            "poste": "BOTTOM",
            "famille": "hybride",
            "parties": 98,
            "part_des_parties_pct": 11.3,
            "victoires_pct": 60.2,
            "victoires_bas_pct": 50.3,
            "victoires_haut_pct": 69.3,
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
            # Aucun objet connu (LEFT JOIN vide) : la ligne reste sans objets.
            "objets_principaux": None,
        },
    ],
}
ARGS_EZREAL = {"champion": "Ezreal", "patch": "16.23", "poste": "adc"}


def test_the_verified_detail_copies_the_verdict_sentences_word_for_word():
    detail = detail_verifie([("changements_du_patch", {"patch": "16.23"}, CHANGEMENTS)])

    assert detail.splitlines() == [
        "Changements du patch 16.23 :",
        f"- {ANNIE}",
        f"- {GALIO}",
    ]


def test_the_verified_detail_writes_one_line_per_build_family():
    detail = detail_verifie([("builds_du_champion", ARGS_EZREAL, BUILDS)])

    assert detail.splitlines() == [
        "Builds de Ezreal au patch 16.23 :",
        "- BOTTOM, hybride : 98 parties (11,3 % des parties), victoires 60,2 % "
        "[50,3 % ; 69,3 %], rang 1 parmi les choix ; objets : Manamune (99 %), "
        "Horizon Focus (69 %), Essence Reaver (51 %)",
        "- BOTTOM, critique : 6 parties (2,2 % des parties), victoires 66,7 % "
        "[30,0 % ; 90,3 %], moins de 10 parties : pas un choix",
    ]


def test_the_remark_of_an_empty_result_is_shown():
    vide = {
        "champion": "Teemoo",
        "patch": "16.99",
        "familles": [],
        "remarque": "aucun build trouve",
    }

    detail = detail_verifie([("builds_du_champion", {"champion": "Teemoo"}, vide)])

    assert detail.splitlines() == [
        "Builds de Teemoo au patch 16.99 :",
        "- aucun build trouve",
    ]


def test_a_refused_call_is_shown_as_an_error():
    detail = detail_verifie(
        [("builds_du_champion", {"poste": "roamer"}, {"erreur": "poste inconnu"})]
    )

    assert detail == "builds_du_champion : erreur : poste inconnu"


def test_the_same_call_twice_is_shown_once():
    appel_ezreal = ("builds_du_champion", ARGS_EZREAL, BUILDS)

    detail = detail_verifie([appel_ezreal, appel_ezreal])

    assert detail.count("Builds de Ezreal") == 1


def test_no_tool_called_means_no_detail():
    assert detail_verifie([]) == ""


def test_a_tool_without_a_layout_says_so():
    # Un nouvel outil ajoute sans sa mise en forme : le detail le dit, au lieu
    # de planter ou de se taire.
    assert detail_verifie([("autre_outil", {}, {"x": 1})]) == (
        "autre_outil : pas de detail pour cet outil"
    )


# --- temperature 0 et consignes du resume (23/11, deuxieme essai du lanceur) ---


def test_the_model_answers_without_randomness():
    # Temperature 0 : le mot le plus probable, toujours. La meme question donne
    # la meme reponse, et deux essais se comparent.
    ollama = FakeOllama([texte("ok")])

    repondre("?", ollama, {}, patch_actuel="16.23")

    assert ollama.envois[0][1]["options"]["temperature"] == 0


def consignes_envoyees():
    ollama = FakeOllama([texte("ok")])
    repondre("?", ollama, {}, patch_actuel="16.23")
    return ollama.envois[0][1]["messages"][0]["content"]


def test_the_instructions_keep_proven_for_what_is_proven():
    # Essai du 23/11 : Galio et LeBlanc dits « confirmes », rien de prouve.
    assert "que si la phrase dit « et c'est prouve »" in consignes_envoyees()


def test_the_instructions_say_damage_and_survival_are_theoretical_values():
    # Essai du 23/11 : « Galio : survie et victoires ont augmente ».
    consignes = consignes_envoyees()

    assert "degats et survie sont des valeurs theoriques" in consignes
    assert "jamais des mesures du ladder" in consignes
