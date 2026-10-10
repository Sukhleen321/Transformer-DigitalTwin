"""Opt-in adapter of accepted fictional LV telemetry to the existing demo engine.

No operational profile is published. LV per-unit loading drives the 10 A
synthetic reference; it is not a measurement-side conversion for real equipment.
"""

import logging
import math
from datetime import UTC, datetime
from uuid import uuid4

from app.core.config import get_settings
from app.models.transformer import Transformer
from app.services import live_physics_demo as demo
from ml.demo_physics.fleet import load_fleet
from ml.demo_physics.scenario import DemoRun

logger = logging.getLogger(__name__)


def inputs(row, asset, fleet, now):
    """Strict units, provenance, synthetic registry and source-identity boundary."""
    cfg = fleet["configuration"]
    if row.transformer_id not in {a["transformer_id"] for a in fleet["assets"]}:
        raise ValueError("Asset is not in the explicitly configured fictional fleet")
    if asset is None or row.transformer_id != asset.id:
        raise ValueError("Telemetry/registry identity mismatch")
    meta = asset.configuration_metadata or {}
    if (
        asset.schema_version != "1.1.0"
        or meta.get("status") != "SYNTHETIC_CONFIG"
        or meta.get("version") != cfg["configuration_version"]
        or asset.measurement_side != "LV"
        or any(
            getattr(asset, k) != cfg[k]
            for k in ("rated_current_a", "rated_voltage_lv", "rated_power_kva")
        )
    ):
        raise ValueError("Registry does not match the explicit fictional LV fleet")
    acq = row.acquisition or {}
    if (
        row.schema_version != "1.1.0"
        or row.ingestion_outcome != "ACCEPTED"
        or acq.get("source_kind") != "SIMULATED"
        or acq.get("origin_kind") != "SIMULATED"
        or acq.get("measurement_side") != "LV"
        or acq.get("map_version") != fleet["map_version"]
        or acq.get("timezone_status") != "DECLARED_UTC"
        or acq.get("snapshot_id") != row.payload_hash
        or not row.payload_hash
    ):
        raise ValueError("Only accepted, identified synthetic LV snapshots are eligible")
    age = (now - row.timestamp).total_seconds()
    if not 0 <= age <= 15:
        raise ValueError("Source event is stale or future-dated")
    names = {
        **dict.fromkeys(("current_l1", "current_l2", "current_l3"), "A"),
        "ambient_temperature": "DEG_C",
        "oil_temperature": "DEG_C",
    }
    for name, unit in names.items():
        value = getattr(row, name)
        if (
            acq.get("field_units", {}).get(name) != unit
            or acq.get("field_verification", {}).get(name) != "SYNTHETIC"
            or type(value) not in (float, int)
            or not math.isfinite(value)
        ):
            raise ValueError("Missing, invalid or unsupported synthetic input: " + name)
    currents = [getattr(row, "current_l" + str(i)) for i in (1, 2, 3)]
    if any(value < 0 for value in currents):
        raise ValueError("Negative synthetic RMS current")
    load = sum(currents) / (3 * cfg["rated_current_a"])
    ambient, sensor = row.ambient_temperature + 273.15, row.oil_temperature + 273.15
    if not 0 <= load <= 1.5 or not 250 <= ambient <= 350 or not 250 <= sensor <= 400:
        raise ValueError("Synthetic operating point outside declared demo envelope")
    return {"current_a": 10 * load, "ambient_k": ambient, "oil_sensor_k": sensor}


def prepare(session, row, *, duplicate=False):
    """Called inside ingestion's asset lock; SQL checkpoint is authoritative."""
    settings = get_settings()
    if (
        settings.physics_demo_input_mode != "accepted-telemetry"
        or duplicate
        or row.ingestion_outcome != "ACCEPTED"
        or not demo.enabled(settings, session)
    ):
        return
    # Keep a failed asset's demo calculation out of the accepted telemetry/ML
    # transaction. No speculative state is retained outside this savepoint.
    try:
        with session.begin_nested():
            fleet = load_fleet(settings.operational_fleet_file)
            asset = session.get(Transformer, row.transformer_id)
            operating = inputs(row, asset, fleet, datetime.now(UTC))
            head = demo.latest(session, row.transformer_id)
            if head and head.checkpoint.get("source_telemetry", {}).get("id") == row.id:
                return
            run = demo.restore(head) if head else None
            if run and not run.variable_ambient:
                raise ValueError("Standalone state cannot be reused for MQTT telemetry")
            gap = (row.timestamp - head.timestamp).total_seconds() if head else None
            if gap is not None and gap <= 0:
                raise ValueError("Source event does not advance the demo watermark")
            if run is None or gap > 30:
                run = DemoRun(
                    row.transformer_id,
                    row.timestamp,
                    uuid4().hex,
                    demo.reference_fem(),
                    variable_ambient=True,
                )
            raw = run.generate(row.timestamp, operating)
            result = demo.persist(
                session,
                run,
                row.timestamp,
                raw,
                source=dict(
                    id=row.id,
                    payload_hash=row.payload_hash,
                    transformer_id=row.transformer_id,
                    timestamp=demo.codec.encode(row.timestamp),
                ),
            )
            if gap is not None and gap > 30:
                # The newly initialized result already withholds unsupported
                # history; the checkpoint records the explicit discontinuity.
                result["reason"] = "New synthetic run after source gap >30 s; history reset"
                saved = demo.latest(session, row.transformer_id)
                saved.result = result
                saved.sha256 = demo.codec.digest(dict(result=result, checkpoint=saved.checkpoint))
    except Exception as exc:
        # Read checks the newest accepted source watermark and withholds old
        # values when this event could not be calculated. Never invent inputs.
        logger.warning(
            "Synthetic physics unavailable asset=%s error_type=%s",
            row.transformer_id,
            type(exc).__name__,
        )
