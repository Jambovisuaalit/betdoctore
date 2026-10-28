"""Every metric, publisher and byte fixture here is explicitly synthetic."""
import hashlib
import math
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from betdoctore.advanced_staging import (
    AdvancedObservation,
    AdvancedSourceManifest,
    assess_for_cutoff,
    observation_digest,
    readiness_report,
    stage_batch,
)
from betdoctore.storage import AdvancedStageRow, Base, SourceRecord

RAW = b"explicitly synthetic advanced-metric source bytes for software tests only"
RECEIPT = datetime(2026, 10, 27, 6, tzinfo=UTC)
TIPOFF = RECEIPT+timedelta(hours=3)
CUTOFF = TIPOFF-timedelta(minutes=60)
KEY = "nba:2021-01-01:BKN:PHX"


def manifest(**updates):
    definitions = {}
    for metric in ("pace", "offensive_rating", "defensive_rating"):
        definitions[metric] = {"definition_version":"synthetic-fixture-v1",
            "units":"possessions_per_48_minutes" if metric == "pace" else "points_per_100_possessions",
            "possession_method":"explicit synthetic possession convention",
            "overtime_policy":"included_and_normalized", "aggregation":"per_game"}
    return AdvancedSourceManifest.model_validate({"source":"synthetic-test-only",
        "source_url":"https://example.invalid/synthetic", "source_version":"synthetic-fixture-v1", "normalization_version":"synthetic-normalization-v1",
        "snapshot_sha256":hashlib.sha256(RAW).hexdigest(), "retrieved_at":RECEIPT,
        "authorization_reference":"synthetic test authorization only", "authorized_for_research":True,
        "use_scope":"private_noncommercial", "definitions":definitions, "synthetic":True, **updates})


def observation(team="BKN", **updates):
    return AdvancedObservation.model_validate({"source_row_id":f"synthetic-{team}",
        "source_game_id":"synthetic-game-1", "source_team_id":f"synthetic-provider-{team}",
        "game_key":KEY, "team":team, "season_end_year":2021, "phase":"regular_season",
        "statistic_scope":"per_game", "effective_period_start":datetime(2021,1,1,20,tzinfo=UTC),
        "effective_period_end":datetime(2021,1,1,23,tzinfo=UTC),
        "provider_published_at":datetime(2021,1,2,tzinfo=UTC),
        "source_observed_at":datetime(2021,1,2,tzinfo=UTC), "received_at":RECEIPT,
        "revision":"synthetic-v1", "metrics":{"pace":100.,"offensive_rating":110.,"defensive_rating":108.},
        "synthetic":True, **updates})


def database():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return engine


def assess(record=None, source=None, **updates):
    return assess_for_cutoff(record or observation(), source or manifest(), CUTOFF,
        regular_scope_verified=True, real_evaluation=False, prediction_tipoff=TIPOFF,
        source_snapshot_verified=True, normalization_verified=True, **updates)


def test_historical_publication_claim_never_backdates_advanced_availability():
    record = observation(historical_timing_claim_reference="synthetic historical publication label")
    old_tipoff = datetime(2021,1,5,20,tzinfo=UTC)
    result = assess_for_cutoff(record,manifest(),old_tipoff-timedelta(minutes=60),
        prediction_tipoff=old_tipoff, regular_scope_verified=True, real_evaluation=False,
        source_snapshot_verified=True, normalization_verified=True)
    assert not result["eligible"]
    assert "HISTORICAL_ADVANCED_AVAILABILITY_NOT_VERIFIED" in result["reasons"]
    assert result["historical_claim_promoted"] is False
    assert record.received_at == RECEIPT
    assert result["production_features_written"] is False


def test_prospective_subset_can_pass_review_without_any_playoff_dependency():
    result = assess()
    assert result["eligible"]
    assert not any("PLAYOFF" in reason for reason in result["reasons"])
    with pytest.raises(ValueError, match="60 minutes"):
        assess_for_cutoff(observation(),manifest(),CUTOFF+timedelta(seconds=1),prediction_tipoff=TIPOFF)


