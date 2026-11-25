"""Le banc d'essai de l'assistant (25/11/2026) : des questions fixes, posees au
modele, et pour chacune l'outil et les arguments attendus. Ne de l'incident du
25/11 : une mise a jour automatique d'Ollama avait casse l'appel d'outils sans
qu'aucun test le voie. Ici, un faux Ollama rejoue les appels du modele."""

from evaluation import ESSAIS, evaluer
from fakes import FakeOllama


def appel(nom, arguments):
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": nom, "arguments": arguments}}],
    }


def texte(contenu):
    return {"role": "assistant", "content": contenu}


def outil(**arguments):
    return {"ok": True}


OUTILS = {
    "bulletin_du_patch": outil,
    "builds_du_champion": outil,
    "changements_du_patch": outil,
    "objets_du_champion": outil,
}
BULLETIN = {
    "question": "Que dit le bulletin du dernier patch ?",
    "outil": "bulletin_du_patch",
    "arguments": {"patch": "{patch}"},
}
BUILDS = {
    "question": "Quels builds pour Ezreal en adc ?",
    "outil": "builds_du_champion",
    "arguments": {"champion": "Ezreal", "patch": "{patch}", "poste": "adc"},
}


def test_the_expected_tool_with_the_expected_arguments_passes():
    ollama = FakeOllama([appel("bulletin_du_patch", {"patch": "16.23"}), texte("ok")])

    (resultat,) = evaluer([BULLETIN], ollama, OUTILS, patch_actuel="16.23")

    assert resultat["ok"] is True
    assert resultat["appels"] == [("bulletin_du_patch", {"patch": "16.23"})]


def test_the_right_tool_with_an_invented_patch_fails():
    # Le cas du 25/11 : le bon outil, mais un patch « 11.23 » invente.
    ollama = FakeOllama([appel("bulletin_du_patch", {"patch": "11.23"}), texte("ok")])

    (resultat,) = evaluer([BULLETIN], ollama, OUTILS, patch_actuel="16.23")

    assert resultat["ok"] is False


def test_the_wrong_tool_fails():
    ollama = FakeOllama([appel("objets_du_champion", {"patch": "16.23"}), texte("ok")])

    (resultat,) = evaluer([BULLETIN], ollama, OUTILS, patch_actuel="16.23")

    assert resultat["ok"] is False


def test_no_tool_called_fails():
    # Le cas du 25/11 : le modele « pense a voix haute » et n'appelle rien.
    ollama = FakeOllama([texte("Okay, the user is asking...")])

    (resultat,) = evaluer([BULLETIN], ollama, OUTILS, patch_actuel="16.23")

    assert resultat["ok"] is False
    assert resultat["appels"] == []


def test_upper_case_and_role_names_are_accepted():
    # « EZREAL » et « ADC » ou « bottom » : l'outil les comprend, le banc aussi.
    for poste in ("ADC", "bottom"):
        ollama = FakeOllama(
            [
                appel(
                    "builds_du_champion",
                    {"champion": "EZREAL", "patch": "16.23", "poste": poste},
                ),
                texte("ok"),
            ]
        )

        (resultat,) = evaluer([BUILDS], ollama, OUTILS, patch_actuel="16.23")

        assert resultat["ok"] is True, poste


def test_a_missing_argument_fails():
    ollama = FakeOllama(
        [
            appel("builds_du_champion", {"champion": "Ezreal", "patch": "16.23"}),
            texte("ok"),
        ]
    )

    (resultat,) = evaluer([BUILDS], ollama, OUTILS, patch_actuel="16.23")

    assert resultat["ok"] is False


def test_a_model_stuck_in_tools_fails_and_the_next_question_still_runs():
    # Plus de tours d'outils que permis : repondre leve une erreur. Le banc la
    # note et passe a la question suivante.
    boucle = [appel("objets_du_champion", {"patch": "16.23"})] * 4
    ollama = FakeOllama(
        [*boucle, appel("bulletin_du_patch", {"patch": "16.23"}), texte("ok")]
    )

    premier, second = evaluer([BUILDS, BULLETIN], ollama, OUTILS, patch_actuel="16.23")

    assert premier["ok"] is False
    assert "tours" in premier["reponse"]
    assert second["ok"] is True


def test_the_test_questions_cover_every_tool():
    # Un outil ajoute sans question d'essai : ce test le rappelle.
    assert {essai["outil"] for essai in ESSAIS} == set(OUTILS)
