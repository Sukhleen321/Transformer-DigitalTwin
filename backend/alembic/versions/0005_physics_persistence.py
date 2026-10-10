"""Add isolated physics persistence; no fixtures or legacy data changes."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "physics_records",
        sa.Column(
            "transformer_id", sa.String(128), sa.ForeignKey("transformers.id"), primary_key=True
        ),
        sa.Column("kind", sa.String(32), primary_key=True),
        sa.Column("identity", sa.String(128), primary_key=True),
        sa.Column("content", JSONB(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column(
            "published_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "physics_profiles",
        sa.Column(
            "transformer_id", sa.String(128), sa.ForeignKey("transformers.id"), primary_key=True
        ),
        sa.Column("configuration_version", sa.String(128), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "physics_events",
        sa.Column(
            "telemetry_id",
            sa.BigInteger(),
            sa.ForeignKey("telemetry.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "transformer_id", sa.String(128), sa.ForeignKey("transformers.id"), nullable=False
        ),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("result", JSONB(), nullable=False),
        sa.Column("result_sha256", sa.String(64), nullable=False),
        sa.Column("outcome", sa.String(64), nullable=False),
    )
    op.create_index(
        "ix_physics_events_asset_event_desc",
        "physics_events",
        ["transformer_id", sa.text("event_time DESC")],
    )
    op.create_table(
        "physics_checkpoints",
        sa.Column(
            "transformer_id", sa.String(128), sa.ForeignKey("transformers.id"), primary_key=True
        ),
        sa.Column(
            "telemetry_id",
            sa.BigInteger(),
            sa.ForeignKey("telemetry.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("body", JSONB(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.execute("""CREATE FUNCTION physics_record_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Published physics identities are immutable'; END; $$""")
    op.execute("""CREATE TRIGGER physics_record_immutable BEFORE UPDATE OR DELETE ON physics_records
        FOR EACH ROW EXECUTE FUNCTION physics_record_immutable()""")
    op.execute("""CREATE TRIGGER physics_event_immutable BEFORE UPDATE ON physics_events
        FOR EACH ROW EXECUTE FUNCTION physics_record_immutable()""")


def downgrade():
    op.drop_table("physics_checkpoints")
    op.drop_table("physics_events")
    op.drop_table("physics_profiles")
    op.drop_table("physics_records")
    op.execute("DROP FUNCTION physics_record_immutable()")
