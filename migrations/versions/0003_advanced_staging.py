"""Isolated append-only advanced metric staging; no production feature promotion."""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("advanced_stage_batches",
                    sa.Column("digest", sa.String, primary_key=True),
                    sa.Column("source", sa.String, nullable=False),
                    sa.Column("snapshot_sha256", sa.String, nullable=False),
                    sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("manifest", sa.JSON, nullable=False))
    op.create_table("advanced_stage_rows",
                    sa.Column("digest", sa.String, primary_key=True),
                    sa.Column("batch_digest", sa.String, nullable=False),
                    sa.Column("source_row_id", sa.String, nullable=False),
                    sa.Column("content_digest", sa.String, nullable=False),
                    sa.Column("status", sa.String, nullable=False),
                    sa.Column("payload", sa.JSON, nullable=False),
                    sa.Column("validation_reasons", sa.JSON, nullable=False),
                    sa.UniqueConstraint("batch_digest", "source_row_id"),
                    sa.ForeignKeyConstraint(["batch_digest"], ["advanced_stage_batches.digest"]))
    op.create_index("ix_advanced_stage_rows_batch_digest", "advanced_stage_rows", ["batch_digest"])


def downgrade():
    op.drop_table("advanced_stage_rows")
    op.drop_table("advanced_stage_batches")
