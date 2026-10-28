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
