"""Documented synthetic case using the unchanged, eligibility-checked estimator."""

import math
import re

import numpy as np

from ml.physics import (
    Evidence,
    Lineage,
    ModelSelection,
    PhysicsEstimator,
    Policy,
    Provenance,
    Quantity,
    Snapshot,
    Versions,
)
from ml.physics.estimator import MODEL_ID, OUTPUTS, REGISTRY_VERSION
from ml.physics.types import iso, utc

from .fem import SheetFEM

CASE = "LIVE_SYNTHETIC_TWO_LAYER_V1"
REFERENCE = "docs/live_physics_demo_model.md"
MODELS = {
    "measured_oil_temperature": "DEMO_SENSOR_LAG_V1",
    "top_oil_temperature": MODEL_ID,
    "hot_spot_temperature": MODEL_ID,
    "top_oil_rise": MODEL_ID,
    "winding_hot_spot_gradient": MODEL_ID,
    "total_loss": "PROJECT_CURRENT_SQUARED_LOSS_V1",
    "ageing_acceleration_factor": "DEMO_EXP_TEMPERATURE_INDEX_V1",
    "equivalent_ageing_hours": "DEMO_TRAPEZOID_HOURS_V1",
    "fem_hot_spot_temperature": "DEMO_TWO_SHEET_FEM_MEAN_V1",
    "hot_spot_difference": "DEMO_SHARED_WINDING_MEAN_V1",
}


def acceleration(winding_k):
    if (
        type(winding_k) not in (int, float)
        or not math.isfinite(winding_k)
        or not 250 <= winding_k <= 400
    ):
        raise ValueError("Unsupported illustrative ageing temperature")
    return math.exp((winding_k - 310) / 20)


def operating_current(seconds):
    return 10 * (0.55 + 0.25 * math.sin(seconds / 20))


def validate_raw(raw, asset, run_id, sequence, event, *, variable_ambient=False):
    """Strict demo-only input boundary, separate from frozen operational telemetry."""
    keys = {
        "raw_contract_version",
        "event_id",
        "transformer_id",
        "run_id",
        "sequence",
        "timestamp",
        "source",
        "provenance",
        "reference",
        "values",
    }
    if not isinstance(raw, dict) or set(raw) != keys:
        raise ValueError("Missing or extra raw simulation event fields")
    identity = f"{CASE}/{run_id}/{asset}/{sequence}"
    if (
        raw["raw_contract_version"] != "1.0.0"
        or raw["event_id"] != identity
        or raw["transformer_id"] != asset
        or raw["run_id"] != run_id
        or re.fullmatch(r"[0-9a-f]{32}", run_id) is None
        or type(raw["sequence"]) is not int
        or raw["sequence"] != sequence
        or raw["timestamp"] != iso(utc(event))
        or raw["source"] != CASE
        or raw["provenance"] != "SYNTHETIC_SIMULATED"
        or raw["reference"] != REFERENCE
    ):
        raise ValueError("Raw simulation event identity/provenance mismatch")
    specifications = {
        "current_a": ("A", 0, 20),
        "load_fraction": ("1", 0, 2),
        "ambient_k": ("K", 250, 400) if variable_ambient else ("K", 300, 300),
        "oil_sensor_k": ("K", 250, 400),
        "oil_heat_w": ("W", 6, 6),
        "winding_heat_w": ("W", 0, 100),
    }
    values = raw["values"]
    if not isinstance(values, dict) or set(values) != set(specifications):
        raise ValueError("Missing or extra raw simulation inputs")
    for name, (unit, low, high) in specifications.items():
        quantity = values[name]
        if (
            not isinstance(quantity, dict)
            or set(quantity) != {"value", "unit"}
            or quantity["unit"] != unit
            or type(quantity["value"]) not in (int, float)
            or not math.isfinite(quantity["value"])
            or not low <= quantity["value"] <= high
        ):
            raise ValueError("Invalid raw simulation input: " + name)
    numbers = {name: quantity["value"] for name, quantity in values.items()}
    if (
        abs(numbers["load_fraction"] - numbers["current_a"] / 10) > 1e-12
        or abs(numbers["winding_heat_w"] - 30 * numbers["load_fraction"] ** 2) > 1e-10
    ):
        raise ValueError("Inconsistent synthetic rating/loss inputs")
    return numbers


