"""Synthetic evidence fixtures only; no fabricated historical data is shipped."""
import base64
import hashlib
import json
from datetime import UTC, date, datetime

import pytest

from betdoctore.historical_availability import (
    ORIGINAL,
    capture_evidence,
    score_identity,
    scores_available_by,
    verify_capture,
)
from betdoctore.private_results import NAMES
from betdoctore.results import TEAMS, BasicResult
from betdoctore.season_audit import coverage_audit, load_contract


def basic_record(a="BKN", b="PHX", points_a=120, points_b=110, day=date(2021, 1, 1)):
    return BasicResult(source="synthetic-test-only", source_snapshot_sha256="a"*64,
                       source_row_numbers=[2], game_key=f"nba:{day}:{a}:{b}", game_date=day,
                       season_end_year=2021, team_a=a, team_b=b, points_a=points_a, points_b=points_b,
                       neutral=False, phase="non_playoff_unspecified",
                       retrieved_at=datetime(2026, 10, 27, tzinfo=UTC),
                       available_at=datetime(2026, 10, 27, tzinfo=UTC))


def capture_bundle(tmp_path, body=None):
    raw = body or (b"date,season,neutral,playoff,team1,team2,score1,score2\n"
                   b"2021-01-01,2021,0,,BRK,PHO,120,110\n"
                   b"2023-01-01,2023,0,,BRK,PHO,,\n")
    row = {"timestamp": "20220305022316", "original": ORIGINAL, "mimetype": "text/csv",
           "statuscode": "200", "digest": base64.b32encode(hashlib.sha1(raw).digest()).decode().rstrip("=")}
    index = [list(row), list(row.values())]
    (tmp_path/"20220305022316.csv").write_bytes(raw)
    (tmp_path/"20220305022316.metadata.json").write_text(json.dumps({
        "cdx": row, "retrieved_at": "2026-10-27T00:00:00Z",
        "url": f"https://web.archive.org/web/20220305022316id_/{ORIGINAL}"}))
    return raw, row, index


def test_archive_payload_must_match_index_and_origin(tmp_path):
    raw, row, index = capture_bundle(tmp_path)
    verify_capture(raw, row, index)
    with pytest.raises(ValueError, match="digest"):
        verify_capture(raw+b"tampered", row, index)
    with pytest.raises(ValueError, match="absent"):
        verify_capture(raw, row, [index[0]])
    with pytest.raises(ValueError, match="Unapproved"):
        verify_capture(raw, {**row, "original": "https://example.com/other.csv"}, index)


def test_capture_proves_available_by_not_first_publication_or_local_receipt(tmp_path):
    _, _, index = capture_bundle(tmp_path)
    evidence, captures = capture_evidence(tmp_path, index)
    record = basic_record()
    identity = score_identity(record.game_key, 120, 110)
    assert captures[0]["completed_rows_in_scope"] == 1
    assert evidence[identity]["first_publication_at"] is None
    assert "actual_tipoff" in evidence[identity]["does_not_verify"]
    assert not scores_available_by(record, datetime(2021, 1, 2, tzinfo=UTC), evidence)
    assert not scores_available_by(record, datetime(2022, 3, 5, 2, 23, 15, tzinfo=UTC), evidence)
    assert scores_available_by(record, datetime(2022, 3, 5, 2, 23, 16, tzinfo=UTC), evidence)
    assert record.available_at == datetime(2026, 10, 27, tzinfo=UTC)
    revised = record.model_copy(update={"points_a": 121})
    assert not scores_available_by(revised, datetime(2023, 1, 1, tzinfo=UTC), evidence)
    with pytest.raises(ValueError, match="Aware"):
        scores_available_by(record, datetime(2023, 1, 1), evidence)


def test_scored_future_game_is_rejected_but_unscored_schedule_is_not_evidence(tmp_path):
    body = (b"date,season,neutral,playoff,team1,team2,score1,score2\n"
            b"2023-01-01,2023,0,,BRK,PHO,120,110\n")
    _, _, index = capture_bundle(tmp_path, body)
    with pytest.raises(ValueError, match="future game"):
        capture_evidence(tmp_path, index)


