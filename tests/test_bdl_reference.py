"""Deterministic BALLDONTLIE importer tests, no live or billable API calls."""
from datetime import date

import httpx
import pytest

from betdoctore.bdl_reference import acquire, dry_run, normalize
from betdoctore.independent_regular_season import load_external_reference


def sample_event():
    return {"id": 1199001, "season": 2021, "date": "2021-12-01",
            "datetime": "2021-12-02T00:30:00Z", "postseason": False,
            "status": "Final", "status_state": "final",
            "home_team": {"abbreviation": "ATL"},
            "visitor_team": {"abbreviation": "BOS"}}


def mock_client(pages):
    requests = []
    def respond(request):
        requests.append(request)
        if not pages:
            raise AssertionError("Unexpected additional API request")
        return httpx.Response(200, json=pages.pop(0))
    return httpx.Client(transport=httpx.MockTransport(respond)), requests


def test_dry_run_is_free_and_no_auth_or_network_required():
    plan = dry_run(2021, 2021)
    assert plan["status"] == "DRY_RUN_NO_NETWORK"
    assert plan["minimum_pages"] >= 13
    with pytest.raises(ValueError):
        dry_run(2019, 2025)


def test_event_normalization_is_explicit_and_timezone_aware():
    event = normalize(sample_event(), 2021, set())
    assert event.provider_event_id == "bdl:1199001"
    assert event.game_key == "nba:2021-12-01:ATL:BOS"
    assert event.home == "ATL"
    assert event.game_date == date(2021, 12, 1)
    row = {**sample_event(), "datetime": "2021-12-03T00:30:00Z"}
    with pytest.raises(ValueError, match="local tipoff"):
        normalize(row, 2021, set())


def test_regular_filter_and_cup_exclusion():
    bad = {**sample_event(), "postseason": True}
    with pytest.raises(ValueError, match="Non-regular"):
        normalize(bad, 2021, set())
    assert normalize(sample_event(), 2021,
                     {"nba:2021-12-01:ATL:BOS"}) is None


def test_mocked_api_exports_checksum_verified_private_reference(tmp_path):
    first = {"data": [sample_event()], "meta": {"next_cursor": 12}}
    second = {"data": [], "meta": {"next_cursor": None}}
    client, requests = mock_client([first, second])
    out = tmp_path / "private-reference"
    report = acquire(out, "fixture-key", start_year=2021, end_year=2021,
                     max_requests=2, client=client, sleep=lambda _: None)
    assert report["events"] == 1
    assert len(requests) == 2
    assert all("season_type=regular" in str(q.url) for q in requests)
    assert all(q.headers.get("Authorization") == "fixture-key" for q in requests)
    events, receipt = load_external_reference(out / "events.json", out / "provenance.json")
    assert events[0].provider_event_id == "bdl:1199001"
    assert receipt.lineage_reviewed is False
    assert receipt.review_eligible is False
    assert (out / "request-receipts.json").exists()
    with pytest.raises(FileExistsError):
        acquire(out, "fixture-key", start_year=2021, end_year=2021,
                max_requests=1, client=client)


def test_request_budget_fail_closed_without_partial_export(tmp_path):
    client, _ = mock_client([
        {"data": [sample_event()], "meta": {"next_cursor": 100}},
    ])
    with pytest.raises(RuntimeError, match="budget"):
        acquire(tmp_path, "fixture-key", start_year=2021, end_year=2021,
                max_requests=1, client=client, sleep=lambda _: None)
    assert not (tmp_path / "events.json").exists()


def test_duplicate_provider_id_rejected(tmp_path):
    client, _ = mock_client([{"data": [sample_event(), sample_event()],
                             "meta": {"next_cursor": None}}])
    with pytest.raises(ValueError, match="Duplicate"):
        acquire(tmp_path, "fixture-key", start_year=2021, end_year=2021,
                client=client, sleep=lambda _: None)
    assert not list(tmp_path.glob("*.json"))


def test_response_season_and_page_must_match(tmp_path):
    bad = {**sample_event(), "season": 2022}
    client, _ = mock_client([{"data": [bad], "meta": {"next_cursor": None}}])
    with pytest.raises(ValueError, match="season"):
        acquire(tmp_path, "fixture-key", start_year=2021, end_year=2021,
                client=client, sleep=lambda _: None)
    assert not (tmp_path / "events.json").exists()
