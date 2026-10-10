"""Separate physics identities, profile pointer, event ledger and checkpoint."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PhysicsRecord(Base):
    __tablename__ = "physics_records"
    transformer_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("transformers.id"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    identity: Mapped[str] = mapped_column(String(128), primary_key=True)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    sha256: Mapped[str] = mapped_column(String(64))
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PhysicsProfile(Base):
    __tablename__ = "physics_profiles"
    transformer_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("transformers.id"), primary_key=True
    )
    configuration_version: Mapped[str] = mapped_column(String(128))
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PhysicsEvent(Base):
    __tablename__ = "physics_events"
    telemetry_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("telemetry.id", ondelete="CASCADE"), primary_key=True
    )
    transformer_id: Mapped[str] = mapped_column(String(128), ForeignKey("transformers.id"))
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    snapshot_sha256: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    result_sha256: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        Index("ix_physics_events_asset_event_desc", transformer_id, event_time.desc()),
    )


class PhysicsCheckpoint(Base):
    __tablename__ = "physics_checkpoints"
    transformer_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("transformers.id"), primary_key=True
    )
    telemetry_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("telemetry.id", ondelete="CASCADE")
    )
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    body: Mapped[dict[str, Any]] = mapped_column(JSONB)
    sha256: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
