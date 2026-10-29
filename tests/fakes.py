"""Faux objets partages par les tests : aucun appel reseau, aucun appel a Google.

Chacun note ce qu'on lui demande et renvoie ce qu'on a regle a l'avance.
"""

import requests


class FakeResponse:
    """Ce que renvoie le faux requests.get : une reponse reglee a la main."""

    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Server Error")

    def json(self):
        return self._data


class FakeHttp:
    """Remplace requests.get pendant un test. On regle la reponse a renvoyer,
    et chaque appel est note pour verifier ce que le code a demande.

    `reponse` sert pour toute URL ; `reponses` permet de repondre differemment
    selon l'URL demandee, quand une fonction en appelle plusieurs."""

    def __init__(self):
        self.reponse = FakeResponse([])
        self.reponses = {}
        self.appels = []

    def get(self, url, **options):
        self.appels.append((url, options))
        return self.reponses.get(url, self.reponse)


class FakeJob:
    """Un chargement en cours chez BigQuery. On note s'il a ete attendu."""

    def __init__(self, output_rows):
        self.output_rows = output_rows
        self.attendu = False

    def result(self):
        self.attendu = True
        return self


class FakeBigQuery:
    """Remplace le client BigQuery : aucun appel reel. On peut lui faire
    annoncer un nombre de lignes chargees different de celui envoye."""

    def __init__(self, lignes_annoncees=None):
        self.lignes_annoncees = lignes_annoncees
        self.appels = []
        self.job = None

    def load_table_from_json(self, rows, destination, job_config=None):
        self.appels.append((rows, destination, job_config))
        if self.lignes_annoncees is None:
            annoncees = len(rows)
        else:
            annoncees = self.lignes_annoncees
        self.job = FakeJob(annoncees)
        return self.job
