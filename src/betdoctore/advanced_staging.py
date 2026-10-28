"""Immutable, isolated staging for advanced metrics; never a feature-store shortcut.

Historical timing claims are retained as claims. This module has no historical
advanced-data verifier and therefore never backdates eligibility from publication
labels, Git dates, or score-only archive captures.
"""
import hashlib
import json
import math
from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .engine import digest
from .results import TEAMS
from .storage import AdvancedStageBatch, AdvancedStageRow

Metric = Literal["pace", "offensive_rating", "defensive_rating"]
REQUIRED_METRICS = frozenset(["pace", "offensive_rating", "defensive_rating"])


class StagingContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    @model_validator(mode="after")
    def aware_timestamps(self):
        for value in self.__dict__.values():
            if isinstance(value, datetime) and value.utcoffset() is None:
                raise ValueError("Timezone-aware staging timestamps required")
        return self


class MetricDefinition(StagingContract):
    definition_version: str = Field(min_length=1)
    units: Literal["possessions_per_48_minutes", "points_per_100_possessions", "unknown"]
    possession_method: str = Field(min_length=1)
    overtime_policy: Literal["included_and_normalized", "regulation_only", "unknown"]
    aggregation: Literal["per_game", "rolling", "season_to_date", "unknown"]


class AdvancedSourceManifest(StagingContract):
    source: str = Field(min_length=1)
    source_url: str = Field(pattern=r"^https://")
    source_version: str = Field(min_length=1)
    normalization_version: str = Field(default="unreviewed", min_length=1)
    selection_manifest_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    snapshot_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    retrieved_at: datetime
    authorization_reference: str = Field(min_length=1)
    authorized_for_research: bool = False
    use_scope: Literal["private_noncommercial", "redistributable"]
    definitions: dict[Metric, MetricDefinition] = Field(default_factory=dict)
    synthetic: bool = False


class AdvancedObservation(StagingContract):
    source_row_id: str = Field(min_length=1)
    source_game_id: str = Field(min_length=1)
    source_team_id: str = Field(min_length=1)
    game_key: str | None = None
    team: str | None = None
    season_end_year: int = Field(ge=2020, le=2027)
    phase: Literal["regular_season", "playoffs", "play_in", "cup_final", "unknown"] = "unknown"
    statistic_scope: Literal["per_game", "rolling", "season_to_date", "unknown"] = "unknown"
    effective_period_start: datetime | None = None
    effective_period_end: datetime | None = None
    provider_published_at: datetime | None = None
    source_observed_at: datetime | None = None
    received_at: datetime
    revision: str = Field(min_length=1)
    supersedes_content_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    metrics: dict[Metric, float] = Field(default_factory=dict)
    historical_timing_claim_reference: str | None = None
    synthetic: bool = False

    @model_validator(mode="after")
    def chronological_and_numeric_validity(self):
        if (self.effective_period_start and self.effective_period_end
                and self.effective_period_start >= self.effective_period_end):
            raise ValueError("Metric effective period must have positive duration")
        if self.provider_published_at and self.provider_published_at > self.received_at:
            raise ValueError("Publication cannot follow receipt")
        if (self.statistic_scope == "per_game" and self.effective_period_end
                and self.provider_published_at and self.provider_published_at < self.effective_period_end):
            raise ValueError("Final per-game metric publication precedes effective-period completion")
        if self.source_observed_at and self.source_observed_at > self.received_at:
            raise ValueError("Observation cannot follow receipt")
        for metric, value in self.metrics.items():
            if not 0 < value <= (300 if metric == "pace" else 400):
                raise ValueError(f"Invalid {metric} value; retain raw row for review")
        return self


def observation_digest(record: AdvancedObservation) -> str:
    """Exact staged content version, including revision and availability provenance."""
    return digest(record.model_dump(mode="json"))


