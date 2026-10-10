"""Transport-independent input records for physics contract 1.0.0.

No constructor supplies a physical parameter value. Bad/missing values are
classified by the estimator, without changing legacy ingestion validation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any


class InputIssue(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def utc(value: datetime | None) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise InputIssue("TIMESTAMP_UNSUPPORTED", "An aware event timestamp is required.")
    return value.astimezone(timezone.utc)


def iso(value: datetime | None) -> str | None:
    return None if value is None else utc(value).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Evidence:
    title: str
    locator: str
    applicability: str
    kind: str  # EQUIPMENT_RECORD, SENSOR_RECORD, SYNTHETIC_CASE, TECHNICAL_REFERENCE
    content_digest: str | None = None


@dataclass(frozen=True)
class Provenance:
    evidence_reference: str | None
    source_id: str | None
    applicability: str | None
    original_unit: str | None
    original_value: Any
    conversion_id: str = "identity"
    semantics: str | None = None


@dataclass(frozen=True)
class Quantity:
    value: Any
    unit: str
    quantity_kind: str
    verification: str
    provenance: Provenance
    effective_at: datetime | None
    valid_range: tuple[float | None, float | None] | None = None
    uncertainty: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class Versions:
    model_version: str | None = None
    parameter_version: str | None = None
    configuration_version: str | None = None
    preprocessing_version: str | None = None
    equation_registry_version: str | None = None


@dataclass(frozen=True)
class Lineage:
    source_kind: str = "UNKNOWN"
    origin_kind: str = "UNKNOWN"
    input_verification: str = "UNKNOWN"
    acquisition_reference: str | None = None
    origin_transformer_id: str | None = None
    replay_run_id: str | None = None
    evidence_references: tuple[str, ...] = ()
    timezone_status: str = "UNKNOWN"
    case_id: str | None = None


@dataclass(frozen=True)
class Policy:
    max_sample_age_seconds: Quantity | None
    max_gap_seconds: Quantity | None
    required_history_seconds: Quantity | None
    initialization_policy: str | None
    initialization_reference: str | None
    range_policy_reference: str | None
    forcing_policy: str | None  # PREVIOUS_SAMPLE_HOLD, declared rather than inferred
    forcing_reference: str | None


@dataclass(frozen=True)
class ModelSelection:
    thermal_model_id: str | None = None
    loss_enabled: bool = False
    measurement_side: str | None = None
    current_basis: str | None = None
    loss_basis_reference: str | None = None
    energized: bool | None = None


@dataclass(frozen=True)
class Snapshot:
    transformer_id: str
    timestamp: datetime | None
    evaluated_at: datetime
    evaluation_time: datetime
    context: str
    lineage: Lineage
    versions: Versions
    selection: ModelSelection
    policy: Policy | None
    evidence: Mapping[str, Evidence] = field(default_factory=dict)
    observed: Mapping[str, Quantity] = field(default_factory=dict)
    equipment: Mapping[str, Quantity] = field(default_factory=dict)
    model_parameters: Mapping[str, Quantity] = field(default_factory=dict)
    environment: Mapping[str, Quantity] = field(default_factory=dict)
    simulation: Mapping[str, Quantity] = field(default_factory=dict)

    def __post_init__(self):
        # Snapshot maps cannot be edited after evaluation or from another caller.
        for name in (
            "evidence",
            "observed",
            "equipment",
            "model_parameters",
            "environment",
            "simulation",
        ):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))


@dataclass(frozen=True)
class ThermalState:
    timestamp: datetime
    started_at: datetime
    oil_k: float
    winding_k: float
    ambient_k: float
    oil_heat_w: float
    winding_heat_w: float
    identity: str
    request_identity: str
    evidence_references: tuple[str, ...]
    gap_count: int
