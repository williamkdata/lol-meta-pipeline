"""Client de l'API Riot : limiteur de debit, appels, gestion des refus (429)."""

import logging
import os
import time
from collections import deque
from pathlib import Path

import requests

# Le journal de ce module. Ses messages arrivent dans le journal de la tache
# Airflow, avec l'heure et le niveau (INFO, WARNING).
journal = logging.getLogger(__name__)

# Deux familles d'hotes : la PLATEFORME (euw1) pour les ligues, la REGION
# (europe) pour les matchs. Chacune a ses propres quotas.
PLATEFORME = "https://euw1.api.riotgames.com"
REGION = "https://europe.api.riotgames.com"
# Cle personal : 20 requetes par seconde et 100 par 2 minutes, par region.
LIMITES_PERSONAL = [(20, 1.0), (100, 120.0)]
FILE_CLASSEE_SOLO = 420
TIMEOUT_S = 10
MAX_TENTATIVES = 5

# Marge ajoutee a chaque fenetre : notre horloge et celle de Riot ne sont pas
# parfaitement synchronisees, et une requete met quelques millisecondes a
# arriver. Un dixieme de seconde evite de tomber pile sur la limite.
MARGE_S = 0.1


class RateLimiter:
    """Ne laisse jamais passer plus de N requetes sur T secondes, pour chaque
    couple (N, T) fourni. Exemple pour une cle personal : [(20, 1.0), (100, 120.0)].

    Fenetre GLISSANTE et non token bucket : on garde l'instant de chaque
    requete recente, et on verifie toutes les fenetres avant d'en envoyer une
    nouvelle. Garantie la plus stricte, quelle que soit la facon dont Riot
    decoupe ses propres fenetres.
    """

    def __init__(self, limites, horloge=time.monotonic, dormir=time.sleep):
        if not limites:
            raise ValueError("au moins une limite (nombre, secondes) est requise")
        self.limites = limites
        self.horloge = horloge
        self.dormir = dormir
        self.plus_longue_fenetre = max(fenetre for _, fenetre in limites)
        self.instants = deque()
        # Le temps total passe a attendre ici : apres un run lent, il dit si
        # c'est NOUS qui avons freine.
        self.attente_s = 0.0

    def attendre_son_tour(self) -> None:
        """Bloque juste le temps necessaire, puis enregistre la requete."""
        while True:
            maintenant = self.horloge()

            # On oublie les requetes sorties de la plus longue fenetre : elles
            # ne comptent plus pour aucune limite.
            while self.instants and (
                maintenant - self.instants[0] >= self.plus_longue_fenetre + MARGE_S
            ):
                self.instants.popleft()

            attente = 0.0
            for nombre, fenetre in self.limites:
                recentes = [
                    t for t in self.instants if maintenant - t < fenetre + MARGE_S
                ]
                if len(recentes) >= nombre:
                    # Il faut que la plus ancienne des `nombre` dernieres
                    # requetes sorte de la fenetre.
                    sortie = recentes[-nombre] + fenetre + MARGE_S
                    attente = max(attente, sortie - maintenant)

            if attente <= 0:
                self.instants.append(maintenant)
                return
            self.attente_s += attente
            self.dormir(attente)

    def marquer_retour(self) -> None:
        """Re-date la derniere requete a l'instant ou sa reponse est revenue.

        Riot compte une requete a son ARRIVEE, quelque part entre son depart et
        le retour de la reponse. La dater au retour place notre fenetre toujours
        APRES celle de Riot : jamais en avance, quelle que soit la latence.
        (03/11 : 1re connexion de ~10 s -> un 429 avec Retry-After de 11 s.)"""
        if self.instants:
            self.instants[-1] = self.horloge()


def read_api_key(chemin=".env") -> str:
    """La cle Riot : variable d'environnement d'abord (Airflow), sinon .env.
    Les guillemets et espaces autour de la valeur sont retires. La valeur
    n'apparait JAMAIS dans un message d'erreur."""
    valeur = os.environ.get("RIOT_API_KEY")
    if valeur is None:
        fichier = Path(chemin)
        lignes = (
            fichier.read_text(encoding="utf-8").splitlines() if fichier.exists() else []
        )
        for ligne in lignes:
            if ligne.startswith("RIOT_API_KEY="):
                valeur = ligne.split("=", 1)[1]
                break
    if valeur is None:
        raise ValueError("RIOT_API_KEY introuvable (variable d'environnement ou .env)")

    valeur = valeur.strip().strip('"').strip("'").strip()
    if not valeur.startswith("RGAPI-"):
        raise ValueError(
            "RIOT_API_KEY ne ressemble pas a une cle Riot (prefixe RGAPI- attendu)"
        )
    return valeur


