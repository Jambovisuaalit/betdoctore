"""Basic observed results, deliberately separate from possession/efficiency inputs."""
from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

TEAMS = frozenset(['ATL', 'BOS', 'BKN', 'CHA', 'CHI', 'CLE', 'DAL', 'DEN', 'DET', 'GSW', 'HOU', 'IND', 'LAC', 'LAL', 'MEM', 'MIA', 'MIL', 'MIN', 'NOP', 'NYK', 'OKC', 'ORL', 'PHI', 'PHX', 'POR', 'SAC', 'SAS', 'TOR', 'UTA', 'WAS'])
ALIASES = {"BRK": "BKN", "CHO": "CHA", "PHO": "PHX"}


class BasicResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    source: str = Field(min_length=1)
    source_snapshot_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_row_numbers: list[int] = Field(min_length=1)
    game_key: str
    game_date: date
    date_basis: Literal["source_calendar_date", "scheduled_america_new_york_date"] = "source_calendar_date"
    season_end_year: int = Field(ge=2020, le=2027)
    team_a: str
    team_b: str
    points_a: int = Field(gt=0, le=250, strict=True)
    points_b: int = Field(gt=0, le=250, strict=True)
    designated_home: str | None = None
    neutral: bool | None
    phase: Literal["playoffs", "non_playoff_unspecified", "unknown"]
    venue: str | None = None
    scheduled_tipoff: datetime | None = None
    actual_tipoff: datetime | None = None
    completed_at: datetime | None = None
    result_published_at: datetime | None = None
    retrieved_at: datetime
    available_at: datetime
    synthetic: Literal[False] = False

    @model_validator(mode="after")
    def integrity(self):
        if self.team_a not in TEAMS or self.team_b not in TEAMS or self.team_a >= self.team_b:
            raise ValueError("Teams must be distinct canonical NBA IDs in sorted order")
        if self.points_a == self.points_b:
            raise ValueError("Final NBA results cannot be tied")
        if self.designated_home not in (None, self.team_a, self.team_b):
            raise ValueError("Home designation must identify a participant")
        if self.game_key != f"nba:{self.game_date}:{self.team_a}:{self.team_b}":
            raise ValueError("Invalid stable internal game key")
        for v in self.__dict__.values():
            if isinstance(v, datetime) and v.utcoffset() is None:
                raise ValueError("Aware timestamps required; do not invent midnight tipoffs")
        if self.available_at < self.retrieved_at:
            raise ValueError("Historical availability is unknown; cannot predate acquisition")
        if self.game_date > self.retrieved_at.date():
            raise ValueError("Future result")
        return self


def parse_neil_paine(rows: list[dict], snapshot_sha: str, retrieved_at: datetime,
                     start: date, end: date) -> tuple[list[BasicResult], dict]:
    """Validate opposing team rows before collapsing into one observed game.

    Never import Elo, probabilities, RAPTOR or fabricated advanced statistics.
    Neither team is assigned home when the source supplies no home designation.
    """
    if start > end or end > retrieved_at.date():
        raise ValueError("Invalid acquisition interval")
    grouped = defaultdict(list)
    errors, exclusions = [], Counter()
    for row_number, row in enumerate(rows, start=2):
        try:
            day = date.fromisoformat(str(row["date"]))
            if not start <= day <= end:
                exclusions["outside_interval"] += 1
                continue
            a, b = (ALIASES.get(str(row[k]), str(row[k])) for k in ("team1", "team2"))
            if a not in TEAMS or b not in TEAMS or a == b:
                raise ValueError("Unknown or identical teams")
            # Keys retain no dependence on a later home/away correction.
            key = (day, *sorted((a, b)))
            grouped[key].append((row_number, {**row, "team1": a, "team2": b}))
        except (KeyError, ValueError) as exc:
            errors.append({"row": row_number, "error": str(exc)})
    results = []
    for (day, a, b), pair in sorted(grouped.items()):
        try:
            if len(pair) != 2:
                raise ValueError("Expected exactly two opposing source rows")
            (_, left), (_, right) = pair
            if left["team1"] != right["team2"] or left["team2"] != right["team1"]:
                raise ValueError("Opposing row identity mismatch")
            if left["score1"] != right["score2"] or left["score2"] != right["score1"]:
                raise ValueError("Opposing final scores disagree")
            if any(left[k] != right[k] for k in ("season", "neutral", "playoff")):
                raise ValueError("Opposing metadata disagree")
            if str(left["neutral"]) not in {"0", "1"}:
                raise ValueError("Unknown neutral-site encoding")
            if str(left["playoff"]) not in {"", "TRUE"}:
                raise ValueError("Unknown playoff encoding")
            if any(str(r["is_home"]) not in {"0", "1"} for _, r in pair):
                raise ValueError("Unknown home designation encoding")
            home = [r["team1"] for _, r in pair if str(r["is_home"]) == "1"]
            if len(home) > 1:
                raise ValueError("Multiple home designations")
            points = {left["team1"]: int(str(left["score1"])),
                      left["team2"]: int(str(left["score2"]))}
            results.append(BasicResult(
                source="neil-paine-nba-elo", source_snapshot_sha256=snapshot_sha,
                source_row_numbers=[n for n, _ in pair], game_key=f"nba:{day}:{a}:{b}",
                game_date=day, season_end_year=int(str(left["season"])),
                team_a=a, team_b=b, points_a=points[a], points_b=points[b],
                designated_home=home[0] if home else None, neutral=str(left["neutral"]) == "1",
                phase="playoffs" if left["playoff"] == "TRUE" else "non_playoff_unspecified",
                retrieved_at=retrieved_at, available_at=retrieved_at))
        except (KeyError, ValueError) as exc:
            errors.append({"game": f"{day}:{a}:{b}", "rows": [n for n, _ in pair],
                           "error": str(exc)})
    return results, {"source_rows": len(rows), "excluded": dict(exclusions),
                     "accepted_games": len(results), "errors": errors}


