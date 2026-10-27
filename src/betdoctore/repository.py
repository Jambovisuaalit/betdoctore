from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .domain import Game
from .engine import features
from .storage import Snapshot, SourceRecord


def snapshot(session: Session, game_id: str, home: str, away: str, tipoff: datetime) -> dict:
    records = session.scalars(select(SourceRecord).where(SourceRecord.kind == "game")).all()
    payload = features([Game.model_validate(r.payload) for r in records],
                       game_id, home, away, tipoff)
    if session.get(Snapshot, payload["digest"]) is None:
        session.add(Snapshot(digest=payload["digest"], game_id=game_id,
                             cutoff=datetime.fromisoformat(payload["cutoff"]),
                             version=payload["version"], payload=payload))
        session.flush()
    return payload
