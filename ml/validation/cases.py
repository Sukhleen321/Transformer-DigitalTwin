"""Strict, explicit synthetic verification inputs; no equipment defaults."""

from __future__ import annotations

import json
import math
from datetime import datetime
from importlib.resources import files


class ValidationError(ValueError):
    def __init__(self, code, message, status="INVALID_CONFIGURATION"):
        super().__init__(message)
        self.code, self.status = code, status


def finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError("INVALID_JSON", "Duplicate keys are unsupported.")
        result[key] = value
    return result


def _constant(value):
    raise ValidationError("INVALID_JSON", "Nonfinite JSON values are unsupported.")


def read_case(path=None):
    try:
        text = (
            files("ml.validation").joinpath("cases_v1.json") if path is None else path
        ).read_text(encoding="utf-8")
        return json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError("CASE_UNREADABLE", "Missing or invalid case JSON.") from exc


PARAMETERS = {
    "oil_thermal_resistance": ("K/W", "thermal_resistance"),
    "winding_thermal_resistance": ("K/W", "thermal_resistance"),
    "oil_thermal_capacitance": ("J/K", "thermal_capacitance"),
    "winding_thermal_capacitance": ("J/K", "thermal_capacitance"),
    **{
        key: ("K", "absolute_temperature")
        for key in (
            "ambient_temperature",
            "initial_oil_temperature",
            "initial_winding_temperature",
            "minimum_temperature",
            "maximum_temperature",
        )
    },
    "oil_heat_input": ("W", "heat_rate"),
    "winding_heat_input": ("W", "heat_rate"),
}
POLICY = {
    **{
        key: ("s", "duration")
        for key in ("max_sample_age_seconds", "max_gap_seconds", "required_history_seconds")
    },
    **{
        key: ("K", "temperature_difference")
        for key in (
            "analytic_temperature_tolerance",
            "steady_temperature_tolerance",
            "sanity_temperature_tolerance",
            "relative_denominator_floor",
        )
    },
    "energy_balance_tolerance": ("J", "energy"),
    "power_balance_tolerance": ("W", "heat_rate"),
    "fem_balance_tolerance": ("W", "heat_rate"),
}
VARIATIONS = {
    **{
        key: ("1", "dimensionless")
        for key in ("heat_multiplier", "ambient_resistance_multiplier", "capacitance_multiplier")
    },
    "time_scale_probe": ("s", "duration"),
}


def record(value, definition, case_id, *, bounded=False, zero=False):
    if not isinstance(value, dict) or set(value) != {
        "value",
        "unit",
        "quantity_kind",
        "verification",
        "evidence_reference",
        "valid_range",
    }:
        raise ValidationError("QUANTITY_REQUIRED", "Explicit quantity record required.")
    if (value["unit"], value["quantity_kind"]) != definition:
        raise ValidationError("UNSUPPORTED_UNIT", "No missing or inferred units allowed.")
    if value["verification"] != "SYNTHETIC" or value["evidence_reference"] != case_id:
        raise ValidationError("EVIDENCE_REQUIRED", "This synthetic case's evidence is required.")
    number = value["value"]
    if not finite(number) or number < 0 or (not zero and number == 0):
        raise ValidationError(
            "VALUE_INVALID", "Finite supported nonnegative/positive input required."
        )
    bounds = value["valid_range"]
    if bounds is not None:
        if (
            not isinstance(bounds, list)
            or len(bounds) != 2
            or not all(finite(x) for x in bounds)
            or not bounds[0] <= number <= bounds[1]
        ):
            raise ValidationError("RANGE_INVALID", "Quantity is outside its declared finite range.")
    elif bounded:
        raise ValidationError("RANGE_REQUIRED", "Physical input requires explicit supported range.")
    return number


def validate_case(case):
    keys = {
        "validation_id",
        "version",
        "context",
        "origin_kind",
        "input_verification",
        "evidence_reference",
        "epoch",
        "thermal_parameters",
        "policy",
        "sample_times",
        "variations",
        "fem_case_id",
        "fem_case_sha256",
        "fem_sanity_subdivisions",
    }
    if not isinstance(case, dict) or set(case) != keys:
        raise ValidationError(
            "CASE_FIELDS_INVALID", "All explicit fields required; unknown fields unsupported."
        )
    for key, value in {
        "context": "CONTROLLED_SIMULATION",
        "origin_kind": "SIMULATED",
        "input_verification": "SYNTHETIC",
    }.items():
        if case[key] != value:
            raise ValidationError(
                "CASE_UNSUPPORTED", "Only declared synthetic verification is supported."
            )
    for key in ("validation_id", "version", "evidence_reference", "fem_case_id", "fem_case_sha256"):
        if not isinstance(case[key], str) or not case[key].strip():
            raise ValidationError("IDENTITY_REQUIRED", "Named versioned evidence required.")
    try:
        epoch = datetime.fromisoformat(case["epoch"].replace("Z", "+00:00"))
        if epoch.tzinfo is None or epoch.utcoffset().total_seconds() != 0:
            raise ValueError()
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValidationError("TIMESTAMP_UNSUPPORTED", "Declared UTC epoch required.") from exc
    groups = []
    for key, definitions in (
        ("thermal_parameters", PARAMETERS),
        ("policy", POLICY),
        ("variations", VARIATIONS),
    ):
        group = case[key]
        if not isinstance(group, dict) or set(group) != set(definitions):
            raise ValidationError(
                "INPUTS_REQUIRED", "Complete physical and numerical inputs required."
            )
        groups.append(
            {
                name: record(
                    group[name],
                    definition,
                    case["validation_id"],
                    bounded=key == "thermal_parameters",
                    zero=name
                    in ("oil_heat_input", "winding_heat_input", "required_history_seconds"),
                )
                for name, definition in definitions.items()
            }
        )
    p, policy, variations = groups
    # The declared monotonicity checks apply specifically to a cold equilibrium seed.
    if not (
        p["minimum_temperature"] < p["maximum_temperature"]
        and p["initial_oil_temperature"]
        == p["initial_winding_temperature"]
        == p["ambient_temperature"]
    ):
        raise ValidationError(
            "CASE_UNSUPPORTED", "Cold equilibrium seeds and ordered envelope required."
        )
    if not isinstance(case["sample_times"], list) or not 3 <= len(case["sample_times"]) <= 100:
        raise ValidationError("TIMES_INVALID", "Explicit bounded sample sequence required.")
    times = [
        record(q, ("s", "duration"), case["validation_id"], zero=True) for q in case["sample_times"]
    ]
    if times[0] != 0 or any(
        b <= a or b - a > policy["max_gap_seconds"]
        for a, b in zip(times[:-1], times[1:], strict=True)
    ):
        raise ValidationError(
            "TIMES_INVALID", "Samples must start at zero, increase and respect gap policy."
        )
    if (
        times[-1] > policy["max_gap_seconds"]
        or variations["time_scale_probe"] * variations["capacitance_multiplier"]
        > policy["max_gap_seconds"]
    ):
        raise ValidationError(
            "TIMES_INVALID", "Single-step scaling checks must respect gap policy."
        )
    n = record(case["fem_sanity_subdivisions"], ("count", "count"), case["validation_id"])
    if type(n) is not int:
        raise ValidationError("MESH_INVALID", "Subdivision count must be an integer.")
    return p, policy, variations, times, epoch, n
