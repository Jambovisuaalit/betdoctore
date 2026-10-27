"""Field-scoped public-capture evidence, without backdating local ingestion."""
import base64
import csv
import hashlib
import io
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import httpx

from .result_sources import sha256, write_once
from .results import ALIASES, TEAMS, BasicResult

ORIGINAL = "https://projects.fivethirtyeight.com/nba-model/nba_elo.csv"
LATEST_ORIGINAL = "https://projects.fivethirtyeight.com/nba-model/nba_elo_latest.csv"
NEIL_ORIGINAL = "https://raw.githubusercontent.com/Neil-Paine-1/NBA-elo/main/nba_elo.csv"
SOURCES = {"fivethirtyeight": (ORIGINAL, "text/csv", 2021, 2023),
           "neil-paine": (NEIL_ORIGINAL, "text/plain", 2023, 2026),
           "fivethirtyeight-latest": (LATEST_ORIGINAL, "text/csv", 2021, 2023)}
CDX_URL = "https://web.archive.org/cdx/search/cdx"
CDX_PARAMS = {"url": ORIGINAL.removeprefix("https://"), "output": "json",
              "filter": "statuscode:200", "collapse": "timestamp:6", "from": "2021", "to": "2023"}


def acquire_captures(directory: Path, client: httpx.Client | None = None,
                     source: str = "fivethirtyeight"):
    if source not in SOURCES:
        raise ValueError("Unapproved historical archive source")
    original, _, start, end = SOURCES[source]
    params = {**CDX_PARAMS, "url": original.removeprefix("https://"), "from": str(start), "to": str(end)}
    owned = client is None
    client = client or httpx.Client(timeout=90, follow_redirects=False)
    try:
        response = client.get(CDX_URL, params=params)
        response.raise_for_status()
        index = response.json()
        index_id = sha256(response.content)
        write_once(directory/f"{index_id}.cdx.json", response.content)
        receipt = {"url": CDX_URL, "params": params, "sha256": index_id,
                   "retrieved_at": datetime.now(UTC).isoformat()}
        # Each CDX lookup has a distinct receipt, even when response bytes repeat.
        receipt_id = sha256(json.dumps(receipt, sort_keys=True).encode())
        write_once(directory/f"{receipt_id}.index-receipt.json", json.dumps(receipt, indent=2).encode())
        records = []
        for values in index[1:]:
            row = dict(zip(index[0], values, strict=True))
            validate_cdx_row(row)
            timestamp = row["timestamp"]
            path = directory/f"{timestamp}.csv"
            metadata_path = directory/f"{timestamp}.metadata.json"
            if path.exists() and metadata_path.exists():
                verify_capture(path.read_bytes(), json.loads(metadata_path.read_text())["cdx"], index)
            else:
                url = f"https://web.archive.org/web/{timestamp}id_/{row['original']}"
                capture = client.get(url)
                capture.raise_for_status()
                verify_capture(capture.content, row, index)
                write_once(path, capture.content)
                write_once(metadata_path, json.dumps({"url": url, "cdx": row,
                    "retrieved_at": datetime.now(UTC).isoformat()}, sort_keys=True, indent=2).encode())
            records.append({"timestamp": timestamp, "sha256": sha256(path.read_bytes()),
                            "cdx_digest": row["digest"], "local_path": path.name})
        return {"index_sha256": index_id, "index_receipt": f"{receipt_id}.index-receipt.json",
                "captures": records}
    finally:
        if owned:
            client.close()


def validate_cdx_row(row: dict):
    approved = [s for s in SOURCES.values() if s[0] == row["original"]]
    if not approved:
        raise ValueError("Unapproved CDX capture")
    _, mime, start, end = approved[0]
    if (row["statuscode"] != "200" or row["mimetype"] != mime
            or len(row["timestamp"]) != 14 or not row["timestamp"].isdigit()
            or not start <= int(row["timestamp"][:4]) <= end):
        raise ValueError("Unapproved CDX capture")


def verify_capture(raw: bytes, row: dict, index: list):
    validate_cdx_row(row)
    if row not in [dict(zip(index[0], values, strict=True)) for values in index[1:]]:
        raise ValueError("Capture absent from fetched archive index")
    # SHA-1 is the archive's payload identifier; SHA-256 also identifies local artifacts.
    actual = base64.b32encode(hashlib.sha1(raw).digest()).decode().rstrip("=")
    if actual != row["digest"]:
        raise ValueError("Archive payload differs from CDX digest")
    if not raw.startswith(b"date,season,neutral,playoff,team1,team2,"):
        raise ValueError("Unexpected historical CSV schema")


def score_identity(game_key: str, points_a: int, points_b: int) -> str:
    return sha256(json.dumps([game_key, points_a, points_b], separators=(",", ":")).encode())


