"""Chronological baseline calibration using only previously available results."""
import math
from datetime import datetime
from pathlib import Path

from .domain import Game
from .engine import Model, digest, features


def fit(games: list[Game], trained_until: datetime, minimum_samples: int = 50) -> tuple[Model, dict]:
    eligible = sorted((g for g in games if max(g.available_at, g.observed_at,
                                               g.completed_at) <= trained_until),
                      key=lambda g: (g.tipoff, g.game_id))
    if len({g.game_id for g in eligible}) != len(eligible):
        raise ValueError("Duplicate training game identities")
    residuals, source_ids = [], []
    base = Model(trained_until=datetime.min.replace(tzinfo=trained_until.tzinfo),
                 overtime_probability=0)
    for g in eligible:
        try:
            snap = features(eligible, g.game_id, g.home, g.away, g.tipoff)
        except ValueError:
            continue
        if min(t["n"] for t in snap["teams"].values()) < 5:
            continue
        prediction = base.distribution(snap, 220)["mean"]
        # Fit regulation residuals separately from overtime mixture.
        regulation_total = (g.home_points+g.away_points)*48/(48+5*g.overtime_periods)
        residuals.append(regulation_total-prediction)
        source_ids.append(g.source+":"+g.source_id)
    if len(residuals) < minimum_samples:
        raise ValueError(f"Calibration requires {minimum_samples} prior forecast residuals")
    bias = sum(residuals)/len(residuals)
    sigma = math.sqrt(sum((r-bias)**2 for r in residuals)/len(residuals))
    model = Model(trained_until=trained_until, sigma=max(sigma, 1), bias=bias,
                  overtime_probability=sum(g.overtime_periods > 0 for g in eligible)/len(eligible),
                  calibrated=True, calibration_samples=len(residuals),
                  training_digest=digest({"records": [g.model_dump(mode="json") for g in eligible]}),
                  synthetic=any(g.synthetic for g in eligible))
    evidence = {"method": "chronological forecast residual moment fit", "source_ids": source_ids,
                "samples": len(residuals), "bias": bias,
                "limitation": "Fitted calibration is not independent holdout verification"}
    return model, evidence


def save(model: Model, evidence: dict, directory: Path):
    import json
    directory.mkdir(parents=True, exist_ok=True)
    payload = model.model_dump(mode="json")
    identity = digest(payload)
    (directory/f"{identity}.json").write_text(json.dumps(payload, indent=2))
    (directory/f"{identity}.evidence.json").write_text(json.dumps(evidence, indent=2))
    return identity
