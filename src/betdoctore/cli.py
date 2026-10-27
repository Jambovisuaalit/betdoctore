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


@app.command()
def results_acquire(directory: Path = Path("data/results/neil-paine")):
    """Download only a pinned, licensed basic-result archive and its license."""
    from .result_sources import acquire
    typer.echo(str(acquire(directory)))


@app.command()
def results_import(directory: Path = Path("data/results/neil-paine"),
                   start: str = "2021-01-01", end: str = "2026-10-27"):
    """Audit and persist basic results without filling missing advanced statistics."""
    from datetime import date

    from .result_sources import normalize, persist
    records, report, manifest = normalize(directory, date.fromisoformat(start), date.fromisoformat(end))
    if report["structural_status"] != "PASS":
        typer.echo(json.dumps(report, indent=2))
        raise typer.Exit(1)
    with Session(create_engine(Configuration().database_url)) as session:
        imported = persist(session, records, manifest, report)
        session.commit()
    typer.echo(json.dumps({"database": imported, "audit": report}, indent=2))


@app.command()
def private_results_import(directory: Path = Path("data/results/private-fixturedownload"),
                           start: str = "2021-01-01", end: str = "2026-10-27",
                           private_research: bool = False):
    """Personal non-commercial results. Raw records are excluded from public API/Git."""
    from datetime import date

    from .private_results import acquire_private, normalize_private
    from .result_sources import persist
    if not private_research:
        raise typer.BadParameter("Use --private-research only for personal non-commercial scope")
    summaries = []
    for year in range(2020, 2027):
        acquire_private(directory, year, private_research=True)
        records, report, manifest = normalize_private(directory/str(year), date.fromisoformat(start),
                                                     date.fromisoformat(end))
        if report["structural_status"] != "PASS":
            raise typer.BadParameter(f"Season {year}: inspect local audit before importing")
        with Session(create_engine(Configuration().database_url)) as session:
            imported = persist(session, records, manifest, report)
            session.commit()
        summaries.append({"season_start": year, "imported": imported})
    typer.echo(json.dumps({"use_scope": "private_noncommercial", "seasons": summaries}, indent=2))


@app.command()
def results_reconcile(output: Path = Path("data/results/private-reconciliation"),
                      start: str = "2021-01-01", end: str = "2026-10-27"):
    """Write local cross-source reconciliation; conflicts stay quarantined."""
    from datetime import date

    from sqlalchemy import select

    from .result_reconciliation import reconcile, save_reconciliation
    from .results import BasicResult
    from .storage import BasicResultRow
    with Session(create_engine(Configuration().database_url)) as session:
        records = [BasicResult.model_validate(r.payload)
                   for r in session.scalars(select(BasicResultRow)).all()]
    report = reconcile(records, date.fromisoformat(start), date.fromisoformat(end))
    path = save_reconciliation(report, output)
    typer.echo(json.dumps({"report": str(path), **{k: v for k, v in report.items()
                                                  if k not in {"accepted", "quarantine",
                                                               "possible_date_conflicts"}}}, indent=2))


@app.command()
def availability_acquire(directory: Path = Path("data/availability/wayback"),
                         source: str = "fivethirtyeight"):
    """Fetch checksum-verified public historical captures; never backdate ingestion."""
    from .historical_availability import acquire_captures
    typer.echo(json.dumps(acquire_captures(directory, source=source), indent=2))


@app.command()
def foundation_audit(root: Path = Path("data/results"),
                     captures: Path = Path("data/availability/wayback"),
                     index: Path = Path("data/availability/wayback"),
                     as_of: str = "2026-10-27", output: Path = Path("data/coverage/reports")):
    """Audit season boundaries, count/identity gaps and field-scoped availability evidence."""
    from datetime import date

    from .season_audit import run_foundation_audit
    typer.echo(str(run_foundation_audit(root, captures, index, date.fromisoformat(as_of), output)))


@app.command("regular-season-verify")
def regular_season_verify(
    reference_file: Path,
    provenance_file: Path,
    root: Path = Path("data/results"),
    output: Path = Path("data/coverage/approved"),
    as_of: str = "2026-10-27",
):
    """Reconcile an independent licensed event manifest against private local results."""
    from datetime import date

    from .independent_regular_season import run_regular_season_audit
    path = run_regular_season_audit(
        root, reference_file, provenance_file, output, date.fromisoformat(as_of)
    )
    typer.echo(str(path))


