"""Serialized synthetic writes from a separate producer; GET never writes."""

import copy
import hashlib
import re
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

import numpy as np
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.models.live_physics_demo import LivePhysicsDemoEvent
from app.models.transformer import Transformer
from app.schemas.live_physics_demo import LivePhysicsDemoResult
from app.services import physics_codec as codec
from app.services.query_service import require_transformer
from ml.demo_physics.fem import SheetFEM
from ml.demo_physics.scenario import CASE, DemoRun, validate_raw


@lru_cache(maxsize=1)
def reference_fem():
    return SheetFEM()


@lru_cache(maxsize=1)
def model_digest():
    import ml.demo_physics.fem as fem_module
    import ml.demo_physics.scenario as scenario_module

    return hashlib.sha256(
        Path(fem_module.__file__).read_bytes() + Path(scenario_module.__file__).read_bytes()
    ).hexdigest()


def enabled(settings, session):
    database = make_url(settings.database_url).database or ""
    binding = session.get_bind()
    bound = getattr(binding, "engine", binding).url.database
    return (
        settings.physics_enabled
        and settings.live_physics_demo_enabled
        and settings.env == "local-demo"
        and re.fullmatch(r"live_physics_demo_[0-9a-f]{32}", database) is not None
        and database == bound
    )


def latest(session, asset):
    return session.scalar(
        select(LivePhysicsDemoEvent)
        .where(LivePhysicsDemoEvent.transformer_id == asset)
        .order_by(LivePhysicsDemoEvent.timestamp.desc())
        .limit(1)
    )


def checkpoint(run):
    return dict(
        case_id=CASE,
        model_digest=model_digest(),
        epoch=codec.encode(run.epoch),
        run_id=run.run_id,
        sequence=run.sequence,
        variable_ambient=run.variable_ambient,
        thermal=codec.encode(run.estimator.state(run.asset)),
        fields=run.fields.tolist(),
        sensor_k=run.sensor_k,
        hours=run.hours,
    )


def restore(row, fem=None):
    if codec.digest(dict(result=row.result, checkpoint=row.checkpoint)) != row.sha256:
        raise ValueError("Demo event/checkpoint digest mismatch")
    body = LivePhysicsDemoResult.model_validate(row.result)
    cp = row.checkpoint
    if (
        cp["case_id"] != CASE
        or cp.get("model_digest") != model_digest()
        or cp["run_id"] != row.run_id
        or body.run_id != row.run_id
        or cp["sequence"] != row.sequence
        or body.sequence != row.sequence
        or body.timestamp != row.timestamp
        or body.transformer_id != row.transformer_id
    ):
        raise ValueError("Demo checkpoint identity mismatch")
    run = DemoRun(
        row.transformer_id,
        codec.time(cp["epoch"]),
        row.run_id,
        fem or reference_fem(),
        variable_ambient=cp.get("variable_ambient", False),
    )
    thermal = codec.thermal_state(cp["thermal"])
    if thermal is None or thermal.timestamp != row.timestamp or thermal.started_at != run.epoch:
        raise ValueError("Demo thermal watermark mismatch")
    inputs = validate_raw(
        cp["raw_event"],
        row.transformer_id,
        row.run_id,
        row.sequence,
        row.timestamp,
        variable_ambient=run.variable_ambient,
    )
    if (
        any(getattr(body.inputs, name) != inputs[name] for name in type(body.inputs).model_fields)
        or inputs["oil_sensor_k"] != cp["sensor_k"]
        or abs(
            body.components["measured_oil_temperature"].value - (inputs["oil_sensor_k"] - 273.15)
        )
        > 1e-10
        or thermal.oil_heat_w != inputs["oil_heat_w"]
        or thermal.winding_heat_w != inputs["winding_heat_w"]
    ):
        raise ValueError("Raw simulation event/result/state mismatch")
    fields = np.asarray(cp["fields"], dtype=float)
    if (
        fields.shape != (2 * run.fem.count,)
        or not np.all(np.isfinite(fields))
        or fields.min() < 250
        or fields.max() > 400
        or type(cp["sensor_k"]) not in (float, int)
        or not 250 <= cp["sensor_k"] <= 400
        or type(cp["hours"]) not in (float, int)
        or not np.isfinite(cp["hours"])
        or cp["hours"] < 0
    ):
        raise ValueError("Invalid demo checkpoint fields")
    if (
        max(
            abs(a - b)
            for a, b in zip(run.fem.means(fields), (thermal.oil_k, thermal.winding_k), strict=True)
        )
        > 1e-8
    ):
        raise ValueError("Demo checkpoint mean mismatch")
    run.estimator._states[run.asset] = thermal  # existing guarded codec, fresh owned estimator
    run.fields, run.sensor_k, run.hours, run.sequence = (
        fields,
        cp["sensor_k"],
        cp["hours"],
        cp["sequence"],
    )
    return run


