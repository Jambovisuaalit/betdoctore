"""Authorized exports only; never scrape bookmaker websites."""
from datetime import UTC
from pathlib import Path
from typing import Protocol

import pandas as pd
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .domain import Game, Odds
from .storage import SourceRecord


class OddsProvider(Protocol):
    def snapshots(self) -> list[Odds]: ...


class ExportProvider:
    def __init__(self, path: Path, bookmaker: str | None = None):
        self.path, self.bookmaker = path, bookmaker

    def snapshots(self) -> list[Odds]:
        frame = (pd.read_parquet(self.path) if self.path.suffix == ".parquet"
                 else pd.read_csv(self.path))
        rows = [Odds.model_validate(row) for row in frame.to_dict("records")]
        if self.bookmaker and any(x.bookmaker != self.bookmaker for x in rows):
            raise ValueError("Export contains wrong bookmaker")
        return rows


class PinnacleAdapter(ExportProvider):
    def __init__(self, authorized_export: Path):
        super().__init__(authorized_export, "pinnacle")


class Bet365Adapter(ExportProvider):
    def __init__(self, authorized_export: Path):
        super().__init__(authorized_export, "bet365")


def ingest(session: Session, rows: list[dict], kind: str) -> dict:
    if kind not in {"game", "odds"}:
        raise ValueError("Unknown record kind")
    schema = Game if kind == "game" else Odds
    report = {"accepted": 0, "duplicates": 0, "errors": []}
    for index, row in enumerate(rows):
        try:
            record = schema.model_validate(row)
            existing = session.scalar(select(SourceRecord).where(
                SourceRecord.kind == kind, SourceRecord.source == record.source,
                SourceRecord.source_id == record.source_id))
            payload = record.model_dump(mode="json")
            if existing:
                if existing.payload != payload:
                    raise ValueError("Conflicting source identity; corrections need new source_id")
                report["duplicates"] += 1
                continue
            session.add(SourceRecord(
                kind=kind, source=record.source, source_id=record.source_id,
                game_id=record.game_id, observed_at=record.observed_at,
                available_at=record.available_at, synthetic=record.synthetic, payload=payload))
            session.flush()
            report["accepted"] += 1
        except (ValidationError, ValueError) as exc:
            report["errors"].append({"row": index, "error": str(exc)})
    return report


class HistoricalOddsAPI:
    """Paid historical endpoint; bookmaker coverage depends on subscription/date.

    Archive timestamps reconstruct historical availability, not local receipt time.
    The caller must confirm overtime settlement rules from their licensed contract.
    """
    def __init__(self, api_key: str, at, includes_overtime: bool, client=None):
        import httpx
        if not api_key or at.utcoffset() is None:
            raise ValueError("API key and aware historical timestamp required")
        self.api_key, self.at = api_key, at
        self.includes_overtime = includes_overtime
        self.client = client or httpx.Client(timeout=30)

    def snapshots(self) -> list[Odds]:
        from datetime import datetime

        from .engine import digest
        response = self.client.get(
            "https://api.the-odds-api.com/v4/historical/sports/basketball_nba/odds",
            params={"apiKey": self.api_key, "bookmakers": "pinnacle,bet365",
                    "markets": "totals", "oddsFormat": "decimal",
                    "date": self.at.astimezone(UTC).isoformat().replace("+00:00", "Z")})
        # Do not expose request URLs containing the API key in error messages.
        if response.status_code != 200:
            raise ValueError(f"Historical provider status {response.status_code}")
        payload = response.json()
        stamp = datetime.fromisoformat(payload["timestamp"])
        if stamp > self.at:
            raise ValueError("Provider returned a future archive snapshot")
        rows = []
        for event in payload["data"]:
            for book in event["bookmakers"]:
                if book["key"] not in {"pinnacle", "bet365"}:
                    continue
                for market in book["markets"]:
                    if market["key"] != "totals":
                        continue
                    outcomes = market["outcomes"]
                    over = {x["point"]: x["price"] for x in outcomes if x["name"] == "Over"}
                    under = {x["point"]: x["price"] for x in outcomes if x["name"] == "Under"}
                    for line in sorted(over.keys() & under.keys()):
                        identity = {"event": event["id"], "book": book["key"],
                                    "line": line, "archive": stamp.isoformat(),
                                    "over": over[line], "under": under[line]}
                        rows.append(Odds(source="the-odds-api:archive", source_id=digest(identity),
                                         game_id=event["id"], bookmaker=book["key"], line=line,
                                         over=over[line], under=under[line], observed_at=stamp,
                                         available_at=stamp,
                                         includes_overtime=self.includes_overtime))
        return rows
