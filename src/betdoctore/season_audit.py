"""Season identity/count coverage and separate historical availability gates."""
import csv
import html
import json
from collections import Counter
from datetime import date, datetime
from importlib.resources import files
from pathlib import Path
from zoneinfo import ZoneInfo

from .historical_availability import audit_availability, capture_evidence, load_capture_index
from .private_results import NAMES, parse_private, verify_private
from .result_reconciliation import reconcile
from .result_sources import sha256, verify_bundle, write_once
from .results import TEAMS, BasicResult, parse_neil_paine


def load_contract() -> dict:
    return json.loads(files("betdoctore").joinpath("resources/season-contract.json").read_text())


def load_full_sources(root: Path, as_of: date):
    # Full 2020–21 season boundary is audited, without modifying the accepted Jan-2021 database scope.
    start = date(2020, 12, 1)
    archive = root/"neil-paine"
    manifest = verify_bundle(archive)
    records, report = parse_neil_paine(list(csv.DictReader((archive/"source.csv").read_text().splitlines())),
                                     manifest["sha256"], datetime.fromisoformat(manifest["retrieved_at"]),
                                     start, as_of)
    if report["errors"]:
        raise ValueError("Archive structural errors block season audit")
    schedules, manifests = {}, [manifest]
    for year in range(2020, 2027):
        directory = root/"private-fixturedownload"/str(year)
        m = verify_private(directory)
        raw = json.loads((directory/"source.json").read_text())
        normalized, parsed = parse_private(raw, m, start, as_of)
        if parsed["errors"]:
            raise ValueError(f"Private source season {year}: structural audit failed")
        records.extend(normalized)
        schedules[year+1] = {"rows": raw, "manifest": m}
        manifests.append(m)
    return records, schedules, manifests


def schedule_keys(schedule: dict, completed_season: bool, as_of: date):
    expected, unscored, errors = set(), set(), []
    receipt = datetime.fromisoformat(schedule["manifest"]["retrieved_at"])
    for row in schedule["rows"]:
        try:
            scheduled = datetime.fromisoformat(row["DateUtc"])
            if scheduled.utcoffset() is None:
                raise ValueError("Naive schedule timestamp")
            day = scheduled.astimezone(ZoneInfo("America/New_York")).date()
            if not completed_season and (day > as_of or scheduled > receipt):
                continue
            teams = sorted((NAMES[row["HomeTeam"]], NAMES[row["AwayTeam"]]))
            if teams[0] == teams[1]:
                raise ValueError("Identical fixture participants")
            key = f"nba:{day}:{teams[0]}:{teams[1]}"
            if key in expected:
                raise ValueError("Duplicate fixture identity")
            expected.add(key)
            if row["HomeTeamScore"] is None or row["AwayTeamScore"] is None:
                unscored.add(key)
        except (KeyError, ValueError) as exc:
            errors.append(str(exc))
    return expected, unscored, errors


