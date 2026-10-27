from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from betdoctore.api import app
from betdoctore.backtest import run, write_reports
from betdoctore.domain import Odds
from betdoctore.engine import Model, Settings, compare_exact, decision, features
from betdoctore.fixtures import dataset
from betdoctore.ingestion import ingest
from betdoctore.storage import Base


def setup_case():
    games, odds = dataset()
    g = games[-1]
    snap = features(games, g.game_id, g.home, g.away, g.tipoff)
    model = Model(trained_until=datetime(2019, 1, 1, tzinfo=UTC))
    return games, odds, snap, model


def test_future_game_and_delayed_availability_cannot_leak():
    games, _, snap, _ = setup_case()
    altered = [g.model_copy(update={"home_points": 999}) if g.game_id == games[-1].game_id
               else g for g in games]
    assert features(altered, games[-1].game_id, "AAA", "BBB", games[-1].tipoff) == snap
    delayed = games[-2].model_copy(update={"available_at": games[-1].tipoff})
    reduced = games[:-2] + [delayed, games[-1]]
    expected = features(games[:-2], games[-1].game_id, "AAA", "BBB", games[-1].tipoff)
    assert features(reduced, games[-1].game_id, "AAA", "BBB", games[-1].tipoff) == expected


@pytest.mark.parametrize("line", [210, 210.5, 220, 220.5])
def test_distribution_conserves_probability(line):
    _, _, snap, model = setup_case()
    p = model.distribution(snap, line)
    assert sum(p[s] for s in ("over", "under", "push")) == pytest.approx(1)
    assert p["push"] > 0 if line == int(line) else p["push"] == pytest.approx(0)


def test_pass_and_model_leakage():
    _, odds, snap, model = setup_case()
    assert "UNCALIBRATED_MODEL" in decision(odds[-1], snap, model, Settings())["reasons"]
    future = model.model_copy(update={"trained_until": odds[-1].available_at+timedelta(days=1)})
    with pytest.raises(ValueError, match="after prediction"):
        decision(odds[-1], snap, future, Settings())
    late = odds[-1].model_copy(update={"available_at": datetime.fromisoformat(snap["cutoff"])
                                     + timedelta(seconds=1)})
    assert "FUTURE_ODDS" in decision(late, snap, model, Settings())["reasons"]


def test_ingest_conflict_and_validation():
    games, _, _, _ = setup_case()
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        row = games[0].model_dump(mode="json")
        assert ingest(session, [row], "game")["accepted"] == 1
        assert ingest(session, [row], "game")["duplicates"] == 1
        assert ingest(session, [{**row, "home_points": 1}], "game")["errors"]
        assert ingest(session, [{**row, "observed_at": "2020-01-01"}], "game")["errors"]


def test_exact_lines_and_price_math():
    _, odds, snap, model = setup_case()
    o = odds[-1]
    assert len(compare_exact([o, o.model_copy(update={"line": 221})])) == 2
    result = decision(o, snap, model, Settings())
    assert result["margin"] == pytest.approx(2/1.91-1)
    assert result["no_vig_over"] == .5
    assert result["stake_fraction"] == 0


def test_fixture_backtest_reports_and_api(tmp_path):
    games, odds, _, model = setup_case()
    report = run(games, odds, model, Settings())
    assert report["synthetic"]
    assert report["predictions"]
    assert report["bets"] == []
    assert report["metrics"]["roi"] is None
    write_reports(report, tmp_path)
    assert (tmp_path / "backtest.html").exists()
    client = TestClient(app)
    assert client.get("/health").json()["production_ready"] is False
    assert client.post("/health").status_code == 405


def test_invalid_odds():
    _, odds, _, _ = setup_case()
    row = odds[0].model_dump()
    with pytest.raises(ValueError):
        Odds.model_validate({**row, "over": 1})
    with pytest.raises(ValueError):
        Odds.model_validate({**row, "line": 220.25})


def test_push_aware_kelly_and_ev():
    _, odds, snap, model = setup_case()
    # Synthetic math verification only; evidence string is not a real trained artifact.
    model = model.model_copy(update={"calibrated": True, "calibration_samples": 100,
                                     "training_digest": "synthetic-test"})
    offer = odds[-1].model_copy(update={"line": 240})
    settings = Settings(max_bankroll_fraction=1)
    result = decision(offer, snap, model, settings)
    assert result["action"] == "BET"
    p = result["probabilities"]
    price = getattr(offer, result["side"])
    win = p[result["side"]]
    lose = p["under" if result["side"] == "over" else "over"]
    ev = win*(price-1)-lose
    assert result["ev"] == pytest.approx(ev)
    assert result["stake_fraction"] == pytest.approx(.25*ev/((price-1)*(win+lose)))
    assert decision(offer, snap, model, Settings(min_ev=1))["action"] == "PASS"
