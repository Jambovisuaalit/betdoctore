"""Synthetic, no-network Sportradar subscription and schema probe tests."""
import json

import httpx

from betdoctore import sportradar_trial_probe as m


def _client(responder):
    return httpx.Client(transport=httpx.MockTransport(responder), follow_redirects=False)


def _response(payload, status=200):
    return httpx.Response(status, json=payload, headers={"etag": '"revision-1"'})


def test_nba_three_seasons_and_old_game_summary_only():
    paths = []
    def respond(req):
        paths.append(req.url.path)
        assert req.headers["x-api-key"] == "test-private-key"
        assert "api_key" not in str(req.url)
        if req.url.path.endswith("/2020/REG/schedule.json"):
            return _response({"games": [
                {"id":"56767fa6-731c-403e-9534-491a20c15ac0",
                 "scheduled":"2020-12-23T00:00:00Z", "home_points":125},
                {"id":"4d0b82b4-10cc-45f5-8633-d4d1749219a6",
                 "scheduled":"2020-12-22T00:00:00Z", "home_points":90}]})
        return _response({"games":[],"summary":{"points":200}})
    with _client(respond) as client:
        result = m.probe("nba", "test-private-key", client, pause=lambda _: None)
    assert result["calls_consumed"] == 4
    assert paths[:3] == [f"/nba/trial/v8/en/games/{y}/REG/schedule.json"
                          for y in (2020, 2021, 2022)]
    assert paths[3].endswith("/4d0b82b4-10cc-45f5-8633-d4d1749219a6/summary.json")
    assert result["source_admitted_games"] == 0
    assert result["raw_response_stored"] is False
    assert result["model_training_eligible"] is False
    assert "test-private-key" not in json.dumps(result)
    assert "200" not in json.dumps(result["checks"][3]["response_schema"])


def test_synergy_seasons_games_events_three_calls():
    paths=[]
    def respond(req):
        paths.append(req.url.path)
        if req.url.path.endswith("/seasons"):
            return _response({"data":[{"id":"historicalseason2021", "name":"2021-22"}]})
        if req.url.path.endswith("/games"):
            assert req.url.params["take"] == "2"
            return _response({"data":[{"id":"historicalgame2021"}]})
        return _response({"data":[{"playType":"Transition","shotX":20,
                                   "shotY":100,"lineup":[1,2]}]})
    with _client(respond) as client:
        result=m.probe("synergy","test-private-key",client,pause=lambda _: None)
    assert result["calls_consumed"]==3
    assert paths[-1].endswith("/historicalgame2021/events")
    assert {"playType","shotX","shotY","lineup"} <= set(
        result["checks"][2]["observed_fields"])
    assert result["historical_as_of_availability_verified"] is False


def test_synergy_zero_games_no_events():
    paths=[]
    def respond(req):
        paths.append(req.url.path)
        return _response({"data":[]})
    with _client(respond) as client:
        result=m.probe("synergy","key",client,pause=lambda _:None)
    assert result["calls_consumed"]==2
    assert all(not path.endswith("/events") for path in paths)


def test_auth_failure_stops_and_does_not_store_credentials():
    with _client(lambda req:httpx.Response(403,text="private server message")) as client:
        result=m.probe("nba","sensitive-key",client,pause=lambda _:None)
    assert result["calls_consumed"]==1
    assert result["checks"][0]["error_code"]=="HTTP_403"
    assert "sensitive-key" not in json.dumps(result)
    assert "private server message" not in json.dumps(result)


def test_response_hash_and_schema_only():
    response_body=b'{"data":[{"name":"secret-person","playType":"Iso"}]}'
    with _client(lambda req:httpx.Response(200,content=response_body)) as client:
        receipt,obj=m._request(client,"privatekey",
            "/synergy/basketball/nba/seasons",{}, "synergy")
    assert receipt["response_sha256"]==m.sha256(response_body)
    assert receipt["response_bytes"]==len(response_body)
    assert "secret-person" not in json.dumps(receipt)
    assert "Iso" not in json.dumps(receipt)
    assert obj["data"][0]["playType"]=="Iso"


def test_oversized_body_never_claims_access_or_admission():
    with _client(lambda req:httpx.Response(200,content=b"x"*(m.MAX_BYTES+1))) as client:
        receipt,obj=m._request(client,"key","/nba/trial/v8/en/games/2020/REG/schedule.json",{},"nba")
    assert receipt["error_code"]=="BODY_OVER_LIMIT"
    assert obj is None
    assert not receipt["access_verified"]


