"""Strict identity approval never infers an independent reference or training readiness."""
import hashlib
import json
from datetime import UTC, date, datetime

import pytest

from betdoctore.independent_regular_season import (
    ExternalEvent,
    ReferenceProvenance,
    audit_regular_seasons,
    load_external_reference,
    write_regular_season_audit,
)
from betdoctore.results import BasicResult


def record(key_date="2021-12-01", a=100, b=101, source="archive", home="ATL"):
    day = date.fromisoformat(key_date)
    return BasicResult(
        source=source, source_snapshot_sha256="a" * 64, source_row_numbers=[1],
        game_key=f"nba:{day}:ATL:BOS", game_date=day, season_end_year=2022,
        team_a="ATL", team_b="BOS", points_a=a, points_b=b,
        designated_home=home, neutral=False, phase="non_playoff_unspecified",
        retrieved_at=datetime(2026, 10, 27, tzinfo=UTC),
        available_at=datetime(2026, 10, 27, tzinfo=UTC),
    )


def event(day="2021-12-01", eid="ind-001", home="ATL"):
    return ExternalEvent(provider_event_id=eid, season_end_year=2022,
                         game_date=date.fromisoformat(day), home=home,
                         away="ATL" if home == "BOS" else "BOS", phase="regular_season")


def provenance(reviewed=True):
    return ReferenceProvenance(
        schema_version=1, provider_id="independent-licensed-provider",
        source_url="https://example.com/schedule",
        terms_url="https://example.com/terms", license_scope="private_research",
        source_sha256="b" * 64, acquired_at=datetime(2026, 10, 27, tzinfo=UTC),
        lineage_reviewed=reviewed, reviewed_by="data-auditor" if reviewed else None,
        review_evidence="https://example.com/provenance" if reviewed else None,
    )


def contract():
    return {"seasons": [{"season_end_year": 2022, "regular_expected_games": 1230,
                         "regular_games_per_team": 82}]}


def season(records, events=None, prov=None):
    return audit_regular_seasons(records, events or [event()],
                                 prov or provenance(), contract())["seasons"][0]


def test_two_feeds_and_reviewed_reference_produce_partial_approved_list():
    result = season([record(), record(source="different")])
    assert result["approved_count"] == 1
    assert result["approved_games"][0]["provider_event_id"] == "ind-001"
    assert result["approved_games"][0]["training_eligible"] is False
    assert result["status"] == "BLOCKED"  # only 1 of 1230 reference events


def test_single_source_remains_pending_not_approved():
    result = season([record()])
    assert result["approved_count"] == 0
    assert result["pending_games"][0]["reason"] == "SINGLE_SOURCE_RESULT"


def test_score_conflicts_enter_quarantine():
    result = season([record(), record(b=110, source="different")])
    assert result["approved_count"] == 0
    assert result["quarantined_count"] == 1
    assert "SCORE_CONFLICT" in result["quarantined_games"][0]["reasons"]


def test_home_conflict_against_reference_enters_quarantine():
    result = season([record(), record(source="different")], [event(home="BOS")])
    assert result["approved_count"] == 0
    assert "HOME_DESIGNATION_MISMATCH" in result["quarantined_games"][0]["reasons"]


def test_duplicate_independent_event_ids_fail_closed():
    with pytest.raises(ValueError, match="Duplicate external event ID"):
        season([record()], [event(), event("2021-12-02")])


def test_duplicate_independent_game_keys_are_quarantined():
    result = season([record(), record(source="different")],
                    [event(), event(eid="second-id")])
    assert result["approved_count"] == 0
    assert result["quarantined_count"] == 2
    assert all("AMBIGUOUS_EXTERNAL_IDENTITY" in q["reasons"]
               for q in result["quarantined_games"])


def test_unreviewed_or_derived_reference_cannot_approve():
    result = season([record(), record(source="different")], prov=provenance(False))
    assert result["approved_count"] == 0
    assert result["pending_games"][0]["reason"] == "REFERENCE_LINEAGE_UNVERIFIED"
    bad = provenance().model_copy(update={"derived_from": ["fixturedownload-private"]})
    result = season([record(), record(source="different")], prov=bad)
    assert result["approved_count"] == 0


def test_existing_reference_source_rejected():
    with pytest.raises(ValueError, match="Existing result"):
        provenance().model_copy(update={"provider_id": "fixturedownload-private"})
        ReferenceProvenance.model_validate({
            **provenance().model_dump(), "provider_id": "fixturedownload-private"
        })


def test_reference_checksum_and_local_date_basis(tmp_path):
    events = [event().model_dump(mode="json")]
    raw = json.dumps(events).encode()
    path = tmp_path / "independent.json"
    path.write_bytes(raw)
    receipt = provenance().model_copy(
        update={"source_sha256": hashlib.sha256(raw).hexdigest()}
    )
    prov_path = tmp_path / "receipt.json"
    prov_path.write_text(receipt.model_dump_json())
    actual, _ = load_external_reference(path, prov_path)
    assert actual[0].game_key == "nba:2021-12-01:ATL:BOS"
    path.write_text("[]")
    with pytest.raises(ValueError, match="SHA-256"):
        load_external_reference(path, prov_path)


def test_outside_reference_is_not_auto_labeled_missing_or_regular():
    result = season([record(key_date="2021-12-02"),
                     record(key_date="2021-12-02", source="different")])
    assert result["approved_count"] == 0
    assert result["pending_games"][0]["reason"] == "RESULT_UNAVAILABLE"
    assert "nba:2021-12-02:ATL:BOS" in result["outside_regular_reference_keys"]


def test_private_immutable_reports_repeat_byte_identically(tmp_path):
    report = audit_regular_seasons([record(), record(source="different")],
                                   [event()], provenance(), contract())
    first = write_regular_season_audit(report, tmp_path)
    second = write_regular_season_audit(report, tmp_path)
    assert first == second
    assert first.read_bytes() == second.read_bytes()
    assert len(list(tmp_path.glob("*.approved.json"))) == 1
    assert json.loads(first.read_text())["seasons"][0]["approved_count"] == 1


def test_wrong_season_date_and_team_rejected():
    with pytest.raises(ValueError):
        ExternalEvent.model_validate({**event().model_dump(), "home": "XXX"})
    with pytest.raises(ValueError):
        ExternalEvent.model_validate({**event().model_dump(), "game_date": "2020-01-01"})
