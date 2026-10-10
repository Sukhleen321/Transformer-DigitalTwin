"""Empty opt-in demo ledger; no data/configuration/profile publication."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "live_physics_demo_events",
        sa.Column(
            "transformer_id", sa.String(128), sa.ForeignKey("transformers.id"), primary_key=True
        ),
        sa.Column("run_id", sa.String(32), primary_key=True),
        sa.Column("sequence", sa.Integer(), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", JSONB(), nullable=False),
        sa.Column("checkpoint", JSONB(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
    )
    op.create_index(
        "ix_live_physics_demo_asset_time",
        "live_physics_demo_events",
        ["transformer_id", "timestamp"],
    )


def downgrade():
    op.drop_table("live_physics_demo_events")
