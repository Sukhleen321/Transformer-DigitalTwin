"""Bounded PostgreSQL physics writes; caller owns locking and transaction."""

from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import delete, func, select, true
from sqlalchemy.dialects.postgresql import insert

from app.models.physics import PhysicsCheckpoint, PhysicsEvent, PhysicsProfile, PhysicsRecord
from app.models.telemetry import Telemetry
from app.services.physics_codec import KINDS, digest, identity

MAX_RECORDS = 4096
MAX_EVENTS = 4096
RETENTION_DAYS = 31


def publish_record(session, asset, kind, version, content):
    identity(version)
    if kind not in KINDS:
        raise ValueError("Unsupported physics record kind.")
    sha = digest(content)
    row = session.get(PhysicsRecord, (asset, kind, version))
    if row is not None:
        if row.sha256 != sha or row.content != content:
            raise HTTPException(409, {"code": "IMMUTABLE_IDENTITY_CONFLICT"})
        return row
    count = session.scalar(
        select(func.count()).select_from(PhysicsRecord).where(PhysicsRecord.transformer_id == asset)
    )
    if count >= MAX_RECORDS:
        raise HTTPException(422, {"code": "PHYSICS_RECORD_CAP"})
    row = PhysicsRecord(
        transformer_id=asset, kind=kind, identity=version, content=content, sha256=sha
    )
    session.add(row)
    session.flush()
    return row


def resolve(session, asset, kind, version):
    if version is None:
        return None
    row = session.get(PhysicsRecord, (asset, kind, version), populate_existing=True)
    if row is None or row.sha256 != digest(row.content):
        raise ValueError("Physics identity is missing or corrupt.")
    return row.content


def selected_telemetry(session, asset, cutoff):
    return session.scalar(
        select(Telemetry)
        .where(
            Telemetry.transformer_id == asset,
            Telemetry.timestamp <= cutoff,
            Telemetry.timestamp >= cutoff - timedelta(days=RETENTION_DAYS),
        )
        .order_by(Telemetry.timestamp.desc())
        .limit(1)
    )


def save_event(session, row):
    session.add(row)
    session.flush()


def save_checkpoint(session, event, body):
    session.execute(
        insert(PhysicsCheckpoint)
        .values(
            transformer_id=event.transformer_id,
            telemetry_id=event.telemetry_id,
            event_time=event.event_time,
            body=body,
            sha256=digest(body),
        )
        .on_conflict_do_update(
            index_elements=[PhysicsCheckpoint.transformer_id],
            set_={
                "telemetry_id": event.telemetry_id,
                "event_time": event.event_time,
                "body": body,
                "sha256": digest(body),
                "updated_at": func.now(),
            },
        )
    )


def prune(session, asset, keep, now):
    # Deletes remain asset-local. The head event is always kept for recovery.
    oldest = session.scalar(
        select(PhysicsEvent.event_time)
        .where(PhysicsEvent.transformer_id == asset, PhysicsEvent.telemetry_id != keep)
        .order_by(PhysicsEvent.event_time.desc())
        .offset(max(0, MAX_EVENTS - 2))
        .limit(1)
    )
    expired = (
        true()
        if MAX_EVENTS == 1
        else PhysicsEvent.received_at < now - timedelta(days=RETENTION_DAYS)
    )
    if oldest is not None:
        expired = expired | (PhysicsEvent.event_time < oldest)
    session.execute(
        delete(PhysicsEvent).where(
            PhysicsEvent.transformer_id == asset, PhysicsEvent.telemetry_id != keep, expired
        )
    )


def profile(session, asset):
    return session.get(PhysicsProfile, asset, populate_existing=True)


def checkpoint(session, asset):
    return session.get(PhysicsCheckpoint, asset, populate_existing=True)
