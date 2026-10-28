"""Append-only provenance records and reproducible feature/model snapshots."""
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, UniqueConstraint
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


class ResultSourceSnapshot(Base):
    __tablename__ = "result_source_snapshots"
    sha256: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String)
    retrieved_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    manifest: Mapped[dict] = mapped_column(JSON)


class BasicResultRow(Base):
    __tablename__ = "basic_results"
    __table_args__ = (UniqueConstraint("snapshot_sha256", "game_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_sha256: Mapped[str] = mapped_column(String)
    game_key: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class AdvancedStageBatch(Base):
    __tablename__ = "advanced_stage_batches"
    digest: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String)
    snapshot_sha256: Mapped[str] = mapped_column(String)
    retrieved_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    manifest: Mapped[dict] = mapped_column(JSON)


class AdvancedStageRow(Base):
    __tablename__ = "advanced_stage_rows"
    __table_args__ = (UniqueConstraint("batch_digest", "source_row_id"),)
    digest: Mapped[str] = mapped_column(String, primary_key=True)
    batch_digest: Mapped[str] = mapped_column(String, ForeignKey("advanced_stage_batches.digest"), index=True)
    source_row_id: Mapped[str] = mapped_column(String)
    content_digest: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON)
    validation_reasons: Mapped[list] = mapped_column(JSON)
