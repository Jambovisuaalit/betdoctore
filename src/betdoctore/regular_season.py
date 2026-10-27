"""Regular-season V1 curation; postseason backlog cannot block an eligible regular cohort.

Private source observations and reports stay local. No current observation or source
snapshot is overwritten by curation. Evidence-supported corrections remain proposals
until a traceable adjudication is accepted.
"""
import html
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from .historical_availability import score_identity
from .result_sources import sha256, write_once
from .results import TEAMS, BasicResult
from .season_audit import schedule_keys


def _reference(record: BasicResult) -> dict:
    return {"source": record.source, "snapshot_sha256": record.source_snapshot_sha256,
            "source_rows": record.source_row_numbers, "game_key": record.game_key}


def build_regular_manifest(records: list[BasicResult], schedules: dict, contract: dict,
                           as_of: date, earliest: dict | None = None) -> dict:
    """Select by explicit fixture identities, not the archive's broad non-playoff flag.

    A cohort evaluator may evaluate a clean subset. It must independently validate
    that subset's historical fixture and feature availability. Global playoff gaps
    and unrelated seasons are deliberately not V1 cohort blockers.
    """
    earliest = earliest or {}
    by_key = defaultdict(list)
    for record in records:
        if record.game_date <= as_of:
            by_key[record.game_key].append(record)
    cups = {x["game_key"] for x in contract["cup_finals"]}
    games, quality_queue, availability_queue, seasons = [], [], [], []
    postseason_queue, excluded_keys = [], set()
    for spec in contract["seasons"]:
        season = spec["season_end_year"]
        if season not in schedules:
            quality_queue.append({"season_end_year": season, "kind": "MISSING_REGULAR_CATALOG"})
            continue
        fixture, unscored, errors = schedule_keys(schedules[season], True, as_of)
        regular = fixture-cups
        observations = [r for r in records if r.season_end_year == season and r.game_date <= as_of]
        archive_keys = {r.game_key for r in observations if r.source == "neil-paine-nba-elo"}
        outside = [r for r in observations if r.game_key not in regular and r.game_key not in cups]
        # Detect opponent/date catalog disagreements even when total game counts balance.
        # No replacement is applied: each candidate retains exact source provenance.
        identity_issues = {}
        for key in sorted(regular-archive_keys):
            current = [r for r in by_key[key] if r.season_end_year == season]
            alternatives = [r for r in outside if r.source == "neil-paine-nba-elo"
                            and r.phase != "playoffs"
                            and any(r.game_date == x.game_date
                                    and {r.team_a,r.team_b} & {x.team_a,x.team_b}
                                    for x in current)]
            if alternatives:
                identity_issues[key] = alternatives
        team_counts = Counter(team for key in regular for team in key.split(":")[2:])
        catalog_valid = (len(regular) == spec["regular_expected_games"] and set(team_counts) == TEAMS
                         and all(n == spec["regular_games_per_team"] for n in team_counts.values())
                         and not errors)
        if not catalog_valid:
            quality_queue.append({"season_end_year": season, "kind": "REGULAR_CATALOG_VALIDATION",
                                  "errors": errors, "observed_catalog_count": len(regular),
                                  "expected_catalog_count": spec["regular_expected_games"]})
        season_games = []
        for key in sorted(regular):
            observed = [r for r in by_key[key] if r.season_end_year == season]
            score_pairs = {(r.points_a,r.points_b) for r in observed}
            home = {r.designated_home for r in observed if r.designated_home is not None}
            reasons = []
            if not observed:
                reasons.append("MISSING_RESULT")
            if len(score_pairs) > 1:
                reasons.append("SCORE_CONFLICT")
            if len(home) > 1:
                reasons.append("HOME_CONFLICT")
            if len({r.source for r in observed}) != len(observed):
                reasons.append("SOURCE_REVISIONS_REQUIRE_REVIEW")
            if key in identity_issues:
                reasons.append("OPPONENT_IDENTITY_CONFLICT")
            captured = [{"points_a":a,"points_b":b,"evidence":earliest[identity]}
                        for a,b in sorted(score_pairs)
                        if (identity:=score_identity(key,a,b)) in earliest]
            proof_candidate = captured[0] if len(captured) == 1 else None
            selected = next(iter(score_pairs)) if len(score_pairs) == 1 and not reasons else None
            scheduled = {r.scheduled_tipoff for r in observed if r.scheduled_tipoff is not None}
            entry = {"game_key":key,"season_end_year":season,"phase":"regular_season",
                     "phase_basis":"saved_fixture_identity_excluding_explicit_cup_final",
                     "status":"QUARANTINED" if reasons else "CONSISTENT",
                     "result_consistency_passed":not reasons,
                     "verification_status":"CONFLICT_REVIEW" if reasons else
                         "CROSS_PUBLISHER_CORROBORATED" if len({r.source for r in observed}) >= 2
                         else "SINGLE_SOURCE_UNVERIFIED",
                     "points_a":selected[0] if selected else None,
                     "points_b":selected[1] if selected else None,
                     "designated_home":next(iter(home)) if len(home)==1 else None,
                     "scheduled_tipoff":next(iter(scheduled)).isoformat() if len(scheduled)==1 else None,
                     "scheduled_tipoff_is_historically_verified":False,
                     "capture_evidence":captured,"reasons":reasons,
                     "observations":[r.model_dump(mode="json") for r in observed]}
            season_games.append(entry)
            games.append(entry)
            if reasons:
                queue = {"game_key":key,"season_end_year":season,"kind":"RESULT_OR_IDENTITY_REVIEW",
                         "reasons":reasons,"source_references":[_reference(r) for r in observed],
                         "capture_supported_score_candidate":proof_candidate,
                         "automatic_adjudication_applied":False}
                if key in identity_issues:
                    queue["replacement_identity_candidates"] = [
                        {"record":r.model_dump(mode="json"),"capture_evidence":earliest.get(
                            score_identity(r.game_key,r.points_a,r.points_b))}
                        for r in identity_issues[key]]
                quality_queue.append(queue)
            if not captured:
                availability_queue.append({"game_key":key,"season_end_year":season,
                                           "kind":"NO_MATCHING_HISTORICAL_SCORE_CAPTURE"})
        playoff_count = len({r.game_key for r in outside if r.phase == "playoffs"})
        postseason_queue.append({"season_end_year":season,"queue":"postseason_separate_from_v1",
                                 "playoff_expected":spec["playoff_expected_games"],
                                 "playoff_observed":playoff_count,
                                 "play_in_expected":spec["play_in_expected_games"],
                                 "exact_play_in_identity_verified":False,
                                 "blocks_regular_v1_cohort":False})
        excluded_keys.update(r.game_key for r in outside)
        seasons.append({"season_end_year":season,"expected_regular":spec["regular_expected_games"],
                        "catalog_keys":len(regular),"catalog_count_and_team_balance_valid":catalog_valid,
                        "consistent_result_keys":sum(r["result_consistency_passed"] for r in season_games),
                        "quarantined_keys":sum(not r["result_consistency_passed"] for r in season_games),
                        "cross_publisher_keys":sum(r["verification_status"]=="CROSS_PUBLISHER_CORROBORATED"
                                                    for r in season_games),
                        "fixture_unscored_keys":sorted(unscored & regular)})
    return {"schema_version":1,"as_of":str(as_of),"use_scope":"private_noncommercial",
            "scope":"NBA regular seasons ending 2021–2026","games":games,"seasons":seasons,
            "regular_catalog_games":len(games),
            "consistent_result_games":sum(g["result_consistency_passed"] for g in games),
            "quarantined_regular_games":sum(not g["result_consistency_passed"] for g in games),
            "consistent_game_keys":[g["game_key"] for g in games if g["result_consistency_passed"]],
            "excluded_cup_final_keys":sorted(cups),"excluded_non_regular_keys":sorted(excluded_keys),
            "work_queues":{"regular_data_quality":quality_queue,
                           "regular_historical_availability":availability_queue,
                           "playoffs":postseason_queue},
            "v1_cohort_policy":{"all_seasons_must_be_complete":False,
                                 "playoff_gaps_block_regular_cohort":False,
                                 "required_per_evaluated_target":["regular identity verified against historical fixture",
                                     "no unresolved result or identity conflicts","causal history available before cutoff",
                                     "frozen protocol and recorded cohort exclusions"],
                                 "advanced_staging_is_not_feature_approval":True},
            "source_observations_rewritten":False,"automatic_adjudication_applied":False,
            "production_ready":False}