def coverage_audit(records: list[BasicResult], schedules: dict, contract: dict, as_of: date) -> dict:
    rec = reconcile(records, date(2020, 12, 1), as_of)
    accepted = {r["game_key"] for r in rec["accepted"]}
    quarantined = {r["game_key"] for r in rec["quarantine"]}
    cups = {r["season_end_year"]: r["game_key"] for r in contract["cup_finals"]}
    seasons = []
    for spec in contract["seasons"]:
        year = spec["season_end_year"]
        observed = [r for r in records if r.season_end_year == year]
        identities = {r.game_key for r in observed}
        archive_identities = {r.game_key for r in observed if r.source == "neil-paine-nba-elo"}
        expected, unscored, errors = schedule_keys(schedules[year], True, as_of)
        cup_key = cups.get(year)
        regular = expected-{cup_key} if cup_key else expected
        per_team = Counter(team for key in regular for team in key.split(":")[2:])
        schedule_count_match = (len(regular) == spec["regular_expected_games"] and set(per_team) == TEAMS
                                and all(n == spec["regular_games_per_team"] for n in per_team.values())
                                and not errors)
        playoff_keys = {r.game_key for r in observed if r.phase == "playoffs"}
        pair_counts = Counter(tuple(k.split(":")[2:]) for k in playoff_keys)
        series = [{**s, "observed_games": pair_counts[(s["team_a"], s["team_b"])],
                   "match": pair_counts[(s["team_a"], s["team_b"])] == s["expected_games"]}
                  for s in spec["playoff_series"]]
        known_pairs = {(s["team_a"], s["team_b"]) for s in spec["playoff_series"]}
        unknown_playoff_pairs = sorted(set(pair_counts)-known_pairs)
        outside = identities-regular-playoff_keys-({cup_key} if cup_key else set())
        seasons.append({"season_end_year": year, "season": f"{year-1}–{str(year)[-2:]}",
                        "regular": {"expected": spec["regular_expected_games"],
                            "source_schedule_keys": len(regular), "schedule_count_and_team_balance_match": schedule_count_match,
                            "observed_keys": len(regular & identities), "usable_result_keys": len(regular & accepted),
                            "missing_result_keys": sorted(regular-identities),
                            "keys_also_in_archive_source": len(regular & archive_identities),
                            "keys_only_in_fixture_source": sorted(regular-archive_identities),
                            "quarantined_keys": sorted(regular & quarantined),
                            "unscored_in_fixture_source": sorted(unscored & regular),
                            "team_counts": dict(sorted(per_team.items())),
                            "coverage_status": "SOURCE_MANIFEST_MATCH" if schedule_count_match and regular <= identities
                            else "FAIL", "independent_full_event_manifest_verified": False},
                        "playoffs": {"expected": spec["playoff_expected_games"],
                            "observed": len(playoff_keys), "usable": len(playoff_keys & accepted),
                            "series": series, "unknown_pairs": unknown_playoff_pairs,
                            "series_count_status": "MATCH" if all(s["match"] for s in series)
                            and not unknown_playoff_pairs else "MISSING_OR_MISMATCH",
                            "exact_event_identity_manifest_verified": False},
                        "play_in": {"expected": spec["play_in_expected_games"],
                            "unclassified_non_regular_candidates": len(outside),
                            "candidate_keys": sorted(outside), "exact_phase_identity_verified": False},
                        "cup_final": {"expected": int(cup_key is not None), "game_key": cup_key,
                            "observed": int(cup_key in identities) if cup_key else 0,
                            "included_in_regular_counts": False},
                        "distinct_observed": len(identities), "quarantined": len(identities & quarantined),
                        "coverage_status": "BLOCKED_EXACT_MANIFEST_OR_PHASE_REVIEW",
                        "source_errors": errors})
    ongoing = None
    if 2027 in schedules:
        due, unscored, errors = schedule_keys(schedules[2027], False, as_of)
        ongoing_keys = {r.game_key for r in records if r.season_end_year == 2027}
        ongoing = {"season": "2026–27", "status": "IN_PROGRESS", "as_of": str(as_of),
                   "past_scheduled_keys_in_source": len(due), "observed_results": len(ongoing_keys),
                   "past_scheduled_unscored_keys": sorted(unscored),
                   "missing_due_result_keys": sorted(due-ongoing_keys), "source_errors": errors,
                   "complete_82_game_season_claimed": False}
    return {"schema_version": 1, "as_of": str(as_of), "season_end_years": [2021,2022,2023,2024,2025,2026],
            "technical_result_foundation": "ACCEPTED_BY_USER_2026-10-27",
            "original_database_scope_start": "2021-01-01", "audit_source_scope_start": "2020-12-01",
            "boundary_2020_game_keys": len({r.game_key for r in records if r.game_date.year == 2020}),
            "database_rows_added_or_rewritten": False, "seasons": seasons, "ongoing_season": ongoing,
            "quarantined_keys": sorted(quarantined),
            "reconciliation_summary": {k:v for k,v in rec.items() if k not in {"accepted","quarantine","possible_date_conflicts"}},
            "coverage_status": "BLOCKED", "ADVANCED_STATS_UNLOCKED": False}


