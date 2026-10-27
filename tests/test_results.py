"""All fabricated rows in this module are explicitly synthetic test inputs only."""
import copy
import os
from datetime import UTC, date, datetime

import httpx
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from betdoctore.result_sources import acquire, persist
from betdoctore.results import BasicResult, audit, parse_neil_paine
from betdoctore.storage import Base, BasicResultRow

RECEIVED = datetime(2026, 10, 27, tzinfo=UTC)
SHA = "a"*64


def source_rows():
    return [{"date": "2021-01-01", "season": "2021", "neutral": "0", "playoff": "",
             "team1": "BRK", "team2": "PHO", "score1": "120", "score2": "110", "is_home": "1"},
            {"date": "2021-01-01", "season": "2021", "neutral": "0", "playoff": "",
             "team1": "PHO", "team2": "BRK", "score1": "110", "score2": "120", "is_home": "0"}]


def parse(rows=None):
    return parse_neil_paine(rows or source_rows(), SHA, RECEIVED,
                            date(2021, 1, 1), date(2026, 10, 27))


def test_pair_collapses_without_advanced_values_or_invented_time():
    results, report = parse()
    assert not report["errors"]
    assert len(results) == 1
    r = results[0]
    assert (r.team_a, r.team_b, r.points_a, r.points_b) == ("BKN", "PHX", 120, 110)
    assert r.designated_home == "BKN"
    assert r.actual_tipoff is r.completed_at is r.result_published_at is None
    assert r.available_at == RECEIVED
    assert "home_possessions" not in r.model_dump()
    with pytest.raises(ValueError):
        BasicResult.model_validate({**r.model_dump(), "available_at": RECEIVED.replace(year=2021)})


@pytest.mark.parametrize("change", ["score", "missing", "duplicate", "team", "phase", "home"])
def test_pair_corruption_fails_closed(change):
    rows = source_rows()
    if change == "score":
        rows[1]["score1"] = "109"
    elif change == "missing":
        rows.pop()
    elif change == "duplicate":
        rows.append(copy.deepcopy(rows[0]))
    elif change == "team":
        rows[1]["team1"] = "UNKNOWN"
    elif change == "phase":
        rows[1]["playoff"] = "TRUE"
    elif change == "home":
        rows[1]["is_home"] = "1"
    results, report = parse(rows)
    assert report["errors"]
    assert not results


def test_neutral_site_keeps_unknown_home_unknown():
    rows = source_rows()
    for row in rows:
        row.update(neutral="1", is_home="0")
    results, report = parse(rows)
    assert not report["errors"]
    assert results[0].neutral
    assert results[0].designated_home is None


def test_year_coverage_and_independent_check_do_not_unlock_advanced():
    records, parsing = parse()
    report = audit(records, date(2021, 1, 1), date(2026, 10, 27), parsing)
    assert report["structural_status"] == "PASS"
    assert report["missing_years"] == [2022, 2023, 2024, 2025, 2026]
    assert report["independent_crosscheck"]["status"] == "NOT_RUN"
    assert report["ADVANCED_STATS_UNLOCKED"] is False
    duplicate_source = audit(records, date(2021, 1, 1), date(2026, 10, 27), parsing, records)
    assert duplicate_source["independent_crosscheck"]["status"] == "FAIL"
    other = records[0].model_copy(update={"source": "independent-test-source", "points_a": 121})
    conflict = audit(records, date(2021, 1, 1), date(2026, 10, 27), parsing, [other])
    assert conflict["independent_crosscheck"]["conflicts"] == [other.game_key]


def test_acquisition_rejects_html_and_unapproved_content(tmp_path):
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, text="<html>moved</html>")))
    with pytest.raises(ValueError, match="checksum"):
        acquire(tmp_path, client)
    assert not (tmp_path/"manifest.json").exists()


def test_database_batch_idempotence_conflicts_and_invalid_batch():
    records, parsing = parse()
    report = audit(records, date(2021, 1, 1), date(2026, 10, 27), parsing)
    manifest = {"source": "neil-paine-nba-elo", "sha256": SHA,
                "retrieved_at": RECEIVED.isoformat()}
    engine = create_engine(os.environ.get("DATABASE_URL", "sqlite://"))
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        assert persist(session, records, manifest, report)["inserted"] == 1
        assert persist(session, records, manifest, report)["duplicates"] == 1
        assert session.scalar(select(func.count()).select_from(BasicResultRow)) == 1
        with pytest.raises(ValueError, match="conflict"):
            persist(session, [records[0].model_copy(update={"points_a": 121})], manifest, report)
        with pytest.raises(ValueError, match="invalid batch"):
            persist(session, records, manifest, {**report, "structural_status": "FAIL"})


def private_manifest():
    return {"sha256": SHA, "retrieved_at": RECEIVED.isoformat(), "season_start_year": 2020}