@app.command("reference-bdl-acquire")
def reference_bdl_acquire(
    output: Path = Path("data/coverage/independent/balldontlie"),
    execute: bool = False,
    start_year: int = 2020,
    end_year: int = 2025,
    max_requests: int = 100,
):
    """Dry-run by default; opt-in free Games API download into local-only archive."""
    from .bdl_reference import run

    typer.echo(json.dumps(run(output, execute, start_year, end_year, max_requests), indent=2))


@app.command()
def regular_manifest(root: Path = Path("data/results"), captures: Path = Path("data/availability/wayback"),
                     as_of: str = "2026-10-27", output: Path = Path("data/regular-season")):
    """Curate regular targets; keep postseason in its own nonblocking queue."""
    from datetime import date

    from .historical_availability import capture_evidence, load_capture_index
    from .regular_season import build_regular_manifest, save_regular_manifest
    from .season_audit import load_contract, load_full_sources
    records, schedules, _ = load_full_sources(root,date.fromisoformat(as_of))
    earliest, _ = capture_evidence(captures,load_capture_index(captures))
    manifest = build_regular_manifest(records,schedules,load_contract(),date.fromisoformat(as_of),earliest)
    path = save_regular_manifest(manifest,output)
    typer.echo(json.dumps({"manifest":str(path),"regular_games":manifest["regular_catalog_games"],
                          "consistent":manifest["consistent_result_games"],
                          "quarantined":manifest["quarantined_regular_games"]},indent=2))


@app.command()
def regular_evaluation_acquire(directory: Path = Path("data/evaluation/schedule-captures"),
                               private_research: bool = False):
    """Acquire the pinned historical schedules for the private baseline assessment."""
    from .regular_evaluation import acquire_schedule_captures
    if not private_research:
        raise typer.BadParameter("Personal non-commercial scope requires --private-research")
    typer.echo(json.dumps(acquire_schedule_captures(directory),indent=2))


@app.command()
def regular_evaluate(manifest: Path, history: Path = Path("data/availability/wayback"),
                     schedules: Path = Path("data/evaluation/schedule-captures"),
                     output: Path = Path("data/evaluation/real-regular-v1"),
                     result_root: Path = Path("data/results")):
    """Freeze causal score-only forecasts, then assess the exact real regular cohort."""
    from .regular_evaluation import run_evaluation
    path,result = run_evaluation(history,schedules,manifest,output,result_root)
    typer.echo(json.dumps({"report":str(path),"status":result["status"],
                          "model":result["model_metrics"],"benchmark":result["benchmark_metrics"]},indent=2))


@app.command()
def advanced_stage(manifest: Path, rows: Path, raw_source: Path | None = None):
    """Append an isolated advanced-data batch; incomplete evidence remains quarantined."""
    from .advanced_staging import AdvancedSourceManifest, stage_batch
    source = AdvancedSourceManifest.model_validate_json(manifest.read_text())
    with Session(create_engine(Configuration().database_url)) as session:
        report = stage_batch(session,source,json.loads(rows.read_text()),
                             source_bytes=raw_source.read_bytes() if raw_source else None)
        session.commit()
    typer.echo(json.dumps(report,indent=2))


@app.command()
def advanced_readiness(batch: str, curated_keys: Path, manifest: Path,
                       cutoff: Annotated[datetime,typer.Argument(formats=["%Y-%m-%dT%H:%M:%S%z"])],
                       prediction_tipoff: Annotated[datetime,typer.Argument(formats=["%Y-%m-%dT%H:%M:%S%z"])]):
    """Assess a selected regular subset; this command never promotes staged rows."""
    from .advanced_staging import readiness_report
    from .regular_season import target_gate
    keys = set(json.loads(curated_keys.read_text()))
    regular = json.loads(manifest.read_text())
    if not keys or any(not target_gate(regular,key)["passed"] for key in keys):
        raise typer.BadParameter("Each selected game must pass the explicit regular result gate")
    with Session(create_engine(Configuration().database_url)) as session:
        report = readiness_report(session,batch,cutoff,keys,prediction_tipoff,
                                  normalization_verified=False,real_evaluation=True)
    typer.echo(json.dumps(report,indent=2))
