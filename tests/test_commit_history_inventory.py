"""Outcome-blind commit timestamp candidates, not publication or score proof."""
import json

import httpx
import pytest

from betdoctore.commit_history_inventory import (
    _snapshot,
    compare_commit_timeline,
    fetch_commit_candidates,
)
from betdoctore.result_sources import sha256


def sha(c):
    return c * 40


def commit(c, when):
    return {"sha": sha(c), "commit": {"committer": {"date": when}}}


def inventory():
    return {"status": "INVENTORY_ONLY", "source_admitted_games": 0,
            "periods_locked": False, "outcomes_used_for_selection": False,
            "use_scope": "private_noncommercial", "captures": [{
                "candidate_fixtures": [
                    ["2024-03-14T20:00:00+00:00", "Boston Celtics", "Miami Heat"],
                    ["2024-04-24T20:00:00+00:00", "Utah Jazz", "Denver Nuggets"],
                ]}]}


def test_commit_timeline_does_not_approve_any_game():
    commits = [
        {"sha": sha("a"), "committer_claimed_at": "2024-03-12T12:00:00+00:00"},
        {"sha": sha("b"), "committer_claimed_at": "2024-03-15T12:00:00+00:00"},
    ]
    result = compare_commit_timeline(inventory(), commits)
    assert result["schedule_candidates"] == 2
    assert result["claimed_timestamp_compatible"] == 1
    assert result["source_admitted_games"] == 0
    assert not result["independent_historical_publication_verified"]
    assert result["cases"][0]["commit_candidate"]["sha"] == sha("a")
    assert result["cases"][0]["git_date_proves_public_availability"] is False
    assert result["cases"][1]["commit_candidate"] is None


def test_cannot_relax_seven_day_window():
    with pytest.raises(ValueError, match="seven-day"):
        compare_commit_timeline(inventory(), [], max_age_days=8)


def test_reject_bad_git_metadata():
    with pytest.raises(ValueError, match="Git commit SHA"):
        compare_commit_timeline(inventory(), [
            {"sha": "unknown", "committer_claimed_at": "2024-03-01T00:00:00Z"}])
    with pytest.raises(ValueError, match="Duplicate"):
        compare_commit_timeline(inventory(), [
            {"sha": sha("a"), "committer_claimed_at": "2024-03-01T00:00:00Z"}]*2)


def test_inventory_sha_and_controlled_scope(tmp_path):
    raw = json.dumps(inventory()).encode()
    path = tmp_path / f"{sha256(raw)}.combined-inventory.json"
    path.write_bytes(raw)
    assert len(_snapshot(path)["captures"]) == 1
    path.write_bytes(raw+b" ")
    with pytest.raises(ValueError, match="checksum"):
        _snapshot(path)


def test_github_requests_metadata_only_and_paginates():
    calls = []
    def respond(req):
        calls.append(req)
        return httpx.Response(200, json=[commit("a", "2024-03-12T12:00:00Z")] if len(calls)==1 else [])
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        commits, receipts = fetch_commit_candidates(client)
    assert len(commits) == 1
    assert len(receipts) == 1
    assert calls[0].url.path.endswith("/commits")
    assert "path=nba_elo.csv" in str(calls[0].url)
    assert not any("raw.githubusercontent" in str(x.url) for x in calls)
