"""Opt-in free-tier NBA game ID exporter. Source independence is NOT inferred."""
import json
import os
import time
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from .independent_regular_season import ExternalEvent, ReferenceProvenance
from .result_sources import sha256, write_once
from .results import ALIASES, TEAMS
from .season_audit import load_contract

ENDPOINT = "https://api.balldontlie.io/v1/games"
DOCS = "https://docs.balldontlie.io/"
TERMS = "https://www.balldontlie.io/terms.html"
MIN_INTERVAL_SECONDS = 12.5  # Free plan: max 5 calls per minute.


class ProviderDateMismatch(ValueError):
    """Two date claims disagree; keep both as evidence, never guess the canonical date."""

    def __init__(self, provider_date: date, new_york_date: date):
        self.provider_date = provider_date
        self.new_york_date = new_york_date
        super().__init__("Provider date and New York tipoff date differ: review required")



def dry_run(start_year: int = 2020, end_year: int = 2025) -> dict:
    if not (2020 <= start_year <= end_year <= 2025):
        raise ValueError("Only completed seasons 2020-21 through 2025-26")
    specs = {s["season_end_year"]: s for s in load_contract()["seasons"]}
    games = sum(specs[y + 1]["regular_expected_games"] for y in range(start_year, end_year + 1))
    min_pages = sum((specs[y + 1]["regular_expected_games"] + 99) // 100
                    for y in range(start_year, end_year + 1))
    return {"status": "DRY_RUN_NO_NETWORK", "provider": "balldontlie-nba",
            "seasons": list(range(start_year, end_year + 1)),
            "expected_regular_games": games, "minimum_pages": min_pages,
            "endpoint": ENDPOINT, "free_tier": True,
            "api_key_required": True, "lineage_review": "REQUIRED",
            "note": "Historical game-ID coverage and rights remain unverified until imported"}


def normalize(row: dict, season: int, cup_keys: set[str]):
    if not isinstance(row, dict):
        raise TypeError("Invalid provider record")
    raw_id = row.get("id")
    if not isinstance(raw_id, int) or raw_id <= 0:
        raise ValueError("Missing valid provider event ID")
    if row.get("season") != season:
        raise ValueError("Provider season disagrees with request")
    if row.get("postseason") is True:
        raise ValueError("Non-regular event in regular-season response")
    if row.get("status_state") not in ("final", None) and row.get("status") != "Final":
        raise ValueError("Historical NBA game is not final")
    day = date.fromisoformat(row["date"])
    stamp = row.get("datetime")
    if stamp:
        tipoff = datetime.fromisoformat(stamp)
        if tipoff.utcoffset() is None:
            raise ValueError("Provider tipoff missing timezone")
        local_day = tipoff.astimezone(ZoneInfo("America/New_York")).date()
        if local_day != day:
            raise ProviderDateMismatch(day, local_day)
    def team(side):
        abbreviation = row[side]["abbreviation"]
        key = ALIASES.get(abbreviation, abbreviation)
        if key not in TEAMS:
            raise ValueError("Unrecognized team abbreviation")
        return key
    event = ExternalEvent(provider_event_id=f"bdl:{raw_id}",
                          season_end_year=season + 1, game_date=day,
                          home=team("home_team"), away=team("visitor_team"),
                          phase="regular_season")
    if row.get("ist_stage") == "Championship" or event.game_key in cup_keys:
        return None
    return event


