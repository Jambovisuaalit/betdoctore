"""Exploratory paired errors; source admission remains a separate, mandatory gate."""
import math
import random
from collections import defaultdict
from datetime import date, datetime, timedelta


def _instant(value):
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None:
        raise ValueError("Cutoffs must be timezone aware")
    return stamp


def paired_errors(model: list[dict], baseline: list[dict]) -> list[dict]:
    """Require identical games, instants and outcomes; never silently intersect cohorts."""
    def index(rows):
        result = {}
        for row in rows:
            key = row["game_key"]
            if key in result:
                raise ValueError("Duplicate game")
            if not all(math.isfinite(row[k]) for k in ("prediction", "actual")):
                raise ValueError("Nonfinite score")
            result[key] = row
        return result
    left, right = index(model), index(baseline)
    if not left or left.keys() != right.keys():
        raise ValueError("Models must use exactly the same nonempty cohort")
    paired = []
    for key, row in sorted(left.items()):
        other = right[key]
        if (_instant(row["cutoff"]) != _instant(other["cutoff"])
                or row["actual"] != other["actual"] or row["date"] != other["date"]):
            raise ValueError("Cutoff, outcome or game date mismatch")
        day = date.fromisoformat(row["date"])
        paired.append({"game_key": key, "date": day.isoformat(),
                       "difference": abs(row["prediction"]-row["actual"])
                       - abs(other["prediction"]-other["actual"])})
    return paired


def compare(model: list[dict], baseline: list[dict], periods: list[dict], *,
            block_days: int = 7, repetitions: int = 2000, seed: int = 20261027) -> dict:
    """Period-stratified moving calendar-block bootstrap, including empty days.

    Positive differences mean the model has higher MAE. Period game-count weights
    stay fixed. This function does not certify provenance or independent holdouts.
    """
    if block_days < 1 or repetitions < 100:
        raise ValueError("Require positive block length and at least 100 replicates")
    paired = paired_errors(model, baseline)
    windows = sorted((date.fromisoformat(p["start"]), date.fromisoformat(p["end"]))
                     for p in periods)
    if not windows or any(a > b for a, b in windows):
        raise ValueError("Invalid periods")
    if any(windows[i][0] <= windows[i-1][1] for i in range(1, len(windows))):
        raise ValueError("Periods must not overlap")
    groups = [defaultdict(list) for _ in windows]
    for row in paired:
        day = date.fromisoformat(row["date"])
        if day.year == 2022:
            raise ValueError("2022 is development data, not a new independent test")
        matches = [i for i, (a, b) in enumerate(windows) if a <= day <= b]
        if len(matches) != 1:
            raise ValueError("Every game must belong to one declared period")
        groups[matches[0]][day].append(row["difference"])
    if any(not group for group in groups):
        raise ValueError("Each declared period must contain games")
    count = len(paired)
    result = {"games": count, "periods": len(windows),
              "planning_target_met": count >= 300 and len(windows) >= 2,
              "planning_target_is_significance_guarantee": False,
              "paired_mae_difference": sum(r["difference"] for r in paired)/count,
              "positive_difference_means": "model_worse",
              "method": "period_stratified_moving_calendar_day_blocks",
              "block_days": block_days, "repetitions": repetitions, "seed": seed,
              "confidence_level": 0.95, "interval": None,
              "source_admission": "NOT_VERIFIED_BY_THIS_ANALYSIS",
              "independent_test_ready": False, "production_ready": False}
    series = []
    for group in groups:
        # Use the observed span, not empty padding outside the sample.
        start, end = min(group), max(group)
        days = [group[start+timedelta(days=i)] for i in range((end-start).days+1)]
        if len(days) < 3*block_days:
            result["uncertainty_status"] = "INSUFFICIENT_TEMPORAL_SUPPORT"
            return result
        series.append((days, sum(len(v) for v in days)/count))
    rng = random.Random(seed)
    draws = []
    for _ in range(repetitions):
        estimate = 0.0
        for days, weight in series:
            sampled = []
            while len(sampled) < len(days):
                first = rng.randrange(len(days)-block_days+1)
                sampled.extend(days[first:first+block_days])
            values = [v for day in sampled[:len(days)] for v in day]
            if not values:
                break
            estimate += weight*sum(values)/len(values)
        else:
            draws.append(estimate)
    if len(draws) != repetitions:
        result["uncertainty_status"] = "EMPTY_BOOTSTRAP_REPLICATE"
        return result
    draws.sort()
    def quantile(q):
        position = (len(draws)-1)*q
        lo = math.floor(position)
        hi = math.ceil(position)
        return draws[lo]+(draws[hi]-draws[lo])*(position-lo)
    result["interval"] = [quantile(.025), quantile(.975)]
    result["uncertainty_status"] = "EXPLORATORY_INTERVAL_AVAILABLE"
    return result