def write(session, asset, event, run_id, fem=None):
    if not enabled(get_settings(), session):
        raise ValueError("Demo producer restricted to opted-in newly named local-demo database")
    row = session.scalar(select(Transformer).where(Transformer.id == asset).with_for_update())
    if row is None or row.name != "LIVE SIMULATION · " + asset:
        raise ValueError("Only explicitly registered synthetic demo assets can be written")
    head = latest(session, asset)
    run = restore(head, fem) if head else DemoRun(asset, event, run_id, fem or reference_fem())
    if run.run_id != run_id:
        raise ValueError("Another demo run owns this asset")
    raw_event = run.generate(event)
    return persist(session, run, event, raw_event)


def persist(session, run, event, raw_event, *, source=None):
    """Internal persistence primitive; callers enforce writer/source eligibility."""
    asset = run.asset
    result = run.advance(event, raw_event)
    result["published_at"] = codec.encode(datetime.now(UTC))
    result["evaluated_at"] = result["published_at"]
    LivePhysicsDemoResult.model_validate(result)
    cp = checkpoint(run)
    cp["raw_event"] = raw_event
    if source is not None:
        cp["source_telemetry"] = source
    row = LivePhysicsDemoEvent(
        transformer_id=asset,
        run_id=run.run_id,
        sequence=run.sequence,
        timestamp=event,
        result=result,
        checkpoint=cp,
        sha256=codec.digest(dict(result=result, checkpoint=cp)),
    )
    session.add(row)
    session.flush()
    # Bounded ledger. The complete latest checkpoint survives pruning.
    if run.sequence > 4096:
        session.execute(
            delete(LivePhysicsDemoEvent).where(
                LivePhysicsDemoEvent.transformer_id == asset,
                LivePhysicsDemoEvent.run_id == run.run_id,
                LivePhysicsDemoEvent.sequence <= run.sequence - 4096,
            )
        )
    return result


def read(session, asset, *, settings=None):
    require_transformer(session, asset)
    settings = get_settings() if settings is None else settings
    if not enabled(settings, session):
        raise HTTPException(404, "Live physics demo is disabled for this environment")
    head = latest(session, asset)
    if head is None:
        raise HTTPException(404, "No live simulation event available")
    try:
        restore(head)
        if codec.digest(dict(result=head.result, checkpoint=head.checkpoint)) != head.sha256:
            raise ValueError("Digest mismatch")
        body = copy.deepcopy(head.result)
        parsed = LivePhysicsDemoResult.model_validate(body)
        if (
            parsed.transformer_id != asset
            or parsed.timestamp != head.timestamp
            or parsed.sequence != head.sequence
            or parsed.run_id != head.run_id
        ):
            raise ValueError("Stored identity mismatch")
        now = datetime.now(UTC)
        age = (now - head.timestamp).total_seconds()
        body["evaluated_at"] = codec.encode(now)
        if settings.physics_demo_input_mode == "accepted-telemetry":
            from app.models.telemetry import Telemetry

            newest = session.scalar(
                select(Telemetry)
                .where(
                    Telemetry.transformer_id == asset,
                    Telemetry.ingestion_outcome == "ACCEPTED",
                )
                .order_by(Telemetry.timestamp.desc())
                .limit(1)
            )
            source = head.checkpoint.get("source_telemetry", {})
            if (
                newest is None
                or source.get("id") != newest.id
                or source.get("payload_hash") != newest.payload_hash
                or source.get("transformer_id") != asset
                or source.get("timestamp") != codec.encode(newest.timestamp)
            ):
                body["status"] = "UNAVAILABLE"
                body["reason"] = (
                    "Latest accepted telemetry has no eligible demo calculation; "
                    "inputs or state invalid"
                )
                for component in body["components"].values():
                    component.update(value=None, status="UNAVAILABLE")
        if age < 0 or age > 15:
            body["status"] = "UNAVAILABLE"
            body["reason"] = (
                "Future simulation event"
                if age < 0
                else "Simulation event is stale; producer may have stopped"
            )
            for component in body["components"].values():
                component.update(value=None, status="UNAVAILABLE")
        return LivePhysicsDemoResult.model_validate(body)
    except (ValueError, TypeError, KeyError):
        raise HTTPException(503, "Live simulation result is invalid; values withheld") from None
