"""Wayback capture evidence tests; only synthetic/fixture snapshots, no production data."""
import base64
import hashlib

import httpx
import pytest

from betdoctore.point_in_time_history import discover_index, verify_bodies


def sample_inventory():
    return {"status": "INVENTORY_ONLY", "captures": [{
        "candidate_fixtures": [
            ["2024-03-15T00:30:00+00:00", "Atlanta Hawks", "Boston Celtics"]]}]}


def source_row(raw):
    from betdoctore.historical_availability import NEIL_ORIGINAL
    return {"urlkey": "com,githubusercontent,raw)/neil-paine-1/nba-elo/main/nba_elo.csv",
            "timestamp": "20240313120000", "original": NEIL_ORIGINAL,
            "mimetype": "text/plain", "statuscode": "200",
            "digest": base64.b32encode(hashlib.sha1(raw).digest()).decode().rstrip("=")}


def sample_csv():
    header = "date,season,neutral,playoff,team1,team2,score1,score2,is_home\n"
    rows = ["2024-03-12,2024,0,,ATL,BOS,110,105,1\n",
            "2024-03-12,2024,0,,BOS,ATL,105,110,0\n"]
    return (header + "".join(rows)).encode()


def test_uncollapsed_index_only_does_not_accept_games():
    raw = sample_csv()
    record = source_row(raw)
    def respond(req):
        assert "collapse=" not in str(req.url)
        return httpx.Response(200, json=[list(record), list(record.values())])
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        report, source = discover_index(sample_inventory(), client)
    assert source
    assert report["index_captures"] == 1
    assert report["timestamp_candidates"] == 1
    assert report["source_admitted_games"] == 0
    assert report["cases"][0]["capture"]["digest"] == record["digest"]


def test_preselected_snapshot_verification_never_promotes(tmp_path):
    raw = sample_csv()
    record = source_row(raw)
    idx = [list(record), list(record.values())]
    def respond(req):
        return httpx.Response(200, content=raw)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        discovery, _ = discover_index(
            sample_inventory(),
            httpx.Client(transport=httpx.MockTransport(
                lambda req: httpx.Response(200, json=idx))))
        result = verify_bodies(discovery, idx, client, tmp_path)
    assert result["archive_payloads_verified"] == 1
    assert result["source_admitted_games"] == 0
    assert result["status_counts"] == {"INSUFFICIENT_TEAM_OR_LEAGUE_HISTORY": 1}
    assert not result["training_eligible"]


def test_tampered_capture_fails_before_review(tmp_path):
    raw = sample_csv()
    record = source_row(raw)
    idx = [list(record), list(record.values())]
    with httpx.Client(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json=idx))) as client:
        discovery, _ = discover_index(sample_inventory(), client)
    with (
        httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, content=raw + b"tampered"))) as client,
        pytest.raises(ValueError, match="digest"),
    ):
        verify_bodies(discovery, idx, client, tmp_path)
    assert not list(tmp_path.glob("*review.json"))


def test_seven_day_cutoff_enforced():
    raw = sample_csv()
    record = source_row(raw)
    late = {**record, "timestamp": "20240315000100"}
    old = {**record, "timestamp": "20240301000000"}
    idx = [list(record), list(late), list(old)]
    with httpx.Client(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json=idx))) as client:
        report, _ = discover_index(sample_inventory(), client)
    assert report["timestamp_candidates"] == 1
    assert report["cases"][0]["capture"]["timestamp"] == record["timestamp"]


def test_index_over_limit_fails_closed():
    raw = sample_csv()
    record = source_row(raw)
    idx = [list(record)] + [list(record.values())] * 5000
    with (
        httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, json=idx))) as client,
        pytest.raises(ValueError, match="cap"),
    ):
        discover_index(sample_inventory(), client)