def test_real_evaluation_rejects_synthetic_and_scope_incompatible_sources():
    result = assess_for_cutoff(observation(),manifest(),CUTOFF,
        regular_scope_verified=True, real_evaluation=True, prediction_tipoff=TIPOFF,
        source_snapshot_verified=True, normalization_verified=True,
        evaluation_use_scope="commercial")
    assert "SYNTHETIC_DATA_EXCLUDED_FROM_REAL_EVALUATION" in result["reasons"]
    assert "SOURCE_USE_SCOPE_MISMATCH" in result["reasons"]
    assert not result["eligible"]


@pytest.mark.parametrize("change,reason", [
    ({"game_key":None},"UNMAPPED_GAME_OR_TEAM"),
    ({"game_key":"nba:2021-99-99:BKN:PHX"},"INVALID_CANONICAL_GAME_OR_TEAM"),
    ({"phase":"playoffs"},"OUTSIDE_V1_REGULAR_SEASON_SCOPE"),
    ({"phase":"cup_final"},"OUTSIDE_V1_REGULAR_SEASON_SCOPE"),
    ({"effective_period_end":None},"EFFECTIVE_PERIOD_UNVERIFIED"),
    ({"metrics":{"pace":100}},"INCOMPLETE_METRIC_BUNDLE"),
    ({"effective_period_end":CUTOFF+timedelta(minutes=1),"received_at":CUTOFF+timedelta(minutes=2), "provider_published_at":CUTOFF+timedelta(minutes=1)},"FUTURE_EFFECTIVE_PERIOD"),
])
def test_unverified_or_future_rows_cannot_pass(change, reason):
    assert reason in assess(observation(**change))["reasons"]


def test_unknown_metric_units_and_overtime_are_blocked():
    payload = manifest().model_dump(mode="json")
    payload["definitions"]["pace"]["units"] = "unknown"
    payload["definitions"]["offensive_rating"]["overtime_policy"] = "unknown"
    result = assess(source=AdvancedSourceManifest.model_validate(payload))
    assert "UNVERIFIED_UNITS:pace" in result["reasons"]
    assert "OVERTIME_POLICY_UNVERIFIED:offensive_rating" in result["reasons"]


def test_staging_is_idempotent_isolated_and_invalid_rows_are_retained():
    engine = database()
    rows = [observation().model_dump(mode="json"),
            {**observation("PHX").model_dump(mode="json"), "metrics":{"pace":math.nan}}]
    with Session(engine) as session:
        result = stage_batch(session,manifest(),rows,RAW)
        assert (result["staged"],result["quarantined"],result["promoted"]) == (1,1,0)
        assert stage_batch(session,manifest(),rows,RAW)["duplicates"] == 2
        assert session.scalar(select(func.count()).select_from(SourceRecord)) == 0
        staged = session.scalars(select(AdvancedStageRow).order_by(AdvancedStageRow.source_row_id)).all()
        assert staged[1].payload["metrics"]["pace"] == {"invalid_nonfinite_float":"nan"}
        assert staged[1].status == "QUARANTINED"
        conflict = {**rows[0],"metrics":{"pace":99,"offensive_rating":110,"defensive_rating":108}}
        with pytest.raises(ValueError,match="Immutable advanced row"):
            stage_batch(session,manifest(),[conflict],RAW)


def test_snapshot_bytes_and_normalization_must_be_verified_separately():
    engine = database()
    with Session(engine) as session:
        with pytest.raises(ValueError,match="checksum"):
            stage_batch(session,manifest(),[observation().model_dump(mode="json")],b"different bytes")
        report = stage_batch(session,manifest(),[observation().model_dump(mode="json")])
        assert report["quarantined"] == 1
        assert "SOURCE_SNAPSHOT_BYTES_NOT_VERIFIED" in report["rows"][0]["reasons"]
    result = assess_for_cutoff(observation(),manifest(),CUTOFF,prediction_tipoff=TIPOFF,
                              regular_scope_verified=True,real_evaluation=False)
    assert "SOURCE_ROW_NORMALIZATION_NOT_VERIFIED" in result["reasons"]
    assert "SOURCE_SNAPSHOT_BYTES_NOT_VERIFIED" in result["reasons"]


