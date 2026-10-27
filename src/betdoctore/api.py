"""Read-only API. Never returns database credentials or source payloads."""
from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import Configuration
from .storage import Snapshot

app = FastAPI(title="BetDoctore", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "production_ready": False}


@app.get("/ready")
def ready():
    try:
        with create_engine(Configuration().database_url).connect() as connection:
            connection.execute(text("SELECT digest FROM feature_snapshots LIMIT 1"))
    except SQLAlchemyError:
        raise HTTPException(503, "Database unavailable or migrations missing") from None
    return {"database": "ready", "production_ready": False}


@app.get("/snapshots/{game_id}")
def snapshots(game_id: str):
    engine = create_engine(Configuration().database_url)
    try:
        with Session(engine) as session:
            rows = session.scalars(select(Snapshot).where(Snapshot.game_id == game_id)).all()
            return [{"digest": r.digest, "payload": r.payload} for r in rows]
    finally:
        engine.dispose()


@app.get("/analysis/{game_id}")
def analysis(game_id: str):
    from .domain import Odds
    from .engine import Model, Settings, decision
    from .storage import ModelArtifact, SourceRecord
    engine = create_engine(Configuration().database_url)
    try:
        with Session(engine) as session:
            snap = session.scalar(select(Snapshot).where(Snapshot.game_id == game_id)
                                  .order_by(Snapshot.cutoff.desc()))
            if snap is None:
                raise HTTPException(404, "No feature snapshot")
            artifact = session.scalar(select(ModelArtifact).where(
                ModelArtifact.trained_until <= snap.cutoff).order_by(
                    ModelArtifact.trained_until.desc()))
            if artifact is None:
                raise HTTPException(404, "No point-in-time model artifact")
            rows = session.scalars(select(SourceRecord).where(
                SourceRecord.kind == "odds", SourceRecord.game_id == game_id,
                SourceRecord.available_at <= snap.cutoff,
                SourceRecord.observed_at <= snap.cutoff)).all()
            offers = [Odds.model_validate(row.payload) for row in rows]
            latest = {}
            for offer in sorted(offers, key=lambda o: (o.observed_at, o.source_id)):
                latest[(offer.bookmaker, offer.line, offer.includes_overtime)] = offer
            config = Configuration()
            settings = Settings(min_ev=config.min_ev, kelly_fraction=config.kelly_fraction,
                                max_bankroll_fraction=config.max_bankroll_fraction)
            model = Model.model_validate(artifact.payload)
            return {"feature_digest": snap.digest, "model_digest": artifact.digest,
                    "synthetic": snap.payload.get("synthetic", False) or model.synthetic
                    or any(o.synthetic for o in offers),
                    "offers": [{"bookmaker": o.bookmaker, "line": o.line,
                                "source_id": o.source_id,
                                "analysis": decision(o, snap.payload, model, settings)}
                               for o in latest.values()]}
    finally:
        engine.dispose()


@app.get("/results")
def basic_results(year: int = 2021, offset: int = 0, limit: int = 100):
    """Observed basic results only; these records do not feed the advanced engine."""
    from .storage import BasicResultRow, ResultSourceSnapshot
    if year not in range(2021, 2027) or offset < 0 or not 1 <= limit <= 500:
        raise HTTPException(422, "Year 2021–2026, offset >= 0 and limit 1–500 required")
    engine = create_engine(Configuration().database_url)
    try:
        with Session(engine) as session:
            rows = session.scalars(select(BasicResultRow).where(
                BasicResultRow.payload["game_date"].as_string().startswith(str(year)),
                BasicResultRow.payload["source"].as_string() == "neil-paine-nba-elo")
                .order_by(BasicResultRow.game_key, BasicResultRow.snapshot_sha256)
                .offset(offset).limit(limit)).all()
            manifests = {r.snapshot_sha256: session.get(ResultSourceSnapshot, r.snapshot_sha256).manifest
                         for r in rows}
            return {"results": [r.payload for r in rows], "source_manifests": manifests,
                    "year": year, "offset": offset, "limit": limit,
                    "advanced_statistics_imported": False,
                    "historical_point_in_time_ready": False,
                    "integrity_status": "STRUCTURAL_ONLY_NOT_FULLY_VERIFIED"}
    finally:
        engine.dispose()