def staging_reasons(record: AdvancedObservation, manifest: AdvancedSourceManifest) -> list[str]:
    reasons = []
    if manifest.normalization_version.strip().lower() in {"unknown", "unreviewed"}:
        reasons.append("NORMALIZATION_VERSION_UNREVIEWED")
    if not manifest.authorized_for_research:
        reasons.append("SOURCE_RESEARCH_AUTHORIZATION_UNVERIFIED")
    if record.synthetic != manifest.synthetic:
        reasons.append("SYNTHETIC_PROVENANCE_MISMATCH")
    if record.received_at < manifest.retrieved_at:
        reasons.append("ROW_RECEIPT_PREDATES_SOURCE_ACQUISITION")
    if record.game_key is None or record.team is None:
        reasons.append("UNMAPPED_GAME_OR_TEAM")
    else:
        parts = record.game_key.split(":")
        try:
            day = date.fromisoformat(parts[1])
            date_valid = day.year in {record.season_end_year-1, record.season_end_year}
        except (ValueError, IndexError):
            date_valid = False
        if (not date_valid or len(parts) != 4 or parts[0] != "nba" or record.team not in TEAMS
                or record.team not in parts[2:] or any(team not in TEAMS for team in parts[2:])
                or parts[2] >= parts[3]):
            reasons.append("INVALID_CANONICAL_GAME_OR_TEAM")
    if record.phase != "regular_season":
        reasons.append("OUTSIDE_V1_REGULAR_SEASON_SCOPE")
    if record.statistic_scope != "per_game":
        reasons.append("UNSUPPORTED_AGGREGATION_FOR_V1")
    if record.effective_period_start is None or record.effective_period_end is None:
        reasons.append("EFFECTIVE_PERIOD_UNVERIFIED")
    elif record.effective_period_end > record.received_at:
        reasons.append("METRIC_PERIOD_ENDS_AFTER_RECEIPT")
    if set(record.metrics) != REQUIRED_METRICS:
        reasons.append("INCOMPLETE_METRIC_BUNDLE")
    for metric in sorted(record.metrics):
        definition = manifest.definitions.get(metric)
        if definition is None:
            reasons.append(f"MISSING_DEFINITION:{metric}")
            continue
        expected_units = "possessions_per_48_minutes" if metric == "pace" else "points_per_100_possessions"
        if definition.units != expected_units:
            reasons.append(f"UNVERIFIED_UNITS:{metric}")
        if definition.possession_method.strip().lower() in {"unknown", "unverified", "n/a"}:
            reasons.append(f"POSSESSION_CONVENTION_UNVERIFIED:{metric}")
        if definition.aggregation != record.statistic_scope:
            reasons.append(f"AGGREGATION_MISMATCH:{metric}")
        if definition.overtime_policy == "unknown":
            reasons.append(f"OVERTIME_POLICY_UNVERIFIED:{metric}")
    if len({d.overtime_policy for d in manifest.definitions.values()}) > 1:
        reasons.append("INCONSISTENT_OVERTIME_CONVENTIONS")
    return reasons


def assess_for_cutoff(record: AdvancedObservation, manifest: AdvancedSourceManifest,
                      cutoff: datetime, regular_scope_verified: bool = False,
                      real_evaluation: bool = True,
                      prediction_tipoff: datetime | None = None,
                      evaluation_use_scope: str = "private_noncommercial",
                      source_snapshot_verified: bool = False,
                      normalization_verified: bool = False) -> dict:
    if cutoff.utcoffset() is None:
        raise ValueError("Aware prediction cutoff required")
    if prediction_tipoff is not None and (prediction_tipoff.utcoffset() is None
            or cutoff != prediction_tipoff-timedelta(minutes=60)):
        raise ValueError("Prediction cutoff must equal verified tipoff minus 60 minutes")
    reasons = staging_reasons(record, manifest)
    if not source_snapshot_verified:
        reasons.append("SOURCE_SNAPSHOT_BYTES_NOT_VERIFIED")
    if not normalization_verified:
        reasons.append("SOURCE_ROW_NORMALIZATION_NOT_VERIFIED")
    if not regular_scope_verified:
        reasons.append("REGULAR_SEASON_CURATED_IDENTITY_NOT_VERIFIED")
    if prediction_tipoff is None:
        reasons.append("PREDICTION_TIPOFF_UNVERIFIED")
    if real_evaluation and (record.synthetic or manifest.synthetic):
        reasons.append("SYNTHETIC_DATA_EXCLUDED_FROM_REAL_EVALUATION")
    if manifest.use_scope == "private_noncommercial" and evaluation_use_scope != "private_noncommercial":
        reasons.append("SOURCE_USE_SCOPE_MISMATCH")
    if max(record.received_at, manifest.retrieved_at) > cutoff:
        reasons.append("HISTORICAL_ADVANCED_AVAILABILITY_NOT_VERIFIED")
    if record.effective_period_end and record.effective_period_end > cutoff:
        reasons.append("FUTURE_EFFECTIVE_PERIOD")
    if record.provider_published_at and record.provider_published_at > cutoff:
        reasons.append("FUTURE_PROVIDER_PUBLICATION")
    if record.source_observed_at and record.source_observed_at > cutoff:
        reasons.append("FUTURE_SOURCE_OBSERVATION")
    return {"eligible": not reasons, "reasons": sorted(set(reasons)),
            "content_digest": observation_digest(record), "source_snapshot_sha256": manifest.snapshot_sha256,
            "cutoff": cutoff.isoformat(), "available_at_used": max(record.received_at, manifest.retrieved_at).isoformat(),
            "historical_claim_promoted": False, "production_features_written": False}


