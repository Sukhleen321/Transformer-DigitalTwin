"""Independent synthetic numerical verification; cross-model comparison blocked."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import replace
from datetime import timedelta

import numpy as np
import scipy

from ml.fem.benchmark import manufactured_fields, run_reference
from ml.fem.benchmark import read_case as read_fem_case
from ml.fem.benchmark import validate_case as validate_fem_case
from ml.fem.solver import FEMError, rectangle_mesh, solve_steady
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
from ml.physics.estimator import MODEL_ID, REGISTRY_VERSION
from ml.physics.units import convert_value

from .cases import ValidationError, finite, read_case, validate_case
from .metrics import blocked_comparison, operand, temperature_rise_errors


def digest(case):
    return hashlib.sha256(
        json.dumps(case, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def modal_reference(p, seconds):
    """Algebraic spectral solution of E1/E2; no production step/rates/expm."""
    ro, rw = p["oil_thermal_resistance"], p["winding_thermal_resistance"]
    co, cw = p["oil_thermal_capacitance"], p["winding_thermal_capacitance"]
    po, pw, ta = p["oil_heat_input"], p["winding_heat_input"], p["ambient_temperature"]
    steady = np.array([ta + ro * (po + pw), ta + ro * (po + pw) + rw * pw])
    matrix = np.array([[-(1 / ro + 1 / rw) / co, 1 / (rw * co)], [1 / (rw * cw), -1 / (rw * cw)]])
    discriminant = math.sqrt((matrix[0, 0] - matrix[1, 1]) ** 2 + 4 * matrix[0, 1] * matrix[1, 0])
    slow = (float(matrix.trace()) + discriminant) / 2
    fast = (float(matrix.trace()) - discriminant) / 2
    if not (finite(slow) and finite(fast) and fast < slow < 0):
        raise ValidationError(
            "NUMERICAL_FAILURE", "Unsupported or unstable analytic modes.", "MODEL_ERROR"
        )
    deviation = np.array([p["initial_oil_temperature"], p["initial_winding_temperature"]]) - steady
    plus = (matrix - fast * np.eye(2)) @ deviation / (slow - fast)
    minus = deviation - plus
    temperatures = steady + plus * math.exp(slow * seconds) + minus * math.exp(fast * seconds)
    integral_oil_rise = (
        (steady[0] - ta) * seconds
        + plus[0] * math.expm1(slow * seconds) / slow
        + minus[0] * math.expm1(fast * seconds) / fast
    )
    net_energy = (po + pw) * seconds - integral_oil_rise / ro
    if not np.all(np.isfinite(temperatures)) or not finite(float(net_energy)):
        raise ValidationError("NUMERICAL_FAILURE", "Analytic reference overflow.", "MODEL_ERROR")
    return temperatures, steady, float(net_energy), (-1 / slow, -1 / fast)


def snapshot(case, p, epoch, seconds, scenario):
    """Production typed snapshots from explicit manifest records, no test helpers."""
    cid = case["validation_id"] + "/" + scenario
    event = epoch + timedelta(seconds=seconds)

    def q(name, group="thermal_parameters", at=epoch):
        definition = case[group][name]
        value = p[name] if group == "thermal_parameters" else definition["value"]
        return Quantity(
            value,
            definition["unit"],
            definition["quantity_kind"],
            "SYNTHETIC",
            Provenance(
                cid, cid, "fictional controlled verification case", definition["unit"], value
            ),
            at,
            None if definition["valid_range"] is None else tuple(definition["valid_range"]),
        )

    policy = Policy(
        *(
            q(key, "policy")
            for key in ("max_sample_age_seconds", "max_gap_seconds", "required_history_seconds")
        ),
        "EXPLICIT_INITIAL_TEMPERATURES",
        cid,
        cid,
        "PREVIOUS_SAMPLE_HOLD",
        cid,
    )
    parameters = {
        key: q(key)
        for key in (
            "oil_thermal_resistance",
            "winding_thermal_resistance",
            "oil_thermal_capacitance",
            "winding_thermal_capacitance",
            "minimum_temperature",
            "maximum_temperature",
        )
    }
    return Snapshot(
        "validation-" + scenario,
        event,
        event,
        event,
        "CONTROLLED_SIMULATION",
        Lineage(
            "SIMULATED",
            "SIMULATED",
            "SYNTHETIC",
            cid + "/event/" + str(seconds),
            evidence_references=(cid,),
            timezone_status="DECLARED_UTC",
            case_id=cid,
        ),
        Versions(
            "1.0.0", cid + "/params-v1", cid + "/config-v1", cid + "/map-v1", REGISTRY_VERSION
        ),
        ModelSelection(MODEL_ID, False),
        policy,
        {
            cid: Evidence(
                "Synthetic independent verification",
                case["evidence_reference"],
                "fictional controlled verification case",
                "SYNTHETIC_CASE",
                digest(case),
            )
        },
        model_parameters=parameters,
        environment={"ambient_temperature": q("ambient_temperature", at=event)},
        simulation={
            key: q(key, at=event if key.endswith("heat_input") else epoch)
            for key in (
                "oil_heat_input",
                "winding_heat_input",
                "initial_oil_temperature",
                "initial_winding_temperature",
            )
        },
    )


def temperatures(result):
    values = []
    for key in ("top_oil_temperature", "hot_spot_temperature"):
        c = result["components"][key]
        if c["status"] != "READY" or not finite(c["value"]) or c["unit"] != "DEG_C":
            raise ValidationError(
                "ESTIMATOR_UNAVAILABLE",
                "Expected controlled temperature unavailable.",
                "MODEL_ERROR",
            )
        values.append(float(convert_value(c["value"], "DEG_C", "K", "absolute_temperature")))
    return np.array(values)


def stream(case, p, epoch, times, name):
    estimator = PhysicsEstimator()
    return [estimator.evaluate(snapshot(case, p, epoch, t, name)) for t in times]


def _thermal(case, p, policy, variations, times, epoch, quantity):
    results = stream(case, p, epoch, times, "base")
    values = [temperatures(result) for result in results[1:]]
    ref = case["evidence_reference"]
    records, errors = [], []
    for t, actual, result in zip(times[1:], values, results[1:], strict=True):
        exact, steady, energy, taus = modal_reference(p, t)
        metrics = {
            node: temperature_rise_errors(
                operand(float(actual[i] - p["ambient_temperature"]), "RC_" + node + "_RISE", ref),
                operand(float(exact[i] - p["ambient_temperature"]), "RC_" + node + "_RISE", ref),
                near_zero_k=policy["relative_denominator_floor"],
                evidence_reference=ref,
            )
            for i, node in enumerate(("OIL", "WINDING"))
        }
        errors.extend(m["absolute_error"]["value"] for m in metrics.values())
        records.append(
            {
                "elapsed_time": quantity(t, "s", "duration"),
                "analytic_temperatures": [
                    quantity(float(v), "K", "absolute_temperature") for v in exact
                ],
                "metrics": metrics,
                "estimator_envelope": result,
            }
        )
    final = values[-1]
    exact, steady, net_energy, taus = modal_reference(p, times[-1])
    # Use a non-steady interior time to check the integrated transient energy balance.
    interior = len(times) - 2
    t_energy = times[interior]
    energy_temperatures = values[interior - 1]
    net_energy = modal_reference(p, t_energy)[2]
    stored = p["oil_thermal_capacitance"] * (
        energy_temperatures[0] - p["initial_oil_temperature"]
    ) + p["winding_thermal_capacitance"] * (
        energy_temperatures[1] - p["initial_winding_temperature"]
    )
    energy_error = float(abs(stored - net_energy))
    power_error = float(
        abs(
            (final[0] - p["ambient_temperature"]) / p["oil_thermal_resistance"]
            - p["oil_heat_input"]
            - p["winding_heat_input"]
        )
    )
    one_step = temperatures(stream(case, p, epoch, [0, times[-1]], "one-step")[-1])
    high = dict(p)
    for key in ("oil_heat_input", "winding_heat_input"):
        high[key] *= variations["heat_multiplier"]
    high_t = temperatures(stream(case, high, epoch, [0, times[-1]], "high-heat")[-1])
    cooling = dict(
        p,
        oil_thermal_resistance=p["oil_thermal_resistance"]
        * variations["ambient_resistance_multiplier"],
    )
    cooling_t = temperatures(
        stream(case, cooling, epoch, [0, times[-1]], "stronger-ambient-conduction")[-1]
    )
    capacity = dict(p)
    for key in ("oil_thermal_capacitance", "winding_thermal_capacitance"):
        capacity[key] *= variations["capacitance_multiplier"]
    probe = variations["time_scale_probe"]
    base_probe = temperatures(stream(case, p, epoch, [0, probe], "time-probe")[-1])
    capacity_t = temperatures(
        stream(
            case,
            capacity,
            epoch,
            [0, probe * variations["capacitance_multiplier"]],
            "capacity-time-scale",
        )[-1]
    )
    zero = dict(p, oil_heat_input=0, winding_heat_input=0)
    zero_result = stream(case, zero, epoch, [0, probe], "zero-heat")[-1]
    zero_t = temperatures(zero_result)
    zero_metrics = temperature_rise_errors(
        operand(float(zero_t[1] - p["ambient_temperature"]), "RC_WINDING_RISE", ref),
        operand(0, "RC_WINDING_RISE", ref),
        near_zero_k=policy["relative_denominator_floor"],
        evidence_reference=ref,
    )
    missing = snapshot(case, p, epoch, probe, "missing-heat")
    simulation = dict(missing.simulation)
    del simulation["winding_heat_input"]
    missing_result = PhysicsEstimator().evaluate(replace(missing, simulation=simulation))
    slack = policy["sanity_temperature_tolerance"]
    monotonic = np.array(
        [[p["initial_oil_temperature"], p["initial_winding_temperature"]], *values]
    )
    checks = {
        "cold_start_unavailable": all(
            results[0]["components"][key]["status"] == "INITIALIZING"
            and results[0]["components"][key]["value"] is None
            for key in ("top_oil_temperature", "hot_spot_temperature")
        ),
        "analytic_temperatures": all(
            finite(e) and e <= policy["analytic_temperature_tolerance"] for e in errors
        ),
        "steady_endpoint": bool(
            np.max(np.abs(final - steady)) <= policy["steady_temperature_tolerance"]
        ),
        "monotonic_heating": bool(np.all(np.diff(monotonic, axis=0) >= -slack)),
        "more_heat_higher_temperature": bool(
            np.all(high_t >= final - slack) and np.any(high_t > final + slack)
        ),
        "stronger_transport_lower_temperature": bool(
            np.all(cooling_t <= final + slack) and np.any(cooling_t < final - slack)
        ),
        "zero_heat_equilibrium": bool(np.max(np.abs(zero_t - p["ambient_temperature"])) <= slack),
        "constant_forcing_subdivision": bool(np.max(np.abs(one_step - final)) <= slack),
        "capacitance_time_scaling": bool(np.max(np.abs(capacity_t - base_probe)) <= slack),
        "transient_energy_balance": energy_error <= policy["energy_balance_tolerance"],
        "steady_heat_balance": power_error <= policy["power_balance_tolerance"],
        "calculation_envelope": bool(
            np.all(monotonic >= p["minimum_temperature"])
            and np.all(monotonic <= p["maximum_temperature"])
        ),
        "missing_heat_unavailable": missing_result["components"]["hot_spot_temperature"]["value"]
        is None
        and missing_result["components"]["hot_spot_temperature"]["status"] != "READY",
        "near_zero_relative_unavailable": zero_metrics["relative_error"]["value"] is None
        and zero_metrics["relative_error"]["status"] == "INSUFFICIENT_DATA"
        and zero_metrics["absolute_error"]["value"] is not None,
        "controlled_proxy_labels": all(
            r["context"] == "CONTROLLED_SIMULATION"
            and r["lineage"]["input_verification"] == "SYNTHETIC"
            and r["components"]["hot_spot_temperature"]["result_kind"] == "CALCULATED_ESTIMATE"
            and any(
                w["code"] == "SIMPLIFIED_NODE_PROXY"
                for w in r["components"]["hot_spot_temperature"]["warnings"]
            )
            for r in results[1:]
        ),
    }
    return {
        "result_kind": "CALCULATED_ESTIMATE",
        "target": "IDEALIZED_UNIFORM_WINDING_NODE_PROXY",
        "status": "READY" if all(checks.values()) else "MODEL_ERROR",
        "checks": checks,
        "modal_times": {
            "slow": quantity(taus[0], "s", "duration"),
            "fast": quantity(taus[1], "s", "duration"),
        },
        "cold_start_envelope": results[0],
        "records": records,
        "maximum_absolute_error": quantity(max(errors), "K", "temperature_difference"),
        "energy_balance_time": quantity(t_energy, "s", "duration"),
        "energy_balance_error": quantity(energy_error, "J", "energy"),
        "steady_power_balance_error": quantity(power_error, "W", "heat_rate"),
        "subdivision_error": quantity(
            float(np.max(np.abs(one_step - final))), "K", "temperature_difference"
        ),
        "capacity_time_error": quantity(
            float(np.max(np.abs(capacity_t - base_probe))), "K", "temperature_difference"
        ),
        "zero_heat_metrics": zero_metrics,
        "missing_heat_envelope": missing_result,
    }


def _fem(case, policy, variations, n, quantity):
    fem_case = read_fem_case()
    if fem_case["case_id"] != case["fem_case_id"] or digest(fem_case) != case["fem_case_sha256"]:
        raise ValidationError(
            "REFERENCE_CHANGED", "Explicit approved FEM identity/digest required."
        )
    p, numerical, meshes = validate_fem_case(fem_case)
    if n not in meshes:
        raise ValidationError(
            "MESH_INVALID", "Sanity mesh must be in approved refinement sequence."
        )
    benchmark = run_reference(fem_case)
    _, _, source, boundary = manufactured_fields(p)
    mesh = rectangle_mesh(p["length_x"], p["length_y"], n, n)
    multiplier = variations["heat_multiplier"]

    def solve(k, thickness, forcing):
        return solve_steady(
            mesh,
            k,
            thickness,
            forcing,
            boundary,
            quadrature_order=numerical["quadrature_order"],
            residual_tolerance=numerical["residual_tolerance"],
        )

    base = solve(p["conductivity"], p["thickness"], source)
    hot = solve(p["conductivity"], p["thickness"], lambda points: multiplier * source(points))
    conductive = solve(multiplier * p["conductivity"], p["thickness"], source)
    thick = solve(p["conductivity"], multiplier * p["thickness"], source)
    zero = solve(p["conductivity"], p["thickness"], lambda points: np.zeros(points.shape[:-1]))
    rise = base.temperature_k - p["boundary_temperature"]
    deviations = {
        "source_scaling": float(
            np.max(np.abs(hot.temperature_k - p["boundary_temperature"] - multiplier * rise))
        ),
        "conductivity_scaling_fixed_source": float(
            np.max(np.abs(conductive.temperature_k - p["boundary_temperature"] - rise / multiplier))
        ),
        "thickness_temperature_invariance": float(
            np.max(np.abs(thick.temperature_k - base.temperature_k))
        ),
        "zero_heat_equilibrium": float(
            np.max(np.abs(zero.temperature_k - p["boundary_temperature"]))
        ),
    }
    slack = policy["sanity_temperature_tolerance"]
    checks = {key: value <= slack for key, value in deviations.items()}
    checks.update(
        {
            "approved_numerical_verification": benchmark["status"] == "READY"
            and all(benchmark["checks"].values()),
            "nonnegative_rise": bool(np.all(rise >= -slack)),
            "more_heat_higher_temperature": bool(
                np.all(hot.temperature_k >= base.temperature_k - slack)
                and np.max(hot.temperature_k) > np.max(base.temperature_k) + slack
            ),
            "stronger_conduction_lower_temperature": bool(
                np.all(conductive.temperature_k <= base.temperature_k + slack)
                and np.max(conductive.temperature_k) < np.max(base.temperature_k) - slack
            ),
            "discrete_balance": all(
                s.balance_error_w <= policy["fem_balance_tolerance"]
                for s in (base, hot, conductive, thick, zero)
            ),
            "thickness_power_scaling": abs(thick.source_power_w - multiplier * base.source_power_w)
            <= policy["fem_balance_tolerance"],
        }
    )
    maximum = benchmark["maximum_temperature"]["value"]
    rise_value = None if maximum is None else maximum - p["boundary_temperature"]
    numeric = operand(rise_value, "FEM_DOMAIN_MAXIMUM_RISE", case["evidence_reference"])
    numeric["status"] = benchmark["status"]
    metrics = temperature_rise_errors(
        numeric,
        operand(p["temperature_amplitude"], "FEM_DOMAIN_MAXIMUM_RISE", case["evidence_reference"]),
        near_zero_k=policy["relative_denominator_floor"],
        evidence_reference=case["evidence_reference"],
    )
    return {
        "result_kind": "SIMULATED_REFERENCE",
        "target": "SYNTHETIC_RECTANGLE_DOMAIN_MAXIMUM",
        "status": "READY" if all(checks.values()) else "MODEL_ERROR",
        "checks": checks,
        "benchmark": benchmark,
        "maximum_rise_metrics": metrics,
        "sanity_deviations": {
            key: quantity(value, "K", "temperature_difference", "SIMULATED_REFERENCE")
            for key, value in deviations.items()
        },
        "maximum_balance_error": quantity(
            max(s.balance_error_w for s in (base, hot, conductive, thick, zero)),
            "W",
            "heat_rate",
            "SIMULATED_REFERENCE",
        ),
        "transient_validation": {
            "status": "INVALID_CONFIGURATION",
            "value": None,
            "reasons": [
                {
                    "code": "NOT_APPLICABLE_STEADY_MODEL",
                    "message": "FEM has no storage, initial condition or transient solver.",
                }
            ],
        },
    }


def run_validation(case=None):
    """PASS refers only to independent checks; never enables blocked comparison."""
    case = copy.deepcopy(read_case() if case is None else case)
    p, policy, variations, times, epoch, n = validate_case(case)
    provenance = {
        "validation_id": case["validation_id"],
        "version": case["version"],
        "case_sha256": digest(case),
        "evidence_reference": case["evidence_reference"],
        "context": "CONTROLLED_SIMULATION",
        "origin_kind": "SIMULATED",
        "input_verification": "SYNTHETIC",
        "scope": "INDEPENDENT_NUMERICAL_VERIFICATION",
    }

    def quantity(value, unit, kind, result_kind="CALCULATED_ESTIMATE"):
        return {
            "value": value,
            "unit": unit,
            "quantity_kind": kind,
            "result_kind": result_kind,
            "provenance": provenance.copy(),
        }

    try:
        with np.errstate(over="raise", divide="raise", invalid="raise"):
            thermal = _thermal(case, p, policy, variations, times, epoch, quantity)
            fem = _fem(case, policy, variations, n, quantity)
    except (ArithmeticError, np.linalg.LinAlgError) as exc:
        raise ValidationError(
            "NUMERICAL_FAILURE", "Validation arithmetic failed.", "MODEL_ERROR"
        ) from exc
    except FEMError as exc:
        raise ValidationError(exc.code, str(exc), exc.status) from exc
    passed = thermal["status"] == fem["status"] == "READY"
    return {
        "artifact_version": "1.0.0",
        "suite_status": "PASS" if passed else "FAIL",
        "result_kind": "CALCULATED_ESTIMATE",
        **provenance,
        "case_definition": case,
        "dependency_versions": {"numpy": np.__version__, "scipy": scipy.__version__},
        "thermal": thermal,
        "fem": fem,
        "comparison": blocked_comparison(),
        "reasons": [
            {"code": "VERIFICATION_FAILED", "path": model + ".checks." + name}
            for model, report in (("thermal", thermal), ("fem", fem))
            for name, passed in report["checks"].items()
            if not passed
        ],
        "limitations": [
            "Synthetic independent numerical verification only.",
            "No common estimator/FEM target, calibration, field validation "
            "or transformer geometry.",
            "No operational hot-spot accuracy, ageing, RUL or standards compliance established.",
        ],
    }
