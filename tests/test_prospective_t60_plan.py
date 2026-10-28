"""Synthetic offline-only prospective T-60 plan guards."""
import json
from datetime import UTC, datetime, timedelta

import pytest

from betdoctore import prospective_t60_plan as m

NOW = datetime(2026, 10, 28, 6, tzinfo=UTC)


def _payload(*, hours=36):
    when = NOW + timedelta(hours=hours)
    return {
        "date": when.date().isoformat(),
        "league": {"name": "NBA", "alias": "NBA"},
        "games": [
            {"id": "11111111-2222-4333-8444-555555555555",
             "scheduled": when.isoformat(), "status": "scheduled",
             "season": {"year": 2026, "type": "REG"},
             "home": {"alias": "AAA"}, "away": {"alias": "BBB"}},
        ],
    }


def _plan(payload):
    return m.make_plan(payload, created_at=NOW, input_sha256="a" * 64)


def test_future_regular_schedule_only_and_no_network_or_admission():
    output = _plan(_payload())
    assert output["status"] == "PROSPECTIVE_T60_PLAN_ONLY"
    assert output["game_count"] == 1
    assert output["network_calls"] == 0
    assert output["training_eligible"] is False
    assert output["t60_feature_capture_eligible"] is False
    assert output["sportradar_betting_use_written_approval_verified"] is False
    assert output["source_admitted_games"] == 0
    game = output["games"][0]
    assert game["planned_capture_window_start_utc"] == (
        NOW + timedelta(hours=36, minutes=-65)).isoformat()
    assert game["scheduled_t60_cutoff_utc"] == (
        NOW + timedelta(hours=35)).isoformat()
    assert game["actual_tipoff_unknown"] is True
    assert "home_points" not in json.dumps(output)


@pytest.mark.parametrize("field", ["home_points", "away_points", "winner", "final_score"])
def test_any_score_or_outcome_field_blocks_entire_plan(field):
    payload = _payload()
    payload["games"][0][field] = 120
    with pytest.raises(ValueError, match="Score/outcome"):
        _plan(payload)


@pytest.mark.parametrize("status", ["closed", "inprogress", "complete", "postponed"])
def test_non_pregame_status_refused(status):
    payload = _payload()
    payload["games"][0]["status"] = status
    with pytest.raises(ValueError, match="pregame"):
        _plan(payload)


def test_historical_daily_game_cannot_be_planned_as_future():
    payload = _payload(hours=-24)
    with pytest.raises(ValueError, match="past T-60"):
        _plan(payload)


def test_near_cutoff_cannot_be_planned():
    with pytest.raises(ValueError, match="too near"):
        _plan(_payload(hours=1))


def test_beyond_one_week_horizon_rejected():
    with pytest.raises(ValueError, match="future horizon"):
        _plan(_payload(hours=24 * 8))


def test_timezone_aware_tipoff_and_observation_required():
    payload = _payload()
    payload["games"][0]["scheduled"] = "2026-10-29T18:00:00"
    with pytest.raises(ValueError, match="Timezone-aware"):
        _plan(payload)
    with pytest.raises(ValueError, match="Timezone-aware"):
        m.make_plan(_payload(), created_at=datetime(2026, 10, 28),
                    input_sha256="a" * 64)


def test_prior_league_day_utc_conversion_accepted():
    payload = _payload()
    payload["games"][0]["scheduled"] = "2026-10-29T00:00:00+02:00"
    output = _plan(payload)
    assert output["games"][0]["scheduled_tipoff_utc"] == "2026-10-28T22:00:00+00:00"


def test_duplicate_game_id_fails_closed():
    payload = _payload()
    payload["games"].append(dict(payload["games"][0]))
    with pytest.raises(ValueError, match="Duplicate"):
        _plan(payload)


def test_empty_games_never_claims_capture():
    payload = _payload()
    payload["games"] = []
    output = _plan(payload)
    assert output["game_count"] == 0
    assert output["training_eligible"] is False


def test_invalid_league_or_season_rejected():
    payload = _payload()
    payload["league"]["alias"] = "WNBA"
    with pytest.raises(ValueError, match="Not an NBA"):
        _plan(payload)
    payload = _payload()
    payload["games"][0]["season"]["type"] = "PST"
    with pytest.raises(ValueError, match="regular season"):
        _plan(payload)


def test_demo_is_fully_synthetic_and_provenance_unverified():
    demo = m._demo(NOW)
    raw = json.dumps(demo, sort_keys=True).encode()
    output = m.make_plan(demo, created_at=NOW, input_sha256=m.sha256(raw),
                         synthetic=True)
    assert output["source"] == "SYNTHETIC"
    assert output["original_provider_received_at"] is None
    assert output["source_publication_timestamp_verified"] is False
    assert output["network_calls"] == 0


def test_input_size_and_game_bounds():
    payload = _payload()
    payload["games"] = payload["games"] * 21
    with pytest.raises(ValueError, match="game budget"):
        _plan(payload)