def snapshot(asset, epoch, event, raw=None, source_event_id=None):
    epoch, event = utc(epoch), utc(event)
    seconds = (event - epoch).total_seconds()
    current = operating_current(seconds) if raw is None else raw["current_a"]

    def q(value, unit, kind, bounds, at=epoch, semantics=None):
        return Quantity(
            value,
            unit,
            kind,
            "SYNTHETIC",
            Provenance(
                CASE,
                CASE,
                "fictional local demo only",
                unit,
                value,
                semantics=semantics,
            ),
            at,
            bounds,
        )

    params = {
        "oil_thermal_resistance": q(0.35, "K/W", "thermal_resistance", (0.01, 10)),
        "winding_thermal_resistance": q(0.2, "K/W", "thermal_resistance", (0.01, 10)),
        "oil_thermal_capacitance": q(80, "J/K", "thermal_capacitance", (1, 1000)),
        "winding_thermal_capacitance": q(40, "J/K", "thermal_capacitance", (1, 1000)),
        "minimum_temperature": q(250, "K", "absolute_temperature", (250, 400)),
        "maximum_temperature": q(400, "K", "absolute_temperature", (250, 400)),
        "no_load_loss": q(6, "W", "active_power", (0, 100)),
        "rated_load_loss": q(30, "W", "active_power", (0, 100)),
        "loss_reference_temperature": q(300, "K", "absolute_temperature", (250, 400)),
    }
    heat = 30 * (current / 10) ** 2 if raw is None else raw["winding_heat_w"]
    return Snapshot(
        asset,
        event,
        event,
        event,
        "CONTROLLED_SIMULATION",
        Lineage(
            "SIMULATED",
            "SIMULATED",
            "SYNTHETIC",
            source_event_id or f"{CASE}/{seconds:.6f}",
            evidence_references=(CASE,),
            timezone_status="DECLARED_UTC",
            case_id=CASE,
        ),
        Versions("1.0.0", CASE + "/params", CASE + "/config", CASE + "/map", REGISTRY_VERSION),
        ModelSelection(MODEL_ID, True, "HV", "RMS_LINE_CURRENT", CASE, True),
        Policy(
            q(15, "s", "duration", (1, 30)),
            q(30, "s", "duration", (1, 30)),
            q(0, "s", "duration", (0, 30)),
            "EXPLICIT_INITIAL_TEMPERATURES",
            CASE,
            CASE,
            "PREVIOUS_SAMPLE_HOLD",
            CASE,
        ),
        {
            CASE: Evidence(
                "Fictional live demo",
                REFERENCE,
                "fictional local demo only",
                "SYNTHETIC_CASE",
            )
        },
        observed={
            f"current_l{i}": q(current, "A", "current", (0, 20), event, "RMS_LINE_CURRENT_HV")
            for i in (1, 2, 3)
        },
        equipment={"rated_current_a": q(10, "A", "current", (1, 20))},
        model_parameters=params,
        environment={
            "ambient_temperature": q(
                300 if raw is None else raw["ambient_k"],
                "K",
                "absolute_temperature",
                (250, 400),
                event,
            )
        },
        simulation={
            "oil_heat_input": q(6, "W", "heat_rate", (0, 100), event),
            "winding_heat_input": q(heat, "W", "heat_rate", (0, 100), event),
            "initial_oil_temperature": q(300, "K", "absolute_temperature", (250, 400)),
            "initial_winding_temperature": q(300, "K", "absolute_temperature", (250, 400)),
        },
    )


