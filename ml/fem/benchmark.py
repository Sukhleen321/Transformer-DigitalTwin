"""Manufactured-solution benchmark, acceptance and simulated-reference artifact.

No estimator imports or fitted parameters. Exact fields are constructed by
analytical differentiation, not by solving a second discretized system.
"""

from __future__ import annotations

import copy
import hashlib
import json
from importlib.resources import files

import numpy as np
import scipy

from .solver import (
    MAX_SUBDIVISIONS,
    FEMError,
    error_norms,
    integer,
    number,
    rectangle_mesh,
    solve_steady,
)

MODEL_ID = "SYNTHETIC_STEADY_P1_CONDUCTION_V1"
MODEL_VERSION = "1.0.0"
PARAMETERS = {
    "length_x": ("m", "length"),
    "length_y": ("m", "length"),
    "thickness": ("m", "length"),
    "conductivity": ("W/(m*K)", "thermal_conductivity"),
    "boundary_temperature": ("K", "absolute_temperature"),
    "temperature_amplitude": ("K", "temperature_difference"),
}
POLICIES = {
    "quadrature_order": ("count", "count"),
    "check_quadrature_order": ("count", "count"),
    "residual_tolerance": ("1", "dimensionless"),
    "balance_tolerance": ("W", "heat_rate"),
    "power_tolerance": ("W", "heat_rate"),
    "minimum_l2_order": ("1", "dimensionless"),
    "minimum_h1_order": ("1", "dimensionless"),
    "final_l2_tolerance": ("K*m", "spatial_l2_temperature_error"),
    "maximum_temperature_tolerance": ("K", "temperature_difference"),
    "quadrature_error_tolerance": ("K*m", "spatial_l2_temperature_error"),
}
DECLARATIONS = {
    "context": "CONTROLLED_SIMULATION",
    "origin_kind": "SIMULATED",
    "input_verification": "SYNTHETIC",
    "geometry": "RECTANGLE_UNIFORM_THICKNESS",
    "material": "HOMOGENEOUS_CONSTANT_ISOTROPIC",
    "source_distribution": "MANUFACTURED_SINE_V1",
    "boundary_condition": "FULL_CONSTANT_DIRICHLET",
    "initial_condition": "NOT_APPLICABLE_STEADY_STATE",
}


def _object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise FEMError("INVALID_JSON", "Duplicate case keys are unsupported.")
        result[key] = value
    return result


def _constant(value):
    raise FEMError("INVALID_JSON", "Nonfinite JSON values are unsupported.")


def read_case(path=None):
    """The default is an explicit packaged synthetic case, never equipment fallback."""
    try:
        text = (
            files("ml.fem").joinpath("synthetic_sine_v1.json").read_text(encoding="utf-8")
            if path is None
            else path.read_text(encoding="utf-8")
        )
        return json.loads(text, object_pairs_hook=_object_pairs, parse_constant=_constant)
    except (OSError, json.JSONDecodeError) as exc:
        raise FEMError("CASE_UNREADABLE", "Case file is missing or invalid JSON.") from exc


def _record(record, unit, kind, case_id, name):
    if not isinstance(record, dict) or set(record) != {
        "value",
        "unit",
        "quantity_kind",
        "verification",
        "evidence_reference",
    }:
        raise FEMError("QUANTITY_MISSING", f"{name} requires an explicit quantity/evidence record.")
    if record["unit"] != unit or record["quantity_kind"] != kind:
        raise FEMError("UNSUPPORTED_UNIT", f"{name} requires {unit} / {kind}; no units inferred.")
    if record["verification"] != "SYNTHETIC" or record["evidence_reference"] != case_id:
        raise FEMError("EVIDENCE_REQUIRED", f"{name} requires this synthetic case's provenance.")
    value = number(
        record["value"],
        name,
        nonnegative=name == "boundary_temperature",
        positive=name != "boundary_temperature",
    )
    return record["value"] if kind == "count" else value


