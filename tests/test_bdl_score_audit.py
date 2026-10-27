"""No-network BALLDONTLIE 2025–26 second score feed tests."""
import json
from datetime import UTC, datetime

import pytest

from betdoctore.bdl_score_audit import _score, acquire_scores
from betdoctore.independent_regular_season import ExternalEvent, ReferenceProvenance


def event(i=15900001):
    return ExternalEvent(provider_event_id=f"bdl:{i}", season_end_year=2026,
                         game_date="2025-12-01", home="ATL", away="BOS",
                         phase="regular_season")


def row(i=15900001, home=101, away=104):
    return {"id": i, "season": 2025, "date": "2025-12-01",
            "datetime": "2025-12-02T00:30:00Z",
            "status_state": "final", "status": "Final", "postseason": False,
            "home_team": {"abbreviation": "ATL"},
            "visitor_team": {"abbreviation": "BOS"},
            "home_team_score": home, "visitor_team_score": away}


def test_score_uses_sorted_canonical_teams_and_validates_id():
    r = _score(row(), event())
    assert r["points_a"] == 101
    assert r["points_b"] == 104
    assert r["provider_event_id"] == "bdl:15900001"
    assert r["game_key"] == "nba:2025-12-01:ATL:BOS"
    with pytest.raises(ValueError, match="identity changed"):
        _score(row(i=15900002), event())
    with pytest.raises(ValueError, match="invalid final score"):
        _score(row(home=101, away=101), event())
    with pytest.raises(ValueError, match="invalid final score"):
        _score(row(home=None), event())


def test_score_non_final_rejected():
    r = {**row(), "status": "7:00 pm ET", "status_state": "scheduled"}
    with pytest.raises(ValueError, match="(?i)(non-final|not final)"):
        _score(r, event())


def test_acquire_rejects_incomplete_reference(tmp_path):
    folder = tmp_path / "reference"
    folder.mkdir()
    es = [event().model_dump(mode="json")]
    raw = json.dumps(es).encode()
    (folder / "events.json").write_bytes(raw)
    from betdoctore.result_sources import sha256
    receipt = ReferenceProvenance(
        schema_version=1, provider_id="balldontlie-nba",
        source_url="https://docs.balldontlie.io/",
        terms_url="https://www.balldontlie.io/terms.html",
        license_scope="personal_research", source_sha256=sha256(raw),
        acquired_at=datetime(2026, 10, 27, tzinfo=UTC),
    )
    (folder / "provenance.json").write_text(receipt.model_dump_json())
    with pytest.raises(ValueError, match="incomplete"):
        acquire_scores(folder, tmp_path / "out", "fake-key",
                       max_requests=20, sleep=lambda _: None)


def test_small_request_budget_and_missing_auth_fail_closed(tmp_path):
    with pytest.raises(ValueError, match="Missing"):
        acquire_scores(tmp_path, tmp_path / "out", "")
    with pytest.raises(ValueError, match="Budget"):
        acquire_scores(tmp_path, tmp_path / "out", "x", max_requests=12)