def test_selection_ignores_scores_and_invalid_ids():
    assert m._nba_game({"games":[{"id":"invalid","scheduled":"2020-01-01"},
                                    {"id":"56767fa6-731c-403e-9534-491a20c15ac0",
                                     "scheduled":"2020-12-22", "home_points":500}]}) == (
                                     "56767fa6-731c-403e-9534-491a20c15ac0")
    assert m._synergy_game({"data":[{"id":"bad space"},{"id":"historicalgame2021"}]}) == (
                           "historicalgame2021")


def test_429_keeps_safe_rate_limit_headers_and_stops_without_retry():
    paths = []
    paused = []
    def respond(req):
        paths.append(req.url.path)
        if req.url.path.endswith("/seasons"):
            return _response({"data": []})
        return httpx.Response(429, text="not-safe-to-log", headers={
            "Retry-After": "15", "X-RateLimit-Remaining": "0",
            "X-Request-ID": "request-test", "X-API-KEY": "must-never-save",
        })
    with _client(respond) as client:
        out = m.probe("synergy", "private-key", client, pause=paused.append)
    assert out["calls_consumed"] == 2
    assert paused == [m.MIN_INTERVAL_SEC]
    assert out["checks"][-1]["error_code"] == "HTTP_429"
    assert out["checks"][-1]["response_headers"]["retry-after"] == "15"
    assert out["checks"][-1]["response_headers"]["x-ratelimit-remaining"] == "0"
    assert "must-never-save" not in json.dumps(out)
    assert "not-safe-to-log" not in json.dumps(out)
    assert "private-key" not in json.dumps(out)


def test_product_specific_application_keys_and_no_implicit_product_sharing(monkeypatch):
    monkeypatch.setenv("SPORTRADAR_API_KEY", "generic-app-key")
    monkeypatch.setenv("SPORTRADAR_NBA_API_KEY", "nba-app-key")
    monkeypatch.setenv("SPORTRADAR_SYNERGY_API_KEY", "synergy-app-key")
    assert m._key("nba") == "nba-app-key"
    assert m._key("synergy") == "synergy-app-key"


def test_rate_limit_receipt_does_not_claim_as_of_or_license():
    with _client(lambda req: httpx.Response(429, json={"message": "over quota"})) as client:
        out = m.probe("synergy", "key", client, pause=lambda _: None)
    assert out["calls_consumed"] == 1
    assert out["source_admitted_games"] == 0
    assert out["historical_as_of_availability_verified"] is False
    assert out["source_contract_rights_approved"] is False
    assert out["model_training_eligible"] is False


def test_nba_seasons_preflight_success_uses_one_read_only_request():
    observed = []
    def respond(request):
        observed.append(str(request.url))
        assert request.url.path == "/nba/trial/v8/en/league/seasons.json"
        assert request.headers["x-api-key"] == "private-key-for-nba"
        assert "private-key-for-nba" not in str(request.url)
        return _response({"league": {"name": "NBA"}, "seasons": [
            {"year": 2020, "type": "REG"}, {"year": 2021, "type": "REG"}]})
    with _client(respond) as client:
        result = m.probe("nba", "private-key-for-nba", client,
                         pause=lambda _: None, preflight_only=True)
    assert len(observed) == 1
    assert result["calls_consumed"] == 1
    assert result["preflight_only"] is True
    assert result["nba_seasons_endpoint_access_verified"] is True
    assert result["source_admitted_games"] == 0
    assert result["historical_as_of_availability_verified"] is False
    assert result["model_training_eligible"] is False
    assert "private-key-for-nba" not in json.dumps(result)


def test_nba_seasons_preflight_401_stops_without_historical_game_calls():
    paths = []
    def respond(request):
        paths.append(request.url.path)
        return httpx.Response(401, text="untrusted auth error body")
    with _client(respond) as client:
        result = m.probe("nba", "private-test-key", client,
                         pause=lambda _: None, preflight_only=True)
    assert paths == ["/nba/trial/v8/en/league/seasons.json"]
    assert result["calls_consumed"] == 1
    assert result["checks"][0]["error_code"] == "HTTP_401"
    assert result["nba_seasons_endpoint_access_verified"] is False
    assert "untrusted auth error body" not in json.dumps(result)


def test_synergy_cannot_be_run_with_nba_preflight_flag():
    import pytest
    with _client(lambda req: httpx.Response(200, json={})) as client:
        with pytest.raises(ValueError, match="only supported"):
            m.probe("synergy", "key", client, preflight_only=True)
