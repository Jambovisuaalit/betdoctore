"""Independent NBA regular-season identity matching; never unlocks training."""
import json
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .result_reconciliation import reconcile
from .result_sources import sha256, write_once
from .results import BasicResult, TEAMS
from .season_audit import load_contract, load_full_sources

EXISTING_LINEAGE = frozenset({
    "fixturedownload-private", "neil-paine-nba-elo", "fivethirtyeight",
})


class ExternalEvent(BaseModel):
    """One event identified by a reviewed, external event-ID source."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    provider_event_id: str = Field(min_length=1)
    season_end_year: int = Field(ge=2021, le=2026)
    game_date: date  # America/New_York local calendar date, not guessed UTC.
    home: str
    away: str
    phase: Literal["regular_season", "play_in", "playoffs", "cup_final"]
    date_basis: Literal["america_new_york"] = "america_new_york"

    @model_validator(mode="after")
    def identity(self):
        if self.home not in TEAMS or self.away not in TEAMS or self.home == self.away:
            raise ValueError("Invalid canonical home/away teams")
        if not date(self.season_end_year - 1, 10, 1) <= self.game_date <= date(
            self.season_end_year, 8, 31
        ):
            raise ValueError("Game date outside season boundary")
        return self

    @property
    def game_key(self) -> str:
        a, b = sorted((self.home, self.away))
        return f"nba:{self.game_date}:{a}:{b}"


class ReferenceProvenance(BaseModel):
    """Manual licensing/lineage review is evidence, not cryptographic independence."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    provider_id: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    terms_url: str = Field(min_length=1)
    license_scope: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    lineage_reviewed: bool = False
    reviewed_by: str | None = None
    review_evidence: str | None = None
    derived_from: list[str] = Field(default_factory=list)
    acquired_at: datetime

    @model_validator(mode="after")
    def check_provenance(self):
        if self.acquired_at.utcoffset() is None:
            raise ValueError("Acquisition timestamp must be timezone aware")
        if self.provider_id.lower() in EXISTING_LINEAGE:
            raise ValueError("Existing result/fixture source cannot be independent manifest")
        if self.lineage_reviewed and not (self.reviewed_by and self.review_evidence):
            raise ValueError("Reviewed lineage requires reviewer and evidence")
        return self

    @property
    def review_eligible(self) -> bool:
        return (self.lineage_reviewed
                and not (set(s.lower() for s in self.derived_from) & EXISTING_LINEAGE))


def load_external_reference(events_path: Path, provenance_path: Path):
    """Read *local* exports and verify original bytes against a separate receipt."""
    raw = events_path.read_bytes()
    provenance = ReferenceProvenance.model_validate_json(provenance_path.read_text())
    if sha256(raw) != provenance.source_sha256:
        raise ValueError("Independent reference export SHA-256 does not match receipt")
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("Reference export must contain a JSON list of events")
    events = [ExternalEvent.model_validate(row) for row in payload]
    return events, provenance