def _json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return {"invalid_nonfinite_float": str(value)}
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k,v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def stage_batch(session: Session, manifest: AdvancedSourceManifest, rows: list[dict],
                source_bytes: bytes | None = None) -> dict:
    if source_bytes is not None and hashlib.sha256(source_bytes).hexdigest() != manifest.snapshot_sha256:
        raise ValueError("Advanced source snapshot bytes do not match manifest checksum")
    manifest_payload = {**manifest.model_dump(mode="json"),
                        "_staging_source_bytes_verified": source_bytes is not None}
    batch_digest = digest(manifest_payload)
    existing = session.get(AdvancedStageBatch, batch_digest)
    if existing is None:
        session.add(AdvancedStageBatch(digest=batch_digest, source=manifest.source,
                                      snapshot_sha256=manifest.snapshot_sha256,
                                      retrieved_at=manifest.retrieved_at, manifest=manifest_payload))
        session.flush()
    elif existing.manifest != manifest_payload:
        raise ValueError("Immutable advanced batch manifest conflict")
    report = {"batch_digest": batch_digest, "staged": 0, "quarantined": 0, "duplicates": 0,
              "promoted": 0, "rows": [], "production_features_written": False, "source_bytes_verified": source_bytes is not None}
    seen = set()
    for index, raw in enumerate(rows, start=1):
        safe_raw = _json_safe(raw)
        # JSON check prevents implicit coercion of arbitrary non-serializable Python objects.
        json.dumps(safe_raw, allow_nan=False)
        raw_id = raw.get("source_row_id") if isinstance(raw, dict) else None
        row_id = raw_id if isinstance(raw_id, str) and raw_id.strip() else f"invalid-row-{index}"
        if not isinstance(safe_raw, dict):
            safe_raw = {"invalid_raw_row": safe_raw}
        if row_id in seen:
            raise ValueError("Duplicate source row identity within advanced batch")
        seen.add(row_id)
        payload, content_id = safe_raw, digest(safe_raw)
        try:
            record = AdvancedObservation.model_validate(raw)
            reasons = staging_reasons(record, manifest)
            if source_bytes is None:
                reasons.append("SOURCE_SNAPSHOT_BYTES_NOT_VERIFIED")
            if record.supersedes_content_digest:
                previous = session.scalar(select(AdvancedStageRow).where(
                    AdvancedStageRow.content_digest == record.supersedes_content_digest))
                previous_batch = session.get(AdvancedStageBatch, previous.batch_digest) if previous else None
                if previous is None:
                    reasons.append("UNKNOWN_SUPERSEDED_VERSION")
                elif (previous.payload.get("game_key") != record.game_key
                      or previous.payload.get("team") != record.team
                      or previous_batch is None or previous_batch.source != manifest.source):
                    reasons.append("SUPERSEDED_VERSION_IDENTITY_MISMATCH")
            payload = record.model_dump(mode="json")
            content_id = observation_digest(record)
        except ValidationError as exc:
            reasons = ["INVALID_OBSERVATION_CONTRACT", str(exc)]
        row = session.scalar(select(AdvancedStageRow).where(
            AdvancedStageRow.batch_digest == batch_digest, AdvancedStageRow.source_row_id == row_id))
        if row is not None:
            if row.content_digest != content_id or row.payload != payload:
                raise ValueError("Immutable advanced row identity conflict; create an explicit source revision")
            report["duplicates"] += 1
            continue
        status = "QUARANTINED" if reasons else "STAGED_NOT_PROMOTED"
        session.add(AdvancedStageRow(digest=digest({"batch":batch_digest,"row":row_id,"content":content_id}),
                                    batch_digest=batch_digest, source_row_id=row_id,
                                    content_digest=content_id, status=status,
                                    payload=payload, validation_reasons=reasons))
        report["quarantined" if reasons else "staged"] += 1
        report["rows"].append({"source_row_id":row_id,"status":status,"reasons":reasons})
    session.flush()
    return report