def acquire(output: Path, api_key: str, *, start_year: int = 2020,
            end_year: int = 2025, max_requests: int = 100,
            client: httpx.Client | None = None, sleep=time.sleep) -> dict:
    """Fetch only authorized free Games endpoint; fail without writing partial data."""
    dry_run(start_year, end_year)
    if not api_key or not api_key.strip():
        raise ValueError("BALLDONTLIE_API_KEY is required")
    if max_requests < 1:
        raise ValueError("max_requests must be >= 1")
    if (output / "events.json").exists() or (output / "provenance.json").exists():
        raise FileExistsError("Existing snapshot; choose a new local output directory")
    owned = client is None
    client = client or httpx.Client(timeout=30, follow_redirects=False)
    receipts, records, excluded = [], [], 0
    date_quarantine = []
    seen_ids = set()
    cups = {x["game_key"] for x in load_contract()["cup_finals"]}
    try:
        for season in range(start_year, end_year + 1):
            cursor, visited = None, set()
            while True:
                if len(receipts) >= max_requests:
                    raise RuntimeError("API request budget exhausted before pagination completed")
                params = {"seasons[]": season, "season_type": "regular", "per_page": 100}
                if cursor is not None:
                    if cursor in visited:
                        raise ValueError("Repeated pagination cursor")
                    visited.add(cursor)
                    params["cursor"] = cursor
                if receipts:
                    sleep(MIN_INTERVAL_SECONDS)
                response = client.get(ENDPOINT, params=params,
                                      headers={"Authorization": api_key})
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                    raise TypeError("Invalid provider payload")
                for row in payload["data"]:
                    # Duplicate provider IDs are fatal, even if an observation is quarantined.
                    raw_id = row.get("id") if isinstance(row, dict) else None
                    if not isinstance(raw_id, int) or raw_id <= 0:
                        raise ValueError("Missing valid provider event ID")
                    if raw_id in seen_ids:
                        raise ValueError("Duplicate provider event ID")
                    seen_ids.add(raw_id)
                    try:
                        event = normalize(row, season, cups)
                    except ProviderDateMismatch as conflict:
                        date_quarantine.append({
                            "provider_event_id": f"bdl:{raw_id}",
                            "season_end_year": season + 1,
                            "provider_date": str(conflict.provider_date),
                            "new_york_tipoff_date": str(conflict.new_york_date),
                            "provider_datetime": row.get("datetime"),
                            "home_team_abbreviation": (
                                row.get("home_team") or {}).get("abbreviation"),
                            "away_team_abbreviation": (
                                row.get("visitor_team") or {}).get("abbreviation"),
                            "reason": "PROVIDER_DATE_VS_NEW_YORK_TIPOFF",
                            "approved": False,
                        })
                        continue
                    if event is None:
                        excluded += 1
                        continue
                    records.append(event)
                meta = payload.get("meta")
                if not isinstance(meta, dict):
                    raise TypeError("Missing pagination metadata")
                receipts.append({"season": season, "cursor": cursor,
                                 "response_sha256": sha256(response.content),
                                 "rows": len(payload["data"]),
                                 "next_cursor": meta.get("next_cursor")})
                cursor = meta.get("next_cursor")
                if cursor in (None, ""):
                    break
    finally:
        if owned:
            client.close()
    normalized = [e.model_dump(mode="json") for e in sorted(
        records, key=lambda e: (e.season_end_year, e.game_date, e.provider_event_id))]
    raw = json.dumps(normalized, sort_keys=True, indent=2).encode()
    manifest = ReferenceProvenance(
        schema_version=1, provider_id="balldontlie-nba", source_url=DOCS,
        terms_url=TERMS,
        license_scope="provider_permits_lawful_analytics_third_party_rights_unverified",
        source_sha256=sha256(raw), acquired_at=datetime.now(UTC),
        lineage_reviewed=False, derived_from=[])
    report = {"status": "ACQUIRED_UNREVIEWED", "provider": "balldontlie-nba",
              "request_count": len(receipts), "events": len(normalized),
              "cup_finals_excluded": excluded,
              "quarantined_date_mismatches": len(date_quarantine),
              "date_quarantine_by_season": dict(sorted(Counter(
                  r["season_end_year"] for r in date_quarantine).items())),
              "counts_by_season": dict(sorted(Counter(
                  r["season_end_year"] for r in normalized).items())),
              "source_sha256": sha256(raw),
              "independence_verified": False, "training_eligible": False,
              "request_receipts": receipts}
    # All data is local under ignored data/; no source records go to the public API.
    write_once(output / "events.json", raw)
    write_once(output / "date-quarantine.json",
               json.dumps(sorted(date_quarantine, key=lambda r: (
                   r["season_end_year"], r["provider_event_id"])),
                   sort_keys=True, indent=2).encode())
    write_once(output / "provenance.json", manifest.model_dump_json(indent=2).encode())
    write_once(output / "request-receipts.json",
               json.dumps(report, sort_keys=True, indent=2).encode())
    return {k: v for k, v in report.items() if k != "request_receipts"}


def run(output: Path, execute: bool, start_year: int, end_year: int,
        max_requests: int) -> dict:
    if not execute:
        return dry_run(start_year, end_year)
    api_key = os.environ.get("BALLDONTLIE_API_KEY", "")
    if not api_key:
        raise ValueError("BALLDONTLIE_API_KEY missing; create a free key and set it locally")
    return acquire(output, api_key, start_year=start_year, end_year=end_year,
                   max_requests=max_requests)
