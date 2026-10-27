"""Validated, immutable source records. All timestamps must be timezone aware."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    source: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    observed_at: datetime
    available_at: datetime
    synthetic: bool = False

    @model_validator(mode="after")
    def timestamps(self):
        for value in self.__dict__.values():
            if isinstance(value, datetime) and value.utcoffset() is None:
                raise ValueError("Timezone-aware timestamps required")
        if self.available_at < self.observed_at:
            raise ValueError("Availability cannot precede observation")
        return self


class Game(Record):
    game_id: str
    tipoff: datetime
    completed_at: datetime
    home: str
    away: str
    home_points: int = Field(ge=0)
    away_points: int = Field(ge=0)
    home_possessions: float = Field(gt=0)
    away_possessions: float = Field(gt=0)
    overtime_periods: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def chronology(self):
        if self.home == self.away or self.completed_at <= self.tipoff:
            raise ValueError("Invalid game identity or completion time")
        if self.observed_at < self.completed_at:
            raise ValueError("Final statistics observed before completion")
        return self


class Odds(Record):
    game_id: str
    bookmaker: Literal["pinnacle", "bet365"]
    line: float = Field(gt=0)
    over: float = Field(gt=1)
    under: float = Field(gt=1)
    includes_overtime: bool = True

    @model_validator(mode="after")
    def grid(self):
        if self.line * 2 != int(self.line * 2):
            raise ValueError("Only integer and half-point totals supported")
        return self
