"""Separate versioned demo schema; production PhysicsResult is unchanged."""

from typing import Literal

from pydantic import Field, model_validator

from app.schemas.common import CanonicalModel, FiniteFloat, UtcDatetime

UNITS = {
    "measured_oil_temperature": "DEG_C",
    "top_oil_temperature": "DEG_C",
    "hot_spot_temperature": "DEG_C",
    "top_oil_rise": "K",
    "winding_hot_spot_gradient": "K",
    "total_loss": "W",
    "ageing_acceleration_factor": "1",
    "equivalent_ageing_hours": "h",
    "fem_hot_spot_temperature": "DEG_C",
    "hot_spot_difference": "K",
}


class DemoComponent(CanonicalModel):
    value: FiniteFloat | None
    unit: Literal["DEG_C", "K", "W", "1", "h"]
    status: Literal["READY", "INITIALIZING", "UNAVAILABLE"]
    provenance: Literal["SYNTHETIC_SIMULATED"]
    model_id: str = Field(min_length=1)
    reference: Literal["docs/live_physics_demo_model.md"]
    target: str = Field(min_length=1)

    @model_validator(mode="after")
    def ready_value(self):
        if (self.status == "READY") != (self.value is not None):
            raise ValueError("Only READY demo components have numeric values")
        return self


class DemoInputs(CanonicalModel):
    current_a: FiniteFloat
    ambient_k: FiniteFloat
    oil_heat_w: FiniteFloat
    winding_heat_w: FiniteFloat


class LivePhysicsDemoResult(CanonicalModel):
    demo_contract_version: Literal["1.0.0"]
    mode: Literal["LIVE_SIMULATION"]
    transformer_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    sequence: int = Field(strict=True, ge=1)
    timestamp: UtcDatetime
    published_at: UtcDatetime
    evaluated_at: UtcDatetime
    status: Literal["READY", "INITIALIZING", "UNAVAILABLE"]
    reason: str | None
    case_id: Literal["LIVE_SYNTHETIC_TWO_LAYER_V1"]
    components: dict[str, DemoComponent]
    inputs: DemoInputs
    maximum_age_seconds: Literal[15.0]

    @model_validator(mode="after")
    def coherent(self):
        if set(self.components) != set(UNITS):
            raise ValueError("Exactly ten demo components required")
        for name, component in self.components.items():
            if component.unit != UNITS[name]:
                raise ValueError("Demo component unit mismatch")
            if (
                name in ("hot_spot_temperature", "fem_hot_spot_temperature", "hot_spot_difference")
                and component.target != "AREA_MEAN_WINDING_PROXY"
            ):
                raise ValueError("Incompatible demo comparison target")
        if self.status == "READY" and any(c.status != "READY" for c in self.components.values()):
            raise ValueError("READY event requires all ten components")
        if self.status == "UNAVAILABLE" and (
            not self.reason or any(c.value is not None for c in self.components.values())
        ):
            raise ValueError("Unavailable event must withhold every value")
        if self.timestamp > self.published_at or self.published_at > self.evaluated_at:
            raise ValueError("Invalid event/publication/evaluation ordering")
        return self