def audit_regular_seasons(
    records: list[BasicResult], events: list[ExternalEvent],
    provenance: ReferenceProvenance, contract: dict,
) -> dict:
    """Produce per-season approved, pending and quarantined records.

    Approval here covers matching *identities and final scores only*.
    It never proves availability of historical efficiency stats or T-60 eligibility.
    """
    records = [r for r in records if 2021 <= r.season_end_year <= 2026]
    rec = reconcile(records, date(2020, 12, 1), date(2026, 8, 31))
    accepted_results = {r["game_key"]: r for r in rec["accepted"]}
    conflict_results = {r["game_key"]: r for r in rec["quarantine"]}
    per_year = defaultdict(list)
    refs_by_key = defaultdict(list)
    ids = defaultdict(set)
    for event in events:
        if event.provider_event_id in ids[event.season_end_year]:
            # Fail closed on duplicate external event IDs.
            raise ValueError(f"Duplicate external event ID in season {event.season_end_year}")
        ids[event.season_end_year].add(event.provider_event_id)
        per_year[event.season_end_year].append(event)
        refs_by_key[event.game_key].append(event)

    observed_by_season = defaultdict(set)
    for record in records:
        observed_by_season[record.season_end_year].add(record.game_key)

    seasons = []
    for spec in contract["seasons"]:
        year = spec["season_end_year"]
        expected = spec["regular_expected_games"]
        per_team_expected = spec["regular_games_per_team"]
        refs = [r for r in per_year[year] if r.phase == "regular_season"]
        team_counts = Counter(team for e in refs for team in (e.home, e.away))
        complete_reference = (
            len(refs) == expected and set(team_counts) == TEAMS
            and all(v == per_team_expected for v in team_counts.values())
            and provenance.review_eligible
        )
        approved, pending, quarantine = [], [], []
        ref_keys = {e.game_key for e in refs}
        for event in sorted(refs, key=lambda e: (e.game_date, e.provider_event_id)):
            key = event.game_key
            basic = {"game_key": key, "provider_event_id": event.provider_event_id,
                     "home": event.home, "away": event.away,
                     "season_end_year": year}
            reasons = []
            if len(refs_by_key[key]) > 1:
                reasons.append("AMBIGUOUS_EXTERNAL_IDENTITY")
            if key in conflict_results:
                reasons.extend(conflict_results[key]["reasons"])
            matched = accepted_results.get(key)
            observations = matched["observations"] if matched else []
            if any(o["season_end_year"] != year for o in observations):
                reasons.append("SEASON_MISMATCH")
            if any(o["designated_home"] not in (None, event.home) for o in observations):
                reasons.append("HOME_DESIGNATION_MISMATCH")
            if reasons:
                quarantine.append({**basic, "reasons": sorted(set(reasons)),
                                   "observations": observations or
                                   conflict_results.get(key, {}).get("observations", [])})
                continue
            if not matched:
                pending.append({**basic, "reason": "RESULT_UNAVAILABLE"})
                continue
            if matched["status"] != "CROSS_SOURCE_CORROBORATED":
                pending.append({**basic, "reason": "SINGLE_SOURCE_RESULT"})
                continue
            if not provenance.review_eligible:
                pending.append({**basic, "reason": "REFERENCE_LINEAGE_UNVERIFIED"})
                continue
            observation = observations[0]
            approved.append({**basic, "game_date": str(event.game_date),
                             "points_a": observation["points_a"],
                             "points_b": observation["points_b"],
                             "team_a": observation["team_a"], "team_b": observation["team_b"],
                             "result_sources": sorted({o["source"] for o in observations}),
                             "source_snapshot_sha256": sorted({
                                 o["source_snapshot_sha256"] for o in observations}),
                             "approval": "IDENTITY_AND_RESULT_ONLY",
                             "upstream_score_independence_verified": False,
                             "training_eligible": False})

        # Preserve score conflicts even when external reference does not list the key.
        for key, conflict in sorted(conflict_results.items()):
            if any(o["season_end_year"] == year for o in conflict["observations"]) and key not in ref_keys:
                quarantine.append({"game_key": key, "reasons": [
                    "UNMAPPED_QUARANTINED_RESULT", *conflict["reasons"]],
                    "observations": conflict["observations"]})

        outside_reference = sorted(observed_by_season[year] - ref_keys)
        manifest_missing = max(0, expected - len(refs))
        reasons = []
        if not provenance.review_eligible:
            reasons.append("INDEPENDENT_LINEAGE_NOT_REVIEWED")
        if not complete_reference:
            reasons.append("REFERENCE_MANIFEST_INCOMPLETE_OR_UNBALANCED")
        if pending or quarantine:
            reasons.append("UNRESOLVED_RESULTS_OR_CONFLICTS")
        seasons.append({
            "season_end_year": year,
            "season": f"{year-1}-{str(year)[-2:]}",
            "regular_expected": expected,
            "reference_regular_ids": len(refs),
            "reference_missing_count": manifest_missing,
            "reference_team_balance_ok": len(refs) == expected and
                set(team_counts) == TEAMS and all(v == per_team_expected for v in team_counts.values()),
            "approved_count": len(approved),
            "pending_count": len(pending),
            "quarantined_count": len(quarantine),
            "outside_regular_reference_count": len(outside_reference),
            "outside_regular_reference_keys": outside_reference,
            "status": "IDENTITY_RESULT_LIST_COMPLETE" if not reasons else "BLOCKED",
            "blocking_reasons": reasons,
            "approved_games": approved,
            "pending_games": pending,
            "quarantined_games": quarantine,
        })

    return {
        "schema_version": 1,
        "scope": "2020-21 through 2025-26 NBA regular season",
        "reference_provider": provenance.provider_id,
        "reference_source_sha256": provenance.source_sha256,
        "reference_acquired_at": provenance.acquired_at.isoformat(),
        "reference_review": "OPERATOR_REVIEWED_NOT_MACHINE_PROVEN" if provenance.review_eligible
            else "UNVERIFIED",
        "scores_are_not_training_features": True,
        "historical_t60_eligibility_verified": False,
        "advanced_stats_unlocked": False,
        "training_eligible": False,
        "license_scope": provenance.license_scope,
        "redistribution_allowed": False,
        "reconciliation": {k: v for k, v in rec.items()
                           if k not in ("accepted", "quarantine", "possible_date_conflicts")},
        "seasons": seasons,
    }


def write_regular_season_audit(report: dict, output: Path) -> Path:
    """Deterministic, private, immutable artifacts. No repo/public API export."""
    raw = json.dumps(report, sort_keys=True, indent=2).encode()
    identity = sha256(raw)
    summary = {k: v for k, v in report.items() if k != "seasons"}
    summary["report_sha256"] = identity
    summary["seasons"] = []
    for season in report["seasons"]:
        year = season["season_end_year"]
        prefix = f"{year-1}-{str(year)[-2:]}-{identity}"
        for field, suffix in (
            ("approved_games", "approved"),
            ("pending_games", "pending"),
            ("quarantined_games", "quarantine"),
        ):
            blob = json.dumps(season[field], sort_keys=True, indent=2).encode()
            write_once(output / f"{prefix}.{suffix}.json", blob)
        summary["seasons"].append({k: v for k, v in season.items() if k not in (
            "approved_games", "pending_games", "quarantined_games",
            "outside_regular_reference_keys",
        )})
    write_once(output / f"{identity}.regular-season-audit.json", raw)
    write_once(output / f"{identity}.summary.json",
               json.dumps(summary, sort_keys=True, indent=2).encode())
    return output / f"{identity}.summary.json"


def run_regular_season_audit(
    root: Path, reference_file: Path, provenance_file: Path, output: Path,
    as_of: date,
) -> Path:
    events, provenance = load_external_reference(reference_file, provenance_file)
    records, _, _ = load_full_sources(root, as_of)
    report = audit_regular_seasons(records, events, provenance, load_contract())
    return write_regular_season_audit(report, output)
