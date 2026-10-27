"""FixtureDownload personal/non-commercial exports. Never publish their raw records.

User authorized private non-commercial research on 2026-10-27. Website terms permit
personal downloads, not commercial reuse or public redistribution. Keep all bundles
under ignored data/ and exclude these observations from the read-only API.
"""
import json
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from .result_sources import sha256, write_once
from .results import BasicResult, audit

NAMES = dict(zip([
    "Atlanta Hawks", "Boston Celtics", "Brooklyn Nets", "Charlotte Hornets", "Chicago Bulls",
    "Cleveland Cavaliers", "Dallas Mavericks", "Denver Nuggets", "Detroit Pistons",
    "Golden State Warriors", "Houston Rockets", "Indiana Pacers", "Los Angeles Clippers",
    "Los Angeles Lakers", "Memphis Grizzlies", "Miami Heat", "Milwaukee Bucks",
    "Minnesota Timberwolves", "New Orleans Pelicans", "New York Knicks", "Oklahoma City Thunder",
    "Orlando Magic", "Philadelphia 76ers", "Phoenix Suns", "Portland Trail Blazers",
    "Sacramento Kings", "San Antonio Spurs", "Toronto Raptors", "Utah Jazz", "Washington Wizards",
], ['ATL', 'BOS', 'BKN', 'CHA', 'CHI', 'CLE', 'DAL', 'DEN', 'DET', 'GSW', 'HOU', 'IND', 'LAC', 'LAL', 'MEM', 'MIA', 'MIL', 'MIN', 'NOP', 'NYK', 'OKC', 'ORL', 'PHI', 'PHX', 'POR', 'SAC', 'SAS', 'TOR', 'UTA', 'WAS'], strict=True))
NAMES["LA Clippers"] = "LAC"
TERMS_URL = "https://fixturedownload.com/terms"


def acquire_private(directory: Path, season: int, private_research: bool,
                    client: httpx.Client | None = None) -> Path:
    if not private_research:
        raise ValueError("Private non-commercial research scope required")
    if season not in range(2020, 2027):
        raise ValueError("Season start year must be 2020–2026")
    directory = directory / str(season)
    path = directory / "manifest.json"
    if path.exists():
        verify_private(directory)
        return path
    owned = client is None
    client = client or httpx.Client(timeout=60, follow_redirects=False)
    try:
        response = client.get(f"https://fixturedownload.com/feed/json/nba-{season}")
        response.raise_for_status()
        raw = response.content
        received = datetime.now(UTC).isoformat()
        if not isinstance(response.json(), list):
            raise TypeError("Expected fixture JSON array")
        terms = client.get(TERMS_URL)
        terms.raise_for_status()
        # Preserve exact terms alongside each local acquisition; no redistribution.
        if b"personal and non-commercial" not in terms.content:
            raise ValueError("Personal download terms changed; review before importing")
    finally:
        if owned:
            client.close()
    manifest = {"schema_version": 1, "source": "fixturedownload-private",
                "url": f"https://fixturedownload.com/feed/json/nba-{season}",
                "season_start_year": season, "sha256": sha256(raw), "bytes": len(raw),
                "retrieved_at": received, "terms_url": TERMS_URL,
                "terms_sha256": sha256(terms.content), "use_scope": "private_noncommercial",
                "redistribution_allowed": False, "historical_availability_verified": False,
                "attribution": "FixtureDownload.com — private personal non-commercial research only",
                "schedule_timezone": "UTC", "event_calendar_timezone": "America/New_York"}
    write_once(directory / "source.json", raw)
    write_once(directory / "terms.html", terms.content)
    write_once(path, json.dumps(manifest, sort_keys=True, indent=2).encode())
    return path