def private_row():
    return {"MatchNumber": 1, "DateUtc": "2021-01-02 00:00:00Z", "Location": "Synthetic Arena",
            "HomeTeam": "Brooklyn Nets", "AwayTeam": "Phoenix Suns", "HomeTeamScore": 120,
            "AwayTeamScore": 110, "Winner": "Brooklyn Nets"}


def test_private_dates_and_metadata_are_explicit():
    from betdoctore.private_results import parse_private
    records, report = parse_private([private_row()], private_manifest(),
                                     date(2021, 1, 1), date(2026, 10, 27))
    assert not report["errors"]
    r = records[0]
    assert r.game_date == date(2021, 1, 1)
    assert r.scheduled_tipoff == datetime(2021, 1, 2, tzinfo=UTC)
    assert r.actual_tipoff is None
    assert r.neutral is None
    assert r.phase == "unknown"
    assert r.source == "fixturedownload-private"


@pytest.mark.parametrize("change", ["partial", "future", "tie", "unknown_team", "winner", "duplicate"])
def test_private_invalid_records_are_quarantined(change):
    from betdoctore.private_results import parse_private
    row = private_row()
    if change == "partial":
        row["AwayTeamScore"] = None
    elif change == "future":
        row["DateUtc"] = "2027-01-02 00:00:00Z"
    elif change == "tie":
        row["AwayTeamScore"] = 120
    elif change == "unknown_team":
        row["HomeTeam"] = "Unknown"
    elif change == "winner":
        row["Winner"] = "Phoenix Suns"
    _records, report = parse_private([row, row] if change == "duplicate" else [row],
                                    private_manifest(), date(2021, 1, 1), date(2026, 10, 27))
    assert report["errors"]


def test_private_acquisition_requires_scope_and_future_schedules_are_not_results(tmp_path):
    from betdoctore.private_results import acquire_private, parse_private
    with pytest.raises(ValueError, match="Private non-commercial"):
        acquire_private(tmp_path, 2026, False)
    row = private_row()
    row.update(DateUtc="2027-01-02 00:00:00Z", HomeTeamScore=None, AwayTeamScore=None)
    records, report = parse_private([row], private_manifest(), date(2021, 1, 1), date(2026, 10, 27))
    assert records == []
    assert report["excluded"]["unscored_or_future_fixture"] == 1
    assert not report["errors"]


def test_private_results_never_appear_in_public_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from betdoctore.api import app
    from betdoctore.private_results import parse_private
    engine = create_engine(f"sqlite:///{tmp_path}/private-api.db")
    monkeypatch.setenv("DATABASE_URL", str(engine.url))
    Base.metadata.create_all(engine)
    records, parsing = parse_private([private_row()], private_manifest(), date(2021, 1, 1),
                                     date(2026, 10, 27))
    report = audit(records, date(2021, 1, 1), date(2026, 10, 27), parsing)
    manifest = {"source": "fixturedownload-private", "sha256": SHA,
                "retrieved_at": RECEIVED.isoformat(), "use_scope": "private_noncommercial"}
    with Session(engine) as session:
        persist(session, records, manifest, report)
        session.commit()
    response = TestClient(app).get("/results?year=2021")
    assert response.status_code == 200
    assert response.json()["results"] == []
    assert response.json()["source_manifests"] == {}


def test_reconciliation_quarantines_conflicts_and_preserves_single_source(tmp_path):
    from betdoctore.result_reconciliation import reconcile, save_reconciliation
    primary, _ = parse()
    other = primary[0].model_copy(update={"source": "fixturedownload-private"})
    matched = reconcile([primary[0], other], date(2021, 1, 1), date(2026, 10, 27))
    assert matched["cross_source_corroborated_before_date_review"] == 1
    assert matched["accepted_working_view"] == 1
    assert matched["ADVANCED_STATS_UNLOCKED"] is False
    conflicting = other.model_copy(update={"points_a": 121})
    report = reconcile([primary[0], conflicting], date(2021, 1, 1), date(2026, 10, 27))
    assert report["accepted"] == []
    assert report["quarantined_game_keys"] == 1
    assert report["quarantine_reasons"]["SCORE_CONFLICT"] == 1
    path = save_reconciliation(report, tmp_path)
    assert path.exists()
    assert list(tmp_path.glob("*.html"))


def test_reconciliation_does_not_silently_shift_dates_or_pick_revisions():
    from betdoctore.result_reconciliation import reconcile
    primary, _ = parse()
    r = primary[0]
    other = r.model_copy(update={"source": "fixturedownload-private", "game_date": date(2021, 1, 2),
                                 "game_key": "nba:2021-01-02:BKN:PHX"})
    report = reconcile([r, other], date(2021, 1, 1), date(2026, 10, 27))
    assert report["accepted"] == []
    assert report["quarantined_game_keys"] == 2
    assert report["possible_date_conflicts"]
    duplicated = reconcile([r, r], date(2021, 1, 1), date(2026, 10, 27))
    assert duplicated["accepted"] == []
    assert "MULTIPLE_REVISIONS_REQUIRE_REVIEW" in duplicated["quarantine"][0]["reasons"]
