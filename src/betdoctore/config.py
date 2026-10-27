from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Configuration(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///betdoctore.db"
    min_ev: float = Field(default=.045, ge=0)
    kelly_fraction: float = Field(default=.25, gt=0, le=1)
    max_bankroll_fraction: float = Field(default=.01, gt=0, le=1)

    @field_validator("database_url")
    @classmethod
    def validate_database(cls, value):
        if not value.startswith(("sqlite:///", "postgresql+psycopg://")):
            raise ValueError("Use PostgreSQL psycopg or local SQLite")
        return value
