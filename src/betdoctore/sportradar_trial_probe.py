"""Private, read-only Sportradar trial smoke test. Not a historical as-of audit."""
import argparse
import getpass
import hashlib
import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from .result_sources import sha256, write_once

BASE = "https://api.sportradar.com"
NBA_YEARS = (2020, 2021, 2022)
SYNERGY_MIN = "2021-12-01T00:00:00Z"
SYNERGY_MAX = "2021-12-03T00:00:00Z"
MAX_BYTES = 12 * 1024 * 1024
UUID = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
SAFE_HEADERS = ("date", "etag", "last-modified", "x-generated-date", "content-type")
FIELD_HINTS = ("playtype", "shotx", "shoty", "lineup", "oplayer", "dplayer",
               "rplayer", "possessions", "offensive_rating", "defensive_rating")


def _shape(value: object, depth: int = 0) -> object:
    """Keys and type structure only; never persist response field values."""
    if depth >= 3:
        return type(value).__name__
    if isinstance(value, dict):
        return {k: _shape(v, depth+1) for k, v in sorted(value.items())[:60]}
    if isinstance(value, list):
        return {"kind": "list", "count": len(value),
                "first_item": _shape(value[0], depth+1) if value else None}
    return type(value).__name__


def _fields(value: object, depth: int = 0) -> list[str]:
    if depth > 7:
        return []
    if isinstance(value, dict):
        matches = [key for key in value if key.lower() in FIELD_HINTS]
        return matches + [x for v in list(value.values())[:30] for x in _fields(v, depth+1)]
    if isinstance(value, list):
        return [x for v in value[:4] for x in _fields(v, depth+1)]
    return []


def _records(data: object, key: str) -> list[dict]:
    if not isinstance(data, dict):
        return []
    collection = data.get(key)
    if not isinstance(collection, list):
        container = data.get("data")
        collection = (container.get(key) if isinstance(container, dict)
                      else container if isinstance(container, list) else [])
    return [x for x in collection if isinstance(x, dict)] if isinstance(collection, list) else []


def _nba_game(schedule: dict) -> str | None:
    """Pick by schedule metadata, never a game outcome or points field."""
    options = []
    for row in _records(schedule, "games"):
        game_id, when = row.get("id"), row.get("scheduled")
        if (isinstance(game_id, str) and UUID.fullmatch(game_id)
                and isinstance(when, str) and when.startswith("2020-")):
            options.append((when, game_id))
    return sorted(options)[0][1] if options else None


def _synergy_game(games: dict) -> str | None:
    """Selection uses identifier only, never a score, model result or odds."""
    options = []
    for row in _records(games, "games"):
        value = row.get("id")
        if isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9_-]{8,90}", value):
            options.append(value)
    return sorted(options)[0] if options else None


def _request(client: httpx.Client, key: str, path: str, params: dict,
             scope: str) -> tuple[dict, dict | None]:
    # All paths come from immutable local constants / validated archived ID.
    if not path.startswith(("/nba/trial/v8/en/", "/synergy/basketball/nba/")):
        raise ValueError("Endpoint not approved for local smoke test")
    started = datetime.now(UTC).isoformat()
    url = BASE + path
    response = None
    receipt = {"scope": scope, "endpoint": path, "params": params,
               "request_started_at": started, "response_received_at": None,
               "status_code": None, "response_sha256": None,
               "response_bytes": None, "response_headers": {},
               "response_schema": None, "observed_fields": [],
               "access_verified": False, "error_code": None}
    payload = None
    try:
        # Header-auth only; no redirects, retries or calls to other hosts.
        with client.stream("GET", url, params=params,
                           headers={"accept": "application/json", "x-api-key": key}) as res:
            response = res
            receipt["response_received_at"] = datetime.now(UTC).isoformat()
            receipt["status_code"] = res.status_code
            receipt["response_headers"] = {
                name: res.headers[name][:128] for name in SAFE_HEADERS if name in res.headers
            }
            body = bytearray()
            digest = hashlib.sha256()
            for chunk in res.iter_bytes():
                digest.update(chunk)
                if len(body) + len(chunk) > MAX_BYTES:
                    receipt["error_code"] = "BODY_OVER_LIMIT"
                    break
                body.extend(chunk)
            if receipt["error_code"] is None:
                receipt["response_bytes"] = len(body)
                receipt["response_sha256"] = digest.hexdigest()
                if res.status_code == 200:
                    try:
                        data = json.loads(body)
                    except (ValueError, UnicodeError):
                        receipt["error_code"] = "RESPONSE_NOT_JSON"
                    else:
                        receipt["response_schema"] = _shape(data)
                        receipt["observed_fields"] = sorted(set(_fields(data)))
                        receipt["access_verified"] = True
                        payload = data if isinstance(data, dict) else None
                else:
                    receipt["error_code"] = f"HTTP_{res.status_code}"
    except (httpx.TimeoutException, httpx.NetworkError, httpx.ProtocolError):
        receipt["error_code"] = "NETWORK_OR_TIMEOUT"
        receipt["response_received_at"] = datetime.now(UTC).isoformat()
    if response is None and receipt["error_code"] is None:
        receipt["error_code"] = "NO_RESPONSE"
    return receipt, payload


