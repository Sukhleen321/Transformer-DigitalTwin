"""Transactional adapter to the unchanged, controlled-only physics foundation.

SQL is authoritative; every ingestion restores a fresh estimator. Reads never
run a solver or advance state. Publication is an internal operator operation.
"""

from __future__ import annotations

import copy
import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException
from ml.physics import Lineage, ModelSelection, PhysicsEstimator, Snapshot, Versions
from ml.physics.estimator import LOSS_ID, MODEL_ID, OUTPUTS, REGISTRY_VERSION, THERMAL
from ml.physics.types import iso
from ml.physics.units import normalize
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.models.physics import PhysicsCheckpoint, PhysicsEvent, PhysicsProfile
from app.models.telemetry import Telemetry
from app.repositories import physics_repo as store
from app.repositories import transformer_repo
from app.schemas.physics import PhysicsResult
from app.schemas.telemetry import TelemetryIn
from app.services import physics_codec as codec
from app.services.query_service import query_error, require_transformer

DERIVED = tuple(name for name in OUTPUTS if name != "measured_oil_temperature")
CHECKPOINT_KEYS = {
    "codec",
    "model_id",
    "owner",
    "telemetry_id",
    "event_time",
    "snapshot_sha256",
    "result_sha256",
    "state",
}
DIAGNOSTICS = {
    "PHYSICS_DISABLED": ("Physics integration is disabled by deployment configuration."),
    "PHYSICS_RESULT_UNAVAILABLE": (
        "No retained physics result matches the selected telemetry event."
    ),
    "PHYSICS_IDENTITIES_UNRESOLVED": (
        "Published model, parameter, configuration, mapping or evidence cannot be resolved."
    ),
    "SOURCE_METADATA_MISSING": ("The selected telemetry has no acquisition identity metadata."),
    "SOURCE_IDENTITY_CONFLICT": (
        "Acquisition identity differs from the published asset source map."
    ),
    "CONFIGURATION_NOT_EFFECTIVE": (
        "The observation precedes the explicit configuration activation."
    ),
    "CHECKPOINT_UNAVAILABLE": (
        "The checkpoint is incompatible or corrupt; explicit operator recovery is required."
    ),
    "UNPROCESSED_INTERVAL": (
        "An intervening accepted observation was not processed; continuity is broken."
    ),
    "LATE_OBSERVATION": (
        "Late observations cannot advance or reconstruct the current thermal state."
    ),
    "FRESHNESS_POLICY_UNAVAILABLE": ("An explicit supported freshness policy is required."),
    "STALE_INPUT": ("The selected event exceeds its declared maximum sample age."),
    "VERSION_PENDING_OBSERVATION": (
        "A new profile is effective but no matching evaluated observation is available."
    ),
}

PRIORITY = {
    "INVALID_CONFIGURATION": 0,
    "INSUFFICIENT_DATA": 1,
    "INITIALIZING": 2,
    "MODEL_ERROR": 3,
    "READY": 4,
}


def clock():
    return datetime.now(UTC)


def implementation_record(kind):
    root = Path(__import__("ml.physics", fromlist=["__file__"]).__file__).parent
    names = ("estimator.py", "types.py", "units.py", "equations.py")
    return {
        "kind": kind,
        "model_id": MODEL_ID,
        "loss_model_id": LOSS_ID,
        "registry_version": REGISTRY_VERSION,
        "source_sha256": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names
        },
    }


def mapping_definition(q):
    return codec.encode(
        replace(
            q, value=None, effective_at=None, provenance=replace(q.provenance, original_value=None)
        )
    )