class DemoRun:
    """Owned event stream; SQL caller serializes/commits its complete checkpoint."""

    def __init__(self, asset, epoch, run_id, fem=None, *, variable_ambient=False):
        self.asset, self.epoch, self.run_id = asset, utc(epoch), run_id
        self.variable_ambient = variable_ambient
        self.estimator = PhysicsEstimator()
        self.fem = fem or SheetFEM()
        self.fields = np.full(2 * self.fem.count, 300.0)
        self.sensor_k, self.hours, self.sequence = 300.0, 0.0, 0

    def generate(self, event, operating=None):
        """First-layer operating/sensor event; deterministic lag, no added noise."""
        event = utc(event)
        previous = self.estimator.state(self.asset)
        dt = (event - previous.timestamp).total_seconds() if previous else 0
        if (previous and not 0 < dt <= 30) or (not previous and event != self.epoch):
            raise ValueError("Non-forward event or unsupported initialization/gap")
        current = operating_current((event - self.epoch).total_seconds())
        sensor = (
            previous.oil_k + (self.sensor_k - previous.oil_k) * math.exp(-dt / 5)
            if previous
            else self.sensor_k
        )
        numbers = dict(
            current_a=current,
            load_fraction=current / 10,
            ambient_k=300.0,
            oil_sensor_k=sensor,
            oil_heat_w=6.0,
            winding_heat_w=30 * (current / 10) ** 2,
        )
        if operating is not None:
            if set(operating) != {"current_a", "ambient_k", "oil_sensor_k"}:
                raise ValueError("Exactly current, ambient and simulated sensor inputs required")
            numbers.update(operating)
            numbers["load_fraction"] = numbers["current_a"] / 10
            numbers["winding_heat_w"] = 30 * numbers["load_fraction"] ** 2
        raw = dict(
            raw_contract_version="1.0.0",
            event_id=f"{CASE}/{self.run_id}/{self.asset}/{self.sequence + 1}",
            transformer_id=self.asset,
            run_id=self.run_id,
            sequence=self.sequence + 1,
            timestamp=iso(event),
            source=CASE,
            provenance="SYNTHETIC_SIMULATED",
            reference=REFERENCE,
            values={
                name: {"value": value, "unit": unit}
                for name, value, unit in (
                    ("current_a", numbers["current_a"], "A"),
                    ("load_fraction", numbers["load_fraction"], "1"),
                    ("ambient_k", numbers["ambient_k"], "K"),
                    ("oil_sensor_k", numbers["oil_sensor_k"], "K"),
                    ("oil_heat_w", numbers["oil_heat_w"], "W"),
                    ("winding_heat_w", numbers["winding_heat_w"], "W"),
                )
            },
        )
        validate_raw(
            raw,
            self.asset,
            self.run_id,
            self.sequence + 1,
            event,
            variable_ambient=self.variable_ambient,
        )
        return raw

    def advance(self, event, raw_event=None):
        event = utc(event)
        previous = self.estimator.state(self.asset)
        if previous:
            dt = (event - previous.timestamp).total_seconds()
            if not 0 < dt <= 30:
                raise ValueError("Non-forward event or unsupported gap; new demo run required")
        elif event != self.epoch:
            raise ValueError("First event must equal explicit initialization time")
        raw_event = self.generate(event) if raw_event is None else raw_event
        inputs = validate_raw(
            raw_event,
            self.asset,
            self.run_id,
            self.sequence + 1,
            event,
            variable_ambient=self.variable_ambient,
        )
        result = self.estimator.evaluate(
            snapshot(self.asset, self.epoch, event, inputs, raw_event["event_id"])
        )
        state = self.estimator.state(self.asset)
        if state is None or result["components"]["total_loss"]["status"] != "READY":
            raise ValueError(
                "Eligibility failed: " + str(result["components"]["total_loss"]["reasons"])
            )
        if previous:
            required = (
                "top_oil_temperature",
                "hot_spot_temperature",
                "top_oil_rise",
                "winding_hot_spot_gradient",
            )
            if any(result["components"][k]["status"] != "READY" for k in required):
                raise ValueError("Thermal eligibility failed")
            fields = self.fem.step(
                self.fields,
                previous.oil_heat_w,
                previous.winding_heat_w,
                dt,
                ambient_k=previous.ambient_k,
            )
            sensor = inputs["oil_sensor_k"]
            hours = (
                self.hours
                + (acceleration(previous.winding_k) + acceleration(state.winding_k)) * dt / 7200
            )
        else:
            fields, sensor, hours = self.fields, inputs["oil_sensor_k"], self.hours
        oil_mean, winding_mean = self.fem.means(fields)
        if max(abs(oil_mean - state.oil_k), abs(winding_mean - state.winding_k)) > 1e-8:
            raise ValueError("Independent common-mean verification failed")
        self.fields, self.sensor_k, self.hours = fields, sensor, hours
        self.sequence += 1
        values = {k: c["value"] for k, c in result["components"].items()}
        values.update(
            measured_oil_temperature=sensor - 273.15,
            ageing_acceleration_factor=acceleration(state.winding_k),
            equivalent_ageing_hours=hours,
            fem_hot_spot_temperature=winding_mean - 273.15,
            hot_spot_difference=state.winding_k - winding_mean,
        )
        components = {}
        for key, value in values.items():
            components[key] = dict(
                value=value,
                unit=OUTPUTS[key][0],
                status="READY" if value is not None else "INITIALIZING",
                provenance="SYNTHETIC_SIMULATED",
                model_id="DEMO_TELEMETRY_SENSOR_INPUT_V1"
                if key == "measured_oil_temperature" and self.variable_ambient
                else MODELS[key],
                reference=REFERENCE,
                target="AREA_MEAN_WINDING_PROXY"
                if key
                in (
                    "hot_spot_temperature",
                    "fem_hot_spot_temperature",
                    "hot_spot_difference",
                )
                else key,
            )
        return dict(
            demo_contract_version="1.0.0",
            mode="LIVE_SIMULATION",
            transformer_id=self.asset,
            run_id=self.run_id,
            sequence=self.sequence,
            timestamp=iso(event),
            published_at=iso(event),
            evaluated_at=iso(event),
            status="READY" if previous else "INITIALIZING",
            reason=None,
            case_id=CASE,
            components=components,
            inputs=dict(
                current_a=inputs["current_a"],
                ambient_k=inputs["ambient_k"],
                oil_heat_w=state.oil_heat_w,
                winding_heat_w=state.winding_heat_w,
            ),
            maximum_age_seconds=15.0,
        )
