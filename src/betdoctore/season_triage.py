"""Local-only NBA identity/date and score-conflict triage; never approves games."""
import argparse
import json
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .independent_regular_season import load_external_reference
from .result_sources import sha256, write_once
from .results import ALIASES, TEAMS, BasicResult
from .season_audit import load_full_sources


def _canonical(code: str) -> str:
    team = ALIASES.get(code, code)
    if team not in TEAMS:
        raise ValueError(f"Unknown team code in quarantined provider record: {code}")
    return team


def _index(records: list[BasicResult]) -> dict:
    indexed = defaultdict(list)
    for record in records:
        if 2021 <= record.season_end_year <= 2026:
            indexed[(record.season_end_year, record.game_date,
                     record.team_a, record.team_b)].append(record)
    return indexed


def _observations(records: list[BasicResult]) -> list[dict]:
    return [{
        "source": r.source, "game_key": r.game_key, "game_date": str(r.game_date),
        "designated_home": r.designated_home,
        "points_a": r.points_a, "points_b": r.points_b,
        "team_a": r.team_a, "team_b": r.team_b,
        "source_row_numbers": r.source_row_numbers,
        "source_snapshot_sha256": r.source_snapshot_sha256,
    } for r in sorted(records, key=lambda x: (
        x.game_date, x.source, x.source_row_numbers[0]))]


def triage_private(
    date_quarantine: list[dict], records: list[BasicResult], audit: dict,
    valid_provider_ids: set[str],
) -> dict:
    """Return reviewed *candidates* only; no date correction or approval writes."""
    idx = _index(records)
    cases, known_ids = [], set()
    for row in date_quarantine:
        year = row["season_end_year"]
        if year not in range(2021, 2027):
            raise ValueError("Unexpected provider season")
        provider_id = row["provider_event_id"]
        if provider_id in known_ids or provider_id in valid_provider_ids:
            raise ValueError("Duplicate provider ID across manifest/quarantine")
        known_ids.add(provider_id)
        provider_date = date.fromisoformat(row["provider_date"])
        ny_date = date.fromisoformat(row["new_york_tipoff_date"])
        stamp = datetime.fromisoformat(row["provider_datetime"])
        if stamp.utcoffset() is None or stamp.astimezone(
            ZoneInfo("America/New_York")
        ).date() != ny_date or provider_date == ny_date:
            raise ValueError("Inconsistent timezone-aware date quarantine record")
        home = _canonical(row["home_team_abbreviation"])
        away = _canonical(row["away_team_abbreviation"])
        if home == away:
            raise ValueError("Duplicate teams in provider record")
        a, b = sorted((home, away))
        candidates = []
        for basis, day in (("provider_date", provider_date),
                           ("new_york_tipoff_date", ny_date)):
            observed = idx.get((year, day, a, b), [])
            if observed:
                mismatched_home = any(r.designated_home not in (None, home)
                                      for r in observed)
                candidates.append({
                    "basis": basis, "game_key": f"nba:{day}:{a}:{b}",
                    "designated_home_conflict": mismatched_home,
                    "observations": _observations(observed),
                })
        bases = {x["basis"] for x in candidates}
        if len(bases) == 2:
            diagnosis = "TWO_POSSIBLE_MATCH_DATES"
        elif len(bases) == 1:
            diagnosis = "SINGLE_DATE_CANDIDATE"
        else:
            diagnosis = "NO_EXACT_DATE_TEAM_MATCH"
        if any(x["designated_home_conflict"] for x in candidates):
            diagnosis = "HOME_CONFLICT_REQUIRES_REVIEW"
        cases.append({
            "provider_event_id": provider_id, "season_end_year": year,
            "teams": [a, b], "provider_home": home, "provider_away": away,
            "provider_date": str(provider_date),
            "new_york_tipoff_date": str(ny_date),
            "day_delta": (ny_date - provider_date).days,
            "diagnosis": diagnosis, "candidate_matches": candidates,
            "approval": "BLOCKED_MANUAL_REVIEW",
            "training_eligible": False,
        })

    score_cases = []
    for season in audit["seasons"]:
        year = season["season_end_year"]
        for row in season["quarantined_games"]:
            if "SCORE_CONFLICT" not in row["reasons"]:
                continue
            key = row["game_key"]
            linked = sorted({
                case["provider_event_id"] for case in cases
                if any(match["game_key"] == key
                       for match in case["candidate_matches"])
            })
            observations = [{
                "source": x["source"], "game_key": x["game_key"],
                "game_date": x["game_date"],
                "team_a": x["team_a"], "team_b": x["team_b"],
                "points_a": x["points_a"], "points_b": x["points_b"],
                "designated_home": x["designated_home"],
                "source_row_numbers": x["source_row_numbers"],
                "source_snapshot_sha256": x["source_snapshot_sha256"],
            } for x in row["observations"]]
            score_cases.append({
                "season_end_year": year, "game_key": key,
                "reasons": row["reasons"], "observations": observations,
                "possible_date_quarantine_links": linked,
                "resolution": "REVIEW_REQUIRED",
                "training_eligible": False,
            })
    cases.sort(key=lambda x: (x["season_end_year"], x["provider_event_id"]))
    score_cases.sort(key=lambda x: (x["season_end_year"], x["game_key"]))
    years = []
    for year in range(2021, 2027):
        subset = [x for x in cases if x["season_end_year"] == year]
        conflicts = [x for x in score_cases if x["season_end_year"] == year]
        years.append({
            "season": f"{year-1}-{str(year)[-2:]}",
            "season_end_year": year,
            "date_quarantine": len(subset),
            "date_diagnosis": dict(sorted(Counter(x["diagnosis"] for x in subset).items())),
            "date_long_range_gt_2_days": sum(abs(x["day_delta"]) > 2 for x in subset),
            "score_conflicts": len(conflicts),
            "score_conflicts_with_possible_date_link": sum(
                bool(x["possible_date_quarantine_links"]) for x in conflicts),
        })
    return {
        "schema_version": 1,
        "scope": "local_private_research_only",
        "source_lineage_approved": False, "training_eligible": False,
        "automatic_game_date_corrections": 0, "automatic_score_corrections": 0,
        "note": "Candidate overlap by teams/date is not proof of identical games",
        "seasons": years,
        "date_cases": cases, "score_cases": score_cases,
    }