def publish_profile(session, template: Snapshot, *, source_name: str, recover=False):
    """Publish explicit evidence/configuration under the ingestion asset lock.

    Caller commits. Savepoint prevents a rejected publication leaving half its
    identities behind. Recovery requires a new configuration and activation.
    """
    require_transformer(session, template.transformer_id)
    transformer_repo.lock_for_ingestion(session, template.transformer_id)
    try:
        raw = codec.encode(template)
        codec.snapshot(raw)
        codec.time(iso(template.timestamp))
        if template.timestamp is None or not source_name or len(source_name) > 255:
            raise codec.CodecError("Explicit activation and source name required.")
        versions = raw["versions"]
        for value in versions.values():
            if value is not None:
                codec.identity(value)
        if not versions["configuration_version"] or not versions["preprocessing_version"]:
            raise codec.CodecError("Configuration and source-map identities required.")
        if set(template.observed) - set(TelemetryIn.model_fields):
            raise codec.CodecError("Unknown observed telemetry field.")
        if set(template.environment) - {"ambient_temperature"}:
            raise codec.CodecError("Unsupported environment source field.")
        for q in (*template.observed.values(), *template.environment.values()):
            if q.unit != q.provenance.original_unit or q.provenance.conversion_id != "identity":
                raise codec.CodecError("Source maps must declare original raw units.")
        if template.context == "OPERATIONAL":
            groups = (
                template.observed,
                template.environment,
                template.equipment,
                template.model_parameters,
                template.simulation,
            )
            if (
                template.lineage.origin_kind != "LIVE"
                or any(q.verification == "SYNTHETIC" for group in groups for q in group.values())
                or any(e.kind == "SYNTHETIC_CASE" for e in template.evidence.values())
                or (
                    template.policy is not None
                    and any(
                        q is not None and q.verification == "SYNTHETIC"
                        for q in (
                            template.policy.max_sample_age_seconds,
                            template.policy.max_gap_seconds,
                            template.policy.required_history_seconds,
                        )
                    )
                )
            ):
                raise codec.CodecError("Synthetic records cannot become operational configuration.")
        config = raw | {
            "model_parameters": {},
            "evidence": {ref: None for ref in raw["evidence"]},
            "observed": {},
            "environment": {},
        }
        mapping = {
            "source_name": source_name,
            "lineage": raw["lineage"],
            "observed": {k: mapping_definition(q) for k, q in template.observed.items()},
            "environment": {k: mapping_definition(q) for k, q in template.environment.items()},
        }
        asset = template.transformer_id
        with session.begin_nested():
            old = store.profile(session, asset)
            head = store.checkpoint(session, asset)
            unchanged = (
                old is not None and old.configuration_version == versions["configuration_version"]
            )
            if (
                head is not None
                and (not unchanged or recover)
                and template.timestamp <= head.event_time
            ):
                raise HTTPException(409, {"code": "ACTIVATION_NOT_AFTER_CHECKPOINT"})
            if recover and unchanged:
                raise HTTPException(409, {"code": "RECOVERY_REQUIRES_NEW_CONFIGURATION"})
            contents = {
                "MODEL": implementation_record("MODEL"),
                "REGISTRY": implementation_record("REGISTRY"),
                "PARAMETERS": raw["model_parameters"],
                "CONFIGURATION": config,
                "SOURCE_MAP": mapping,
            }
            for field, kind in codec.VERSION_KINDS.items():
                if versions[field] is not None:
                    store.publish_record(session, asset, kind, versions[field], contents[kind])
            for ref, body in raw["evidence"].items():
                store.publish_record(session, asset, "EVIDENCE", ref, body)
            if old is None:
                session.add(
                    PhysicsProfile(
                        transformer_id=asset,
                        configuration_version=versions["configuration_version"],
                        effective_at=template.timestamp,
                    )
                )
            elif not unchanged:
                old.configuration_version = versions["configuration_version"]
                old.effective_at = template.timestamp
            if recover:
                session.execute(
                    delete(PhysicsCheckpoint).where(PhysicsCheckpoint.transformer_id == asset)
                )
            session.flush()
    except codec.CodecError as exc:
        raise HTTPException(422, {"code": "PHYSICS_PUBLICATION_INVALID"}) from exc


def load_template(session, asset, version):
    config = copy.deepcopy(store.resolve(session, asset, "CONFIGURATION", version))
    if (
        not isinstance(config, dict)
        or config.get("transformer_id") != asset
        or config.get("versions", {}).get("configuration_version") != version
    ):
        raise ValueError("Configuration ownership mismatch.")
    versions = config["versions"]
    for field, kind in codec.VERSION_KINDS.items():
        body = store.resolve(session, asset, kind, versions[field])
        if (
            kind in ("MODEL", "REGISTRY")
            and body is not None
            and body != implementation_record(kind)
        ):
            raise ValueError("Incompatible implementation identity.")
        if kind == "PARAMETERS":
            config["model_parameters"] = body or {}
    mapping = store.resolve(session, asset, "SOURCE_MAP", versions["preprocessing_version"])
    if mapping["lineage"] != config["lineage"]:
        raise ValueError("Configuration/source-map identity mismatch.")
    config["observed"], config["environment"] = mapping["observed"], mapping["environment"]
    # All referenced evidence is explicit; the immutable configuration retains its IDs.
    refs = list(config["evidence"])
    if not isinstance(refs, list) or len(refs) > codec.MAX_EVIDENCE:
        raise ValueError("Unbounded evidence references.")
    config["evidence"] = {ref: store.resolve(session, asset, "EVIDENCE", ref) for ref in refs}
    template = codec.snapshot(config)
    return template, mapping


