"""Opt-in private BALLDONTLIE score corroboration for completed 2025–26 season.

Does not mark upstream independence reviewed or unlock training.
"""
import argparse
import getpass
import json
import os
import time
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

from .bdl_reference import ENDPOINT, MIN_INTERVAL_SECONDS, normalize
from .independent_regular_season import load_external_reference
from .result_sources import sha256, write_once
from .season_audit import load_contract, load_full_sources

SEASON = 2025
EXPECTED = 1230


def _score(row: dict, expected_event) -> dict:
    """Validate *both* the identity and final score; no source-date guessing."""
    event = normalize(row, SEASON, set())
    if event is None:
        raise ValueError("Cup final must not appear in 2025–26 regular-score pages")
    if event != expected_event:
        raise ValueError("Provider event identity changed since original manifest")
    if row.get("status_state") != "final" and row.get("status") != "Final":
        raise ValueError("Non-final score")
    home, away = row.get("home_team_score"), row.get("visitor_team_score")
    if (type(home) is not int or type(away) is not int or
            not 0 < home <= 250 or not 0 < away <= 250 or home == away):
        raise ValueError("Missing, tied or invalid final score")
    points = {event.home: home, event.away: away}
    a, b = sorted((event.home, event.away))
    return {"provider_event_id": event.provider_event_id,
            "season_end_year": event.season_end_year,
            "game_key": event.game_key,
            "home": event.home, "away": event.away,
            "points_a": points[a], "points_b": points[b],
            "team_a": a, "team_b": b,
            "provider_status": row.get("status_state") or row.get("status")}


def acquire_scores(reference: Path, output: Path, api_key: str, *,
                   max_requests: int = 20, client=None, sleep=time.sleep) -> dict:
    """API calls are opt-in; fail closed before private files are written."""
    if not api_key or not api_key.strip():
        raise ValueError("Missing BALLDONTLIE API key")
    if max_requests < 13:
        raise ValueError("Budget too small for 2025–26 season")
    if (output / "scores.json").exists():
        raise FileExistsError("Score snapshot already exists; never overwrite")
    events, provenance = load_external_reference(reference / "events.json",
                                                 reference / "provenance.json")
    if provenance.provider_id != "balldontlie-nba":
        raise ValueError("Unexpected reference provider")
    expected_events = {e.provider_event_id: e for e in events
                       if e.season_end_year == 2026 and e.phase == "regular_season"}
    if len(expected_events) != EXPECTED:
        raise ValueError("Original 2025–26 BDL identity manifest incomplete")
    if not api_key.strip():
        raise ValueError("Empty key")
    owned = client is None
    client = client or httpx.Client(timeout=30, follow_redirects=False)
    receipts, pages, scores = [], [], {}
    cup_keys = {x["game_key"] for x in load_contract()["cup_finals"]}
    cursor, seen_cursors = None, set()
    try:
        while True:
            if len(receipts) >= max_requests:
                raise RuntimeError("Request budget exceeded: no partial export")
            params = {"seasons[]": SEASON, "season_type": "regular",
                      "per_page": 100}
            if cursor is not None:
                if cursor in seen_cursors:
                    raise ValueError("Repeated pagination cursor")
                seen_cursors.add(cursor)
                params["cursor"] = cursor
            if receipts:
                sleep(MIN_INTERVAL_SECONDS)
            response = client.get(ENDPOINT, params=params,
                                  headers={"Authorization": api_key})
            response.raise_for_status()
            raw = response.content
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                raise TypeError("Unrecognized BALLDONTLIE response")
            for row in payload["data"]:
                if not isinstance(row, dict) or type(row.get("id")) is not int:
                    raise TypeError("Invalid provider event ID")
                ident = f"bdl:{row['id']}"
                # A known Cup final is not a regular-season result.
                if (row.get("ist_stage") == "Championship" or
                        (row.get("home_team") and row.get("visitor_team") and
                         row.get("date") and
                         _key_if_known(row) in cup_keys)):
                    continue
                if ident in scores:
                    raise ValueError("Repeated event ID")
                event = expected_events.get(ident)
                if event is None:
                    raise ValueError("Provider added an unexpected event ID")
                scores[ident] = _score(row, event)
            meta = payload.get("meta")
            if not isinstance(meta, dict):
                raise TypeError("Missing pagination metadata")
            receipts.append({"cursor": cursor, "rows": len(payload["data"]),
                             "response_sha256": sha256(raw),
                             "next_cursor": meta.get("next_cursor")})
            pages.append(raw)
            cursor = meta.get("next_cursor")
            if cursor in (None, ""):
                break
    finally:
        if owned:
            client.close()
    if set(scores) != set(expected_events):
        raise ValueError(f"Incomplete provider score coverage: {len(scores)}/{EXPECTED}")
    serialized = json.dumps(sorted(scores.values(),
                        key=lambda r: r["provider_event_id"]),
                        sort_keys=True, indent=2).encode()
    receipt = {"schema_version": 1, "provider": "balldontlie-nba",
               "scope": "2025-26_regular_season", "expected": EXPECTED,
               "fetched": len(scores), "request_count": len(receipts),
               "source_manifest_sha256": provenance.source_sha256,
               "scores_sha256": sha256(serialized),
               "retrieved_at": datetime.now(UTC).isoformat(),
               "upstream_lineage_reviewed": False,
               "commercial_use_approved": False, "training_eligible": False,
               "pages": receipts}
    # Preserve response bytes for audit privately, after all pagination validated.
    for raw in pages:
        write_once(output / "pages" / f"{sha256(raw)}.json", raw)
    write_once(output / "scores.json", serialized)
    write_once(output / "receipt.json", json.dumps(receipt,
               sort_keys=True, indent=2).encode())
    return {k: v for k, v in receipt.items() if k != "pages"}