def capture_evidence(directory: Path, index: list) -> tuple[dict, list]:
    earliest, captures = {}, []
    for values in index[1:]:
        row = dict(zip(index[0], values, strict=True))
        validate_cdx_row(row)
        path = directory/f"{row['timestamp']}.csv"
        metadata = json.loads((directory/f"{row['timestamp']}.metadata.json").read_text())
        raw = path.read_bytes()
        verify_capture(raw, metadata["cdx"], index)
        if metadata["cdx"] != row:
            raise ValueError("Capture metadata/index mismatch")
        captured = datetime.strptime(row["timestamp"], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        retrieved = datetime.fromisoformat(metadata["retrieved_at"])
        if retrieved.utcoffset() is None or retrieved < captured:
            raise ValueError("Invalid archive acquisition time")
        capture_sha = sha256(raw)
        expected_url = f"https://web.archive.org/web/{row['timestamp']}id_/{row['original']}"
        if metadata["url"] != expected_url:
            raise ValueError("Unexpected archive replay URL")
        matches = 0
        score_ids = set()
        scores_by_key = {}
        for n, item in enumerate(csv.DictReader(io.StringIO(raw.decode())), start=2):
            if item["score1"] in {"", "NA"} or item["score2"] in {"", "NA"} or item["date"] < "2020-12-01":
                continue
            home, away = (ALIASES.get(item[k], item[k]) for k in ("team1", "team2"))
            if home not in TEAMS or away not in TEAMS or home == away:
                raise ValueError("Unknown historical NBA team")
            points = {home: int(item["score1"]), away: int(item["score2"])}
            if points[home] <= 0 or points[away] <= 0 or points[home] == points[away]:
                raise ValueError("Invalid captured final score")
            if item["date"] > str(captured.date()):
                raise ValueError("Captured snapshot contains a scored future game")
            a, b = sorted((home, away))
            key = f"nba:{item['date']}:{a}:{b}"
            identity = score_identity(key, points[a], points[b])
            if key in scores_by_key and scores_by_key[key] != identity:
                raise ValueError("Conflicting final scores within historical capture")
            scores_by_key[key] = identity
            score_ids.add(identity)
            evidence = {"game_key": key, "score_identity": identity,
                        "field_scope": ["participant_ids", "source_calendar_date", "final_scores"],
                        "evidence_kind": "public_archive_capture", "public_available_by": captured.isoformat(),
                        "first_publication_at": None, "local_receipt_at": metadata["retrieved_at"],
                        "capture_url": metadata["url"], "capture_sha256": capture_sha,
                        "cdx_digest": row["digest"], "source_row": n,
                        "does_not_verify": ["actual_tipoff", "result_completion_time", "schedule_versions",
                                            "first_publication_time", "advanced_statistics"]}
            if identity not in earliest or captured < datetime.fromisoformat(earliest[identity]["public_available_by"]):
                earliest[identity] = evidence
            matches += 1
        captures.append({"captured_at": captured.isoformat(), "sha256": sha256(raw),
                         "cdx_digest": row["digest"], "completed_rows_in_scope": matches, "unique_score_identities": len(score_ids),
                         "original_url": row["original"],
                         "field_scope": "result_scores_only"})
    return earliest, captures


def audit_availability(records: list[BasicResult], earliest: dict, captures: list,
                       quarantined_keys: set[str]) -> dict:
    by_season = defaultdict(lambda: {"game_keys": set(), "captured": set(), "local_only": set(), "capture_times": set()})
    per_game = []
    for record in records:
        identity = score_identity(record.game_key, record.points_a, record.points_b)
        evidence = earliest.get(identity)
        group = by_season[record.season_end_year]
        group["game_keys"].add(record.game_key)
        group["captured" if evidence else "local_only"].add(record.game_key)
        if evidence:
            group["capture_times"].add(evidence["public_available_by"])
        per_game.append({"game_key": record.game_key, "source": record.source,
                         "score_identity": identity, "system_available_at": record.available_at.isoformat(),
                         "public_capture_evidence": evidence,
                         "quarantined": record.game_key in quarantined_keys,
                         "first_publication_at": None,
                         "historical_feature_eligibility": "BLOCKED_METADATA_AND_COVERAGE"})
    summary = {}
    for season, group in sorted(by_season.items()):
        # A mismatching source row cannot inherit another publisher's score proof.
        summary[str(season)] = {"distinct_game_keys": len(group["game_keys"]),
                                "keys_with_matching_captured_score": len(group["captured"]),
                                "keys_with_at_least_one_unproven_observation": len(group["local_only"]),
                                "captured_keys_still_quarantined": len(group["captured"] & quarantined_keys),
                                "unquarantined_keys_with_matching_capture": len(group["captured"] - quarantined_keys),
                                "earliest_matching_capture": min(group["capture_times"]) if group["capture_times"] else None,
                                "latest_available_by_bound_needed": max(group["capture_times"]) if group["capture_times"] else None,
                                "count_note": "Matching and unproven sets can overlap when publishers disagree",
                                "local_receipt_does_not_prove_historical_publication": True}
    return {"schema_version": 1, "captures": captures, "seasons": summary,
            "meaning": "Public available-by upper bound for exact score content; never first publication",
            "local_timestamps_rewritten": False, "historical_schedule_versions_verified": False,
            "historical_first_publication_verified": False,
            "pace_ortg_drtg_availability_verified": False, "ADVANCED_STATS_UNLOCKED": False,
            "observations": per_game}


def scores_available_by(record: BasicResult, cutoff: datetime, earliest: dict) -> bool:
    """Score-content evidence only. This is not permission to train with unverified metadata."""
    if cutoff.utcoffset() is None:
        raise ValueError("Aware prediction cutoff required")
    if record.available_at <= cutoff:
        return True
    evidence = earliest.get(score_identity(record.game_key, record.points_a, record.points_b))
    return bool(evidence and datetime.fromisoformat(evidence["public_available_by"]) <= cutoff)


def load_capture_index(path: Path) -> list:
    if path.is_file():
        return json.loads(path.read_text())
    paths = sorted(path.glob("*.cdx.json"))
    if not paths:
        raise ValueError("No acquired archive indices")
    header, rows = None, set()
    for file in paths:
        data = json.loads(file.read_text())
        if header is None:
            header = data[0]
        if data[0] != header:
            raise ValueError("Incompatible archive index schemas")
        rows.update(tuple(row) for row in data[1:])
    return [header, *[list(row) for row in sorted(rows, key=lambda r:r[1])]]
