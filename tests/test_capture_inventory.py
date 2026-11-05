"""Synthetic capture bytes; these tests provide no historical source evidence."""
import base64
import hashlib
import json

import httpx
import pytest

from betdoctore.capture_inventory import CDX, TERMS, acquire_inventory, validate_schedule

PREFIX = "https://fixturedownload.com/feed/json/nba-2023"


def fixture():
    raw = json.dumps([{"DateUtc": "2024-02-24T20:00:00+00:00", "HomeTeam": "Boston Celtics",
                       "AwayTeam": "Miami Heat", "HomeTeamScore": None,
                       "AwayTeamScore": None}]).encode()
    row = {"original": PREFIX+"/boston-celtics", "timestamp": "20240223035542",
           "mimetype": "application/json", "statuscode": "200",
           "digest": base64.b32encode(hashlib.sha1(raw).digest()).decode().rstrip("=")}
    index = [list(row), list(row.values())]
    return raw, row, index


def test_archive_integrity_and_no_automatic_admission():
    raw, row, index = fixture()
    evidence = validate_schedule(raw, row, index, PREFIX)
    assert evidence["candidate_future_unscored_rows"] == 1
    assert not evidence["source_admitted"]
    with pytest.raises(ValueError, match="digest"):
        validate_schedule(raw+b" ", row, index, PREFIX)
    with pytest.raises(ValueError, match="origin"):
        validate_schedule(raw, {**row, "original": PREFIX+"evil"}, index, PREFIX)


def test_scored_or_postcutoff_row_is_not_candidate():
    raw, row, _ = fixture()
    for change in ({"HomeTeamScore": 100}, {"DateUtc": "2024-02-23T04:30:00+00:00"}):
        value = [{**json.loads(raw)[0], **change}]
        body = json.dumps(value).encode()
        revised = {**row, "digest": base64.b32encode(hashlib.sha1(body).digest()).decode().rstrip("=")}
        result = validate_schedule(body, revised, [list(revised), list(revised.values())], PREFIX)
        assert result["candidate_future_unscored_rows"] == 0


def test_receipts_empty_indexes_and_failures(tmp_path):
    def respond(request):
        if str(request.url) == TERMS:
            return httpx.Response(200, content=b"synthetic terms - not permission evidence")
        if str(request.url).startswith(CDX):
            return httpx.Response(200, json=[])
        raise AssertionError("Empty discovery must not fetch a capture")
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        report = acquire_inventory(tmp_path, [2023], private_research=True, client=client)
    assert report["queries"][0]["rows"] == 0
    assert report["candidate_unique_fixtures"] == 0
    assert report["source_admitted_games"] == 0
    assert not report["periods_locked"]
    assert (tmp_path/report["inventory_path"]).exists()
    with pytest.raises(ValueError):
        acquire_inventory(tmp_path, [2023], private_research=False)
    with pytest.raises(ValueError):
        acquire_inventory(tmp_path, [2022], private_research=True)


def test_temporal_compatibility_is_necessary_not_admission():
    from betdoctore.capture_inventory import temporal_support
    report = {"captures": [{"candidate_fixtures": [["2024-02-24T20:00:00+00:00", "A", "B"]]}]}
    good = [{"archive_captured_at": "2024-02-23T03:55:42+00:00"}]
    stale = [{"archive_captured_at": "2024-01-01T00:00:00+00:00"}]
    future = [{"archive_captured_at": "2024-02-24T19:00:01+00:00"}]
    assert temporal_support(report, good)["timestamp_compatible_history_candidates"] == 1
    assert temporal_support(report, stale)["timestamp_compatible_history_candidates"] == 0
    assert temporal_support(report, future)["timestamp_compatible_history_candidates"] == 0
    assert not temporal_support(report, good)["sample_lock_ready"]
