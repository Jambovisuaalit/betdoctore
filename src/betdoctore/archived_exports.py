"""Literal archived HTML exports; no JavaScript execution or live-data fallback.

Private research evidence only. Discovery/capacity never opens outcome manifests.
"""
import base64
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from .capture_inventory import CDX, TERMS, save
from .private_results import NAMES
from .result_sources import sha256

# Retained FixtureDownload terms reviewed for the user-authorized private scope.
PRIVATE_TERMS_SHA256 = "3cc63ebadee16794c698663a400b029a4366a9d70cbf79ee4f0eee010537282c"

ORIGIN = re.compile(r"https://fixturedownload\.com/view/json/nba-(2022|2023|2024|2025)(?:/[a-z0-9-]+)?\Z")

RESULT_ORIGIN = re.compile(r"https://fixturedownload\.com/results/nba-(2022|2023|2024|2025)(?:/[a-z0-9-]+)?\Z")


class LiteralJSON(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.active = False
        self.buffers = []

    def handle_starttag(self, tag, attrs):
        if tag == "textarea":
            if self.active:
                raise ValueError("Nested textarea")
            self.active = True
            self.buffers.append([])

    def handle_endtag(self, tag):
        if tag == "textarea":
            self.active = False

    def handle_data(self, data):
        if self.active:
            self.buffers[-1].append(data)


def parse_export(raw: bytes, row: dict, index: list) -> dict:
    """Hash the original HTML, then decode one literal textarea JSON array."""
    match = ORIGIN.fullmatch(row["original"])
    if not match or row["statuscode"] != "200" or row["mimetype"] != "text/html":
        raise ValueError("Unapproved HTML export")
    if row not in [dict(zip(index[0], v, strict=True)) for v in index[1:]]:
        raise ValueError("Capture absent from fetched index")
    digest = base64.b32encode(hashlib.sha1(raw).digest()).decode().rstrip("=")
    if digest != row["digest"]:
        raise ValueError("Original HTML digest mismatch")
    captured = datetime.strptime(row["timestamp"], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    if captured.year <= 2022:
        raise ValueError("Development-year capture excluded")
    parser = LiteralJSON()
    parser.feed(raw.decode("utf-8-sig"))
    parser.close()
    if len(parser.buffers) != 1 or parser.active:
        raise ValueError("Exactly one closed literal JSON textarea required")
    values = json.loads("".join(parser.buffers[0]))
    if not isinstance(values, list):
        raise TypeError("Embedded export must be a JSON array")
    records = normalize_rows(values, int(match[1]), captured, sha256(raw))
    return {"original": row["original"], "archive_captured_at": captured.isoformat(),
            "payload_sha256": sha256(raw), "rows": records,
            "phase_verified": False, "actual_tipoff_verified": False,
            "source_admitted": False, "use_scope": "private_noncommercial"}


def normalize_rows(values: list, season: int, captured: datetime, payload_sha256: str,
                   provider_ids: bool = True) -> list[dict]:
    """Common identities for literal HTML and original JSON, retaining original hashes."""
    records, ids = [], set()
    for number, value in enumerate(values, 1):
        event = value["MatchNumber"] if provider_ids else number
        if type(event) is not int or event <= 0 or event in ids:
            raise ValueError("Invalid or duplicate provider identity")
        ids.add(event)
        tip = datetime.fromisoformat(value["DateUtc"])
        if tip.utcoffset() != timedelta(0):
            raise ValueError("DateUtc must explicitly identify UTC")
        home, away = NAMES[value["HomeTeam"]], NAMES[value["AwayTeam"]]
        if home == away:
            raise ValueError("Identical participants")
        day = tip.astimezone(ZoneInfo("America/New_York")).date()
        a, b = sorted((home, away))
        points = [value["HomeTeamScore"], value["AwayTeamScore"]]
        if any(v is not None for v in points):
            if (any(type(v) is not int or v <= 0 for v in points)
                    or points[0] == points[1] or tip > captured):
                raise ValueError("Malformed or future-scored game")
            winner = value["HomeTeam"] if points[0] > points[1] else value["AwayTeam"]
            if value.get("Winner") not in (None, "", winner):
                raise ValueError("Winner contradicts captured scores")
        elif value.get("Winner") not in (None, ""):
            raise ValueError("Winner without scores")
        if not datetime(season, 10, 1).date() <= day <= datetime(season+1, 7, 1).date():
            raise ValueError("Event outside declared season")
        records.append({"provider_id": f"nba-{season}:{event}" if provider_ids else None,
                        "eligible_as_target": provider_ids,
                        "game_key": f"nba:{day}:{a}:{b}", "game_date": day.isoformat(),
                        "home": home, "away": away, "teams": [a, b],
                        "season_end_year": season+1,
                        "scheduled_tipoff": tip.astimezone(UTC).isoformat(),
                        "total": None if points[0] is None else sum(points),
                        "score_identity": None if points[0] is None else [points[0], points[1]],
                        "source_row": number, "snapshot_sha256": payload_sha256,
                        "public_available_by": captured.isoformat(),
                        "result_status": "SCORE_OBSERVED_NOT_EXPLICIT_FINAL_STATUS"})
    return records


def discover_exports(directory: Path, year: int, client: httpx.Client,
                     kind: str = "view/json") -> dict:
    if year not in (2022, 2023, 2024, 2025):
        raise ValueError("New season family required")
    if kind not in ("view/json", "results"):
        raise ValueError("Unsupported archived representation")
    params = {"url": f"fixturedownload.com/{kind}/nba-{year}", "matchType": "prefix",
              "output": "json", "filter": "statuscode:200", "from": str(max(year, 2023)),
              "to": str(year+1), "limit": "2000"}
    receipt = {"url": CDX, "params": params, "retrieved_at": datetime.now(UTC).isoformat()}
    try:
        response = client.get(CDX, params=params)
        receipt["http_status"] = response.status_code
        receipt["response_sha256"] = sha256(response.content)
        receipt["response_path"] = save(directory, "cdx-response", response.content)
        response.raise_for_status()
        index = response.json()
        if not isinstance(index, list):
            raise TypeError("CDX array required")
        receipt["rows"] = max(0, len(index)-1)
        if receipt["rows"] >= 2000:
            raise ValueError("Possibly truncated index; partition before use")
        receipt["index"] = index
    except (ValueError, TypeError, httpx.HTTPError) as exc:
        receipt["error"] = str(exc)
    receipt["receipt_path"] = save(directory, "discovery.json", receipt)
    return receipt


def acquire_export(directory: Path, row: dict, index: list, terms: bytes,
                   client: httpx.Client) -> dict:
    """Requires source terms reviewed separately before any subsequent admission."""
    if not (ORIGIN.fullmatch(row["original"]) or RESULT_ORIGIN.fullmatch(row["original"])):
        raise ValueError("Unapproved origin")
    captured = datetime.strptime(row["timestamp"], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    if captured > datetime.now(UTC):
        raise ValueError("Future capture")
    url = f"https://web.archive.org/web/{row['timestamp']}id_/{row['original']}"
    response = client.get(url)
    response.raise_for_status()
    parser = parse_results if RESULT_ORIGIN.fullmatch(row["original"]) else parse_export
    # Retain failed responses for forensic review; they are never capture receipts.
    response_path = save(directory, "archive-response", response.content)
    try:
        snapshot = parser(response.content, row, index)
    except (ValueError, KeyError, TypeError) as exc:
        save(directory, "rejected-response.json", {"url": url, "cdx": row,
             "payload_path": response_path, "payload_sha256": sha256(response.content),
             "retrieved_at": datetime.now(UTC).isoformat(), "error": str(exc),
             "source_admitted": False})
        raise
    receipt = {"url": url, "cdx": row, "index_path": save(directory, "cdx.json", index),
               "index_sha256": sha256(json.dumps(index, sort_keys=True, indent=2).encode()),
               "payload_path": save(directory, "export.html", response.content),
               "payload_sha256": snapshot["payload_sha256"],
               "retrieved_at": datetime.now(UTC).isoformat(),
               "terms_url": TERMS, "terms_sha256": sha256(terms),
               "terms_path": save(directory, "terms.html", terms),
               "terms_review": "REQUIRED_BEFORE_ADMISSION",
               "use_scope": "private_noncommercial", "redistribution_allowed": False}
    snapshot["receipt_path"] = save(directory, "capture-receipt.json", receipt)
    snapshot["private_terms_verified"] = sha256(terms) == PRIVATE_TERMS_SHA256
    return snapshot


def load_export(directory: Path, receipt_path: Path) -> dict:
    receipt = json.loads(receipt_path.read_text())
    if receipt["use_scope"] != "private_noncommercial" or receipt["redistribution_allowed"]:
        raise ValueError("Unsupported source scope")
    def read_local(name):
        if Path(name).name != name:
            raise ValueError("Local artifact basename required")
        return (directory/name).read_bytes()
    if (sha256(read_local(receipt["terms_path"])) != receipt["terms_sha256"]
            or receipt["terms_url"] != TERMS):
        raise ValueError("Source terms integrity mismatch")
    index_bytes = read_local(receipt["index_path"])
    raw = read_local(receipt["payload_path"])
    if (sha256(index_bytes) != receipt["index_sha256"]
            or sha256(raw) != receipt["payload_sha256"]):
        raise ValueError("Capture/index SHA-256 mismatch")
    row = receipt["cdx"]
    expected_url = f"https://web.archive.org/web/{row['timestamp']}id_/{row['original']}"
    captured = datetime.strptime(row["timestamp"], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    retrieved = datetime.fromisoformat(receipt["retrieved_at"])
    if retrieved.utcoffset() is None or retrieved < captured or receipt["url"] != expected_url:
        raise ValueError("Invalid acquisition receipt")
    parser = parse_results if RESULT_ORIGIN.fullmatch(row["original"]) else parse_export
    snapshot = parser(raw, row, json.loads(index_bytes))
    snapshot["receipt_path"] = receipt_path.name
    snapshot["private_terms_verified"] = receipt["terms_sha256"] == PRIVATE_TERMS_SHA256
    return snapshot


def history_capacity(snapshots: list[dict], maximum_age_days: int = 7, *,
                     include_history: bool = False) -> dict:
    """Outcome-blind feasibility only; no predictions, locked periods or accuracy."""
    if maximum_age_days <= 0:
        raise ValueError("Positive history age required")
    from .season_audit import load_contract
    excluded_keys = {r["game_key"] for r in load_contract()["cup_finals"]}
    all_rows = [row for snapshot in snapshots for row in snapshot["rows"]
                if row["game_key"] not in excluded_keys]
    candidates = {}
    for row in all_rows:
        stamp = datetime.fromisoformat(row["public_available_by"])
        cutoff = datetime.fromisoformat(row["scheduled_tipoff"])-timedelta(minutes=60)
        if (row.get("eligible_as_target", True) and row["total"] is None and stamp <= cutoff
                and not row["game_date"].startswith("2022-")):
            identity = row["provider_id"]
            if identity not in candidates or stamp < datetime.fromisoformat(candidates[identity]["public_available_by"]):
                candidates[identity] = row
    from collections import Counter
    key_counts = Counter(r["game_key"] for r in candidates.values())
    accepted, excluded = [], []
    for identity, target in sorted(candidates.items()):
        if key_counts[target["game_key"]] > 1:
            excluded.append({"provider_id": identity, "reason": "AMBIGUOUS_PROVIDER_IDS_FOR_GAME"})
            continue
        cutoff = datetime.fromisoformat(target["scheduled_tipoff"])-timedelta(minutes=60)
        known = [r for r in all_rows if datetime.fromisoformat(r["public_available_by"]) <= cutoff]
        target_rows = [r for r in known if r["provider_id"] == identity
                       or r["game_key"] == target["game_key"]]
        if any(r["total"] is not None or (r["home"], r["away"], r["scheduled_tipoff"])
               != (target["home"], target["away"], target["scheduled_tipoff"]) for r in target_rows):
            excluded.append({"provider_id": identity, "reason": "TARGET_ALREADY_SCORED_OR_REVISED"})
            continue
        history = {}
        conflicts = set()
        for row in known:
            stamp = datetime.fromisoformat(row["public_available_by"])
            if (row["total"] is None or row["game_key"] == target["game_key"]
                    or row["season_end_year"] != target["season_end_year"]
                    or cutoff-stamp > timedelta(days=maximum_age_days)
                    or row["game_date"] >= stamp.astimezone(ZoneInfo("America/New_York")).date().isoformat()):
                continue
            key = row["game_key"]
            if (key in history and (history[key]["score_identity"], history[key]["home"])
                    != (row["score_identity"], row["home"])):
                conflicts.add(key)
            history[key] = row
        if conflicts:
            excluded.append({"provider_id": identity, "reason": "CONFLICTING_CAPTURED_HISTORY"})
            continue
        counts = {t: sum(t in r["teams"] for r in history.values()) for t in target["teams"]}
        if min(counts.values()) < 5:
            excluded.append({"provider_id": identity, "reason": "INSUFFICIENT_FRESH_TEAM_HISTORY"})
            continue
        accepted.append({"game_key": target["game_key"], "provider_id": identity,
                         "cutoff": cutoff.isoformat(), "team_history_counts": counts,
                         "history_games": len(history),
                         "input_capture_sha256": sorted({r["snapshot_sha256"] for r in history.values()})})
        if include_history:
            accepted[-1]["target"] = target
            accepted[-1]["causal_history"] = sorted(history.values(), key=lambda r: (r["game_date"], r["game_key"]))
    return {"status": "CAPACITY_ONLY_NOT_ADMITTED", "candidate_games": len(key_counts),
            "fresh_history_capacity_games": len(accepted), "maximum_age_days": maximum_age_days,
            "candidates_with_history": accepted, "excluded": excluded,
            "periods_locked": False, "predictions_frozen": False, "source_admitted_games": 0,
            "outcome_manifest_opened": False, "production_ready": False,
            "private_source_terms_verified": bool(snapshots) and all(
                s.get("private_terms_verified", False) for s in snapshots),
            "pending_checks": ["captured score semantics and integrity",
                               "regular-season membership", "historical schedule reconciliation"]}


def load_feed_inventory(directory: Path, path: Path) -> list[dict]:
    """Reverify already acquired original feed bytes; never synthesize HTML proofs."""
    from .capture_inventory import validate_schedule
    inventory = json.loads(path.read_text())
    if inventory["use_scope"] != "private_noncommercial" or inventory["redistribution_allowed"]:
        raise ValueError("Private source scope required")
    terms = inventory["terms"]
    if Path(terms["local_path"]).name != terms["local_path"]:
        raise ValueError("Local terms basename required")
    if sha256((directory/terms["local_path"]).read_bytes()) != terms["sha256"]:
        raise ValueError("Feed terms integrity mismatch")
    snapshots = []
    for item in inventory["captures"]:
        row = item["cdx"]
        match = re.fullmatch(r"https://fixturedownload\.com/feed/json/nba-(2022|2023|2024|2025)(?:/[a-z0-9-]+)?", row["original"])
        if not match:
            raise ValueError("Unapproved feed origin")
        season = int(match[1])
        if not max(f"{season}1001000000", "20230101000000") <= row["timestamp"] < f"{season+1}0416000000":
            continue
        if Path(item["local_path"]).name != item["local_path"]:
            raise ValueError("Local payload basename required")
        raw = (directory/item["local_path"]).read_bytes()
        index_hash = item["index_sha256"]
        if not re.fullmatch("[0-9a-f]{64}", index_hash):
            raise ValueError("Invalid index identifier")
        index_bytes = (directory/f"{index_hash}.cdx-response").read_bytes()
        if sha256(index_bytes) != index_hash or sha256(raw) != item["payload_sha256"]:
            raise ValueError("Feed payload/index SHA-256 mismatch")
        validate_schedule(raw, row, json.loads(index_bytes),
                          f"https://fixturedownload.com/feed/json/nba-{season}")
        captured = datetime.strptime(row["timestamp"], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        retrieved = datetime.fromisoformat(item["retrieved_at"])
        expected_url = f"https://web.archive.org/web/{row['timestamp']}id_/{row['original']}"
        if (retrieved.utcoffset() is None or retrieved < captured
                or item["replay_url"] != expected_url or item["terms_sha256"] != terms["sha256"]):
            raise ValueError("Invalid feed acquisition receipt")
        snapshots.append({"original": row["original"], "archive_captured_at": captured.isoformat(),
                          "payload_sha256": sha256(raw),
                          "rows": normalize_rows(json.loads(raw), season, captured, sha256(raw)),
                          "private_terms_verified": terms["sha256"] == PRIVATE_TERMS_SHA256,
                          "source_admitted": False, "use_scope": "private_noncommercial"})
    return snapshots


class ResultTables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.inside = False
        self.cell = None
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            if self.inside:
                raise ValueError("Nested result tables unsupported")
            self.inside = True
            self.tables.append([])
        elif tag == "tr" and self.inside:
            self.current = []
            self.tables[-1].append(self.current)
        elif tag in ("th", "td") and self.inside:
            if self.current is None:
                raise ValueError("Result cell outside row")
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ("th", "td") and self.cell is not None:
            self.current.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "table":
            self.inside = False

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def parse_results(raw: bytes, row: dict, index: list) -> dict:
    """Only literal UTC tables; source supplies no provider event ID here."""
    match = RESULT_ORIGIN.fullmatch(row["original"])
    if not match or row["mimetype"] != "text/html" or row["statuscode"] != "200":
        raise ValueError("Unapproved results page")
    if row not in [dict(zip(index[0], v, strict=True)) for v in index[1:]]:
        raise ValueError("Results page absent from archive index")
    digest = base64.b32encode(hashlib.sha1(raw).digest()).decode().rstrip("=")
    if digest != row["digest"]:
        raise ValueError("Results page digest mismatch")
    text = raw.decode("utf-8-sig")
    if "Your time zone is not set and will use UTC by default." not in unescape(text):
        raise ValueError("Archived display timezone is not proven UTC")
    parser = ResultTables()
    parser.feed(text)
    parser.close()
    headers = ["Round Number", "Date", "Location", "Home Team", "Away Team", "Result"]
    tables = [t for t in parser.tables if t and t[0] == headers]
    if len(tables) != 1 or parser.inside or parser.cell is not None:
        raise ValueError("One complete expected results table required")
    values = []
    for cells in tables[0][1:]:
        if len(cells) != len(headers):
            raise ValueError("Unexpected result table width")
        item = dict(zip(headers, cells, strict=True))
        score = re.fullmatch(r"([0-9]+) - ([0-9]+)", item["Result"])
        if item["Result"] not in ("", "-") and score is None:
            raise ValueError("Unrecognized result status")
        tip = datetime.strptime(item["Date"], "%d/%m/%Y %H:%M").replace(tzinfo=UTC)
        values.append({"DateUtc": tip.isoformat(), "HomeTeam": item["Home Team"],
                       "AwayTeam": item["Away Team"],
                       "HomeTeamScore": int(score[1]) if score else None,
                       "AwayTeamScore": int(score[2]) if score else None})
    captured = datetime.strptime(row["timestamp"], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    if captured.year <= 2022:
        raise ValueError("Development-year capture excluded")
    records = normalize_rows(values, int(match[1]), captured, sha256(raw), provider_ids=False)
    if len({r["game_key"] for r in records}) != len(records):
        raise ValueError("Duplicate result-table identity")
    return {"original": row["original"], "archive_captured_at": captured.isoformat(),
            "payload_sha256": sha256(raw), "rows": records, "source_admitted": False,
            "phase_verified": False, "actual_tipoff_verified": False,
            "use_scope": "private_noncommercial", "target_identity_authority": False}