def audit(results: list[BasicResult], start: date, end: date, parsing: dict,
          reference: list[BasicResult] | None = None) -> dict:
    counts = Counter(r.game_date.year for r in results)
    identities = Counter(r.game_key for r in results)
    missing_years = [y for y in range(start.year, end.year+1) if not counts[y]]
    errors = list(parsing.get("errors", []))
    errors.extend({"game": k, "error": "Duplicate normalized identity"}
                  for k, n in identities.items() if n > 1)
    errors.extend({"game": r.game_key, "error": "Outside audited date interval"}
                  for r in results if not start <= r.game_date <= end)
    conflicts, matched, missing_reference, extra_reference = [], 0, [], []
    if reference is not None:
        refs = {r.game_key: r for r in reference}
        if len(refs) != len(reference):
            errors.append({"error": "Duplicate independent reference identity"})
        for r in results:
            other = refs.get(r.game_key)
            if other is None:
                missing_reference.append(r.game_key)
            elif r.source == other.source:
                errors.append({"game": r.game_key, "error": "Reference source is not independent"})
            elif (r.points_a, r.points_b) != (other.points_a, other.points_b):
                conflicts.append(r.game_key)
            else:
                matched += 1
        extra_reference = sorted(set(refs)-set(identities))
    return {"scope": {"start": str(start), "end": str(end), "basis": "calendar years"},
            "real_games": len(results), "years": {str(y): counts[y] for y in range(start.year, end.year+1)},
            "first_game": str(min(r.game_date for r in results)) if results else None,
            "last_game": str(max(r.game_date for r in results)) if results else None,
            "source_snapshots": sorted({r.source_snapshot_sha256 for r in results}),
            "phase_counts": dict(Counter(r.phase for r in results)),
            "missing_years": missing_years, "unknown_home_games": sum(r.designated_home is None for r in results),
            "unknown_actual_tipoff_games": sum(r.actual_tipoff is None for r in results),
            "unknown_publication_time_games": sum(r.result_published_at is None for r in results),
            "structural_status": "PASS" if results and not errors else "FAIL",
            "errors": errors, "independent_crosscheck": {
                "status": "NOT_RUN" if reference is None else "PASS" if (
                    matched == len(results) and not conflicts and not extra_reference and not errors
                ) else "FAIL", "matched": matched, "conflicts": conflicts,
                "missing": missing_reference, "reference_only": extra_reference},
            "coverage_status": "BLOCKED" if missing_years else "UNVERIFIED",
            "coverage_note": "Row counts do not establish complete seasons or date coverage",
            "ADVANCED_STATS_UNLOCKED": False,
            "gate_reasons": ["Full 2021–2026 coverage requires independent expected-game manifest",
                             "Independent source reconciliation required",
                             "Tipoff/publication metadata not historically verified"],
            "synthetic": False}
