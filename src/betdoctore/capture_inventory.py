"""Private, outcome-blind discovery of new pregame schedule evidence.

Inventory is not source admission, a locked sample, or an evaluation result.
"""
import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from .result_sources import sha256, write_once

CDX = "https://web.archive.org/cdx/search/cdx"
TERMS = "https://fixturedownload.com/terms"


def save(directory: Path, suffix: str, value: dict | bytes) -> str:
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, indent=2).encode()
    name = f"{sha256(raw)}.{suffix}"
    write_once(directory/name, raw)
    return name


def validate_schedule(raw: bytes, row: dict, index: list, prefix: str) -> dict:
    """Verify archived bytes before inspecting future schedule rows; ignore score values."""
    if (not row["original"].startswith(prefix)
            or row["original"][len(prefix):len(prefix)+1] not in ("", "/")
            or row["statuscode"] != "200" or row["mimetype"] != "application/json"):
        raise ValueError("Unapproved schedule origin or response")
    if row not in [dict(zip(index[0], v, strict=True)) for v in index[1:]]:
        raise ValueError("Capture missing from original index")
    digest = base64.b32encode(hashlib.sha1(raw).digest()).decode().rstrip("=")
    if digest != row["digest"]:
        raise ValueError("Archive payload digest mismatch")
    captured = datetime.strptime(row["timestamp"], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    if captured.year == 2022:
        raise ValueError("Development capture excluded")
    rows = json.loads(raw)
    if not isinstance(rows, list):
        raise TypeError("Schedule must be an array")
    future = set()
    for item in rows:
        tip = datetime.fromisoformat(item["DateUtc"])
        if tip.utcoffset() is None:
            raise ValueError("Timezone-aware schedule required")
        home, away = item["HomeTeam"], item["AwayTeam"]
        if not isinstance(home, str) or not isinstance(away, str) or home == away:
            raise ValueError("Invalid participants")
        if (tip.year != 2022 and captured <= tip-timedelta(minutes=60)
                and item.get("HomeTeamScore") is None and item.get("AwayTeamScore") is None
                and item.get("Winner") in (None, "")):
            future.add((tip.isoformat(), home, away))
    return {"archive_captured_at": captured.isoformat(), "payload_sha256": sha256(raw),
            "candidate_future_unscored_rows": len(future),
            "candidate_fixtures": [list(v) for v in sorted(future)],
            "historical_publication_first_seen": "UNKNOWN",
            "source_admitted": False, "schedule_reconciliation": "NOT_PERFORMED"}


def acquire_inventory(directory: Path, years: list[int], *, private_research: bool,
                      client: httpx.Client | None = None) -> dict:
    if not private_research:
        raise ValueError("Private noncommercial research scope required")
    if not years or any(y not in (2023, 2024, 2025) for y in years):
        raise ValueError("Only new 2023-2025 season families are supported")
    directory.mkdir(parents=True, exist_ok=True)
    owned = client is None
    client = client or httpx.Client(timeout=45, follow_redirects=False)
    now = datetime.now(UTC)
    report = {"retrieved_at": now.isoformat(), "use_scope": "private_noncommercial",
              "redistribution_allowed": False, "outcomes_used_for_selection": False,
              "periods_locked": False, "source_admitted_games": 0,
              "status": "INVENTORY_ONLY", "queries": [], "captures": [], "failures": []}
    try:
        terms = client.get(TERMS)
        terms.raise_for_status()
        report["terms"] = {"url": TERMS, "sha256": sha256(terms.content),
                           "local_path": save(directory, "terms.html", terms.content),
                           "retrieved_at": now.isoformat(), "review_required": True}
        for year in sorted(set(years)):
            prefix = f"https://fixturedownload.com/feed/json/nba-{year}"
            params = {"url": prefix.removeprefix("https://"), "matchType": "prefix",
                      "output": "json", "filter": "statuscode:200", "from": str(year),
                      "to": str(year+1), "limit": "2000"}
            receipt = {"url": CDX, "params": params, "retrieved_at": datetime.now(UTC).isoformat()}
            try:
                response = client.get(CDX, params=params)
                receipt["http_status"] = response.status_code
                receipt["response_path"] = save(directory, "cdx-response", response.content)
                receipt["response_sha256"] = sha256(response.content)
                response.raise_for_status()
                index = response.json()
                receipt["rows"] = max(0, len(index)-1)
                receipt["possibly_truncated"] = receipt["rows"] >= 2000
                if receipt["possibly_truncated"]:
                    raise ValueError("Index limit reached: partition search before acquisition")
                for values in index[1:]:
                    row = dict(zip(index[0], values, strict=True))
                    url = f"https://web.archive.org/web/{row['timestamp']}id_/{row['original']}"
                    try:
                        captured = datetime.strptime(row["timestamp"], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
                        if captured > now:
                            raise ValueError("Future archive timestamp")
                        body = client.get(url)
                        body.raise_for_status()
                        evidence = validate_schedule(body.content, row, index, prefix)
                        evidence.update({"original": row["original"], "replay_url": url,
                                         "cdx": row, "index_sha256": receipt["response_sha256"],
                                         "retrieved_at": datetime.now(UTC).isoformat(),
                                         "local_path": save(directory, "schedule.json", body.content),
                                         "terms_sha256": report["terms"]["sha256"],
                                         "use_scope": "private_noncommercial"})
                        report["captures"].append(evidence)
                    except (ValueError, KeyError, TypeError, httpx.HTTPError) as exc:
                        report["failures"].append({"url": url, "reason": str(exc)})
            except (ValueError, TypeError, httpx.HTTPError) as exc:
                receipt["error"] = str(exc)
            report["queries"].append(receipt)
            save(directory, "query-receipt.json", receipt)
    finally:
        if owned:
            client.close()
    report["candidate_unique_fixtures"] = len({tuple(v) for capture in report["captures"]
                                                 for v in capture["candidate_fixtures"]})
    report["inventory_path"] = save(directory, "inventory.json", report)
    return report


def inventory_history(directory: Path) -> list[dict]:
    """Reverify existing score-capture bytes/indexes without parsing target outcomes."""
    from .historical_availability import load_capture_index, verify_capture
    index = load_capture_index(directory)
    records = []
    for path in sorted(directory.glob("*.metadata.json")):
        metadata = json.loads(path.read_text())
        row = metadata["cdx"]
        if int(row["timestamp"][:4]) <= 2022:
            continue
        raw = (directory/f"{row['timestamp']}.csv").read_bytes()
        verify_capture(raw, row, index)
        captured = datetime.strptime(row["timestamp"], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        retrieved = datetime.fromisoformat(metadata["retrieved_at"])
        expected = f"https://web.archive.org/web/{row['timestamp']}id_/{row['original']}"
        if retrieved.utcoffset() is None or retrieved < captured or metadata["url"] != expected:
            raise ValueError("Invalid score capture acquisition receipt")
        records.append({"original": row["original"], "archive_captured_at": captured.isoformat(),
                        "replay_url": expected, "retrieved_at": retrieved.isoformat(),
                        "payload_sha256": sha256(raw), "receipt_sha256": sha256(path.read_bytes()),
                        "use_scope": "private_noncommercial", "role": "candidate_score_history",
                        "license_review": "REQUIRED_FOR_NEW_CAPTURE_ADMISSION",
                        "license_candidates": ["MIT (Neil Paine)", "CC BY 4.0 (FiveThirtyEight)"],
                        "source_admitted": False, "target_outcomes_parsed": False})
    return records


def temporal_support(report: dict, history: list[dict], maximum_age_days: int = 7) -> dict:
    """Necessary timestamp compatibility only, not sufficient team-history eligibility."""
    if maximum_age_days <= 0:
        raise ValueError("History age must be positive")
    fixtures = {tuple(v) for c in report["captures"] for v in c["candidate_fixtures"]}
    instants = [datetime.fromisoformat(c["archive_captured_at"]) for c in history]
    supported = 0
    for tip, _, _ in fixtures:
        cutoff = datetime.fromisoformat(tip)-timedelta(minutes=60)
        if any(t <= cutoff <= t+timedelta(days=maximum_age_days) for t in instants):
            supported += 1
    return {"maximum_history_capture_age_days": maximum_age_days,
            "schedule_candidates": len(fixtures),
            "timestamp_compatible_history_candidates": supported,
            "team_history_and_source_admission_verified": False,
            "sample_lock_ready": False}