def validate_case(case):
    if not isinstance(case, dict):
        raise FEMError("CASE_INVALID", "Case must be an object.")
    required = set(DECLARATIONS) | {
        "case_id",
        "case_version",
        "evidence",
        "parameters",
        "numerical_policy",
    }
    if set(case) != required:
        raise FEMError(
            "CASE_FIELDS_INVALID",
            "All declared case fields are required; unknown fields unsupported.",
        )
    for key, expected in DECLARATIONS.items():
        if case[key] != expected:
            raise FEMError(
                "CASE_UNSUPPORTED", f"{key} is not supported by this synthetic reference."
            )
    for key in ("case_id", "case_version"):
        if (
            not isinstance(case[key], str)
            or not case[key].strip()
            or case[key] != case[key].strip()
        ):
            raise FEMError(
                "IDENTITY_REQUIRED", "Explicit immutable case identity/version required."
            )
    evidence = case["evidence"]
    if (
        not isinstance(evidence, dict)
        or set(evidence) != {"kind", "reference", "applicability"}
        or evidence["kind"] != "SYNTHETIC_CASE"
    ):
        raise FEMError("EVIDENCE_REQUIRED", "Synthetic case evidence is required.")
    if any(
        not isinstance(evidence[key], str) or not evidence[key].strip()
        for key in ("reference", "applicability")
    ):
        raise FEMError("EVIDENCE_REQUIRED", "Evidence must specify reference and applicability.")
    parameters = case["parameters"]
    policy = case["numerical_policy"]
    if not isinstance(parameters, dict) or set(parameters) != set(PARAMETERS):
        raise FEMError("PARAMETERS_MISSING", "All six explicit benchmark parameters are required.")
    if not isinstance(policy, dict) or set(policy) != set(POLICIES) | {"subdivisions"}:
        raise FEMError("POLICY_MISSING", "All numerical verification policies are required.")
    p = {
        key: _record(parameters[key], *definition, case["case_id"], key)
        for key, definition in PARAMETERS.items()
    }
    c = {
        key: _record(policy[key], *definition, case["case_id"], key)
        for key, definition in POLICIES.items()
    }
    subdivisions = policy["subdivisions"]
    if not isinstance(subdivisions, list) or not 3 <= len(subdivisions) <= 6:
        raise FEMError("MESH_SEQUENCE_INVALID", "Three to six refinement levels are required.")
    ns = [
        _record(record, "count", "count", case["case_id"], "subdivisions")
        for record in subdivisions
    ]
    for n in ns:
        integer(n, "subdivisions", 2, MAX_SUBDIVISIONS)
    if any(b != 2 * a for a, b in zip(ns[:-1], ns[1:], strict=True)):
        raise FEMError("MESH_SEQUENCE_INVALID", "Each mesh must double both subdivision counts.")
    integer(c["quadrature_order"], "quadrature_order", 2, 9)
    integer(c["check_quadrature_order"], "check_quadrature_order", 3, 10)
    if c["check_quadrature_order"] <= c["quadrature_order"]:
        raise FEMError("QUADRATURE_CHECK_INVALID", "Check quadrature must have higher order.")
    return p, c, ns


def manufactured_fields(parameters):
    """Independent closed-form target, gradient, forcing and boundary."""
    lx, ly = parameters["length_x"], parameters["length_y"]
    amplitude, base = parameters["temperature_amplitude"], parameters["boundary_temperature"]
    ax, ay = np.pi / lx, np.pi / ly
    source_scale = parameters["conductivity"] * amplitude * (ax**2 + ay**2)
    if not np.isfinite(source_scale):
        raise FEMError(
            "NUMERICAL_FAILURE", "Manufactured source arithmetic overflow.", "MODEL_ERROR"
        )

    def exact(points):
        return base + amplitude * np.sin(ax * points[..., 0]) * np.sin(ay * points[..., 1])

    def gradient(points):
        x, y = points[..., 0], points[..., 1]
        return np.stack(
            (
                amplitude * ax * np.cos(ax * x) * np.sin(ay * y),
                amplitude * ay * np.sin(ax * x) * np.cos(ay * y),
            ),
            axis=-1,
        )

    def source(points):
        return source_scale * np.sin(ax * points[..., 0]) * np.sin(ay * points[..., 1])

    def boundary(points):
        return np.full(points.shape[:-1], base)

    return exact, gradient, source, boundary


def run_reference(case):
    """Publish only finite diagnostics; invalid data never becomes a zero norm."""
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            return _run_reference(copy.deepcopy(case))
    except FEMError:
        raise
    except (ArithmeticError, np.linalg.LinAlgError) as exc:
        raise FEMError("NUMERICAL_FAILURE", "Benchmark arithmetic failed.", "MODEL_ERROR") from exc


