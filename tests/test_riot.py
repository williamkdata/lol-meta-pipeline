import pytest
import requests

from fakes import FakeHttp, FakeLimiter, FakeResponse
from riot import (
    PLATEFORME,
    REGION,
    RateLimiter,
    RiotClient,
    fetch_match,
    fetch_timeline,
    ladder_puuids,
    match_ids,
    read_api_key,
)

LIMITES_PERSONAL = [(20, 1.0), (100, 120.0)]


class FakeClock:
    """Une horloge que le test fait avancer. dormir() avance le temps au lieu
    d'attendre vraiment : 2 minutes simulees prennent quelques millisecondes."""

    def __init__(self):
        self.t = 1000.0
        self.attentes = []

    def maintenant(self):
        return self.t

    def dormir(self, secondes):
        self.attentes.append(secondes)
        self.t += secondes


def limiteur(horloge):
    return RateLimiter(
        LIMITES_PERSONAL, horloge=horloge.maintenant, dormir=horloge.dormir
    )


def max_dans_une_fenetre(instants, fenetre):
    """Le plus grand nombre d'appels tombes dans une meme fenetre glissante."""
    pire = 0
    for i, debut in enumerate(instants):
        pire = max(pire, sum(1 for t in instants[i:] if t - debut < fenetre))
    return pire


def test_rate_limiter_lets_the_first_20_calls_through_without_waiting():
    horloge = FakeClock()
    rl = limiteur(horloge)

    for _ in range(20):
        rl.attendre_son_tour()

    assert horloge.attentes == []


def test_rate_limiter_makes_the_21st_call_wait():
    horloge = FakeClock()
    rl = limiteur(horloge)

    for _ in range(21):
        rl.attendre_son_tour()

    assert horloge.attentes, "la 21e requete aurait du attendre"
    assert horloge.t - 1000.0 >= 1.0


def test_rate_limiter_never_exceeds_the_personal_key_limits():
    """La propriete qui compte : sur 250 requetes envoyees aussi vite que
    possible, jamais plus de 20 par seconde ni plus de 100 par 2 minutes."""
    horloge = FakeClock()
    rl = limiteur(horloge)
    instants = []

    for _ in range(250):
        rl.attendre_son_tour()
        instants.append(horloge.t)

    assert max_dans_une_fenetre(instants, 1.0) <= 20
    assert max_dans_une_fenetre(instants, 120.0) <= 100


def test_rate_limiter_does_not_wait_when_calls_are_spaced_out():
    horloge = FakeClock()
    rl = limiteur(horloge)

    for _ in range(200):
        rl.attendre_son_tour()
        horloge.t += 1.5  # une requete toutes les 1,5 s : 80 par 2 minutes

    assert horloge.attentes == []


def test_rate_limiter_adds_up_the_time_it_waited():
    """Le temps passe a attendre dans le limiteur est compte : c'est ce qui
    permet de dire, apres un run lent, si c'est NOUS qui avons freine."""
    horloge = FakeClock()
    rl = limiteur(horloge)

    for _ in range(25):
        rl.attendre_son_tour()

    assert rl.attente_s == sum(horloge.attentes)
    assert rl.attente_s > 0


def test_rate_limiter_counts_a_request_from_when_its_answer_came_back():
    """Riot date une requete a son ARRIVEE ; le limiteur la datait a son
    DEPART. Le 03/11, la 1re connexion a mis ~10 s : Riot l'a vue 10 s plus
    tard, et la 101e requete a recu un 429 (Retry-After : 11 s). Dater au
    RETOUR de la reponse garantit de ne jamais etre en avance sur Riot."""
    horloge = FakeClock()
    rl = RateLimiter([(100, 120.0)], horloge=horloge.maintenant, dormir=horloge.dormir)

    rl.attendre_son_tour()  # la 1re requete part a t = 1000...
    horloge.t += 10  # ... et sa reponse revient 10 s plus tard
    rl.marquer_retour()
    for _ in range(99):
        rl.attendre_son_tour()
        rl.marquer_retour()
    rl.attendre_son_tour()  # la 101e

    assert horloge.t >= 1000 + 10 + 120.0


def test_rate_limiter_refuses_an_empty_list_of_limits():
    with pytest.raises(ValueError):
        RateLimiter([])


# --- read_api_key -----------------------------------------------------------

FAUSSE_CLE = "RGAPI-00000000-0000-0000-0000-000000000000"


def ecrire_env(tmp_path, ligne):
    chemin = tmp_path / ".env"
    chemin.write_text("AUTRE=1\n" + ligne + "\n", encoding="utf-8")
    return chemin


def test_read_api_key_removes_double_quotes(tmp_path, monkeypatch):
    """La vraie cle de William est entouree de guillemets dans son .env :
    envoyes tels quels, ils feraient refuser la cle par Riot."""
    monkeypatch.delenv("RIOT_API_KEY", raising=False)

    env = ecrire_env(tmp_path, f'RIOT_API_KEY="{FAUSSE_CLE}"')

    assert read_api_key(env) == FAUSSE_CLE