def source_issue(row, template, mapping):
    a = row.acquisition
    if not a:
        return "SOURCE_METADATA_MISSING"
    expected = template.lineage
    checks = {
        "source_kind": expected.source_kind,
        "origin_kind": expected.origin_kind,
        "origin_transformer_id": expected.origin_transformer_id,
        "replay_run_id": expected.replay_run_id,
        "source_name": mapping["source_name"],
        "map_version": template.versions.preprocessing_version,
    }
    if any(a.get(k) != v for k, v in checks.items()):
        return "SOURCE_IDENTITY_CONFLICT"
    if (
        template.selection.measurement_side is not None
        and a.get("measurement_side") != template.selection.measurement_side
    ):
        return "SOURCE_IDENTITY_CONFLICT"
    return None


def adapt(row, template, now):
    a = row.acquisition or {}
    groups = {}
    for group in ("observed", "environment"):
        quantities = {}
        for key, q in getattr(template, group).items():
            unit = a.get("field_units", {}).get(key, "UNKNOWN")
            verification = a.get("field_verification", {}).get(key, "UNVERIFIED")
            if unit != q.unit or verification != q.verification:
                verification = "UNVERIFIED"
            value = getattr(row, key)
            quantities[key] = replace(
                q,
                value=value,
                unit=unit,
                verification=verification,
                effective_at=row.timestamp,
                provenance=replace(
                    q.provenance, original_unit=unit, original_value=value, conversion_id="identity"
                ),
            )
        groups[group] = quantities
    lineage = replace(
        template.lineage,
        source_kind=a.get("source_kind", "UNKNOWN"),
        origin_kind=a.get("origin_kind", "UNKNOWN"),
        origin_transformer_id=a.get("origin_transformer_id"),
        replay_run_id=a.get("replay_run_id"),
        acquisition_reference=f"telemetry:{row.id}:{row.payload_hash or 'unresolved'}",
        timezone_status=a.get("timezone_status", "UNKNOWN"),
    )
    if any(q.verification == "UNVERIFIED" for group in groups.values() for q in group.values()):
        lineage = replace(
            lineage,
            input_verification="MIXED"
            if template.context == "CONTROLLED_SIMULATION"
            else "UNVERIFIED",
        )
    simulation = {
        k: replace(q, effective_at=row.timestamp)
        if k in ("oil_heat_input", "winding_heat_input")
        else q
        for k, q in template.simulation.items()
    }
    return replace(
        template,
        timestamp=row.timestamp,
        evaluated_at=now,
        evaluation_time=row.timestamp if template.context == "CONTROLLED_SIMULATION" else now,
        lineage=lineage,
        simulation=simulation,
        **groups,
    )


def unavailable_snapshot(asset, row, now):
    a = row.acquisition if row is not None and row.acquisition else {}
    return Snapshot(
        asset,
        None if row is None else row.timestamp,
        now,
        now,
        "CONTROLLED_SIMULATION" if a.get("origin_kind") == "SIMULATED" else "OPERATIONAL",
        Lineage(
            source_kind=a.get("source_kind", "UNKNOWN"),
            origin_kind=a.get("origin_kind", "UNKNOWN"),
            acquisition_reference=None if row is None else f"telemetry:{row.id}",
            origin_transformer_id=a.get("origin_transformer_id"),
            replay_run_id=a.get("replay_run_id"),
            timezone_status=a.get("timezone_status", "UNKNOWN"),
        ),
        Versions(),
        ModelSelection(),
        None,
    )


def withhold(result, code, *, status="INVALID_CONFIGURATION", names=tuple(OUTPUTS)):
    for name in names:
        c = result["components"][name]
        c["value"] = None
        if PRIORITY[status] < PRIORITY[c["status"]]:
            c["status"] = status
        c["reasons"].append(
            {
                "code": code,
                "message": DIAGNOSTICS[code],
                "paths": ["persistence." + code.lower()],
            }
        )
        c["missing_inputs"] = list(
            dict.fromkeys(c["missing_inputs"] + ["persistence." + code.lower()])
        )
        c["coverage"]["missing_fields"] = list(
            dict.fromkeys(c["coverage"]["missing_fields"] + ["persistence." + code.lower()])
        )
    return result


