"""Versioned, bounded JSON codec around the unchanged physics dataclasses."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime

from ml.physics import (
    Evidence,
    Lineage,
    ModelSelection,
    Policy,
    Provenance,
    Quantity,
    Snapshot,
    Versions,
)
from ml.physics.types import ThermalState, iso
from pydantic import TypeAdapter

from app.schemas.common import UtcDatetime

MAX_BYTES = 65536
MAX_EVIDENCE = 64
CODEC = "physics-state-v1"
KINDS = {"MODEL", "REGISTRY", "PARAMETERS", "CONFIGURATION", "SOURCE_MAP", "EVIDENCE"}
VERSION_KINDS = dict(
    model_version="MODEL",
    parameter_version="PARAMETERS",
    configuration_version="CONFIGURATION",
    preprocessing_version="SOURCE_MAP",
    equation_registry_version="REGISTRY",
)
TIME = TypeAdapter(UtcDatetime)


class CodecError(ValueError):
    pass


def identity(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", value):
        raise CodecError("A bounded canonical identity is required.")
    return value


def encode(value):
    if isinstance(value, datetime):
        return iso(value)
    if is_dataclass(value):
        return {field.name: encode(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise CodecError("JSON record keys must be strings.")
        return {key: encode(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [encode(item) for item in value]
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise CodecError("Unsupported JSON record value.")


def canonical(value):
    try:
        result = json.dumps(
            encode(value), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise CodecError("Record cannot be encoded as finite JSON.") from exc
    if len(result) > MAX_BYTES:
        raise CodecError("Physics record exceeds the encoded size cap.")
    return result


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _members(value, cls):
    if not isinstance(value, dict) or set(value) != {f.name for f in fields(cls)}:
        raise CodecError("Record does not match its versioned dataclass.")
    return dict(value)


def time(value):
    return None if value is None else TIME.validate_python(value)


def quantity(value):
    data = _members(value, Quantity)
    data["provenance"] = Provenance(**_members(data["provenance"], Provenance))
    data["effective_at"] = time(data["effective_at"])
    bounds = data["valid_range"]
    if bounds is not None and (not isinstance(bounds, list) or len(bounds) != 2):
        raise CodecError("Invalid quantity range shape.")
    data["valid_range"] = None if bounds is None else tuple(bounds)
    return Quantity(**data)


def snapshot(value):
    canonical(value)
    data = _members(value, Snapshot)
    for key in ("timestamp", "evaluated_at", "evaluation_time"):
        data[key] = time(data[key])
    if data["evaluated_at"] is None or data["evaluation_time"] is None:
        raise CodecError("Explicit evaluation times are required.")
    if data["context"] not in ("OPERATIONAL", "CONTROLLED_SIMULATION"):
        raise CodecError("Unsupported physics context.")
    lineage = _members(data["lineage"], Lineage)
    labels = {
        "source_kind": ("LIVE", "SIMULATED", "REPLAYED", "UNKNOWN"),
        "origin_kind": ("LIVE", "SIMULATED", "UNKNOWN"),
        "input_verification": ("VERIFIED", "UNVERIFIED", "SYNTHETIC", "MIXED", "UNKNOWN"),
    }
    if any(lineage[key] not in allowed for key, allowed in labels.items()):
        raise CodecError("Unsupported source lineage label.")
    data["lineage"] = Lineage(**lineage)
    data["versions"] = Versions(**_members(data["versions"], Versions))
    data["selection"] = ModelSelection(**_members(data["selection"], ModelSelection))
    if data["policy"] is not None:
        policy = _members(data["policy"], Policy)
        for key in ("max_sample_age_seconds", "max_gap_seconds", "required_history_seconds"):
            policy[key] = None if policy[key] is None else quantity(policy[key])
        data["policy"] = Policy(**policy)
    evidence = data["evidence"]
    if not isinstance(evidence, dict) or len(evidence) > MAX_EVIDENCE:
        raise CodecError("Bounded evidence map required.")
    data["evidence"] = {identity(k): Evidence(**_members(v, Evidence)) for k, v in evidence.items()}
    for key in ("observed", "equipment", "model_parameters", "environment", "simulation"):
        if not isinstance(data[key], dict) or len(data[key]) > 32:
            raise CodecError("Bounded quantity maps required.")
        data[key] = {k: quantity(v) for k, v in data[key].items()}
    return Snapshot(**data)


def thermal_state(value):
    if value is None:
        return None
    data = _members(value, ThermalState)
    for key in ("timestamp", "started_at"):
        data[key] = time(data[key])
    if (
        data["timestamp"] is None
        or data["started_at"] is None
        or data["started_at"] > data["timestamp"]
    ):
        raise CodecError("Incompatible checkpoint timestamps.")
    for key in ("oil_k", "winding_k", "ambient_k", "oil_heat_w", "winding_heat_w"):
        number = data[key]
        try:
            valid = type(number) in (float, int) and math.isfinite(number) and number >= 0
        except OverflowError:
            valid = False
        if not valid:
            raise CodecError("Incompatible checkpoint scalar.")
    if any(
        not isinstance(data[k], str) or not re.fullmatch("[0-9a-f]{64}", data[k])
        for k in ("identity", "request_identity")
    ):
        raise CodecError("Invalid checkpoint identities.")
    if type(data["gap_count"]) is not int or data["gap_count"] < 0:
        raise CodecError("Invalid checkpoint gap count.")
    refs = data["evidence_references"]
    if (
        not isinstance(refs, list)
        or len(refs) > MAX_EVIDENCE
        or any(not isinstance(ref, str) for ref in refs)
        or len(set(refs)) != len(refs)
    ):
        raise CodecError("Invalid checkpoint references.")
    data["evidence_references"] = tuple(identity(ref) for ref in refs)
    return ThermalState(**data)
