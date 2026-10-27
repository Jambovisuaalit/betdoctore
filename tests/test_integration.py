import os
from datetime import UTC, datetime, timedelta

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from betdoctore.api import app
from betdoctore.backtest import run
from betdoctore.engine import Model, Settings
from betdoctore.fixtures import dataset
from betdoctore.ingestion import HistoricalOddsAPI, PinnacleAdapter, ingest
from betdoctore.repository import snapshot
from betdoctore.storage import Base
from betdoctore.training import fit


def test_exports_roundtrip(tmp_path):
    _, odds = dataset()
    frame = pd.DataFrame([o.model_dump(mode="json") for o in odds])
    for extension in ("csv", "parquet"):
        path = tmp_path/f"odds.{extension}"
        if extension == "csv":
            frame.to_csv(path, index=False)
        else:
            frame.to_parquet(path)
        assert PinnacleAdapter(path).snapshots() == odds


def test_provider_exact_line_pairs_and_future_rejection():
    stamp = datetime(2020, 1, 1, tzinfo=UTC)
    payload = {"timestamp": stamp.isoformat(), "data": [{"id": "nba1", "bookmakers": [
        {"key": "pinnacle", "markets": [{"key": "totals", "outcomes": [
            {"name": "Over", "point": 220, "price": 1.9},
            {"name": "Under", "point": 221, "price": 1.9}]}]}]}]}
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)))
    provider = HistoricalOddsAPI("synthetic-test-key", stamp, True, client)
    assert provider.snapshots() == []
    payload["data"][0]["bookmakers"][0]["markets"][0]["outcomes"][1]["point"] = 220
    assert provider.snapshots()[0].line == 220
    provider.at = stamp-timedelta(seconds=1)
    with pytest.raises(ValueError, match="future archive"):
        provider.snapshots()


def test_database_snapshot_api(tmp_path, monkeypatch):
    url = os.environ.get("DATABASE_URL", f"sqlite:///{tmp_path}/integration.db")
    monkeypatch.setenv("DATABASE_URL", url)
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    games, _ = dataset()
    with Session(engine) as session:
        report = ingest(session, [g.model_dump(mode="json") for g in games], "game")
        assert not report["errors"]
        g = games[-1]
        first = snapshot(session, g.game_id, g.home, g.away, g.tipoff)
        assert snapshot(session, g.game_id, g.home, g.away, g.tipoff) == first
        session.commit()
    client = TestClient(app)
    assert client.get("/ready").status_code == 200
    assert client.get(f"/snapshots/{g.game_id}").json()[0]["digest"] == first["digest"]
    engine.dispose()


def test_calibration_boundary_and_walk_forward():
    games, odds = dataset()
    with pytest.raises(ValueError, match="50 prior"):
        fit(games, games[-1].completed_at)
    model = Model(trained_until=datetime(2019, 1, 1, tzinfo=UTC))
    report = run(games, odds, model, Settings(), walk_forward=True)
    assert report["bets"] == []
    assert report["walk_forward"]
    assert report["metrics"]["mae"] is None


@pytest.mark.parametrize("side,total,profit_sign", [("under", 200, 1), ("under", 250, -1),
                                                   ("over", 250, 1), ("over", 200, -1),
                                                   ("over", 220, 0)])
def test_settlement(monkeypatch, side, total, profit_sign):
    games, odds = dataset()
    games[-1] = games[-1].model_copy(update={"home_points": 100, "away_points": total-100})
    odds[-1] = odds[-1].model_copy(update={"line": 220})
    def fake_decision(*args):
        return {"action": "BET", "side": side, "stake_fraction": .01,
                "probabilities": {"mean": 220, "over": .45, "under": .45, "push": .1,
                                  "model_digest": "synthetic-test"}}
    monkeypatch.setattr("betdoctore.backtest.decision", fake_decision)
    model = Model(trained_until=datetime(2019, 1, 1, tzinfo=UTC))
    result = run(games, [odds[-1]], model, Settings())
    profit = result["bets"][0]["profit"]
    assert (profit > 0) - (profit < 0) == profit_sign


def test_fitted_artifact_is_reproducible_and_future_safe(tmp_path):
    from betdoctore.training import save
    games, _ = dataset(80)
    boundary = games[70].completed_at
    first, evidence = fit(games, boundary)
    changed = [g if g.completed_at <= boundary else g.model_copy(update={"home_points": 999})
               for g in games]
    second, _ = fit(changed, boundary)
    assert first == second
    assert first.calibration_samples >= 50
    assert first.synthetic
    identity = save(first, evidence, tmp_path)
    assert Model.model_validate_json((tmp_path/f"{identity}.json").read_text()) == first