def check_event(event, asset):
    if (
        event.transformer_id != asset
        or event.snapshot_sha256 != codec.digest(event.snapshot)
        or event.result_sha256 != codec.digest(event.result)
    ):
        raise ValueError("Corrupt physics event.")
    result = PhysicsResult.model_validate(event.result)
    snap = codec.snapshot(event.snapshot)
    if (
        result.transformer_id != asset
        or snap.transformer_id != asset
        or result.timestamp != event.event_time
        or snap.timestamp != event.event_time
    ):
        raise ValueError("Physics event identity mismatch.")
    return snap


def restore(session, head, asset):
    body = head.body
    if (
        head.sha256 != codec.digest(body)
        or set(body) != CHECKPOINT_KEYS
        or body["codec"] != codec.CODEC
        or body["model_id"] != MODEL_ID
        or body["owner"] != asset
        or body["telemetry_id"] != head.telemetry_id
        or codec.time(body["event_time"]) != head.event_time
    ):
        raise ValueError("Incompatible physics checkpoint.")
    event = session.get(PhysicsEvent, head.telemetry_id)
    if event is None or event.event_time != head.event_time:
        raise ValueError("Checkpoint event unavailable.")
    snap = check_event(event, asset)
    if (
        body["snapshot_sha256"] != event.snapshot_sha256
        or body["result_sha256"] != event.result_sha256
    ):
        raise ValueError("Checkpoint pair mismatch.")
    load_template(session, asset, snap.versions.configuration_version)
    state = codec.thermal_state(body["state"])
    if state is not None:
        if (
            state.timestamp != head.event_time
            or snap.context != "CONTROLLED_SIMULATION"
            or snap.selection.thermal_model_id != MODEL_ID
            or snap.versions.model_version != "1.0.0"
            or snap.versions.equation_registry_version != REGISTRY_VERSION
        ):
            raise ValueError("Checkpoint model mismatch.")
        lo = normalize(
            snap.model_parameters["minimum_temperature"], "K", "absolute_temperature"
        ).value
        hi = normalize(
            snap.model_parameters["maximum_temperature"], "K", "absolute_temperature"
        ).value
        if not lo <= state.oil_k <= hi or not lo <= state.winding_k <= hi:
            raise ValueError("Checkpoint outside declared model range.")
        for ref in state.evidence_references:
            store.resolve(session, asset, "EVIDENCE", ref)
        for key, value in (
            ("top_oil_temperature", state.oil_k),
            ("hot_spot_temperature", state.winding_k),
        ):
            c = event.result["components"][key]
            if c["status"] == "READY" and abs((c["value"] + 273.15) - value) > 1e-9:
                raise ValueError("Checkpoint output mismatch.")
    return state