def run_triage(root: Path, reference: Path, audit_path: Path,
               output: Path, as_of: date) -> Path:
    events, provenance = load_external_reference(
        reference / "events.json", reference / "provenance.json")
    source = json.loads((reference / "request-receipts.json").read_text())
    if source["source_sha256"] != provenance.source_sha256:
        raise ValueError("Provider receipt and manifest digest mismatch")
    if source["events"] != len(events):
        raise ValueError("Provider event count mismatch")
    raw = audit_path.read_bytes()
    if audit_path.name != f"{sha256(raw)}.regular-season-audit.json":
        raise ValueError("Full regular-season audit is not content-addressed")
    audit = json.loads(raw)
    if audit["reference_source_sha256"] != provenance.source_sha256:
        raise ValueError("Audit and provider reference snapshots differ")
    if audit["training_eligible"] is not False:
        raise ValueError("Unexpected unlocked training gate")
    date_raw = (reference / "date-quarantine.json").read_bytes()
    date_rows = json.loads(date_raw)
    if len(date_rows) != source["quarantined_date_mismatches"]:
        raise ValueError("Provider date quarantine count mismatch")
    records, _, _ = load_full_sources(root, as_of)
    report = triage_private(date_rows, records, audit,
                            {x.provider_event_id for x in events})
    report["input_sha256"] = {
        "manifest": provenance.source_sha256,
        "provider_date_quarantine": sha256(date_raw),
        "regular_season_audit": sha256(raw),
    }
    payload = json.dumps(report, sort_keys=True, indent=2).encode()
    digest = sha256(payload)
    summary = {key: val for key, val in report.items()
               if key not in {"date_cases", "score_cases"}}
    summary["report_sha256"] = digest
    summary["totals"] = {
        "date_quarantine": len(report["date_cases"]),
        "score_conflicts": len(report["score_cases"]),
        "possible_date_score_links": sum(
            bool(x["possible_date_quarantine_links"])
            for x in report["score_cases"]),
    }
    write_once(output / f"{digest}.date-cases.json",
               json.dumps(report["date_cases"], sort_keys=True, indent=2).encode())
    write_once(output / f"{digest}.score-cases.json",
               json.dumps(report["score_cases"], sort_keys=True, indent=2).encode())
    write_once(output / f"{digest}.triage.json", payload)
    path = output / f"{digest}.summary.json"
    write_once(path, json.dumps(summary, sort_keys=True, indent=2).encode())
    return path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Private, read-only NBA date/score-conflict candidate matching")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat,
                        default=date(2026, 10, 27))
    args = parser.parse_args()
    path = run_triage(args.root, args.reference, args.audit,
                      args.output, args.as_of)
    report = json.loads(path.read_text())
    print(f"Private summary: {path}")
    for season in report["seasons"]:
        print(f"{season['season']}: dates={season['date_quarantine']}; "
              f"score_conflicts={season['score_conflicts']}; "
              f"possible_links={season['score_conflicts_with_possible_date_link']}; "
              f"diagnoses={season['date_diagnosis']}")
    print("No games approved; no sources rewritten; no training gates unlocked.")


if __name__ == "__main__":
    main()
