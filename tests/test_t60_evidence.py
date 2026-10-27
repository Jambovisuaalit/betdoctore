"""Historical T-60 availability cannot be invented from retrospective scores."""
import json
from datetime import UTC, datetime

import pytest

from betdoctore.t60_evidence import audit_file, audit_target, REQUIRED_FEATURES


def target():
    return {"game_key": "nba:2025-12-01:ATL:BOS",
            "scheduled_tipoff": "2025-12-02T00:30:00Z",
            "actual_tipoff": "2025-12-02T00:30:00Z",
            "features": [{
                "name": name, "source_published_at": "2025-12-01T22:00:00Z",
                "archive_captured_at": "2025-12-01T23:20:00Z",
                "snapshot_observed_at": "2025-12-01T23:20:00Z",
                "snapshot_sha256": "a" * 64,
                "evidence_kind": "independently_verified_capture",
            } for name in sorted(REQUIRED_FEATURES)]}


def test_temporal_candidate_never_unlocks_production_training():
    report = audit_target(target())
    assert report["conservative_cutoff"] == "2025-12-01T23:30:00+00:00"
    assert report["temporal_candidate"] is True
    assert report["historical_t60_verified"] is False
    assert report["training_eligible"] is False


def test_late_capture_disqualifies_candidate():
    item = target()
    item["features"][0]["archive_captured_at"] = "2025-12-02T00:00:00Z"
    result = audit_target(item)
    assert not result["temporal_candidate"]
    assert "ARCHIVE_CAPTURE_AFTER_T60" in result["features"][0]["reasons"]


def test_missing_actual_tipoff_blocks_cutoff():
    item = target()
    item["actual_tipoff"] = None
    result = audit_target(item)
    assert result["conservative_cutoff"] is None
    assert "ACTUAL_TIPOFF_NOT_HISTORICALLY_VERIFIED" in result["reasons"]


def test_total_odds_must_be_fresh_at_cutoff():
    item = target()
    obs = next(x for x in item["features"] if x["name"] == "total_odds")
    obs["snapshot_observed_at"] = "2025-12-01T23:10:00Z"
    result = audit_target(item)
    feature = next(x for x in result["features"] if x["name"] == "total_odds")
    assert "ODDS_STALE_AT_T60" in feature["reasons"]


def test_target_final_score_is_leakage_even_with_early_metadata():
    item = target()
    item["features"].append({**item["features"][0], "name": "target_final_score"})
    assert "TARGET_GAME_POSTGAME_LEAKAGE" in audit_target(item)["features"][-1]["reasons"]


def test_naive_datetime_rejected():
    item = target()
    item["scheduled_tipoff"] = "2025-12-02T00:30:00"
    with pytest.raises(ValueError, match="timezone-aware"):
        audit_target(item)


def test_immutable_local_report_and_duplicate_rejection(tmp_path):
    source = tmp_path / "in.json"
    source.write_text(json.dumps({"schema_version": 1, "games": [target()]}))
    a = audit_file(source, tmp_path / "out")
    b = audit_file(source, tmp_path / "out")
    assert a == b
    assert json.loads(a.read_text())["training_eligible_count"] == 0
    source.write_text(json.dumps({"schema_version": 1, "games": [target(), target()]}))
    with pytest.raises(ValueError, match="Duplicate"):
        audit_file(source, tmp_path / "out")
