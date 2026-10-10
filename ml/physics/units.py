"""Explicit unit conversions. Registry agreement is checked in unit tests."""

from __future__ import annotations

import math
from dataclasses import replace
from decimal import Decimal

from .types import InputIssue, Quantity

# (quantity kind, source, normalized target): (ID, exact scale, exact offset)
RULES = {
    ("absolute_temperature", "DEG_C", "K"): ("absolute_deg_c_to_k", "1", "273.15"),
    ("temperature_difference", "DEG_C", "K"): ("difference_deg_c_to_k", "1", "0"),
    ("active_power", "kW", "W"): ("kw_to_w", "1000", "0"),
    ("apparent_power", "kVA", "VA"): ("kva_to_va", "1000", "0"),
    ("reactive_power", "kVAr", "var"): ("kvar_to_var", "1000", "0"),
    ("energy", "kWh", "J"): ("kwh_to_j", "3600000", "0"),
    ("duration", "h", "s"): ("hours_to_seconds", "3600", "0"),
    ("fraction", "percent", "1"): ("percent_to_one", "0.01", "0"),
    ("length", "mm", "m"): ("mm_to_m", "0.001", "0"),
}
UNIT_KINDS = {
    "absolute_temperature": "K",
    "temperature_difference": "K",
    "active_power": "W",
    "heat_rate": "W",
    "apparent_power": "VA",
    "reactive_power": "var",
    "energy": "J",
    "duration": "s",
    "fraction": "1",
    "length": "m",
    "current": "A",
    "voltage": "V",
    "frequency": "Hz",
    "thermal_resistance": "K/W",
    "thermal_capacitance": "J/K",
    "thermal_conductivity": "W/(m*K)",
    "density": "kg/m^3",
    "specific_heat": "J/(kg*K)",
    "volumetric_heat_rate": "W/m^3",
    "heat_transfer_coefficient": "W/(m^2*K)",
    "heat_flux": "W/m^2",
    "status": "STATUS",
    "count": "count",
}


def finite(value) -> float:
    if type(value) not in (int, float, Decimal):
        raise InputIssue(
            "MISSING_INPUT" if value is None else "INVALID_NUMBER",
            "A finite numeric value is required; no coercion or zero filling.",
        )
    try:
        number = float(value)
    except (ValueError, OverflowError) as exc:
        raise InputIssue("INVALID_NUMBER", "Numeric value is not representable.") from exc
    if not math.isfinite(number):
        raise InputIssue("INVALID_NUMBER", "Numeric value must be finite.")
    return number


def convert_value(value, source_unit: str, target_unit: str, kind: str) -> float:
    number = finite(value)
    if not all(isinstance(item, str) for item in (source_unit, target_unit, kind)):
        raise InputIssue("UNIT_UNSUPPORTED", "Units and quantity kind must be declared strings.")
    canonical = UNIT_KINDS.get(kind)
    if canonical is None:
        raise InputIssue("QUANTITY_KIND_UNSUPPORTED", "Unknown quantity kind.")
    permitted_identity = source_unit == canonical or any(
        k == kind and source_unit in (source, target) for k, source, target in RULES
    )
    if source_unit == target_unit and permitted_identity:
        result = number
    else:
        key = (kind, source_unit, target_unit)
        inverse = False
        if key not in RULES:
            key = (kind, target_unit, source_unit)
            inverse = True
        if key not in RULES:
            raise InputIssue("UNIT_UNSUPPORTED", "No approved conversion for this quantity.")
        _, scale, offset = RULES[key]
        source = Decimal(str(value))
        result = float(
            (source - Decimal(offset)) / Decimal(scale)
            if inverse
            else source * Decimal(scale) + Decimal(offset)
        )
    result = finite(result)
    if kind == "absolute_temperature":
        minimum = -273.15 if target_unit == "DEG_C" else 0
        if result < minimum:
            raise InputIssue("OUT_OF_RANGE", "Temperature is below absolute zero.")
    if kind in ("count", "status"):
        if not result.is_integer() or (kind == "status" and result not in (0, 1)):
            raise InputIssue("OUT_OF_RANGE", "Count/contact must be an integer code.")
    return result


def normalize(quantity: Quantity, target_unit: str, kind: str) -> Quantity:
    if not isinstance(quantity, Quantity) or quantity.quantity_kind != kind:
        raise InputIssue("QUANTITY_KIND_UNSUPPORTED", "A compatible quantity record is required.")
    value = convert_value(quantity.value, quantity.unit, target_unit, kind)
    bounds = quantity.valid_range
    if bounds is not None:
        if not isinstance(bounds, tuple) or len(bounds) != 2:
            raise InputIssue("RANGE_INVALID", "Range must contain min/max in the source unit.")
        lower, upper = (None if v is None else finite(v) for v in bounds)
        if lower is not None and upper is not None and lower > upper:
            raise InputIssue("RANGE_INVALID", "Minimum exceeds maximum.")
        number = finite(quantity.value)
        if (lower is not None and number < lower) or (upper is not None and number > upper):
            raise InputIssue("OUT_OF_RANGE", "Value is outside its declared range.")
        bounds = tuple(
            None if v is None else convert_value(v, quantity.unit, target_unit, kind)
            for v in (lower, upper)
        )
    provenance = quantity.provenance
    if provenance.original_unit is None:
        raise InputIssue("UNIT_UNVERIFIED", "Original source unit is required.")
    original = convert_value(
        provenance.original_value, provenance.original_unit, quantity.unit, kind
    )
    expected_stage = "identity"
    if provenance.original_unit != quantity.unit:
        forward = RULES.get((kind, provenance.original_unit, quantity.unit))
        backward = RULES.get((kind, quantity.unit, provenance.original_unit))
        expected_stage = forward[0] if forward else "inverse:" + backward[0]
    if provenance.conversion_id != expected_stage:
        raise InputIssue(
            "CONVERSION_INCONSISTENT",
            "Declared conversion ID is incompatible with the source record.",
        )
    if not math.isclose(original, finite(quantity.value), rel_tol=1e-12, abs_tol=1e-12):
        raise InputIssue("CONVERSION_INCONSISTENT", "Value disagrees with its source conversion.")
    rule = RULES.get((kind, provenance.original_unit, target_unit))
    conversion_id = rule[0] if rule else "identity"
    if provenance.original_unit != target_unit and rule is None:
        raise InputIssue("UNIT_UNSUPPORTED", "Original unit has no approved normalization.")
    return replace(
        quantity,
        value=value,
        unit=target_unit,
        valid_range=bounds,
        provenance=replace(provenance, conversion_id=conversion_id),
    )