def test_readiness_requires_both_teams_and_explicit_curated_regular_subset():
    engine = database()
    with Session(engine) as session:
        first = stage_batch(session,manifest(),[observation().model_dump(mode="json")],RAW)
        report = readiness_report(session,first["batch_digest"],CUTOFF,{KEY},TIPOFF,
                                  real_evaluation=False,normalization_verified=True)
        assert report["status"] == "BLOCKED"
        assert "INCOMPLETE_OR_DUPLICATED_GAME_TEAM_PAIR" in report["rows"][0]["reasons"]
        stage_batch(session,manifest(),[observation("PHX").model_dump(mode="json")],RAW)
        report = readiness_report(session,first["batch_digest"],CUTOFF,{KEY},TIPOFF,
                                  real_evaluation=False,normalization_verified=True)
        assert report["status"] == "READY_FOR_EXPLICIT_CURATED_REVIEW"
        assert report["eligible_rows"] == 2
        assert report["auto_promotion"] is False
        assert report["missing_playoffs_blocks_v1"] is False
        report = readiness_report(session,first["batch_digest"],CUTOFF,set(),TIPOFF,
                                  real_evaluation=False,normalization_verified=True)
        assert report["status"] == "BLOCKED"


def test_revision_requires_known_same_identity_and_never_silently_replaces():
    engine = database()
    original = observation()
    with Session(engine) as session:
        stage_batch(session,manifest(),[original.model_dump(mode="json")],RAW)
        revision = observation(source_row_id="synthetic-v2",revision="synthetic-v2",
                               supersedes_content_digest=observation_digest(original),
                               metrics={"pace":101,"offensive_rating":111,"defensive_rating":109})
        assert stage_batch(session,manifest(),[revision.model_dump(mode="json")],RAW)["staged"] == 1
        assert session.scalar(select(func.count()).select_from(AdvancedStageRow)) == 2
        report = readiness_report(session,manifest_batch_digest(session),CUTOFF,{KEY},TIPOFF,
                                  real_evaluation=False,normalization_verified=True)
        assert report["status"] == "BLOCKED"
        unknown = observation(source_row_id="synthetic-unknown",supersedes_content_digest="b"*64)
        assert "UNKNOWN_SUPERSEDED_VERSION" in stage_batch(session,manifest(),[unknown.model_dump(mode="json")],RAW)["rows"][0]["reasons"]


def manifest_batch_digest(session):
    from betdoctore.storage import AdvancedStageBatch
    return session.scalars(select(AdvancedStageBatch.digest)).first()


def test_unselected_playoff_staging_rows_do_not_block_curated_regular_subset():
    engine = database()
    regular = [observation().model_dump(mode="json"),observation("PHX").model_dump(mode="json")]
    playoff = observation(team="BOS",source_row_id="synthetic-playoff",
                          game_key="nba:2021-01-03:BOS:CHI",phase="playoffs").model_dump(mode="json")
    with Session(engine) as session:
        batch = stage_batch(session,manifest(),[*regular,playoff],RAW)
        assert batch["quarantined"] == 1
        report = readiness_report(session,batch["batch_digest"],CUTOFF,{KEY},TIPOFF,
                                  real_evaluation=False,normalization_verified=True)
        assert report["status"] == "READY_FOR_EXPLICIT_CURATED_REVIEW"
        assert report["eligible_rows"] == 2
        assert len(report["excluded_staging_rows"]) == 1
        assert report["missing_playoffs_blocks_v1"] is False
        missing = readiness_report(session,batch["batch_digest"],CUTOFF,{KEY,"nba:2021-01-04:ATL:BOS"},TIPOFF,
                                   real_evaluation=False,normalization_verified=True)
        assert missing["status"] == "BLOCKED"
        assert missing["missing_curated_game_keys"] == ["nba:2021-01-04:ATL:BOS"]