def test_read_api_key_removes_single_quotes_and_spaces(tmp_path, monkeypatch):
    monkeypatch.delenv("RIOT_API_KEY", raising=False)

    env = ecrire_env(tmp_path, f"RIOT_API_KEY= '{FAUSSE_CLE}' ")

    assert read_api_key(env) == FAUSSE_CLE


def test_read_api_key_prefers_the_environment_variable(tmp_path, monkeypatch):
    """Dans Airflow, la cle arrivera par une variable d'environnement."""
    monkeypatch.setenv("RIOT_API_KEY", FAUSSE_CLE)

    assert read_api_key(tmp_path / "absent.env") == FAUSSE_CLE


def test_read_api_key_refuses_a_missing_key(tmp_path, monkeypatch):
    monkeypatch.delenv("RIOT_API_KEY", raising=False)

    with pytest.raises(ValueError):
        read_api_key(ecrire_env(tmp_path, "AUTRE_CHOSE=2"))


def test_read_api_key_never_shows_the_value_in_its_error(tmp_path, monkeypatch):
    """Une valeur mal formee est refusee, et le message ne la recopie pas :
    une cle ne doit jamais finir dans un journal d'Airflow."""
    monkeypatch.delenv("RIOT_API_KEY", raising=False)
    mauvaise = "pas-une-cle-secret-1234"

    with pytest.raises(ValueError) as erreur:
        read_api_key(ecrire_env(tmp_path, f"RIOT_API_KEY={mauvaise}"))

    assert mauvaise not in str(erreur.value)


# --- RiotClient.get ---------------------------------------------------------

CHEMIN = "/lol/match/v5/matches/EUW1_1"
URL = REGION + CHEMIN


def client_avec(reponses):
    """Un client relie a un faux serveur qui renvoie `reponses` dans l'ordre,
    et a des faux limiteurs. Les attentes sont notees au lieu d'etre faites."""
    http = FakeHttp()
    http.reponses[URL] = reponses
    attentes = []
    limiteurs = {PLATEFORME: FakeLimiter(), REGION: FakeLimiter()}
    client = RiotClient(FAUSSE_CLE, http, limiteurs, dormir=attentes.append)
    return client, http, limiteurs, attentes


def test_get_sends_the_key_in_the_riot_header_with_a_timeout():
    client, http, _, _ = client_avec([FakeResponse({"ok": True})])

    assert client.get(REGION, CHEMIN) == {"ok": True}

    [(url, options)] = http.appels
    assert url == URL
    assert options["headers"] == {"X-Riot-Token": FAUSSE_CLE}
    assert options["timeout"] > 0


def test_get_goes_through_the_limiter_of_the_right_routing_value():
    """Les quotas sont comptes PAR REGION : euw1 et europe ont chacun le leur."""
    client, _, limiteurs, _ = client_avec([FakeResponse({})])

    client.get(REGION, CHEMIN)

    assert limiteurs[REGION].passages == 1
    assert limiteurs[PLATEFORME].passages == 0


def test_get_waits_retry_after_on_a_429_then_retries():
    refus = FakeResponse(status_code=429, headers={"Retry-After": "7"})
    client, http, _, attentes = client_avec([refus, FakeResponse({"ok": True})])

    assert client.get(REGION, CHEMIN) == {"ok": True}
    assert attentes == [7.0]
    assert len(http.appels) == 2


def test_get_waits_one_second_on_a_429_without_retry_after():
    """Un 429 venu d'un service sous-jacent peut arriver sans Retry-After."""
    client, _, _, attentes = client_avec(
        [FakeResponse(status_code=429), FakeResponse({})]
    )

    client.get(REGION, CHEMIN)

    assert attentes == [1.0]


def test_get_retries_a_server_error_with_growing_waits():
    pannes = [FakeResponse(status_code=503), FakeResponse(status_code=503)]
    client, _, _, attentes = client_avec([*pannes, FakeResponse({"ok": True})])

    assert client.get(REGION, CHEMIN) == {"ok": True}
    assert attentes == [2, 4]


def test_get_gives_up_after_too_many_attempts():
    client, http, _, _ = client_avec([FakeResponse(status_code=503)])

    with pytest.raises(RuntimeError):
        client.get(REGION, CHEMIN)
    assert len(http.appels) == 5


def test_get_does_not_retry_a_forbidden_key():
    """403 = cle invalide ou expiree : reessayer ne la reparera pas, et
    marteler l'API avec une cle refusee peut la faire bloquer."""
    client, http, _, _ = client_avec([FakeResponse(status_code=403)])

    with pytest.raises(requests.HTTPError):
        client.get(REGION, CHEMIN)
    assert len(http.appels) == 1


# --- les appels a l'API ----------------------------------------------------


def client_simple(reponses_par_url):
    http = FakeHttp()
    http.reponses.update(reponses_par_url)
    limiteurs = {PLATEFORME: FakeLimiter(), REGION: FakeLimiter()}
    return RiotClient(FAUSSE_CLE, http, limiteurs, dormir=lambda s: None), http