def probe(scope: str, key: str, client: httpx.Client, pause=time.sleep) -> dict:
    if scope not in ("nba", "synergy") or not key.strip():
        raise ValueError("Specify a supported product and a private API key")
    received = []
    # Maximum four NBA calls (three seasons + one old game) or three Synergy calls.
    plan = ([(f"/nba/trial/v8/en/games/{y}/REG/schedule.json", {}) for y in NBA_YEARS]
            if scope == "nba" else [
                ("/synergy/basketball/nba/seasons", {"skip": 0, "take": 25}),
                ("/synergy/basketball/nba/games", {
                    "minDate": SYNERGY_MIN, "maxDate": SYNERGY_MAX,
                    "skip": 0, "take": 2}),
            ])
    nba_first = None
    synergy_games = None
    for path, params in plan:
        if received:
            pause(1.1)  # Stay below the default trial 1-QPS threshold.
        receipt, obj = _request(client, key, path, params, scope)
        received.append(receipt)
        if scope == "nba" and path.endswith("/2020/REG/schedule.json") and obj:
            nba_first = _nba_game(obj)
        if scope == "synergy" and path.endswith("/games") and obj:
            synergy_games = _synergy_game(obj)
        if receipt["error_code"] in ("HTTP_401", "HTTP_403", "HTTP_429",
                                     "BODY_OVER_LIMIT", "NETWORK_OR_TIMEOUT"):
            break
    else:
        if scope == "nba" and nba_first:
            pause(1.1)
            path = f"/nba/trial/v8/en/games/{nba_first}/summary.json"
            received.append(_request(client, key, path, {}, scope)[0])
        if scope == "synergy" and synergy_games:
            pause(1.1)
            path = f"/synergy/basketball/nba/games/{synergy_games}/events"
            received.append(_request(client, key, path, {"skip": 0, "take": 2}, scope)[0])
    return {"schema_version": 1, "status": "TRIAL_ACCESS_REVIEW_ONLY",
            "scope": scope, "checks": received, "calls_consumed": len(received),
            "api_key_stored": False, "raw_response_stored": False,
            "target_games_2024_2025_requested": False,
            "sample_periods_locked": False, "source_admitted_games": 0,
            "historical_as_of_availability_verified": False,
            "seven_day_historical_history_verified": False,
            "source_contract_rights_approved": False,
            "model_training_eligible": False, "production_ready": False}


def _key() -> str:
    result = os.environ.get("SPORTRADAR_API_KEY")
    if result is None:
        result = getpass.getpass("Sportradar API key (hidden, not stored): ")
    if not result.strip():
        raise ValueError("Missing key")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("nba", "synergy"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true",
                        help="Opt in to <=4 NBA or <=3 Synergy authenticated calls")
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({"status": "DRY_RUN_NO_API_REQUESTS", "scope": args.scope,
                          "max_calls": 4 if args.scope == "nba" else 3}, indent=2))
        return
    with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
        report = probe(args.scope, _key(), client)
    raw = json.dumps(report, sort_keys=True, indent=2).encode()
    name = f"{sha256(raw)}.sportradar-{args.scope}-trial.json"
    write_once(args.output/name, raw)
    print(json.dumps({"status": report["status"], "scope": args.scope,
        "calls_consumed": report["calls_consumed"],
        "checks": [{"endpoint": r["endpoint"], "status_code": r["status_code"],
                    "error_code": r["error_code"], "access_verified": r["access_verified"],
                    "observed_fields": r["observed_fields"]}
                   for r in report["checks"]],
        "private_report": str(args.output/name),
        "source_admitted_games": 0, "model_training_eligible": False}, indent=2))


if __name__ == "__main__":
    main()
