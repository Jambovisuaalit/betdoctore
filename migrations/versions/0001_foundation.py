"""Initial provenance and artifact schema. Frozen independently of application models."""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("source_records",
                    sa.Column("id", sa.Integer, primary_key=True),
                    sa.Column("kind", sa.String, nullable=False),
                    sa.Column("source", sa.String, nullable=False),
                    sa.Column("source_id", sa.String, nullable=False),
                    sa.Column("game_id", sa.String, nullable=False),
                    sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("synthetic", sa.Boolean, nullable=False),
                    sa.Column("payload", sa.JSON, nullable=False),
                    sa.UniqueConstraint("kind", "source", "source_id"))
    for column in ("game_id", "observed_at", "available_at"):
        op.create_index(f"ix_source_records_{column}", "source_records", [column])
    op.create_table("feature_snapshots",
                    sa.Column("digest", sa.String, primary_key=True),
                    sa.Column("game_id", sa.String, nullable=False),
                    sa.Column("cutoff", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("version", sa.String, nullable=False),
                    sa.Column("payload", sa.JSON, nullable=False))
    op.create_index("ix_feature_snapshots_game_id", "feature_snapshots", ["game_id"])
    op.create_table("model_artifacts",
                    sa.Column("digest", sa.String, primary_key=True),
                    sa.Column("version", sa.String, nullable=False),
                    sa.Column("trained_until", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("sigma", sa.Float, nullable=False),
                    sa.Column("payload", sa.JSON, nullable=False))


def downgrade():
    for table in ("model_artifacts", "feature_snapshots", "source_records"):
        op.drop_table(table)