def verify_private(directory: Path) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text())
    year = manifest["season_start_year"]
    if (manifest["source"] != "fixturedownload-private" or year not in range(2020, 2027)
            or manifest["use_scope"] != "private_noncommercial"
            or manifest["redistribution_allowed"] is not False
            or manifest["url"] != f"https://fixturedownload.com/feed/json/nba-{year}"
            or manifest["terms_url"] != TERMS_URL):
        raise ValueError("Unapproved private source manifest")
    if sha256((directory / "source.json").read_bytes()) != manifest["sha256"]:
        raise ValueError("Private source checksum mismatch")
    if sha256((directory / "terms.html").read_bytes()) != manifest["terms_sha256"]:
        raise ValueError("Private source terms checksum mismatch")
    return manifest


def parse_private(rows: list[dict], manifest: dict, start: date, end: date):
    retrieved = datetime.fromisoformat(manifest["retrieved_at"])
    if retrieved.utcoffset() is None or start > end or end > retrieved.date():
        raise ValueError("Invalid aware acquisition timestamp or interval")
    results, errors, excluded = [], [], Counter()
    ids = set()
    for number, row in enumerate(rows, start=1):
        try:
            event_id = str(row["MatchNumber"])
            if event_id in ids:
                raise ValueError("Duplicate source match number")
            ids.add(event_id)
            tipoff = datetime.fromisoformat(row["DateUtc"])
            if tipoff.utcoffset() is None:
                raise ValueError("Fixture date lacks explicit UTC timezone")
            # Source explicitly labels DateUtc as scheduled UTC; never call it actual tipoff.
            day = tipoff.astimezone(ZoneInfo("America/New_York")).date()
            scores = (row.get("HomeTeamScore"), row.get("AwayTeamScore"))
            if all(x is None for x in scores):
                excluded["unscored_or_future_fixture"] += 1
                continue
            if any(x is None for x in scores):
                raise ValueError("Partially scored fixture")
            if tipoff > retrieved:
                raise ValueError("Scored fixture scheduled after acquisition")
            if not start <= day <= end:
                excluded["outside_interval"] += 1
                continue
            home, away = NAMES[row["HomeTeam"]], NAMES[row["AwayTeam"]]
            points = {home: scores[0], away: scores[1]}
            if row.get("Winner") not in (None, "", row["HomeTeam"] if scores[0] > scores[1]
                                         else row["AwayTeam"]):
                raise ValueError("Winner contradicts final scores")
            a, b = sorted((home, away))
            results.append(BasicResult(
                source="fixturedownload-private", source_snapshot_sha256=manifest["sha256"],
                source_row_numbers=[number], game_key=f"nba:{day}:{a}:{b}", game_date=day,
                date_basis="scheduled_america_new_york_date",
                season_end_year=manifest["season_start_year"]+1,
                team_a=a, team_b=b, points_a=points[a], points_b=points[b],
                designated_home=home, neutral=None, phase="unknown", venue=row.get("Location") or None,
                scheduled_tipoff=tipoff, retrieved_at=retrieved, available_at=retrieved))
        except (KeyError, ValueError, TypeError) as exc:
            errors.append({"row": number, "error": str(exc)})
    return results, {"source_rows": len(rows), "excluded": dict(excluded),
                     "accepted_games": len(results), "errors": errors}


def normalize_private(directory: Path, start: date, end: date):
    manifest = verify_private(directory)
    records, parsing = parse_private(json.loads((directory/"source.json").read_text()),
                                     manifest, start, end)
    report = audit(records, start, end, parsing)
    report["source_manifest"] = manifest
    report["parsing"] = parsing
    # These detailed artifacts stay local, never under public docs/evidence.
    normalized = json.dumps([r.model_dump(mode="json") for r in records], indent=2, sort_keys=True).encode()
    report["normalized_sha256"] = sha256(normalized)
    report["parser_version"] = "private-results-v1"
    identity = sha256(json.dumps(report, sort_keys=True).encode())
    write_once(directory/f"{identity}.normalized.json", normalized)
    write_once(directory/f"{identity}.audit.json", json.dumps(report, indent=2, sort_keys=True).encode())
    return records, report, manifest
