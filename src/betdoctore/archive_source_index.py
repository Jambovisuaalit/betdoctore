"""Outcome-blind NBA/ESPN Wayback index discovery. No source-content requests."""
import argparse
import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import httpx

from .commit_history_inventory import _snapshot
from .result_sources import sha256, write_once

CDX = "https://web.archive.org/cdx/search/cdx"
AGE_DAYS = 7
ROW_LIMIT = 2500
# Exact candidate originals only. Neither source identity nor its terms are approved.
SOURCES = (
    ("nba-season-2023", "nba", "https://data.nba.com/data/10s/v2015/json/mobile_teams/nba/2023/league/00_full_schedule.json", 2023, None),
    ("nba-season-2024", "nba", "https://data.nba.com/data/10s/v2015/json/mobile_teams/nba/2024/league/00_full_schedule.json", 2024, None),
    ("nba-cdn-rolling", "nba", "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json", None, None),
    ("espn-2024-scoreboard", "espn", "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=2024&limit=500", None, 2024),
    ("espn-2025-scoreboard", "espn", "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=2025&limit=500", None, 2025),
)


def canonical(url: str) -> tuple:
    parsed = urlsplit(url)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or
            parsed.username or parsed.password or parsed.fragment or parsed.port):
        raise ValueError("Unapproved archive URL")
    return (parsed.hostname.lower(), parsed.path,
            tuple(sorted(parse_qsl(parsed.query, keep_blank_values=True))))


def fixtures(inventory: dict) -> list[dict]:
    raw = sorted({tuple(x) for cap in inventory["captures"] for x in cap["candidate_fixtures"]})
    if not raw:
        raise ValueError("Empty fixed schedule candidate inventory")
    result = []
    for game in raw:
        if len(game) != 3:
            raise ValueError("Invalid schedule fixture")
        tip = datetime.fromisoformat(game[0])
        if tip.utcoffset() is None:
            raise ValueError("Timezone-aware historical schedule required")
        cutoff = (tip - timedelta(minutes=60)).astimezone(UTC)
        result.append({"fixture": list(game), "cutoff": cutoff.isoformat(),
                       "year": tip.year, "season": tip.year if tip.month >= 7 else tip.year-1})
    return result


def relevant(game: dict, season: int | None, year: int | None) -> bool:
    return ((season is None or game["season"] == season)
            and (year is None or game["year"] == year))


def fetch_index(client: httpx.Client, url: str, first: datetime,
                last: datetime) -> tuple[list[dict], bytes, dict]:
    params = {"url": url, "matchType": "exact", "output": "json",
              "filter": "statuscode:200", "from": first.strftime("%Y%m%d"),
              "to": last.strftime("%Y%m%d"), "limit": str(ROW_LIMIT)}
    response = client.get(CDX, params=params)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, list) and not data:
        raise ValueError("CDX index returned empty list")
    if not isinstance(data, list) or not isinstance(data[0], list):
        raise TypeError("Malformed CDX index")
    header = data[0]
    if (len(set(header)) != len(header) or
            not {"timestamp", "original", "statuscode", "mimetype", "digest"} <= set(header)):
        raise ValueError("Missing CDX index columns")
    if len(data)-1 >= ROW_LIMIT:
        raise ValueError("CDX row cap: source status remains unknown")
    captures = {}
    for values in data[1:]:
        r = dict(zip(header, values, strict=True))
        if canonical(r["original"]) != canonical(url):
            raise ValueError("CDX original mismatch")
        if r["statuscode"] != "200" or r["mimetype"] not in (
                "application/json", "text/json", "text/plain", "application/octet-stream"):
            raise ValueError("Unexpected CDX MIME or status")
        stamp = r["timestamp"]
        if len(stamp) != 14 or not stamp.isdigit() or len(r["digest"]) < 16:
            raise ValueError("Malformed CDX timestamp or digest")
        instant = datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        if not first <= instant <= last:
            continue
        capture = {"timestamp": stamp, "captured_at": instant.isoformat(),
                   "cdx_digest": r["digest"], "original": r["original"],
                   "payload_verified": False, "source_rights_verified": False}
        captures[(stamp, r["digest"])] = capture
    return sorted(captures.values(), key=lambda x:(x["captured_at"],x["cdx_digest"])), response.content, params


