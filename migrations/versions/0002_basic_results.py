"""Basic result observations separate from advanced-statistic source records."""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("result_source_snapshots",
                    sa.Column("sha256", sa.String, primary_key=True),
                    sa.Column("source", sa.String, nullable=False),
                    sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("manifest", sa.JSON, nullable=False))
    op.create_table("basic_results",
                    sa.Column("id", sa.Integer, primary_key=True),
                    sa.Column("snapshot_sha256", sa.String, nullable=False),
                    sa.Column("game_key", sa.String, nullable=False),
                    sa.Column("payload", sa.JSON, nullable=False),
                    sa.UniqueConstraint("snapshot_sha256", "game_key"))
    op.create_index("ix_basic_results_game_key", "basic_results", ["game_key"])


def downgrade():
    op.drop_table("basic_results")
    op.drop_table("result_source_snapshots")