def readiness_report(session: Session, batch_digest: str, cutoff: datetime,
                     regular_game_keys: set[str], prediction_tipoff: datetime | None = None,
                     real_evaluation: bool = True, normalization_verified: bool = False,
                     evaluation_use_scope: str = "private_noncommercial") -> dict:
    batch = session.get(AdvancedStageBatch, batch_digest)
    if batch is None:
        raise ValueError("Unknown advanced staging batch")
    manifest_payload = dict(batch.manifest)
    source_verified = manifest_payload.pop("_staging_source_bytes_verified", False)
    manifest = AdvancedSourceManifest.model_validate(manifest_payload)
    rows = session.scalars(select(AdvancedStageRow).where(
        AdvancedStageRow.batch_digest == batch_digest).order_by(AdvancedStageRow.source_row_id)).all()
    assessments, by_game, excluded = [], {}, []
    for row in rows:
        try:
            record = AdvancedObservation.model_validate(row.payload)
            if record.game_key not in regular_game_keys:
                excluded.append({"source_row_id":row.source_row_id,
                                 "reason":"OUTSIDE_SELECTED_REGULAR_SUBSET"})
                continue
            assessment = assess_for_cutoff(record, manifest, cutoff,
                regular_scope_verified=record.game_key in regular_game_keys,
                real_evaluation=real_evaluation, prediction_tipoff=prediction_tipoff,
                evaluation_use_scope=evaluation_use_scope, source_snapshot_verified=source_verified,
                normalization_verified=normalization_verified)
            assessment["source_row_id"] = row.source_row_id
            by_game.setdefault(record.game_key, []).append((record.team, assessment))
        except ValidationError:
            if not isinstance(row.payload, dict) or row.payload.get("game_key") not in regular_game_keys:
                excluded.append({"source_row_id":row.source_row_id,
                                 "reason":"INVALID_UNSELECTED_STAGING_ROW"})
                continue
            assessment = {"source_row_id":row.source_row_id, "eligible":False,
                          "reasons":["INVALID_OBSERVATION_CONTRACT"]}
        assessments.append(assessment)
    for key, observations in by_game.items():
        expected = set(key.split(":")[2:]) if key else set()
        teams = [team for team,_ in observations]
        if len(teams) != 2 or set(teams) != expected:
            for _, assessment in observations:
                assessment["eligible"] = False
                assessment["reasons"] = sorted(set(assessment["reasons"]+
                    ["INCOMPLETE_OR_DUPLICATED_GAME_TEAM_PAIR"]))
    missing_games = sorted(regular_game_keys-set(by_game))
    ready = bool(assessments) and not missing_games and all(row["eligible"] for row in assessments)
    return {"batch_digest":batch_digest, "status":"READY_FOR_EXPLICIT_CURATED_REVIEW" if ready else "BLOCKED",
            "rows":assessments, "eligible_rows":sum(row["eligible"] for row in assessments),
            "excluded_staging_rows":excluded, "missing_curated_game_keys":missing_games,
            "production_features_written":False, "auto_promotion":False,
            "missing_playoffs_blocks_v1":False}
