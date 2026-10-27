"""Outcome-blind Git commit score-history candidate inventory (NOT admission).

Git author/committer timestamps are user-controlled metadata, not independently
verified evidence of public availability by the historical prediction cutoff.
"""
import argparse
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from .result_sources import sha256, write_once

URL = "https://api.github.com/repos/Neil-Paine-1/NBA-elo/commits"
SOURCE_PATH = "nba_elo.csv"
SINCE = "2024-02-01T00:00:00Z"
UNTIL = "2025-05-01T00:00:00Z"
GIT_SHA = re.compile(r"^[a-f0-9]{40}$")
MAX_PAGES = 6


def parse_commit(row: dict) -> dict:
    sha = row["sha"]
    if not isinstance(sha, str) or not GIT_SHA.fullmatch(sha):
        raise ValueError("Invalid Git commit SHA")
    commit = row["commit"]
    timestamp = datetime.fromisoformat(commit["committer"]["date"].replace("Z", "+00:00"))
    if timestamp.utcoffset() is None or timestamp > datetime.now(UTC):
        raise ValueError("Invalid commit metadata timestamp")
    return {"sha": sha, "committer_claimed_at": timestamp.isoformat(),
            "github_url": f"https://github.com/Neil-Paine-1/NBA-elo/commit/{sha}",
            "claimed_time_is_publication_proof": False}


def fetch_commit_candidates(client: httpx.Client, *, max_pages: int = MAX_PAGES) -> tuple[list[dict], list[dict]]:
    if not 1 <= max_pages <= MAX_PAGES:
        raise ValueError("Invalid pagination budget")
    commits, receipts, seen = [], [], set()
    for page in range(1, max_pages+1):
        response = client.get(URL, params={"path": SOURCE_PATH, "since": SINCE,
                              "until": UNTIL, "per_page": 100, "page": page},
                              headers={"Accept": "application/vnd.github+json"})
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise TypeError("GitHub commits endpoint returned non-array")
        for row in payload:
            item = parse_commit(row)
            if item["sha"] in seen:
                raise ValueError("Duplicate commit SHA in pagination")
            seen.add(item["sha"])
            commits.append(item)
        receipts.append({"page": page, "source_api_url": str(response.request.url),
                         "response_sha256": sha256(response.content),
                         "count": len(payload)})
        if len(payload) < 100:
            break
    else:
        raise RuntimeError("GitHub history exceeds request budget; no candidate export")
    if not commits:
        raise ValueError("No historical commit candidates found")
    return sorted(commits, key=lambda c: (c["committer_claimed_at"], c["sha"])), receipts


def _snapshot(path: Path) -> dict:
    raw = path.read_bytes()
    name = path.name
    if not name.endswith(".combined-inventory.json") or not name.startswith(
        sha256(raw) + "."
    ):
        raise ValueError("Combined inventory filename/checksum mismatch")
    report = json.loads(raw)
    if (report.get("status") != "INVENTORY_ONLY"
            or report.get("source_admitted_games") != 0
            or report.get("periods_locked") is not False
            or report.get("outcomes_used_for_selection") is not False
            or report.get("use_scope") != "private_noncommercial"
            or not isinstance(report.get("captures"), list)):
        raise ValueError("Invalid outcome-blind private inventory")
    return report


def compare_commit_timeline(report: dict, commits: list[dict], *, max_age_days: int = 7) -> dict:
    if max_age_days != 7:
        raise ValueError("Frozen seven-day freshness requirement must not be relaxed")
    times = []
    seen = set()
    for c in commits:
        item = parse_commit({"sha": c["sha"],
                             "commit": {"committer": {
                                 "date": c["committer_claimed_at"]}}})
        if item["sha"] in seen:
            raise ValueError("Duplicate Git commit")
        seen.add(item["sha"])
        times.append((datetime.fromisoformat(item["committer_claimed_at"]), item["sha"]))
    cases = []
    fixtures = sorted({tuple(v) for cap in report["captures"] for v in cap["candidate_fixtures"]})
    for tip, home, away in fixtures:
        when = datetime.fromisoformat(tip)
        if when.utcoffset() is None:
            raise ValueError("Unzoned scheduled tipoff")
        cutoff = when - timedelta(minutes=60)
        eligible = sorted([(t, sha) for t, sha in times
                          if cutoff-timedelta(days=7) <= t <= cutoff])
        selected = eligible[-1] if eligible else None
        cases.append({
            "scheduled_tipoff": tip, "home": home, "away": away,
            "published_schedule_t60_cutoff": cutoff.isoformat(),
            "commit_candidate": (None if selected is None else {
                "sha": selected[1], "self_declared_committer_date": selected[0].isoformat()}),
            "status": ("COMMIT_DATE_CANDIDATE_UNVERIFIED" if selected
                       else "NO_GIT_COMMIT_DATE_CANDIDATE"),
            "git_date_proves_public_availability": False,
            "source_csv_content_revalidated": False,
            "source_score_rows_read": False,
            "historical_result_availability_verified": False,
            "source_admitted": False,
        })
    count = sum(c["commit_candidate"] is not None for c in cases)
    return {
        "schema_version": 1, "status": "OUTCOME_BLIND_CANDIDATE_INVENTORY",
        "data_source": "Neil-Paine-1/NBA-elo:nba_elo.csv",
        "commits_in_window": len(commits),
        "schedule_candidates": len(cases),
        "claimed_timestamp_compatible": count,
        "no_candidate": len(cases)-count,
        "freshness_days": max_age_days,
        "source_admitted_games": 0,
        "independent_historical_publication_verified": False,
        "publisher_origin_and_rights_reviewed": False,
        "history_rows_validated": False,
        "periods_locked": False,
        "outcomes_read": False,
        "new_forecasts_generated": False,
        "training_eligible": False,
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commits", type=Path,
                        help="Reuse an earlier, checksum-verified local commit candidate list")
    parser.add_argument("--discover", action="store_true",
                        help="Explicitly query GitHub public metadata (no source CSV download)")
    args = parser.parse_args()
    if bool(args.commits) == args.discover:
        parser.error("Choose exactly one of --commits or --discover")
    report = _snapshot(args.inventory)
    if args.discover:
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            commits, receipts = fetch_commit_candidates(client)
    else:
        source_raw = args.commits.read_bytes()
        if not args.commits.name.startswith(sha256(source_raw)+"."):
            raise ValueError("Commit list is not content-addressed")
        commits = json.loads(source_raw)
        receipts = [{"source": str(args.commits), "sha256": sha256(source_raw)}]
    joined = compare_commit_timeline(report, commits)
    joined["inputs"] = {
        "inventory_sha256": sha256(args.inventory.read_bytes()),
        "commit_candidates_sha256": sha256(json.dumps(commits, sort_keys=True).encode()),
        "github_metadata_request_receipts": receipts,
    }
    raw = json.dumps(joined, sort_keys=True, indent=2).encode()
    identity = sha256(raw)
    summary = {k: v for k, v in joined.items() if k != "cases"}
    summary["report_sha256"] = identity
    write_once(args.output / f"{identity}.commit-candidate-inventory.json", raw)
    write_once(args.output / f"{identity}.summary.json",
               json.dumps(summary, sort_keys=True, indent=2).encode())
    commits_raw = json.dumps(commits, sort_keys=True).encode()
    write_once(args.output / f"{sha256(commits_raw)}.commits.json", commits_raw)
    print(json.dumps(summary, sort_keys=True, indent=2))
    print("No historical source admission or model evaluation performed.")


if __name__ == "__main__":
    main()