def test_ladder_puuids_reads_challenger_and_grandmaster_on_euw1():
    ligue = "/lol/league/v4/{}/by-queue/RANKED_SOLO_5x5"
    client, http = client_simple(
        {
            PLATEFORME + ligue.format("challengerleagues"): FakeResponse(
                {"entries": [{"puuid": "a"}, {"puuid": "b"}]}
            ),
            PLATEFORME + ligue.format("grandmasterleagues"): FakeResponse(
                {"entries": [{"puuid": "c"}, {"puuid": "a"}]}
            ),
        }
    )

    assert ladder_puuids(client) == ["a", "b", "c"]
    hotes = {url.split("/lol/")[0] for url, _ in http.appels}
    assert hotes == {"https://euw1.api.riotgames.com"}


def test_match_ids_asks_europe_for_ranked_solo_since_a_date():
    url = REGION + "/lol/match/v5/matches/by-puuid/a/ids"
    client, http = client_simple({url: FakeResponse(["EUW1_1", "EUW1_2"])})

    assert match_ids(client, "a", depuis=1_790_000_000) == ["EUW1_1", "EUW1_2"]

    [(_, options)] = http.appels
    assert options["params"] == {"queue": 420, "startTime": 1_790_000_000, "count": 100}


def test_fetch_match_and_timeline_use_the_documented_paths():
    base = REGION + "/lol/match/v5/matches/EUW1_1"
    client, _ = client_simple(
        {base: FakeResponse({"m": 1}), base + "/timeline": FakeResponse({"t": 1})}
    )

    assert fetch_match(client, "EUW1_1") == {"m": 1}
    assert fetch_timeline(client, "EUW1_1") == {"t": 1}


# --- ce que le client dit de lui-meme (statistiques et journal) -------------

CHEMIN_IDS = "/lol/match/v5/matches/by-puuid/puuid-secret-123/ids"


def test_get_counts_requests_429_and_the_time_riot_made_us_wait():
    refus = FakeResponse(status_code=429, headers={"Retry-After": "7"})
    client, _, _, _ = client_avec([refus, FakeResponse({"ok": True})])

    client.get(REGION, CHEMIN)

    assert client.stats["requetes"] == 2
    assert client.stats["refus_429"] == 1
    assert client.stats["attente_429_s"] == 7.0


def test_get_records_the_limits_announced_by_riot():
    """Riot annonce ses limites dans chaque reponse. Les noter verifie celles
    que notre limiteur suppose (20 par seconde, 100 par 2 minutes)."""
    annonce = {"X-App-Rate-Limit": "20:1,100:120", "X-Method-Rate-Limit": "2000:10"}
    client, _, _, _ = client_avec([FakeResponse({}, headers=annonce)])

    client.get(REGION, CHEMIN)

    assert client.stats["limites_appli"] == "20:1,100:120"
    assert client.stats["limites_methode"] == "2000:10"


def test_get_logs_each_429_with_riot_counters(caplog):
    caplog.set_level("WARNING")
    refus = FakeResponse(
        status_code=429,
        headers={
            "Retry-After": "40",
            "X-Rate-Limit-Type": "application",
            "X-App-Rate-Limit-Count": "3:1,101:120",
        },
    )
    client, _, _, _ = client_avec([refus, FakeResponse({})])

    client.get(REGION, CHEMIN)

    message = caplog.text
    assert "429" in message
    assert "40" in message
    assert "application" in message
    assert "101:120" in message


def test_get_never_writes_a_player_id_in_the_log(caplog):
    """Le chemin des listes de parties contient le puuid du joueur : le
    journal ne doit noter que le TYPE d'appel."""
    caplog.set_level("WARNING")
    http = FakeHttp()
    http.reponses[REGION + CHEMIN_IDS] = [
        FakeResponse(status_code=429, headers={"Retry-After": "1"}),
        FakeResponse([]),
    ]
    limiteurs = {PLATEFORME: FakeLimiter(), REGION: FakeLimiter()}
    client = RiotClient(FAUSSE_CLE, http, limiteurs, dormir=lambda s: None)

    client.get(REGION, CHEMIN_IDS)

    assert "429" in caplog.text
    assert "ids" in caplog.text
    assert "puuid-secret-123" not in caplog.text


def test_client_keeps_one_connection_open_by_default():
    """Une session garde la connexion ouverte d'une requete a l'autre. Mesure
    du 03/11 : depuis ce reseau, une des deux adresses de Riot ne repond
    jamais ; ouvrir une connexion peut couter 10 s, la reutiliser 0,07 s."""
    client = RiotClient(FAUSSE_CLE)

    assert isinstance(client.session, requests.Session)


def test_get_tells_the_limiter_when_the_answer_came_back():
    client, _, limiteurs, _ = client_avec([FakeResponse({})])

    client.get(REGION, CHEMIN)

    assert limiteurs[REGION].retours == 1