def preview(inventory: dict, indexes: dict[str, list[dict] | None]) -> dict:
    cases = []
    for game in fixtures(inventory):
        cutoff = datetime.fromisoformat(game["cutoff"])
        matches = []
        for name, _, url, season, year in SOURCES:
            if not relevant(game, season, year):
                continue
            captures = indexes.get(name)
            if captures is None:
                matches.append({"source": name, "status": "INDEX_UNAVAILABLE_NOT_ZERO"})
                continue
            eligible = sorted(
                (v for v in captures if cutoff-timedelta(days=AGE_DAYS)
                 <= datetime.fromisoformat(v["captured_at"]) <= cutoff),
                key=lambda v:(v["captured_at"],v["cdx_digest"]))
            if not eligible:
                matches.append({"source": name, "status": "NO_INDEX_CANDIDATE"})
                continue
            latest = eligible[-1]
            if len({v["cdx_digest"] for v in eligible
                    if v["timestamp"] == latest["timestamp"]}) > 1:
                matches.append({"source": name, "status": "AMBIGUOUS_ARCHIVE_VERSIONS"})
                continue
            matches.append({"source": name, "status": "TIMESTAMP_CANDIDATE_ONLY",
                            "selected": latest, "candidates": len(eligible)})
        cases.append({**game, "sources": matches, "admitted": False,
                      "model_training_allowed": False})
    counts = Counter(x["status"] for case in cases for x in case["sources"])
    return {"schema_version": 1, "status": "CDX_ONLY_NO_SOURCE_ADMISSION",
            "target_candidates": len(cases), "maximum_capture_age_days": AGE_DAYS,
            "targets_with_index_candidate": sum(any(x["status"]=="TIMESTAMP_CANDIDATE_ONLY"
                for x in row["sources"]) for row in cases),
            "source_status_counts": dict(sorted(counts.items())),
            "outcome_blind_selection_preserved": True, "periods_locked": False,
            "source_admitted_games": 0, "source_licensing_approved": False,
            "nba_use_in_gambling_approved": False, "espn_ai_use_approved": False,
            "payloads_fetched": False, "target_scores_read": False,
            "training_eligible": False, "production_ready": False, "cases": cases}


_KNOWN_CDX_ERRORS = {
    "Malformed CDX index": "CDX_MALFORMED_STRUCTURE",
    "CDX index returned empty list": "CDX_EMPTY_LIST_RESPONSE",
    "Missing CDX index columns": "CDX_MISSING_COLUMNS",
    "CDX row cap: source status remains unknown": "CDX_ROW_CAP",
    "CDX original mismatch": "CDX_ORIGINAL_URL_MISMATCH",
    "Unexpected CDX MIME or status": "CDX_MIME_OR_STATUS_MISMATCH",
    "Malformed CDX timestamp or digest": "CDX_BAD_TIMESTAMP_OR_DIGEST",
    "Unapproved archive URL": "CDX_UNAPPROVED_URL",
}


def failure_reason(exc: Exception) -> str:
    """Stable, non-sensitive failure codes; never serialize arbitrary error text."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP_STATUS_{exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return "HTTP_TIMEOUT"
    if isinstance(exc, httpx.RequestError):
        return "HTTP_REQUEST_FAILED"
    if isinstance(exc, json.JSONDecodeError):
        return "CDX_RESPONSE_NOT_JSON"
    if isinstance(exc, ValueError):
        return _KNOWN_CDX_ERRORS.get(str(exc), "CDX_VALUE_ERROR_UNCLASSIFIED")
    if isinstance(exc, KeyError):
        return "CDX_REQUIRED_KEY_MISSING"
    if isinstance(exc, TypeError):
        return ("CDX_MALFORMED_STRUCTURE" if str(exc) == "Malformed CDX index"
                else "CDX_ROW_TYPE_ERROR")
    return "INDEX_ERROR_UNCLASSIFIED"


def run(inventory_path: Path, out: Path, client: httpx.Client) -> dict:
    inventory = _snapshot(inventory_path)
    targets = fixtures(inventory)
    indexes = {}
    sources = []
    for name, publisher, url, season, year in SOURCES:
        relevant_targets = [x for x in targets if relevant(x, season, year)]
        if not relevant_targets:
            continue
        first = min(datetime.fromisoformat(x["cutoff"]) for x in relevant_targets) - timedelta(days=AGE_DAYS)
        last = max(datetime.fromisoformat(x["cutoff"]) for x in relevant_targets)
        try:
            captures, raw, params = fetch_index(client, url, first, last)
            digest = sha256(raw)
            write_once(out/"cdx"/f"{digest}.json", raw)
            indexes[name] = captures
            sources.append({"name": name, "publisher": publisher, "status": "INDEX_FETCHED",
                            "query": params, "sha256": digest, "index_rows": len(captures)})
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            indexes[name] = None
            sources.append({"name": name, "publisher": publisher,
                            "status": "INDEX_FAILED_NOT_ZERO",
                            "error_class": type(exc).__name__,
                            "error_reason": failure_reason(exc)})
    report = preview(inventory, indexes)
    report["source_queries"] = sources
    report["failed_sources"] = sum(x["status"] != "INDEX_FETCHED" for x in sources)
    report["inventory_sha256"] = sha256(inventory_path.read_bytes())
    raw = json.dumps(report, sort_keys=True, indent=2).encode()
    digest = sha256(raw)
    write_once(out/f"{digest}.multi-source-index.json", raw)
    summary = {k:v for k,v in report.items() if k!="cases"}
    summary["report_file"] = f"{digest}.multi-source-index.json"
    write_once(out/f"{digest}.summary.json", json.dumps(summary, sort_keys=True, indent=2).encode())
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-index", action="store_true")
    args = parser.parse_args()
    if not args.execute_index:
        print(json.dumps({"status":"DRY_RUN_NO_NETWORK","sources":[x[0] for x in SOURCES],
            "age_days":AGE_DAYS,"source_admitted_games":0,"training_eligible":False}, indent=2))
        return
    with httpx.Client(timeout=45, follow_redirects=False) as client:
        summary = run(args.inventory, args.output, client)
    print(json.dumps(summary, indent=2))
    print("Only Wayback index metadata queried; no scores, training or production change.")


if __name__ == "__main__":
    main()
