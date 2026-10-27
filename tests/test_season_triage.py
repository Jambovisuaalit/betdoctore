"""Local-only NBA forensic triage tests: never auto-approve date or score changes."""
from datetime import UTC, date, datetime

import pytest

from betdoctore.results import BasicResult
from betdoctore.season_triage import triage_private


def observed(day="2021-12-02", source="fixture", home="ATL",
             score_a=100, score_b=105):
    d = date.fromisoformat(day)
    return BasicResult(
        source=source, source_snapshot_sha256="a" * 64,
        source_row_numbers=[5], game_key=f"nba:{day}:ATL:BOS", game_date=d,
        season_end_year=2022, team_a="ATL", team_b="BOS",
        points_a=score_a, points_b=score_b,
        designated_home=home, phase="unknown", neutral=None,
        retrieved_at=datetime(2026, 10, 27, tzinfo=UTC),
        available_at=datetime(2026, 10, 27, tzinfo=UTC),
    )


def quarantine(eid="bdl:1"):
    return {"provider_event_id": eid, "season_end_year": 2022,
            "provider_date": "2021-12-01",
            "new_york_tipoff_date": "2021-12-02",
            "provider_datetime": "2021-12-02T23:30:00Z",
            "home_team_abbreviation": "ATL",
            "away_team_abbreviation": "BOS"}


def audit(score_conflict=False):
    return {"seasons": [{"season_end_year": 2022,
                         "quarantined_games": [{
                             "game_key": "nba:2021-12-02:ATL:BOS",
                             "reasons": ["SCORE_CONFLICT"],
                             "observations": [
                                 observed().model_dump(mode="json"),
                                 observed(source="archive", score_b=106).model_dump(
                                     mode="json"),
                             ],
                         }] if score_conflict else []}]}


def test_single_candidate_is_not_approved():
    result = triage_private([quarantine()], [observed()], audit(), set())
    case = result["date_cases"][0]
    assert case["diagnosis"] == "SINGLE_DATE_CANDIDATE"
    assert case["candidate_matches"][0]["basis"] == "new_york_tipoff_date"
    assert case["training_eligible"] is False
    assert result["automatic_game_date_corrections"] == 0


def test_both_dates_are_ambiguous_even_if_both_match():
    result = triage_private([quarantine()],
                            [observed(), observed(day="2021-12-01")],
                            audit(), set())
    assert result["date_cases"][0]["diagnosis"] == "TWO_POSSIBLE_MATCH_DATES"
    assert len(result["date_cases"][0]["candidate_matches"]) == 2


def test_home_disagreement_is_explicit():
    result = triage_private([quarantine()], [observed(home="BOS")],
                            audit(), set())
    assert result["date_cases"][0]["diagnosis"] == "HOME_CONFLICT_REQUIRES_REVIEW"


def test_score_conflict_links_only_exact_candidate_key():
    result = triage_private([quarantine()], [observed()], audit(True), set())
    assert result["score_cases"][0]["possible_date_quarantine_links"] == ["bdl:1"]
    assert result["seasons"][1]["score_conflicts_with_possible_date_link"] == 1
    assert result["score_cases"][0]["resolution"] == "REVIEW_REQUIRED"


def test_fail_closed_on_duplicate_provider_id():
    with pytest.raises(ValueError, match="Duplicate provider ID"):
        triage_private([quarantine()], [], audit(), {"bdl:1"})
    with pytest.raises(ValueError, match="Duplicate provider ID"):
        triage_private([quarantine(), quarantine()], [], audit(), set())


def test_fail_closed_on_invalid_time_and_team():
    row = {**quarantine(), "provider_datetime": "2021-12-03T23:30:00Z"}
    with pytest.raises(ValueError, match="Inconsistent timezone"):
        triage_private([row], [], audit(), set())
    row = {**quarantine(), "home_team_abbreviation": "NOT_NBA"}
    with pytest.raises(ValueError, match="Unknown team"):
        triage_private([row], [], audit(), set())


def test_absent_fixture_does_not_generate_approved_game():
    result = triage_private([quarantine()], [], audit(), set())
    assert result["date_cases"][0]["diagnosis"] == "NO_EXACT_DATE_TEAM_MATCH"
    assert result["seasons"][1]["date_quarantine"] == 1
    assert result["training_eligible"] is False
