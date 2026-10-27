"""Explicit synthetic integration dataset; never a performance claim."""
from datetime import UTC, datetime, timedelta

from .domain import Game, Odds


def dataset(count: int = 20):
    games, odds = [], []
    start = datetime(2020, 1, 1, 20, tzinfo=UTC)
    for i in range(count):
        tip = start + timedelta(days=i*2)
        games.append(Game(source="synthetic", source_id=f"g{i}", game_id=f"g{i}",
                          observed_at=tip+timedelta(hours=3),
                          available_at=tip+timedelta(hours=3), synthetic=True,
                          tipoff=tip, completed_at=tip+timedelta(hours=3),
                          home="AAA", away="BBB", home_points=108+i%7, away_points=102+i%9,
                          home_possessions=98+i%4, away_possessions=99+i%4))
        odds.append(Odds(source="synthetic", source_id=f"o{i}", game_id=f"g{i}",
                         observed_at=tip-timedelta(minutes=90),
                         available_at=tip-timedelta(minutes=89), synthetic=True,
                         bookmaker="pinnacle", line=220.5, over=1.91, under=1.91))
    return games, odds