def target_gate(manifest: dict, game_key: str) -> dict:
    """Cohort-scoped result gate; historical schedule/features remain separate checks."""
    entries = [g for g in manifest["games"] if g["game_key"] == game_key]
    if len(entries) != 1:
        return {"passed":False,"reasons":["TARGET_NOT_UNIQUELY_IN_REGULAR_SCOPE"]}
    row = entries[0]
    return {"passed":row["result_consistency_passed"],"reasons":row["reasons"],
            "verification_status":row["verification_status"],
            "historical_schedule_gate_passed":False,"historical_feature_gate_passed":False,
            "playoff_queue_checked":False}


def save_regular_manifest(manifest: dict, directory: Path) -> Path:
    raw = json.dumps(manifest,sort_keys=True,indent=2).encode()
    identity = sha256(raw)
    path = directory/f"{identity}.regular-manifest.json"
    write_once(path,raw)
    summary = {k:v for k,v in manifest.items() if k not in {"games","consistent_game_keys",
                                                          "excluded_non_regular_keys","work_queues"}}
    summary["queue_counts"] = {k:len(v) for k,v in manifest["work_queues"].items()}
    write_once(directory/f"{identity}.summary.json",json.dumps(summary,sort_keys=True,indent=2).encode())
    document = ('<!doctype html><html lang="fi"><meta charset="utf-8"><title>BetDoctore runkosarja V1</title>'
                '<h1>Runkosarja V1 — lähdeaineisto ja erilliset työjonot</h1>'
                '<p>Vain yksityiseen ei-kaupalliseen tutkimukseen. Playoff-puutteet eivät estä '
                'erikseen hyväksytyn runkosarjakohortin arviointia.</p><pre>'
                +html.escape(json.dumps(summary,indent=2))+'</pre><h2>Runkosarjan laatutyöjono</h2><pre>'
                +html.escape(json.dumps(manifest["work_queues"]["regular_data_quality"],indent=2))
                +'</pre></html>')
    write_once(directory/f"{identity}.html",document.encode())
    return path