def _key_if_known(row: dict) -> str:
    """Known Cup final key for explicit exclusion, independent of score."""
    from .results import ALIASES
    home = ALIASES.get(row["home_team"]["abbreviation"],
                       row["home_team"]["abbreviation"])
    away = ALIASES.get(row["visitor_team"]["abbreviation"],
                       row["visitor_team"]["abbreviation"])
    a, b = sorted((home, away))
    return f"nba:{row['date']}:{a}:{b}"


def compare_scores(root: Path, reference: Path, scores_dir: Path, as_of: date,
                   output: Path) -> dict:
    receipt = json.loads((scores_dir / "receipt.json").read_text())
    raw = (scores_dir / "scores.json").read_bytes()
    if sha256(raw) != receipt["scores_sha256"] or receipt["fetched"] != EXPECTED:
        raise ValueError("Altered or incomplete score snapshot")
    events, provenance = load_external_reference(reference / "events.json",
                                                 reference / "provenance.json")
    if receipt["source_manifest_sha256"] != provenance.source_sha256:
        raise ValueError("Reference lineage/checksum mismatch")
    ref = {e.provider_event_id: e for e in events if e.season_end_year == 2026}
    scores = json.loads(raw)
    if len(scores) != EXPECTED or {r["provider_event_id"] for r in scores} != set(ref):
        raise ValueError("Score provider ID set inconsistent with original manifest")
    observations, _, _ = load_full_sources(root, as_of)
    private = {}
    for r in observations:
        if r.source == "fixturedownload-private" and r.season_end_year == 2026:
            if r.game_key in private:
                raise ValueError("Duplicate private observation")
            private[r.game_key] = r
    details, statuses = [], Counter()
    for row in scores:
        r = private.get(row["game_key"])
        if r is None:
            status = "NO_FIXTURE_RESULT_MATCH"
        elif r.designated_home != row["home"]:
            status = "HOME_DESIGNATION_CONFLICT"
        elif (r.points_a, r.points_b) != (row["points_a"], row["points_b"]):
            status = "SCORE_CONFLICT"
        else:
            status = "TWO_PUBLISHER_SCORE_AGREEMENT_UNREVIEWED"
        statuses[status] += 1
        details.append({
            **row, "status": status,
            "private_source_score": None if r is None else [r.points_a, r.points_b],
            "private_source_sha256": None if r is None else r.source_snapshot_sha256,
            "approval": "PENDING_UPSTREAM_LINEAGE_AND_RIGHTS_REVIEW",
            "training_eligible": False,
        })
    summary = {"schema_version": 1, "season": "2025-26",
               "expected": EXPECTED, "scores_compared": len(details),
               "status_counts": dict(sorted(statuses.items())),
               "source_snapshot_sha256": receipt["scores_sha256"],
               "independent_upstream_lineage_reviewed": False,
               "commercial_rights_reviewed": False, "historical_t60_verified": False,
               "approved_count": 0, "training_eligible": False}
    payload = json.dumps(details, sort_keys=True, indent=2).encode()
    digest = sha256(payload)
    write_once(output / f"{digest}.score-comparison.json", payload)
    write_once(output / f"{digest}.summary.json",
               json.dumps(summary, sort_keys=True, indent=2).encode())
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--comparison-output", type=Path)
    parser.add_argument("--as-of", type=date.fromisoformat,
                        default=date(2026, 10, 27))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-requests", type=int, default=20)
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({"status": "DRY_RUN_NO_NETWORK",
                          "season": "2025-26", "expected_games": EXPECTED,
                          "min_pages": 13, "max_requests": args.max_requests,
                          "estimated_interval_seconds": MIN_INTERVAL_SECONDS,
                          "license_review": "REQUIRED",
                          "training_eligible": False}, indent=2))
        return
    api_key = os.getenv("BALLDONTLIE_API_KEY") or getpass.getpass(
        "BALLDONTLIE_API_KEY (hidden): ")
    acquisition = acquire_scores(args.reference, args.output, api_key,
                                  max_requests=args.max_requests)
    print(json.dumps(acquisition, indent=2))
    if args.root and args.comparison_output:
        print(json.dumps(compare_scores(args.root, args.reference,
                         args.output, args.as_of, args.comparison_output),
                         indent=2))


if __name__ == "__main__":
    main()
