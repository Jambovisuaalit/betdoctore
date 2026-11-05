"""Offline T-60 planning from a *future* NBA daily schedule, never data admission.

No network, keys, live capture, scoring, training, or automated scheduling.
Provider data may be evaluated internally only subject to the user's actual terms.
"""
import argparse
import json
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from .result_sources import sha256, write_once

MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_GAMES = 20
MAX_FUTURE_DAYS = 7
MIN_FUTURE_LEAD = timedelta(minutes=10)
GAME_ID = re.compile(r"^[a-fA-F0-9]{8}-(?:[a-fA-F0-9]{4}-){3}[a-fA-F0-9]{12}$")
ALIAS = re.compile(r"^[A-Z]{2,4}$")
VALID_STATUS = frozenset({"scheduled", "created"})
RESULT_KEYS = frozenset({
    "home_points", "away_points", "home_score", "away_score",
    "final_score", "winner", "boxscore", "scoring",
})
# Nothing from the independent 2024/2025 sample is imported or compared.


def _utc(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("Timezone-aware clock required")
    return value.astimezone(UTC)


def _datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise TypeError("Missing timestamp")
    try:
        return _utc(datetime.fromisoformat(value))
    except ValueError as exc:
        raise ValueError("Invalid timezone-aware tipoff") from exc


def _date(value: object) -> date:
    if not isinstance(value, str):
        raise TypeError("Missing league day")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Invalid league day") from exc
    if parsed.isoformat() != value:
        raise ValueError("Noncanonical league day")
    return parsed


def _game_info(game: object, league_day: date) -> tuple[str, datetime, str, str]:
    if not isinstance(game, dict):
        raise TypeError("Invalid game object")
    if any(game.get(k) is not None for k in RESULT_KEYS):
        raise ValueError("Score/outcome data must not enter a pregame plan")
    if game.get("status") not in VALID_STATUS:
        raise ValueError("Only wholly pregame scheduled/created games accepted")
    season = game.get("season")
    if not isinstance(season, dict) or season.get("type") != "REG":
        raise ValueError("Only regular season games accepted")
    game_id, tip = game.get("id"), _datetime(game.get("scheduled"))
    if not isinstance(game_id, str) or GAME_ID.fullmatch(game_id) is None:
        raise ValueError("Invalid provider game ID")
    home, away = game.get("home"), game.get("away")
    if not isinstance(home, dict) or not isinstance(away, dict):
        raise TypeError("Missing team objects")
    home_alias, away_alias = home.get("alias"), away.get("alias")
    if (not isinstance(home_alias, str) or not isinstance(away_alias, str)
            or ALIAS.fullmatch(home_alias) is None
            or ALIAS.fullmatch(away_alias) is None or home_alias == away_alias):
        raise ValueError("Invalid or duplicate team aliases")
    if tip.date() not in (league_day, league_day + timedelta(days=1)):
        raise ValueError("Scheduled UTC time mismatches NBA league-defined day")
    return game_id.lower(), tip, home_alias, away_alias


def make_plan(payload: object, *, created_at: datetime, input_sha256: str,
              synthetic: bool = False) -> dict:
    """Fail closed on postgame, stale, mixed or malformed input.

    created_at is *planner execution time*, never alleged provider publication.
    """
    now = _utc(created_at)
    if not isinstance(payload, dict) or not isinstance(payload.get("games"), list):
        raise TypeError("Expected Daily Schedule JSON object with games array")
    league = payload.get("league")
    if not isinstance(league, dict) or league.get("alias") != "NBA":
        raise ValueError("Not an NBA Daily Schedule payload")
    league_day = _date(payload.get("date"))
    games = payload["games"]
    if len(games) > MAX_GAMES:
        raise ValueError("Daily schedule exceeds bounded game budget")
    if not isinstance(input_sha256, str) or not re.fullmatch("[0-9a-f]{64}", input_sha256):
        raise ValueError("Invalid input checksum")
    items, seen = [], set()
    for game in games:
        game_id, tip, home, away = _game_info(game, league_day)
        if game_id in seen:
            raise ValueError("Duplicate provider game ID")
        seen.add(game_id)
        deadline = tip - timedelta(minutes=60)
        if deadline < now + MIN_FUTURE_LEAD:
            raise ValueError("Schedule includes games too near/past T-60 cutoff")
        if deadline > now + timedelta(days=MAX_FUTURE_DAYS):
            raise ValueError("Schedule cutoff is beyond safe future horizon")
        items.append({
            "provider_game_id": game_id,
            "league_day": league_day.isoformat(),
            "home_alias": home, "away_alias": away,
            "scheduled_tipoff_utc": tip.isoformat(),
            "planned_capture_window_start_utc":
                (tip - timedelta(minutes=65)).isoformat(),
            "planned_capture_window_end_utc": deadline.isoformat(),
            "scheduled_t60_cutoff_utc": deadline.isoformat(),
            "actual_tipoff_unknown": True,
            "source_published_at_verified": False,
            "provider_capture_completed": False,
            "history_as_of_verified": False,
        })
    items.sort(key=lambda x: (x["scheduled_tipoff_utc"], x["provider_game_id"]))
    return {
        "schema_version": 1,
        "status": "PROSPECTIVE_T60_PLAN_ONLY",
        "source": "SYNTHETIC" if synthetic else "USER_SUPPLIED_LOCAL_JSON",
        "source_claim": "nba_v8_daily_schedule_shape",
        "raw_input_sha256": input_sha256,
        "plan_created_at_utc": now.isoformat(),
        "original_provider_received_at": None,
        "source_publication_timestamp_verified": False,
        "provider_entitlement_verified": False,
        "sportradar_betting_use_written_approval_verified": False,
        "nba_rights_approved": False,
        "network_calls": 0,
        "game_count": len(items),
        "games": items,
        "outcome_blind": True,
        "existing_363_frozen_candidates_unchanged": True,
        "independent_as_of_capture_verified": False,
        "t60_feature_capture_eligible": False,
        "source_admitted_games": 0,
        "training_eligible": False,
        "production_ready": False,
    }


def _demo(now: datetime) -> dict:
    """Entirely synthetic one-game fixture for an offline zero-key demo."""
    future = _utc(now) + timedelta(days=2)
    return {
        "date": future.date().isoformat(),
        "league": {"alias": "NBA"},
        "games": [{
            "id": "11111111-2222-4333-8444-555555555555",
            "scheduled": future.isoformat(),
            "status": "scheduled",
            "season": {"year": future.year, "type": "REG"},
            "home": {"alias": "AAA"}, "away": {"alias": "BBB"},
        }],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--demo", action="store_true", help="No provider data or network")
    mode.add_argument("--input", type=Path, help="Local pregame daily schedule JSON")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    now = datetime.now(UTC)
    if args.demo:
        payload = _demo(now)
        raw = json.dumps(payload, sort_keys=True).encode()
    else:
        if args.input.stat().st_size > MAX_INPUT_BYTES:
            parser.error("Daily schedule input exceeds bounded size")
        raw = args.input.read_bytes()
        if len(raw) > MAX_INPUT_BYTES:
            parser.error("Daily schedule input exceeds bounded size")
        payload = json.loads(raw)
    plan = make_plan(payload, created_at=now, input_sha256=sha256(raw),
                     synthetic=args.demo)
    output_raw = json.dumps(plan, sort_keys=True, indent=2).encode()
    dest = args.output / f"{sha256(output_raw)}.prospective-t60-plan.json"
    write_once(dest, output_raw)
    print(json.dumps({
        "status": plan["status"], "source": plan["source"],
        "game_count": plan["game_count"], "network_calls": 0,
        "private_plan": str(dest), "source_admitted_games": 0,
        "training_eligible": False, "production_ready": False,
    }, indent=2))


if __name__ == "__main__":
    main()
