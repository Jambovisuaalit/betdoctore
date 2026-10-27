import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from .backtest import run, write_reports
from .config import Configuration
from .domain import Game, Odds
from .engine import Model, Settings
from .fixtures import dataset
from .ingestion import ingest

app = typer.Typer(no_args_is_help=True)


@app.command()
def ingest_file(path: Path, kind: str):
    """Import game/odds CSV or Parquet with per-row quality report."""
    frame = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
    with Session(create_engine(Configuration().database_url)) as session:
        report = ingest(session, frame.to_dict("records"), kind)
        session.commit()
    typer.echo(json.dumps(report, indent=2))
    if report["errors"]:
        raise typer.Exit(1)


@app.command()
def fixture_backtest(output: Path = Path("reports/fixture")):
    """Run an explicitly synthetic wiring check with an uncalibrated baseline."""
    games, odds = dataset()
    model = Model(trained_until=datetime(2019, 1, 1, tzinfo=UTC))
    report = run(games, odds, model, Settings())
    write_reports(report, output)
    typer.echo(json.dumps(report["metrics"]))


@app.command()
def backtest(games: Path, odds: Path, artifact: Path, output: Path = Path("reports/research"),
             walk_forward: bool = False):
    """Run explicit JSON source records and a versioned model artifact."""
    game_rows = [Game.model_validate(r) for r in json.loads(games.read_text())]
    odds_rows = [Odds.model_validate(r) for r in json.loads(odds.read_text())]
    model = Model.model_validate_json(artifact.read_text())
    config = Configuration()
    report = run(game_rows, odds_rows, model, Settings(
        min_ev=config.min_ev, kelly_fraction=config.kelly_fraction,
        max_bankroll_fraction=config.max_bankroll_fraction), walk_forward=walk_forward)
    write_reports(report, output)
    typer.echo(json.dumps(report["metrics"]))


@app.command()
def status():
    typer.echo(json.dumps({"CODE_READY": "verification required", "DATA_READY": "BLOCKED",
                           "BACKTEST_READY": "synthetic only", "PRODUCTION_READY": False}))


@app.command()
def train(games: Path, trained_until: Annotated[datetime, typer.Argument(formats=["%Y-%m-%dT%H:%M:%S%z"])],
          output: Path = Path("artifacts")):
    """Fit baseline residual calibration with an explicit availability boundary."""
    from .training import fit, save
    records = [Game.model_validate(r) for r in json.loads(games.read_text())]
    model, evidence = fit(records, trained_until)
    typer.echo(save(model, evidence, output))


@app.command()
def feature_snapshot(game_id: str, home: str, away: str, tipoff: Annotated[datetime, typer.Argument(formats=["%Y-%m-%dT%H:%M:%S%z"])]):
    """Persist an immutable historical snapshot from ingested games."""
    from .repository import snapshot
    with Session(create_engine(Configuration().database_url)) as session:
        payload = snapshot(session, game_id, home, away, tipoff)
        session.commit()
    typer.echo(json.dumps(payload, indent=2))


@app.command()
def register_model(artifact: Path):
    """Register a versioned JSON artifact for the read-only API."""
    from .engine import digest
    from .storage import ModelArtifact
    model = Model.model_validate_json(artifact.read_text())
    payload = model.model_dump(mode="json")
    identity = digest(payload)
    with Session(create_engine(Configuration().database_url)) as session:
        if session.get(ModelArtifact, identity) is None:
            session.add(ModelArtifact(digest=identity, version=model.version,
                                      trained_until=model.trained_until, sigma=model.sigma,
                                      payload=payload))
            session.commit()
    typer.echo(identity)