def _run_reference(case):
    p, policy, ns = validate_case(case)
    encoded = json.dumps(case, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    provenance = {
        "model_id": MODEL_ID,
        "model_version": MODEL_VERSION,
        "equation_ids": ["F1", "F2", "F3", "F4"],
        "case_id": case["case_id"],
        "case_version": case["case_version"],
        "case_sha256": digest,
        "evidence_references": [case["evidence"]["reference"], "docs/fem_reference.md"],
        "numerical_verification_reference": f"manufactured-sine:{digest}",
        "mesh_convergence_reference": f"mesh-refinement:{digest}",
        "comparison_id": None,
    }

    def quantity(value, unit, kind):
        return {
            "value": value,
            "unit": unit,
            "quantity_kind": kind,
            "provenance": provenance.copy(),
        }

    exact, gradient, source, boundary = manufactured_fields(p)
    exact_power = (
        4
        * p["conductivity"]
        * p["temperature_amplitude"]
        * p["thickness"]
        * (p["length_y"] / p["length_x"] + p["length_x"] / p["length_y"])
    )
    records, norms = [], []
    for n in ns:
        mesh = rectangle_mesh(p["length_x"], p["length_y"], n, n)
        solution = solve_steady(
            mesh,
            p["conductivity"],
            p["thickness"],
            source,
            boundary,
            quadrature_order=policy["quadrature_order"],
            residual_tolerance=policy["residual_tolerance"],
        )
        l2, h1 = error_norms(solution, exact, gradient, policy["quadrature_order"])
        h = float(np.hypot(p["length_x"] / n, p["length_y"] / n))
        norms.append((h, l2, h1))
        records.append(
            {
                "nx": quantity(n, "count", "count"),
                "ny": quantity(n, "count", "count"),
                "nodes": quantity(len(mesh.coordinates_m), "count", "count"),
                "elements": quantity(len(mesh.triangles), "count", "count"),
                "h": quantity(h, "m", "length"),
                "l2_error": quantity(l2, "K*m", "spatial_l2_temperature_error"),
                "h1_seminorm_error": quantity(h1, "K", "spatial_h1_temperature_error"),
                "maximum_temperature": quantity(
                    float(np.max(solution.temperature_k)), "K", "absolute_temperature"
                ),
                "scaled_residual": quantity(solution.scaled_residual, "1", "dimensionless"),
                "source_power": quantity(solution.source_power_w, "W", "heat_rate"),
                "outward_reaction_power": quantity(
                    solution.outward_reaction_power_w, "W", "heat_rate"
                ),
                "balance_error": quantity(solution.balance_error_w, "W", "heat_rate"),
            }
        )
    rates_l2, rates_h1 = [], []
    for old, new in zip(norms[:-1], norms[1:], strict=True):
        rates_l2.append(float(np.log(old[1] / new[1]) / np.log(old[0] / new[0])))
        rates_h1.append(float(np.log(old[2] / new[2]) / np.log(old[0] / new[0])))
    higher = solve_steady(
        mesh,
        p["conductivity"],
        p["thickness"],
        source,
        boundary,
        quadrature_order=policy["check_quadrature_order"],
        residual_tolerance=policy["residual_tolerance"],
    )
    higher_l2, _ = error_norms(higher, exact, gradient, policy["check_quadrature_order"])
    quadrature_difference = abs(norms[-1][1] - higher_l2)
    maximum_error = abs(
        float(np.max(solution.temperature_k))
        - (p["boundary_temperature"] + p["temperature_amplitude"])
    )
    checks = {
        "l2_decreases": all(b[1] < a[1] for a, b in zip(norms[:-1], norms[1:], strict=True)),
        "h1_decreases": all(b[2] < a[2] for a, b in zip(norms[:-1], norms[1:], strict=True)),
        "l2_orders": all(rate >= policy["minimum_l2_order"] for rate in rates_l2),
        "h1_orders": all(rate >= policy["minimum_h1_order"] for rate in rates_h1),
        "final_l2": norms[-1][1] <= policy["final_l2_tolerance"],
        "maximum_error": maximum_error <= policy["maximum_temperature_tolerance"],
        "discrete_balance": all(
            record["balance_error"]["value"] <= policy["balance_tolerance"] for record in records
        ),
        "source_quadrature": all(
            abs(record["source_power"]["value"] - exact_power) <= policy["power_tolerance"]
            for record in records
        ),
        "quadrature_sensitivity": quadrature_difference <= policy["quadrature_error_tolerance"],
    }
    passed = all(checks.values())
    return {
        "artifact_version": "1.0.0",
        "result_kind": "SIMULATED_REFERENCE",
        **DECLARATIONS,
        "status": "READY" if passed else "MODEL_ERROR",
        "provenance": provenance,
        "case_definition": case,
        "dependency_versions": {"numpy": np.__version__, "scipy": scipy.__version__},
        "target_definition": "SYNTHETIC_RECTANGLE_DOMAIN_MAXIMUM",
        "maximum_temperature": quantity(
            float(np.max(solution.temperature_k)) if passed else None, "K", "absolute_temperature"
        ),
        "mesh_records": records,
        "checks": checks,
        "l2_orders": [quantity(rate, "1", "dimensionless") for rate in rates_l2],
        "h1_orders": [quantity(rate, "1", "dimensionless") for rate in rates_h1],
        "exact_power": quantity(exact_power, "W", "heat_rate"),
        "exact_maximum_temperature": quantity(
            p["boundary_temperature"] + p["temperature_amplitude"], "K", "absolute_temperature"
        ),
        "maximum_error": quantity(maximum_error, "K", "temperature_difference"),
        "quadrature_l2_difference": quantity(
            quadrature_difference, "K*m", "spatial_l2_temperature_error"
        ),
        "solver": {
            "method": "SCIPY_SUPERLU",
            "ordering": "COLAMD",
            "element": "P1_TRIANGLE",
            "diagonal": "SW_NE",
            "policy": case["numerical_policy"],
        },
        "reasons": [
            {"code": "VERIFICATION_FAILED", "message": key, "paths": ["checks." + key]}
            for key, value in checks.items()
            if not value
        ],
        "warnings": [
            {
                "code": "SYNTHETIC_BENCHMARK_ONLY",
                "message": "Synthetic verification; no field accuracy or compliance claim.",
            },
            {
                "code": "TARGET_NOT_ALIGNED",
                "message": "No estimator spatial mapping or comparison is established.",
            },
        ],
    }