def test_read_only_analysis_uses_past_model(tmp_path, monkeypatch):
    from betdoctore.engine import digest
    from betdoctore.storage import ModelArtifact
    url = f"sqlite:///{tmp_path}/analysis.db"
    monkeypatch.setenv("DATABASE_URL", url)
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    games, odds = dataset()
    model = Model(trained_until=datetime(2019, 1, 1, tzinfo=UTC))
    payload = model.model_dump(mode="json")
    with Session(engine) as session:
        ingest(session, [g.model_dump(mode="json") for g in games], "game")
        ingest(session, [o.model_dump(mode="json") for o in odds], "odds")
        g = games[-1]
        snapshot(session, g.game_id, g.home, g.away, g.tipoff)
        session.add(ModelArtifact(digest=digest(payload), version=model.version,
                                  trained_until=model.trained_until, sigma=model.sigma,
                                  payload=payload))
        session.commit()
    response = TestClient(app).get(f"/analysis/{g.game_id}")
    assert response.status_code == 200
    assert response.json()["offers"][0]["analysis"]["action"] == "PASS"
    assert response.json()["synthetic"]
    engine.dispose()


def test_overlapping_games_reserve_unsettled_stakes(monkeypatch):
    games, odds = dataset()
    shift = games[-2].tipoff + timedelta(minutes=30) - games[-1].tipoff
    row = games[-1].model_dump()
    for key in ("tipoff", "completed_at", "available_at", "observed_at"):
        row[key] += shift
    games[-1] = type(games[-1]).model_validate(row)
    odds[-1] = odds[-1].model_copy(update={
        "observed_at": odds[-1].observed_at+shift,
        "available_at": odds[-1].available_at+shift})
    def fake_decision(*args):
        return {"action": "BET", "side": "under", "stake_fraction": .1,
                "probabilities": {"mean": 220, "over": .5, "under": .5, "push": 0,
                                  "model_digest": "synthetic-test"}}
    monkeypatch.setattr("betdoctore.backtest.decision", fake_decision)
    model = Model(trained_until=datetime(2019, 1, 1, tzinfo=UTC))
    result = run(games, odds[-2:], model, Settings())
    assert len(result["bets"]) == 2
    assert result["bets"][0]["stake"] == pytest.approx(.1)
    assert result["bets"][1]["stake"] == pytest.approx(.09)


def test_clv_requires_near_tipoff_exact_line_close(monkeypatch):
    games, odds = dataset()
    entry = odds[-1]
    def fake_decision(*args):
        return {"action": "BET", "side": "over", "stake_fraction": .01,
                "probabilities": {"mean": 220, "over": .5, "under": .5, "push": 0,
                                  "model_digest": "synthetic-test"}}
    monkeypatch.setattr("betdoctore.backtest.decision", fake_decision)
    model = Model(trained_until=datetime(2019, 1, 1, tzinfo=UTC))
    assert run(games, [entry], model, Settings())["bets"][0]["clv_price_ratio"] is None
    close = entry.model_copy(update={"source_id": "synthetic-close", "over": 1.8,
                                    "observed_at": games[-1].tipoff-timedelta(minutes=2),
                                    "available_at": games[-1].tipoff-timedelta(minutes=1)})
    result = run(games, [entry, close], model, Settings())
    assert result["bets"][0]["clv_price_ratio"] == pytest.approx(1.91/1.8-1)
    wrong_line = close.model_copy(update={"line": 221.5})
    assert run(games, [entry, wrong_line], model, Settings())["bets"][0]["clv_price_ratio"] is None


def test_cli_accepts_documented_aware_training_timestamp(tmp_path):
    import json

    from typer.testing import CliRunner

    from betdoctore.cli import app as cli
    games, _ = dataset(80)
    path = tmp_path/"synthetic-games.json"
    path.write_text(json.dumps([g.model_dump(mode="json") for g in games]))
    result = CliRunner().invoke(cli, ["train", str(path), "2021-01-01T00:00:00Z",
                                     "--output", str(tmp_path/"models")])
    assert result.exit_code == 0, result.output
    assert len(list((tmp_path/"models").glob("*.json"))) == 2
