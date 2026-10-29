"""Faux objets partages par les tests : aucun appel reseau, aucun appel a Google.

Chacun note ce qu'on lui demande et renvoie ce qu'on a regle a l'avance.
"""

import requests


class FakeResponse:
    """Ce que renvoie le faux requests.get : une reponse reglee a la main.

    `data` est ce que renvoie .json() ; `content` les octets bruts d'un fichier
    telecharge."""

    def __init__(self, data=None, status_code=200, content=b""):
        self._data = data
        self.status_code = status_code
        self.content = content

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

    def load_table_from_uri(self, source, destination, job_config=None):
        """Chargement depuis un fichier du bucket : le faux ne lit rien, il
        annonce le nombre de lignes qu'on lui a regle (0 par defaut)."""
        self.appels.append((source, destination, job_config))
        self.job = FakeJob(self.lignes_annoncees or 0)
        return self.job


class FakeBlob:
    """Un objet du faux bucket. Note ce qu'on y a depose."""

    def __init__(self, nom, taille_annoncee=None):
        self.name = nom
        self.data = None
        self.content_type = None
        self.size = None
        self._taille_annoncee = taille_annoncee

    def upload_from_string(self, data, content_type=None):
        self.data = data
        self.content_type = content_type
        if self._taille_annoncee is None:
            self.size = len(data)
        else:
            self.size = self._taille_annoncee


class FakeBucket:
    def __init__(self, nom, client):
        self.name = nom
        self._client = client

    def blob(self, chemin):
        objet = FakeBlob(chemin, self._client.taille_annoncee)
        self._client.objets[(self.name, chemin)] = objet
        return objet


class FakeStorage:
    """Remplace le client Cloud Storage : aucun appel reel. On peut lui faire
    annoncer une taille recue differente de celle envoyee."""

    def __init__(self, taille_annoncee=None):
        self.taille_annoncee = taille_annoncee
        self.objets = {}

    def bucket(self, nom):
        return FakeBucket(nom, self)