def synthetic_season():
    teams = sorted(TEAMS)
    reverse_names = {code:name for name,code in NAMES.items()}
    records, rows = [], []
    for a,b in zip(teams[::2], teams[1::2], strict=True):
        record = basic_record(a,b)
        records.append(record)
        rows.append({"DateUtc": "2021-01-02T00:00:00Z", "HomeTeam": reverse_names[a],
                     "AwayTeam": reverse_names[b], "HomeTeamScore": 120, "AwayTeamScore": 110})
    cup = basic_record("ATL","BOS",day=date(2021, 1, 3))
    records.append(cup)
    rows.append({"DateUtc": "2021-01-04T00:00:00Z", "HomeTeam": reverse_names["ATL"],
                 "AwayTeam": reverse_names["BOS"], "HomeTeamScore": 120, "AwayTeamScore": 110})
    contract = {"seasons": [{"season_end_year":2021,"regular_expected_games":15,
                            "regular_games_per_team":1,"playoff_expected_games":4,
                            "play_in_expected_games":6,
                            "playoff_series":[{"team_a":"ATL","team_b":"BOS","expected_games":4}]}],
                "cup_finals":[{"season_end_year":2021,"game_key":cup.game_key}]}
    schedules = {2021:{"rows":rows,"manifest":{"retrieved_at":"2026-10-27T00:00:00Z"}}}
    return records,schedules,contract


def test_cup_final_is_separate_and_counts_alone_do_not_unlock():
    records,schedules,contract = synthetic_season()
    report = coverage_audit(records,schedules,contract,date(2026, 10, 27))
    s = report["seasons"][0]
    assert s["regular"]["source_schedule_keys"] == 15
    assert s["regular"]["schedule_count_and_team_balance_match"]
    assert s["regular"]["observed_keys"] == 15
    assert s["cup_final"]["observed"] == 1
    assert not s["cup_final"]["included_in_regular_counts"]
    assert s["playoffs"]["observed"] == 0
    assert report["ADVANCED_STATS_UNLOCKED"] is False
    assert s["regular"]["independent_full_event_manifest_verified"] is False


def test_same_total_with_replacement_game_does_not_pass_identity_coverage():
    records,schedules,contract = synthetic_season()
    moved = records[0].model_copy(update={"game_date":date(2021, 2, 1),
        "game_key":f"nba:2021-02-01:{records[0].team_a}:{records[0].team_b}"})
    records[0] = moved
    s = coverage_audit(records,schedules,contract,date(2026, 10, 27))["seasons"][0]
    assert s["regular"]["coverage_status"] == "FAIL"
    assert len(s["regular"]["missing_result_keys"]) == 1


def test_real_rule_contract_separates_short_season_and_completed_series():
    contract = load_contract()
    assert [s["regular_expected_games"] for s in contract["seasons"]] == [1080,1230,1230,1230,1230,1230]
    assert [s["playoff_expected_games"] for s in contract["seasons"]] == [85,87,84,82,84,85]
    assert all(len(s["playoff_series"]) == 15 for s in contract["seasons"])
    assert len(contract["cup_finals"]) == 3


def test_conflicting_rows_in_one_capture_cannot_certify_both_scores(tmp_path):
    body = (b"date,season,neutral,playoff,team1,team2,score1,score2\n"
            b"2021-01-01,2021,0,,BRK,PHO,120,110\n"
            b"2021-01-01,2021,0,,PHO,BRK,111,120\n")
    _, _, index = capture_bundle(tmp_path, body)
    with pytest.raises(ValueError, match="Conflicting"):
        capture_evidence(tmp_path, index)


def test_capture_summary_does_not_clear_quarantine_or_hide_unproven_revision(tmp_path):
    from betdoctore.historical_availability import audit_availability
    _, _, index = capture_bundle(tmp_path)
    evidence, captures = capture_evidence(tmp_path,index)
    r = basic_record()
    conflict = r.model_copy(update={"source":"other-synthetic-test", "points_a":121})
    report = audit_availability([r,conflict],evidence,captures,{r.game_key})
    season = report["seasons"]["2021"]
    assert season["distinct_game_keys"] == 1
    assert season["keys_with_matching_captured_score"] == 1
    assert season["keys_with_at_least_one_unproven_observation"] == 1
    assert season["captured_keys_still_quarantined"] == 1
    assert season["unquarantined_keys_with_matching_capture"] == 0
    assert report["local_timestamps_rewritten"] is False
    assert report["ADVANCED_STATS_UNLOCKED"] is False
