"""Strict private Wayback score-history discovery; no baseline, cohort or training unlock."""
import argparse
import csv
import io
import json
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from .commit_history_inventory import _snapshot
from .historical_availability import CDX_URL, NEIL_ORIGINAL, validate_cdx_row, verify_capture
from .result_sources import sha256, write_once
from .results import ALIASES, TEAMS

MAX_INDEX_ROWS = 5000
HISTORY_DAYS = 7


def _cutoff(fixture: tuple[str, str, str]) -> datetime:
    tipoff = datetime.fromisoformat(fixture[0])
    if tipoff.utcoffset() is None:
        raise ValueError("Historical scheduled tipoff must include timezone")
    return tipoff - timedelta(minutes=60)


def _fixtures(inventory: dict) -> list[tuple[str, str, str]]:
    fixtures = sorted({tuple(f) for c in inventory["captures"] for f in c["candidate_fixtures"]})
    if any(len(f) != 3 for f in fixtures):
        raise ValueError("Unexpected fixture identity")
    return fixtures


def discover_index(inventory: dict, client: httpx.Client) -> tuple[dict, bytes]:
    """Query *all* indexed snapshots in the relevant interval, NOT one per month."""
    fixtures = _fixtures(inventory)
    if not fixtures:
        raise ValueError("Empty outcome-blind candidate inventory")
    cutoffs = [_cutoff(f) for f in fixtures]
    start = min(cutoffs)-timedelta(days=HISTORY_DAYS)
    end = max(cutoffs)
    params = {"url": NEIL_ORIGINAL.removeprefix("https://"), "output": "json",
              "filter": "statuscode:200", "from": start.strftime("%Y%m%d"),
              "to": end.strftime("%Y%m%d"), "limit": str(MAX_INDEX_ROWS)}
    response = client.get(CDX_URL, params=params)
    response.raise_for_status()
    raw = response.content
    index = response.json()
    if not isinstance(index, list) or not index or not isinstance(index[0], list):
        raise ValueError("Wayback did not provide a verifiable CDX index")
    if len(index)-1 >= MAX_INDEX_ROWS:
        raise ValueError("CDX response hit cap; partition before using it")
    keys = index[0]
    if not {"timestamp", "original", "mimetype", "statuscode", "digest"} <= set(keys):
        raise ValueError("Wayback CDX index missing required columns")
    rows, identifiers = [], set()
    for values in index[1:]:
        row = dict(zip(keys, values, strict=True))
        validate_cdx_row(row)
        captured = datetime.strptime(row["timestamp"], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        # CDX from/to parameters are calendar dates, not exact instants.
        # Boundary-day captures outside our precise window are not candidates.
        if not start <= captured <= end:
            continue
        ident = (row["timestamp"], row["original"], row["digest"])
        if ident not in identifiers:
            identifiers.add(ident)
            rows.append(row)
    cases = []
    for fixture, cutoff in zip(fixtures, cutoffs, strict=True):
        matching = sorted(
            (r for r in rows if cutoff-timedelta(days=HISTORY_DAYS)
             <= datetime.strptime(r["timestamp"], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
             <= cutoff), key=lambda r: (r["timestamp"], r["digest"]))
        candidate = matching[-1] if matching else None
        conflict = (len(matching) > 1 and
                    matching[-1]["timestamp"] == matching[-2]["timestamp"] and
                    matching[-1]["digest"] != matching[-2]["digest"])
        cases.append({
            "fixture": list(fixture), "cutoff": cutoff.isoformat(),
            "capture": None if conflict or candidate is None else candidate,
            "candidate_captures": len(matching),
            "status": ("AMBIGUOUS_CAPTURE_VERSION" if conflict else
                       "INDEX_TIMESTAMP_CANDIDATE_NOT_VERIFIED" if candidate else
                       "NO_WITHIN_SEVEN_DAYS_CAPTURE"),
            "body_digest_verified": False, "historical_score_rows_verified": False,
            "source_admitted": False, "training_eligible": False,
        })
    return ({
        "schema_version": 1, "status": "CDX_INDEX_PREVIEW_UNVERIFIED",
        "source": NEIL_ORIGINAL, "index_sha256": sha256(raw),
        "query": params, "seven_day_max_age": HISTORY_DAYS,
        "index_captures": len(rows), "target_candidates": len(fixtures),
        "timestamp_candidates": sum(x["capture"] is not None for x in cases),
        "source_admitted_games": 0, "sample_periods_locked": False,
        "outcome_manifest_read": False, "target_scores_read": False,
        "source_rights_approved": False, "training_eligible": False,
        "cases": cases,
    }, raw)


def _history_keys(raw: bytes, captured: datetime) -> set[tuple[date, str, str]]:
    """Check only historical, already finished regular-game score pairs."""
    pairs = defaultdict(list)
    for item in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        if item["score1"] in ("", "NA") or item["score2"] in ("", "NA"):
            continue
        day = date.fromisoformat(item["date"])
        if day > captured.date():
            raise ValueError("Archive snapshot contains future final score")
        if item["playoff"] not in ("", "FALSE"):
            continue
        home, away = (ALIASES.get(item[k], item[k]) for k in ("team1", "team2"))
        if home not in TEAMS or away not in TEAMS or home == away:
            raise ValueError("Unknown team in archived history")
        scores = (int(item["score1"]), int(item["score2"]))
        if min(scores) <= 0 or scores[0] == scores[1]:
            raise ValueError("Invalid historical final score")
        key = (day, *sorted((home, away)))
        pairs[key].append((home, away, *scores))
    valid = set()
    for key, observed in pairs.items():
        if (len(observed) != 2 or observed[0][0] != observed[1][1]
                or observed[0][1] != observed[1][0]
                or observed[0][2] != observed[1][3]
                or observed[0][3] != observed[1][2]):
            raise ValueError("Unpaired or conflicting archived history score")
        valid.add(key)
    return valid


def verify_bodies(discovery: dict, index: list, client: httpx.Client,
                  output: Path, *, max_downloads: int = 24) -> dict:
    """Verify preselected snapshots only. Never choose a different one after reading scores."""
    if (discovery["status"] != "CDX_INDEX_PREVIEW_UNVERIFIED"
            or discovery["source"] != NEIL_ORIGINAL
            or discovery["seven_day_max_age"] != HISTORY_DAYS
            or discovery["source_admitted_games"] != 0):
        raise ValueError("Invalid discovery controls")
    chosen = {r["timestamp"]: r for case in discovery["cases"]
              if (r := case["capture"]) is not None}
    if len(chosen) > max_downloads:
        raise ValueError("Download budget exceeded: review candidate plan before continuing")
    available = {}
    for timestamp, row in sorted(chosen.items()):
        validate_cdx_row(row)
        url = f"https://web.archive.org/web/{timestamp}id_/{row['original']}"
        response = client.get(url)
        response.raise_for_status()
        raw = response.content
        verify_capture(raw, row, index)
        captured = datetime.strptime(timestamp, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        games = _history_keys(raw, captured)
        write_once(output / "captures" / f"{sha256(raw)}.csv", raw)
        available[timestamp] = {"sha256": sha256(raw), "historical_keys": games,
                                "replay_url": url}
    details, counts = [], defaultdict(int)
    for case in discovery["cases"]:
        fixture = case["fixture"]
        cutoff = _cutoff(tuple(fixture))
        if cutoff.isoformat() != case["cutoff"]:
            raise ValueError("Frozen T-60 cutoff differs from schedule-derived cutoff")
        selected = case["capture"]
        row = {k: v for k, v in case.items() if k != "capture"}
        if selected is None:
            status = case["status"]
        else:
            verified = available[selected["timestamp"]]
            day = datetime.fromisoformat(fixture[0]).astimezone(
                ZoneInfo("America/New_York")).date()
            game_set = {k for k in verified["historical_keys"] if k[0] < day}
            # Never read or use target-game result values.
            home, away = (ALIASES.get(x, x) for x in fixture[1:])
            if home not in TEAMS or away not in TEAMS or home == away:
                status = "UNKNOWN_TEAM_IDENTITY"
            elif any(k[0] == day and set(k[1:]) == {home, away}
                     for k in verified["historical_keys"]):
                status = "TARGET_RESULT_PRESENT_IN_PREGAME_CAPTURE"
            else:
                h = sum(home in k[1:] for k in game_set)
                a = sum(away in k[1:] for k in game_set)
                status = ("TECHNICAL_HISTORY_CANDIDATE_RIGHTS_PENDING"
                          if h >= 5 and a >= 5 and len(game_set) >= 100 else
                          "INSUFFICIENT_TEAM_OR_LEAGUE_HISTORY")
                row.update({"home_history_games": h, "away_history_games": a,
                            "league_history_games": len(game_set)})
            row.update({"capture_timestamp": selected["timestamp"],
                        "capture_sha256": verified["sha256"],
                        "archive_replay": verified["replay_url"]})
        row.update({"status": status, "source_admitted": False,
                    "rights_and_lineage_reviewed": False, "training_eligible": False})
        details.append(row)
        counts[status] += 1
    return {
        "schema_version": 1, "status": "VERIFIED_ARCHIVE_BYTES_RESEARCH_REVIEW_ONLY",
        "source": NEIL_ORIGINAL, "index_sha256": discovery["index_sha256"],
        "archive_payloads_verified": len(available), "target_candidates": len(details),
        "status_counts": dict(sorted(counts.items())),
        "source_admitted_games": 0, "source_rights_approved": False,
        "historical_advanced_availability_approved": False,
        "periods_locked": False, "outcomes_read_for_selection": False,
        "training_eligible": False, "cases": details,
    }


def _verified_json(path: Path, suffix: str) -> dict:
    raw = path.read_bytes()
    if not path.name.endswith(suffix) or not path.name.startswith(sha256(raw)+"."):
        raise ValueError("Content-addressed report checksum mismatch")
    return json.loads(raw)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", type=Path,
                        help="Existing hash-addressed discovery file; opt-in archive body download")
    parser.add_argument("--max-downloads", type=int, default=24)
    args = parser.parse_args()
    inventory = _snapshot(args.inventory)
    with httpx.Client(timeout=90, follow_redirects=False) as client:
        if args.verify is None:
            discovery, raw_index = discover_index(inventory, client)
            index_path = args.output / f"{sha256(raw_index)}.cdx.json"
            write_once(index_path, raw_index)
            report = {**discovery, "index_file": index_path.name}
            suffix = "cdx-history-discovery.json"
        else:
            report = _verified_json(args.verify, ".cdx-history-discovery.json")
            index_raw = (args.output / report["index_file"]).read_bytes()
            if sha256(index_raw) != report["index_sha256"]:
                raise ValueError("Original archive index SHA-256 mismatch")
            index = json.loads(index_raw)
            for case in report["cases"]:
                chosen = case["capture"]
                if chosen and chosen not in [
                    dict(zip(index[0], row, strict=True)) for row in index[1:]
                ]:
                    raise ValueError("Chosen snapshot missing from historical CDX index")
            report = verify_bodies(report, index, client, args.output,
                                   max_downloads=args.max_downloads)
            suffix = "verified-score-history-review.json"
    raw = json.dumps(report, sort_keys=True, indent=2).encode()
    digest = sha256(raw)
    write_once(args.output / f"{digest}.{suffix}", raw)
    summary = {k: v for k, v in report.items() if k != "cases"}
    summary["report_file"] = f"{digest}.{suffix}"
    write_once(args.output / f"{digest}.summary.json",
               json.dumps(summary, sort_keys=True, indent=2).encode())
    print(json.dumps(summary, indent=2))
    print("No games admitted, no target outcomes scored, no training/deployment.")


if __name__ == "__main__":
    main()
