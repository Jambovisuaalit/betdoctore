"""Chronological fixture/research runner. Never fabricates missing odds."""
import html
import json
import math
from datetime import timedelta
from pathlib import Path

from .domain import Game, Odds
from .engine import Model, Settings, decision, features


def run(games: list[Game], odds: list[Odds], model: Model, settings: Settings,
        walk_forward: bool = False) -> dict:
    ids = [g.game_id for g in games]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate game identities")
    bankroll, peak, max_dd = 1., 1., 0.
    bets, predictions, skipped = [], [], []
    pending = []
    model_versions = set()

    def settle(until):
        nonlocal bankroll, peak, max_dd
        for completed, bet in sorted(pending[:], key=lambda item: item[0]):
            if completed <= until:
                bankroll += bet["profit"]
                peak = max(peak, bankroll)
                max_dd = max(max_dd, (peak-bankroll)/peak)
                pending.remove((completed, bet))
    for game in sorted(games, key=lambda g: (g.tipoff, g.game_id)):
        cutoff = game.tipoff - timedelta(minutes=60)
        settle(cutoff)
        if walk_forward:
            from .training import fit
            try:
                model, _ = fit(games, cutoff)
            except ValueError as exc:
                skipped.append({"game_id": game.game_id, "reason": str(exc)})
                continue
        offers = [o for o in odds if o.game_id == game.game_id
                  and max(o.available_at, o.observed_at) <= cutoff]
        if not offers:
            skipped.append({"game_id": game.game_id, "reason": "NO_HISTORICAL_ODDS"})
            continue
        try:
            snap = features(games, game.game_id, game.home, game.away, game.tipoff)
        except ValueError as exc:
            skipped.append({"game_id": game.game_id, "reason": str(exc)})
            continue
        # Fixed source selection before outcomes; latest snapshot, deterministic tie-break.
        offer = max(offers, key=lambda o: (o.observed_at, o.bookmaker, o.source_id))
        result = decision(offer, snap, model, settings)
        total = game.home_points + game.away_points
        outcome = "push" if total == offer.line else "over" if total > offer.line else "under"
        p = result["probabilities"]
        model_versions.add(p["model_digest"])
        predictions.append({"game_id": game.game_id, "absolute_error": abs(p["mean"]-total),
                            "squared_error": (p["mean"]-total)**2,
                            "brier": sum((p[s] - int(s == outcome))**2
                                         for s in ("over", "under", "push")),
                            "log_loss": -math.log(max(p[outcome], 1e-15)),
                            "feature_digest": snap["digest"], "model_digest": p["model_digest"]})
        if result["action"] == "PASS":
            skipped.append({"game_id": game.game_id, "reason": result["reasons"]})
            continue
        free_bankroll = bankroll - sum(b["stake"] for _, b in pending)
        stake = max(0, free_bankroll) * result["stake_fraction"]
        price = getattr(offer, result["side"])
        profit = 0 if outcome == "push" else stake*(price-1) if outcome == result["side"] else -stake
        closing = [o for o in odds if o.game_id == game.game_id
                   and o.bookmaker == offer.bookmaker and o.line == offer.line
                   and o.includes_overtime == offer.includes_overtime
                   and max(o.observed_at, o.available_at) < game.tipoff]
        close = max(closing, key=lambda o: o.observed_at) if closing else None
        bet = {"game_id": game.game_id, "side": result["side"], "stake": stake,
                     "profit": profit, "outcome": outcome,
                     "clv_price_ratio": price/getattr(close, result["side"])-1 if close else None}
        bets.append(bet)
        pending.append((max(game.completed_at, game.observed_at, game.available_at), bet))
    if games:
        settle(max(max(g.completed_at, g.observed_at, g.available_at) for g in games))

    def avg(key):
        return sum(p[key] for p in predictions)/len(predictions) if predictions else None
    wagered = sum(b["stake"] for b in bets)
    return {"synthetic": model.synthetic or any(g.synthetic for g in games) or any(o.synthetic for o in odds),
            "walk_forward": walk_forward, "model_versions": sorted(model_versions),
            "model": model.model_dump(mode="json"), "bets": bets, "skipped": skipped,
            "predictions": predictions, "metrics": {
                "roi": sum(b["profit"] for b in bets)/wagered if wagered else None,
                "max_drawdown": max_dd, "brier": avg("brier"), "log_loss": avg("log_loss"),
                "mae": avg("absolute_error"),
                "rmse": math.sqrt(avg("squared_error")) if predictions else None}}


def write_reports(report: dict, directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    content = json.dumps(report, indent=2, allow_nan=False)
    (directory / "backtest.json").write_text(content)
    (directory / "backtest.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>BetDoctore report</title>'
        '<h1>BetDoctore research report</h1><p>Synthetic status and null metrics are explicit.</p>'
        '<pre>' + html.escape(content) + '</pre></html>')
