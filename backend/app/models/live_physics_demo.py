"""Separate synthetic event/checkpoint ledger; never canonical telemetry."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LivePhysicsDemoEvent(Base):
    __tablename__ = "live_physics_demo_events"
    transformer_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("transformers.id"), primary_key=True
    )
    run_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    __table_args__ = (Index("ix_live_physics_demo_asset_time", "transformer_id", "timestamp"),)