def prepare(session, row, *, duplicate=False):
    """Called only inside the existing locked ingestion transaction."""
    if (
        not get_settings().physics_enabled
        or duplicate
        or session.get(PhysicsEvent, row.id) is not None
    ):
        return
    profile = store.profile(session, row.transformer_id)
    if profile is None:
        return
    now, asset = clock(), row.transformer_id
    estimator = PhysicsEstimator()
    error = None
    try:
        template, mapping = load_template(session, asset, profile.configuration_version)
        snap = adapt(row, template, now)
        error = source_issue(row, template, mapping)
        if row.timestamp < profile.effective_at:
            error = "CONFIGURATION_NOT_EFFECTIVE"
    except (ValueError, TypeError, KeyError, AttributeError):
        snap = unavailable_snapshot(asset, row, now)
        error = "PHYSICS_IDENTITIES_UNRESOLVED"
    head = store.checkpoint(session, asset)
    late = row.ingestion_outcome == "REJECTED_LATE_OBSERVATION" or (
        head is not None and row.timestamp <= head.event_time
    )
    if head is not None and not late and error is None:
        try:
            state = restore(session, head, asset)
            skipped = session.scalar(
                select(Telemetry.id)
                .outerjoin(PhysicsEvent, PhysicsEvent.telemetry_id == Telemetry.id)
                .where(
                    Telemetry.transformer_id == asset,
                    Telemetry.timestamp > head.event_time,
                    Telemetry.timestamp < row.timestamp,
                    PhysicsEvent.telemetry_id.is_(None),
                    Telemetry.ingestion_outcome == "ACCEPTED",
                )
                .limit(1)
            )
            if skipped is not None:
                error = "UNPROCESSED_INTERVAL"
            elif state is not None:
                estimator._states[asset] = state  # codec guarded; no global mutable estimator
        except (ValueError, TypeError, KeyError, AttributeError):
            error = "CHECKPOINT_UNAVAILABLE"
    result = estimator.evaluate(snap)
    if late:
        withhold(result, "LATE_OBSERVATION", status="INSUFFICIENT_DATA", names=THERMAL)
    if error:
        withhold(result, error)
    PhysicsResult.model_validate(result)
    encoded = codec.encode(snap)
    event = PhysicsEvent(
        telemetry_id=row.id,
        transformer_id=asset,
        event_time=row.timestamp,
        received_at=row.ingested_at,
        snapshot=encoded,
        snapshot_sha256=codec.digest(encoded),
        result=result,
        result_sha256=codec.digest(result),
        outcome=error or ("LATE_OBSERVATION" if late else "FORWARD"),
    )
    store.save_event(session, event)
    quarantine = error == "CHECKPOINT_UNAVAILABLE"
    if not late and not quarantine:
        body = dict(
            codec=codec.CODEC,
            model_id=MODEL_ID,
            owner=asset,
            telemetry_id=row.id,
            event_time=iso(row.timestamp),
            snapshot_sha256=event.snapshot_sha256,
            result_sha256=event.result_sha256,
            state=codec.encode(None if error else estimator.state(asset)),
        )
        store.save_checkpoint(session, event, body)
    keep = head.telemetry_id if head is not None and (late or quarantine) else row.id
    store.prune(session, asset, keep, now)


def read(session, asset, at=None):
    require_transformer(session, asset)
    now = clock()
    cutoff = at or now
    if cutoff > now:
        query_error("at", "Event cutoff must not be in the future")
    row = store.selected_telemetry(session, asset, cutoff)
    if not get_settings().physics_enabled:
        result = PhysicsEstimator().evaluate(unavailable_snapshot(asset, row, now))
        return PhysicsResult.model_validate(withhold(result, "PHYSICS_DISABLED"))
    event = session.get(PhysicsEvent, row.id) if row is not None else None
    if event is None:
        result = PhysicsEstimator().evaluate(unavailable_snapshot(asset, row, now))
        return PhysicsResult.model_validate(withhold(result, "PHYSICS_RESULT_UNAVAILABLE"))
    if event.outcome == "SOURCE_IDENTITY_CONFLICT":
        raise HTTPException(409, {"code": "SOURCE_IDENTITY_CONFLICT"})
    snap = check_event(
        event, asset
    )  # corrupt ledger is an internal failure, never an old substitute
    result = copy.deepcopy(event.result)
    result["evaluated_at"] = iso(now)
    head = store.checkpoint(session, asset)
    if head is not None and head.telemetry_id == event.telemetry_id:
        try:
            restore(session, head, asset)
        except (ValueError, TypeError, KeyError, AttributeError):
            withhold(result, "CHECKPOINT_UNAVAILABLE", names=THERMAL)
    try:
        template, mapping = load_template(session, asset, snap.versions.configuration_version)
        if source_issue(row, template, mapping) == "SOURCE_IDENTITY_CONFLICT":
            raise HTTPException(409, {"code": "SOURCE_IDENTITY_CONFLICT"})
        if snap.policy is None or snap.policy.max_sample_age_seconds is None:
            withhold(result, "FRESHNESS_POLICY_UNAVAILABLE")
        else:
            age = normalize(snap.policy.max_sample_age_seconds, "s", "duration").value
            reference = cutoff if snap.context == "CONTROLLED_SIMULATION" else now
            if (reference - row.timestamp).total_seconds() > age:
                withhold(
                    result,
                    "STALE_INPUT",
                    status="INSUFFICIENT_DATA",
                    names=("measured_oil_temperature", *THERMAL, "total_loss"),
                )
        profile = store.profile(session, asset)
        if (
            profile is not None
            and profile.effective_at <= cutoff
            and profile.configuration_version != snap.versions.configuration_version
        ):
            withhold(result, "VERSION_PENDING_OBSERVATION", names=DERIVED)
    except (ValueError, TypeError, KeyError, AttributeError):
        withhold(result, "PHYSICS_IDENTITIES_UNRESOLVED")
    return PhysicsResult.model_validate(result)
