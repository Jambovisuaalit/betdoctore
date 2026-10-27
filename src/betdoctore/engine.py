"""Deterministic T-60 features, discrete totals distribution and conservative decisions."""
import hashlib
import json
import math
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field
from scipy.stats import norm

from .domain import Game, Odds


class Settings(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    min_ev: float = Field(default=.045, ge=0)
    kelly_fraction: float = Field(default=.25, gt=0, le=1)
    max_bankroll_fraction: float = Field(default=.01, gt=0, le=1)
    max_odds_age_minutes: int = Field(default=120, gt=0)
    minimum_history: int = Field(default=5, ge=2)


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def features(games: list[Game], game_id: str, home: str, away: str,
             tipoff: datetime, window: int = 10) -> dict:
    if tipoff.utcoffset() is None:
        raise ValueError("Aware tipoff required")
    if window < 1 or home == away:
        raise ValueError("Invalid history window or team identity")
    if len({g.game_id for g in games}) != len(games):
        raise ValueError("Duplicate canonical game records")
    cutoff = tipoff - timedelta(minutes=60)
    eligible = sorted((g for g in games if g.game_id != game_id
                       and max(g.completed_at, g.available_at, g.observed_at) <= cutoff),
                      key=lambda g: (g.tipoff, g.game_id))
    teams = {}
    used = {}
    for team in (home, away):
        history = [g for g in eligible if team in (g.home, g.away)][-window:]
        if not history:
            raise ValueError(f"Insufficient history: {team}")
        pace, offense, defense = [], [], []
        for g in history:
            # Normalize observed possessions/ratings to regulation minutes.
            factor = 48 / (48 + 5 * g.overtime_periods)
            poss = (g.home_possessions + g.away_possessions) / 2
            own, opp = ((g.home_points, g.away_points) if team == g.home
                        else (g.away_points, g.home_points))
            pace.append(poss * factor)
            offense.append(100 * own / poss)
            defense.append(100 * opp / poss)
            used[g.source + ":" + g.source_id] = g.model_dump(mode="json")
        teams[team] = {
            "pace": sum(pace) / len(pace), "offense": sum(offense) / len(offense),
            "defense": sum(defense) / len(defense), "n": len(history),
            "rest_days": max(0, (tipoff - history[-1].tipoff).total_seconds() / 86400 - 1),
            "back_to_back": (tipoff - history[-1].tipoff).total_seconds() < 36 * 3600,
        }
    payload = {"version": "features-v1", "game_id": game_id, "cutoff": cutoff.isoformat(),
               "home": home, "away": away, "teams": teams,
               "source_digest": digest(used), "source_ids": sorted(used)}
    return {**payload, "digest": digest(payload)}


class Model(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    version: str = "baseline-v1"
    trained_until: datetime
    sigma: float = Field(default=18, gt=0)
    overtime_probability: float = Field(default=.06, ge=0, le=1)
    overtime_points: float = Field(default=22, ge=0)
    bias: float = 0
    calibrated: bool = False
    calibration_samples: int = Field(default=0, ge=0)
    training_digest: str = ""
    synthetic: bool = False

    def distribution(self, snapshot: dict, line: float) -> dict:
        if self.trained_until.utcoffset() is None:
            raise ValueError("Aware training boundary required")
        if self.trained_until > datetime.fromisoformat(snapshot["cutoff"]):
            raise ValueError("Model trained after prediction cutoff")
        h, a = (snapshot["teams"][snapshot[t]] for t in ("home", "away"))
        pace = (h["pace"] + a["pace"]) / 2
        mean = (pace * (h["offense"] + a["defense"] + a["offense"] + h["defense"]) / 200
                + self.bias)

        def cdf(x):
            p = self.overtime_probability
            return float((1-p)*norm.cdf(x, mean, self.sigma)
                         + p*norm.cdf(x, mean+self.overtime_points, self.sigma))

        # Continuity-corrected integer total distribution, censored at zero.
        under = cdf(math.ceil(line) - .5)
        over = 1 - cdf(math.floor(line) + .5)
        push = max(0., 1 - over - under)
        return {"mean": mean + self.overtime_probability * self.overtime_points,
                "over": over, "under": under, "push": push,
                "calibrated": self.calibrated, "model_digest": digest(self.model_dump(mode="json"))}


def decision(odds: Odds, snapshot: dict, model: Model, settings: Settings) -> dict:
    cutoff = datetime.fromisoformat(snapshot["cutoff"])
    reasons = []
    if odds.game_id != snapshot["game_id"]:
        reasons.append("GAME_MISMATCH")
    if max(odds.available_at, odds.observed_at) > cutoff:
        reasons.append("FUTURE_ODDS")
    if cutoff - odds.observed_at > timedelta(minutes=settings.max_odds_age_minutes):
        reasons.append("STALE_ODDS")
    if not odds.includes_overtime:
        reasons.append("MARKET_RULE_MISMATCH")
    if min(t["n"] for t in snapshot["teams"].values()) < settings.minimum_history:
        reasons.append("INSUFFICIENT_HISTORY")
    if not model.calibrated or model.calibration_samples < 50 or not model.training_digest:
        reasons.append("UNCALIBRATED_MODEL")
    probs = model.distribution(snapshot, odds.line)
    margin = 1 / odds.over + 1 / odds.under - 1
    candidates = []
    for side, price in (("over", odds.over), ("under", odds.under)):
        win, lose = probs[side], probs["under" if side == "over" else "over"]
        ev = win * (price - 1) - lose
        kelly = max(0., (win * (price - 1) - lose) / ((price - 1)*(win + lose)))
        candidates.append({"side": side, "ev": ev, "stake_fraction": min(
            settings.max_bankroll_fraction, settings.kelly_fraction * kelly)})
    best = max(candidates, key=lambda c: c["ev"])
    if best["ev"] < settings.min_ev:
        reasons.append("BELOW_MIN_EV")
    return {**best, "action": "PASS" if reasons else "BET", "reasons": reasons,
            "stake_fraction": 0 if reasons else best["stake_fraction"],
            "probabilities": probs, "margin": margin,
            "no_vig_over": (1 / odds.over) / (1 / odds.over + 1 / odds.under)}


def compare_exact(offers: list[Odds]) -> list[dict]:
    groups = {}
    for o in offers:
        key = (o.game_id, o.line, o.includes_overtime)
        groups.setdefault(key, []).append(o)
    return [{"game_id": key[0], "line": key[1], "includes_overtime": key[2],
             "best_over": max(x.over for x in values),
             "best_under": max(x.under for x in values)} for key, values in groups.items()]