class RiotClient:
    """Tous les appels passent par ici : limiteur de la bonne region, cle dans
    l'en-tete, attente sur 429, nouvelles tentatives sur panne serveur."""

    def __init__(self, cle, session=None, limiteurs=None, dormir=time.sleep):
        self.cle = cle
        # Une session garde la connexion ouverte d'une requete a l'autre.
        # Mesure du 03/11 : une des deux adresses de Riot ne repond jamais depuis
        # ce reseau ; chaque NOUVELLE connexion pouvait couter 10 s (le timeout),
        # une connexion reutilisee coute 0,07 s.
        self.session = session or requests.Session()
        self.limiteurs = limiteurs or {
            PLATEFORME: RateLimiter(LIMITES_PERSONAL),
            REGION: RateLimiter(LIMITES_PERSONAL),
        }
        self.dormir = dormir
        # Ce que le client dit de lui-meme a la fin d'un run.
        self.stats = {
            "requetes": 0,
            "refus_429": 0,
            "attente_429_s": 0.0,
            "pannes_5xx": 0,
            "limites_appli": None,
            "limites_methode": None,
        }

    def get(self, hote: str, chemin: str, params=None):
        for tentative in range(1, MAX_TENTATIVES + 1):
            self.limiteurs[hote].attendre_son_tour()
            reponse = self.session.get(
                hote + chemin,
                params=params,
                headers={"X-Riot-Token": self.cle},
                timeout=TIMEOUT_S,
            )
            self.limiteurs[hote].marquer_retour()
            self.stats["requetes"] += 1
            # Les limites que Riot annonce, notees a la premiere reponse : elles
            # verifient celles que notre limiteur suppose.
            if self.stats["limites_appli"] is None:
                self.stats["limites_appli"] = reponse.headers.get("X-App-Rate-Limit")
                self.stats["limites_methode"] = reponse.headers.get(
                    "X-Method-Rate-Limit"
                )

            if reponse.status_code == 429:
                # Riot dit combien de secondes attendre. Sans l'en-tete (429 d'un
                # service sous-jacent), on attend une seconde.
                attente = float(reponse.headers.get("Retry-After", 1))
                self.stats["refus_429"] += 1
                self.stats["attente_429_s"] += attente
                # Le TYPE d'appel seulement : le chemin contient parfois un puuid.
                journal.warning(
                    "429 sur %s (%s) : attente %s s ; type %s ; compteurs Riot %s",
                    _type_appel(chemin),
                    hote,
                    attente,
                    reponse.headers.get("X-Rate-Limit-Type"),
                    reponse.headers.get("X-App-Rate-Limit-Count"),
                )
                self.dormir(attente)
                continue
            if reponse.status_code >= 500:
                # Panne passagere cote Riot : attentes croissantes, 2 s puis 4 s...
                self.stats["pannes_5xx"] += 1
                journal.warning(
                    "%s sur %s : nouvel essai dans %s s",
                    reponse.status_code,
                    _type_appel(chemin),
                    2**tentative,
                )
                self.dormir(2**tentative)
                continue
            # 4xx autre que 429 (cle invalide, mauvais chemin) : reessayer ne
            # changerait rien. On s'arrete tout de suite.
            reponse.raise_for_status()
            return reponse.json()
        raise RuntimeError(f"{chemin} : abandon apres {MAX_TENTATIVES} tentatives")


def _type_appel(chemin: str) -> str:
    """Le type d'un appel, sans les identifiants qu'il contient (puuid, partie)."""
    if "/league/" in chemin:
        return "ligue"
    if chemin.endswith("/ids"):
        return "ids"
    if chemin.endswith("/timeline"):
        return "timeline"
    return "partie"


def ladder_puuids(client) -> list[str]:
    """Les joueurs Challenger puis Grandmaster d'EUW, sans doublon, dans l'ordre."""
    puuids = []
    deja_vus = set()
    for palier in ("challengerleagues", "grandmasterleagues"):
        ligue = client.get(
            PLATEFORME, f"/lol/league/v4/{palier}/by-queue/RANKED_SOLO_5x5"
        )
        for entree in ligue["entries"]:
            if entree["puuid"] not in deja_vus:
                deja_vus.add(entree["puuid"])
                puuids.append(entree["puuid"])
    return puuids


def match_ids(client, puuid: str, depuis: int) -> list[str]:
    """Les identifiants des parties classees solo d'un joueur depuis `depuis`
    (secondes epoch). 100 au maximum : la limite documentee par Riot."""
    return client.get(
        REGION,
        f"/lol/match/v5/matches/by-puuid/{puuid}/ids",
        params={"queue": FILE_CLASSEE_SOLO, "startTime": depuis, "count": 100},
    )


def fetch_match(client, match_id: str) -> dict:
    return client.get(REGION, f"/lol/match/v5/matches/{match_id}")


def fetch_timeline(client, match_id: str) -> dict:
    return client.get(REGION, f"/lol/match/v5/matches/{match_id}/timeline")