def run_foundation_audit(root: Path, capture_directory: Path, index_path: Path, as_of: date,
                         output: Path) -> Path:
    records, schedules, manifests = load_full_sources(root, as_of)
    contract = load_contract()
    coverage = coverage_audit(records, schedules, contract, as_of)
    index = load_capture_index(index_path)
    earliest, captures = capture_evidence(capture_directory, index)
    availability = audit_availability(records, earliest, captures, set(coverage["quarantined_keys"]))
    report = {"coverage": coverage, "availability": availability,
              "source_snapshot_sha256": sorted(m["sha256"] for m in manifests),
              "contract_sha256": sha256(json.dumps(contract, sort_keys=True).encode()),
              "merged_cdx_index_sha256": sha256(json.dumps(index, sort_keys=True).encode()),
              "technical_foundation_accepted": True, "ADVANCED_STATS_UNLOCKED": False,
              "gates": {"technical_result_foundation": "ACCEPTED",
                        "season_coverage": "BLOCKED_EXACT_IDENTITIES_PHASES_AND_MISSING_RESULTS",
                        "historical_result_scores": "PARTIAL_AVAILABLE_BY_CAPTURE_EVIDENCE",
                        "historical_schedule_versions": "BLOCKED",
                        "historical_advanced_statistics": "NOT_IMPORTED_NOT_VERIFIED",
                        "pace_ortg_drtg_join": "BLOCKED"},
              "gate_reasons": ["Exact expected event identities and phase labels require verification",
                               "Missing 2025/2026 postseason and play-in results",
                               "Quarantined result conflicts remain unresolved",
                               "Public score captures do not prove first publication, historical schedules or advanced stats",
                               "Local receipt times remain 2026; no retroactive system-availability claim"]}
    raw = json.dumps(report, sort_keys=True, indent=2).encode()
    identity = sha256(raw)
    target = output/f"{identity}.foundation-audit.json"
    write_once(target, raw)
    summary = {**report, "availability": {k:v for k,v in availability.items() if k != "observations"}}
    write_once(output/f"{identity}.summary.json", json.dumps(summary,sort_keys=True,indent=2).encode())
    rows = ''.join(f'<tr><td>{s["season"]}</td><td>{s["regular"]["observed_keys"]}/'
                   f'{s["regular"]["expected"]}</td><td>{s["regular"]["usable_result_keys"]}</td>'
                   f'<td>{s["playoffs"]["observed"]}/{s["playoffs"]["expected"]}</td>'
                   f'<td>{s["play_in"]["unclassified_non_regular_candidates"]}/6</td></tr>'
                   for s in coverage["seasons"])
    document = ('<!doctype html><html lang="fi"><meta charset="utf-8"><title>BetDoctore kausiauditointi</title>'
                '<h1>Kausikattavuus ja historiallinen saatavuus</h1>'
                '<p>Yksityinen, ei-kaupallinen tutkimus. Advanced-portti: LUKITTU.</p>'
                '<p>Runkosarjan otteluavaimet verrataan lähteen nykyiseen otteluluetteloon. '
                'Sarjakohtaiset playoff-määrät eivät yksin todista täyttä otteluidentiteettikattavuutta.</p>'
                '<table border="1"><tr><th>Kausi</th><th>Runkosarja havaitut/odotetut</th>'
                '<th>Runkosarja ilman karanteenia</th><th>Playoff havaitut/odotetut</th>'
                '<th>Luokittelemattomat play-in-ehdokkaat</th></tr>'+rows+'</table>'
                '<h2>Näyttö ja avoimet puutteet</h2><pre>'+html.escape(json.dumps(summary,indent=2))+'</pre></html>')
    write_once(output/f"{identity}.html", document.encode())
    return target
