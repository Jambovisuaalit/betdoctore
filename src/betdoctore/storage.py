"""Append-only provenance records and reproducible feature/model snapshots."""
from sqlalchemy import JSON, Boolean, DateTime, Float, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SourceRecord(Base):
    __tablename__ = "source_records"
    __table_args__ = (UniqueConstraint("kind", "source", "source_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String)
    source_id: Mapped[str] = mapped_column(String)
    game_id: Mapped[str] = mapped_column(String, index=True)
    observed_at: Mapped[object] = mapped_column(DateTime(timezone=True), index=True)
    available_at: Mapped[object] = mapped_column(DateTime(timezone=True), index=True)
    synthetic: Mapped[bool] = mapped_column(Boolean)
    payload: Mapped[dict] = mapped_column(JSON)


class Snapshot(Base):
    __tablename__ = "feature_snapshots"
    digest: Mapped[str] = mapped_column(String, primary_key=True)
    game_id: Mapped[str] = mapped_column(String, index=True)
    cutoff: Mapped[object] = mapped_column(DateTime(timezone=True))
    version: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON)


class ModelArtifact(Base):
    __tablename__ = "model_artifacts"
    digest: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[str] = mapped_column(String)
    trained_until: Mapped[object] = mapped_column(DateTime(timezone=True))
    sigma: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict] = mapped_column(JSON)
