"""Runtime response mirror of the unchanged physics-result-v1 schema."""

from typing import Annotated, Literal

from ml.physics.estimator import OUTPUTS
from pydantic import Field, model_validator

from app.schemas.common import CanonicalModel, FiniteFloat, UtcDatetime

Identifier = Annotated[str, Field(min_length=1)]


class Diagnostic(CanonicalModel):
    code: Identifier
    message: Identifier
    paths: list[Identifier]


class Assumption(CanonicalModel):
    message: Identifier
    reference: Identifier


class Coverage(CanonicalModel):
    start: UtcDatetime | None
    end: UtcDatetime | None
    covered_seconds: Annotated[FiniteFloat, Field(ge=0)] | None
    expected_seconds: Annotated[FiniteFloat, Field(ge=0)] | None
    fraction: Annotated[FiniteFloat, Field(ge=0, le=1)] | None
    gap_count: Annotated[int, Field(strict=True, ge=0)]
    missing_fields: list[Identifier]


class Provenance(CanonicalModel):
    model_id: Identifier | None
    equation_ids: list[Identifier]
    input_paths: list[Identifier]
    evidence_references: list[Identifier]
    case_id: Identifier | None
    comparison_id: Identifier | None
    numerical_verification_reference: Identifier | None
    mesh_convergence_reference: Identifier | None


class Component(CanonicalModel):
    value: FiniteFloat | None
    unit: Literal["DEG_C", "K", "W", "1", "h"]
    result_kind: Literal["MEASURED_TELEMETRY", "CALCULATED_ESTIMATE", "SIMULATED_REFERENCE"]
    status: Literal[
        "READY", "INITIALIZING", "INSUFFICIENT_DATA", "INVALID_CONFIGURATION", "MODEL_ERROR"
    ]
    reasons: list[Diagnostic]
    missing_inputs: list[Identifier]
    warnings: list[Diagnostic]
    assumptions: list[Assumption]
    coverage: Coverage
    provenance: Provenance

    @model_validator(mode="after")
    def availability(self):
        if (self.value is not None) != (self.status == "READY"):
            raise ValueError("Only READY has a finite value.")
        if self.status == "READY" and (self.reasons or not self.provenance.evidence_references):
            raise ValueError("READY requires evidence and no eligibility reasons.")
        if self.status != "READY" and not self.reasons:
            raise ValueError("Unavailable outputs require reasons.")
        return self


class Components(CanonicalModel):
    measured_oil_temperature: Component
    top_oil_temperature: Component
    hot_spot_temperature: Component
    top_oil_rise: Component
    winding_hot_spot_gradient: Component
    total_loss: Component
    ageing_acceleration_factor: Component
    equivalent_ageing_hours: Component
    fem_hot_spot_temperature: Component
    hot_spot_difference: Component

    @model_validator(mode="after")
    def units_and_labels(self):
        for name, (unit, kind) in OUTPUTS.items():
            c = getattr(self, name)
            if c.unit != unit or c.result_kind != kind:
                raise ValueError("Frozen component units/labels required.")
            if c.value is not None and (
                (unit == "DEG_C" and c.value < -273.15)
                or (
                    name in ("total_loss", "ageing_acceleration_factor", "equivalent_ageing_hours")
                    and c.value < 0
                )
            ):
                raise ValueError("Output exceeds frozen numeric bounds.")
        return self


class Lineage(CanonicalModel):
    source_kind: Literal["LIVE", "REPLAYED", "SIMULATED", "UNKNOWN"]
    origin_kind: Literal["LIVE", "SIMULATED", "UNKNOWN"]
    input_verification: Literal["VERIFIED", "UNVERIFIED", "SYNTHETIC", "MIXED", "UNKNOWN"]
    acquisition_reference: Identifier | None
    origin_transformer_id: Identifier | None
    replay_run_id: Identifier | None
    evidence_references: list[Identifier]


class Versions(CanonicalModel):
    model_version: Identifier | None
    parameter_version: Identifier | None
    configuration_version: Identifier | None
    preprocessing_version: Identifier | None
    equation_registry_version: Identifier | None


class PhysicsResult(CanonicalModel):
    physics_contract_version: Literal["1.0.0"]
    transformer_id: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^\S(?:.*\S)?$")]
    timestamp: UtcDatetime | None
    evaluated_at: UtcDatetime
    context: Literal["OPERATIONAL", "CONTROLLED_SIMULATION"]
    lineage: Lineage
    versions: Versions
    components: Components

    @model_validator(mode="after")
    def current_eligibility(self):
        for name in OUTPUTS:
            c = getattr(self.components, name)
            if c.status != "READY":
                continue
            if name == "measured_oil_temperature":
                if self.context != "OPERATIONAL" or not self.versions.preprocessing_version:
                    raise ValueError("Measured READY requires operational mapping.")
            elif not all(self.versions.model_dump().values()) or not c.provenance.model_id:
                raise ValueError("Derived READY requires resolved version and model IDs.")
            if self.context == "OPERATIONAL" and (
                self.lineage.origin_kind != "LIVE" or self.lineage.input_verification != "VERIFIED"
            ):
                raise ValueError("Operational READY requires live verified provenance.")
            if name in (
                "ageing_acceleration_factor",
                "equivalent_ageing_hours",
                "fem_hot_spot_temperature",
                "hot_spot_difference",
            ):
                raise ValueError("Current evidence does not support this output.")
            if (
                name
                in (
                    "top_oil_temperature",
                    "hot_spot_temperature",
                    "top_oil_rise",
                    "winding_hot_spot_gradient",
                )
                and self.context != "CONTROLLED_SIMULATION"
            ):
                raise ValueError("Two-node proxy is controlled-only.")
        return self
