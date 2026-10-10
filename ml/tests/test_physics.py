"""Phase 2 numerical/contract checks with declared fictional parameters only.

No fixture represents equipment, calibrated coefficients, sensors or FEM.
"""

from __future__ import annotations

import copy
import json
import math
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from scipy.integrate import solve_ivp

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
from ml.physics.equations import current_squared_loss, two_node_rates, two_node_step
from ml.physics.estimator import MODEL_ID, REGISTRY_VERSION, THERMAL
from ml.physics.types import InputIssue
from ml.physics.units import RULES, convert_value, normalize

ROOT = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 10, 10, tzinfo=timezone.utc)
SCHEMA = json.loads(
    (ROOT / "docs/contracts/physics-result-v1.schema.json").read_text(), parse_float=Decimal
)
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def q(value, unit, kind, *, at=T0, case="case-a", semantics=None, bounds=None):
    return Quantity(
        value,
        unit,
        kind,
        "SYNTHETIC",
        Provenance(
            case, case, "fictional controlled regression case", unit, value, semantics=semantics
        ),
        at,
        bounds,
    )


def sample(seconds=0, *, case="case-a", seed_time=T0, history=0):
    event = T0 + timedelta(seconds=seconds)
    policy = Policy(
        q(60, "s", "duration", case=case),
        q(100, "s", "duration", case=case),
        q(history, "s", "duration", case=case),
        "EXPLICIT_INITIAL_TEMPERATURES",
        case,
        case,
        "PREVIOUS_SAMPLE_HOLD",
        case,
    )
    parameters = {
        "oil_thermal_resistance": q(1, "K/W", "thermal_resistance", case=case, bounds=(0.01, 100)),
        "winding_thermal_resistance": q(
            1, "K/W", "thermal_resistance", case=case, bounds=(0.01, 100)
        ),
        "oil_thermal_capacitance": q(
            1, "J/K", "thermal_capacitance", case=case, bounds=(0.01, 100)
        ),
        "winding_thermal_capacitance": q(
            1, "J/K", "thermal_capacitance", case=case, bounds=(0.01, 100)
        ),
        "minimum_temperature": q(100, "K", "absolute_temperature", case=case),
        "maximum_temperature": q(1000, "K", "absolute_temperature", case=case),
        "no_load_loss": q(10, "W", "active_power", case=case),
        "rated_load_loss": q(30, "W", "active_power", case=case),
        "loss_reference_temperature": q(300, "K", "absolute_temperature", case=case),
    }
    return Snapshot(
        "fixture-" + case,
        event,
        event,
        event,
        "CONTROLLED_SIMULATION",
        Lineage(
            "SIMULATED",
            "SIMULATED",
            "SYNTHETIC",
            case + "/event/" + str(seconds),
            evidence_references=(case,),
            timezone_status="DECLARED_UTC",
            case_id=case,
        ),
        Versions(
            "1.0.0", case + "/params-v1", case + "/config-v1", case + "/map-v1", REGISTRY_VERSION
        ),
        ModelSelection(MODEL_ID, True, "LV", "RMS_LINE_CURRENT", case, True),
        policy,
        {
            case: Evidence(
                "Fictional test case",
                "ml/tests/test_physics.py::sample",
                "fictional controlled regression case",
                "SYNTHETIC_CASE",
            )
        },
        observed={
            f"current_l{i}": q(
                10,
                "A",
                "current",
                at=event,
                case=case,
                semantics="RMS_LINE_CURRENT_LV",
                bounds=(0, 100),
            )
            for i in (1, 2, 3)
        },
        equipment={"rated_current_a": q(10, "A", "current", case=case)},
        model_parameters=parameters,
        environment={
            "ambient_temperature": q(
                300, "K", "absolute_temperature", at=event, case=case, bounds=(100, 1000)
            )
        },
        simulation={
            "oil_heat_input": q(10, "W", "heat_rate", at=event, case=case, bounds=(0, 1000)),
            "winding_heat_input": q(20, "W", "heat_rate", at=event, case=case, bounds=(0, 1000)),
            "initial_oil_temperature": q(300, "K", "absolute_temperature", at=seed_time, case=case),
            "initial_winding_temperature": q(
                300, "K", "absolute_temperature", at=seed_time, case=case
            ),
        },
    )


def changed(snapshot, group, key, value):
    values = dict(getattr(snapshot, group))
    if value is None:
        values.pop(key, None)
    else:
        values[key] = value
    return replace(snapshot, **{group: values})


def check(result):
    VALIDATOR.validate(result)
    json.dumps(result, allow_nan=False)
    for value in result["components"].values():
        assert (value["value"] is not None) == (value["status"] == "READY")
        if value["value"] is not None:
            assert math.isfinite(value["value"])
    return result


def reasons(result, name="hot_spot_temperature"):
    return {entry["code"] for entry in result["components"][name]["reasons"]}


def test_production_conversions_match_every_contract_vector_and_inverse():
    registry = json.loads((ROOT / "docs/contracts/physics-units-v1.json").read_text())
    cases = json.loads((ROOT / "tests/fixtures/physics/cases.json").read_text())
    rules = {entry["id"]: entry for entry in registry["rules"]}
    assert {value[0] for value in RULES.values()} == set(rules)
    for vector in cases["conversion_vectors"]:
        rule = rules[vector["rule"]]
        actual = convert_value(
            Decimal(vector["source"]),
            rule["source_unit"],
            rule["target_unit"],
            rule["quantity_kind"],
        )
        assert actual == float(vector["expected"])
        inverse = convert_value(
            actual, rule["target_unit"], rule["source_unit"], rule["quantity_kind"]
        )
        assert inverse == pytest.approx(float(vector["source"]), abs=1e-12)
    assert convert_value(10, "DEG_C", "K", "temperature_difference") == 10
    assert convert_value(0, "DEG_C", "K", "absolute_temperature") == 273.15


@pytest.mark.parametrize("value", [None, True, "10", float("nan"), float("inf"), -273.16])
def test_invalid_temperature_conversion(value):
    with pytest.raises(InputIssue):
        convert_value(value, "DEG_C", "K", "absolute_temperature")


@pytest.mark.parametrize(
    "source,target,kind",
    [
        ("SOURCE_UNIT", "K", "absolute_temperature"),
        ("STATUS", "K", "absolute_temperature"),
        ("V", "K", "absolute_temperature"),
        ("W", "VA", "apparent_power"),
        ("kV", "V", "voltage"),
        ("A", "A", "active_power"),
    ],
)
def test_unsupported_semantic_conversions(source, target, kind):
    with pytest.raises(InputIssue):
        convert_value(10, source, target, kind)


def test_source_conversion_and_range_are_preserved():
    record = q(20, "DEG_C", "absolute_temperature", bounds=(-20, 50))
    normal = normalize(record, "K", "absolute_temperature")
    assert normal.value == 293.15
    assert normal.valid_range == (253.15, 323.15)
    assert normal.provenance.original_value == 20
    assert normal.provenance.original_unit == "DEG_C"
    assert normal.provenance.conversion_id == "absolute_deg_c_to_k"
    assert normalize(normal, "K", "absolute_temperature") == normal  # no double offset
    with pytest.raises(InputIssue, match="outside"):
        normalize(replace(record, value=60), "K", "absolute_temperature")
    with pytest.raises(InputIssue, match="disagrees"):
        normalize(replace(record, value=21), "K", "absolute_temperature")


def test_loss_analytical_balanced_unbalanced_zero_and_missing():
    assert current_squared_loss((10, 10, 10), 10, 10, 30) == 40
    assert current_squared_loss((0, 10, 20), 10, 10, 30) == 60
    assert current_squared_loss((0, 0, 0), 10, 10, 30) == 10
    for currents in ((None, 10, 10), (-1, 10, 10), (True, 10, 10), (10, 10)):
        with pytest.raises(ValueError):
            current_squared_loss(currents, 10, 10, 30)


def test_two_node_steady_state_and_storage_balance():
    # P_total=30 W, R_o=1 K/W => oil=330 K; winding adds P_w*R_w=20 K.
    assert two_node_rates(330, 350, 300, 10, 20, 1, 1, 1, 1) == (0, 0)
    assert two_node_step(330, 350, 300, 10, 20, 1, 1, 1, 1, 70) == pytest.approx((330, 350))
    oil_rate, winding_rate = two_node_rates(310, 315, 300, 10, 20, 1, 2, 5, 3)
    assert 5 * oil_rate + 3 * winding_rate == pytest.approx(30 - 10)
    assert two_node_step(300, 300, 300, 10, 20, 1, 1, 1, 1, 100) == pytest.approx((330, 350))


def test_exact_flow_against_independent_adaptive_ode_solver():
    # Independent integration of two separate energy balances, not expm.
    def derivative(t, temperatures):
        oil, winding = temperatures
        transfer = (winding - oil) / 2
        return [(11 + transfer - (oil - 290) / 3) / 5, (17 - transfer) / 7]

    reference = solve_ivp(derivative, (0, 23.7), (310, 320), rtol=1e-11, atol=1e-11)
    actual = two_node_step(310, 320, 290, 11, 17, 3, 2, 5, 7, 23.7)
    assert actual == pytest.approx(reference.y[:, -1], abs=2e-9)


def test_physical_heating_cooling_and_higher_cooling_conductance():
    previous = (300, 300)
    for seconds in (0.1, 1, 5, 30):
        result = two_node_step(300, 300, 300, 10, 20, 1, 1, 1, 1, seconds)
        assert all(a >= b for a, b in zip(result, previous, strict=True))
        previous = result
    cooling = two_node_step(350, 350, 300, 0, 0, 1, 1, 1, 1, 10)
    assert all(300 <= value < 350 for value in cooling)
    assert two_node_step(300, 300, 300, 0, 0, 1, 1, 1, 1, 100) == pytest.approx((300, 300))
    hotter = two_node_step(300, 300, 300, 20, 40, 1, 1, 1, 1, 10)
    cooler = two_node_step(300, 300, 300, 10, 20, 0.5, 1, 1, 1, 10)
    base = two_node_step(300, 300, 300, 10, 20, 1, 1, 1, 1, 10)
    assert all(a >= b for a, b in zip(hotter, base, strict=True))
    assert all(a <= b for a, b in zip(cooler, base, strict=True))


@pytest.mark.parametrize("dt", [0, -1, True, float("nan")])
def test_nonpositive_invalid_timesteps(dt):
    with pytest.raises(ValueError):
        two_node_step(300, 300, 300, 10, 20, 1, 1, 1, 1, dt)


def test_initialization_warmup_and_contract_schema():
    estimator = PhysicsEstimator()
    first = check(estimator.evaluate(sample(history=10)))
    assert first["components"]["hot_spot_temperature"]["status"] == "INITIALIZING"
    assert "COLD_START" in reasons(first)
    assert first["components"]["measured_oil_temperature"]["value"] is None
    assert first["components"]["total_loss"]["value"] == 40
    warm = check(estimator.evaluate(sample(3, history=10)))
    assert "HISTORY_WARMUP" in reasons(warm)
    ready = check(estimator.evaluate(sample(10, history=10)))
    assert ready["components"]["hot_spot_temperature"]["status"] == "READY"
    assert ready["components"]["hot_spot_temperature"]["result_kind"] == "CALCULATED_ESTIMATE"
    assert ready["components"]["hot_spot_temperature"]["coverage"]["covered_seconds"] == 10
    assert (
        ready["components"]["hot_spot_temperature"]["warnings"][0]["code"]
        == "SIMPLIFIED_NODE_PROXY"
    )
    for name in (
        "ageing_acceleration_factor",
        "equivalent_ageing_hours",
        "fem_hot_spot_temperature",
        "hot_spot_difference",
    ):
        assert ready["components"][name]["value"] is None


def test_irregular_subdivided_stream_is_deterministic():
    estimators = [PhysicsEstimator(), PhysicsEstimator(), PhysicsEstimator()]
    for estimator, sequence in zip(
        estimators, ([0, 0.1, 3, 20], [0, 20], [0, 0.1, 3, 20]), strict=True
    ):
        for time in sequence:
            check(estimator.evaluate(sample(time)))
    first, second, repeated = [item.state("fixture-case-a") for item in estimators]
    assert (first.oil_k, first.winding_k) == pytest.approx(
        (second.oil_k, second.winding_k), abs=1e-10
    )
    assert first == repeated


def test_current_forcing_is_causal_and_initial_values_are_not_reassimilated():
    a, b = PhysicsEstimator(), PhysicsEstimator()
    a.evaluate(sample())
    b.evaluate(sample())
    altered = changed(
        sample(10),
        "simulation",
        "winding_heat_input",
        q(100, "W", "heat_rate", at=T0 + timedelta(seconds=10), bounds=(0, 1000)),
    )
    altered = changed(
        altered, "simulation", "initial_winding_temperature", q(700, "K", "absolute_temperature")
    )
    ra, rb = check(a.evaluate(sample(10))), check(b.evaluate(altered))
    assert (
        ra["components"]["hot_spot_temperature"]["value"]
        == rb["components"]["hot_spot_temperature"]["value"]
    )
    ra, rb = check(a.evaluate(sample(20))), check(b.evaluate(sample(20)))
    assert (
        rb["components"]["hot_spot_temperature"]["value"]
        > ra["components"]["hot_spot_temperature"]["value"]
    )


def test_exact_retry_equal_time_conflict_and_late_data_do_not_advance_state():
    estimator = PhysicsEstimator()
    initial = sample()
    result = check(estimator.evaluate(initial))
    state = estimator.state(initial.transformer_id)
    assert check(estimator.evaluate(initial)) == result
    assert estimator.state(initial.transformer_id) is state
    check(estimator.evaluate(sample(10)))
    state = estimator.state(initial.transformer_id)
    check(estimator.evaluate(sample(5)))
    assert estimator.state(initial.transformer_id) is state
    conflict = changed(
        sample(10),
        "simulation",
        "oil_heat_input",
        q(20, "W", "heat_rate", at=T0 + timedelta(seconds=10), bounds=(0, 1000)),
    )
    result = check(estimator.evaluate(conflict))
    assert "SEMANTIC_CONFLICT" in reasons(result)
    assert estimator.state(initial.transformer_id) is state


def test_gap_resets_and_requires_new_explicit_initial_conditions():
    estimator = PhysicsEstimator()
    estimator.evaluate(sample())
    reset = check(estimator.evaluate(sample(101)))
    assert "INITIAL_STATE_TIME_MISMATCH" in reasons(reset)
    assert estimator.state("fixture-case-a") is None
    seeded = check(estimator.evaluate(sample(102, seed_time=T0 + timedelta(seconds=102))))
    assert seeded["components"]["hot_spot_temperature"]["status"] == "INITIALIZING"
    assert estimator.state("fixture-case-a").started_at == T0 + timedelta(seconds=102)
    estimator = PhysicsEstimator()
    estimator.evaluate(sample())
    reset = check(estimator.evaluate(sample(101, seed_time=T0 + timedelta(seconds=101))))
    assert "GAP_RESET" in reasons(reset)
    assert reset["components"]["hot_spot_temperature"]["coverage"]["gap_count"] == 1


def test_gap_limit_and_stale_limit_are_inclusive():
    estimator = PhysicsEstimator()
    estimator.evaluate(sample())
    event = sample(100)
    event = replace(event, evaluation_time=event.timestamp + timedelta(seconds=60))
    assert (
        check(estimator.evaluate(event))["components"]["hot_spot_temperature"]["status"] == "READY"
    )


@pytest.mark.parametrize(
    "fault",
    [
        "missing_heat",
        "invalid_heat",
        "unknown_unit",
        "unverified",
        "missing_evidence",
        "bad_target_time",
        "stale",
        "future",
        "naive",
        "missing_event",
    ],
)
def test_bad_data_is_unavailable_and_breaks_continuity(fault):
    estimator = PhysicsEstimator()
    estimator.evaluate(sample())
    event = sample(10)
    heat = event.simulation["oil_heat_input"]
    if fault == "missing_heat":
        event = changed(event, "simulation", "oil_heat_input", None)
    if fault == "invalid_heat":
        event = changed(event, "simulation", "oil_heat_input", replace(heat, value=float("nan")))
    if fault == "unknown_unit":
        event = changed(event, "simulation", "oil_heat_input", replace(heat, unit="SOURCE_UNIT"))
    if fault == "unverified":
        event = changed(
            event, "simulation", "oil_heat_input", replace(heat, verification="UNVERIFIED")
        )
    if fault == "missing_evidence":
        event = replace(event, evidence={})
    if fault == "bad_target_time":
        event = changed(event, "simulation", "oil_heat_input", replace(heat, effective_at=T0))
    if fault == "stale":
        event = replace(event, evaluation_time=event.timestamp + timedelta(seconds=61))
    if fault == "future":
        event = replace(event, evaluation_time=event.timestamp - timedelta(seconds=1))
    if fault == "naive":
        event = replace(event, timestamp=event.timestamp.replace(tzinfo=None))
    if fault == "missing_event":
        event = replace(event, timestamp=None)
    result = check(estimator.evaluate(event))
    assert result["components"]["hot_spot_temperature"]["value"] is None
    assert result["components"]["hot_spot_temperature"]["status"] in (
        "INSUFFICIENT_DATA",
        "INVALID_CONFIGURATION",
    )
    assert estimator.state(event.transformer_id) is None


@pytest.mark.parametrize("evaluation_time", [None, T0.replace(tzinfo=None)])
def test_invalid_evaluation_time_preserves_event_identity_but_breaks_continuity(evaluation_time):
    estimator = PhysicsEstimator()
    estimator.evaluate(sample())
    event = replace(sample(10), evaluation_time=evaluation_time)
    result = check(estimator.evaluate(event))
    thermal = result["components"]["hot_spot_temperature"]
    assert result["timestamp"] == "2026-10-10T00:00:10Z"
    assert thermal["status"] == "INSUFFICIENT_DATA"
    assert thermal["value"] is None
    assert any("evaluation_time" in reason["paths"] for reason in thermal["reasons"])
    assert estimator.state(event.transformer_id) is None


@pytest.mark.parametrize("value", [None, 0, -1, True, "1", float("inf")])
def test_missing_invalid_parameters_never_get_defaults(value):
    event = sample()
    parameter = event.model_parameters["oil_thermal_resistance"]
    event = changed(
        event, "model_parameters", "oil_thermal_resistance", replace(parameter, value=value)
    )
    result = check(PhysicsEstimator().evaluate(event))
    assert result["components"]["hot_spot_temperature"]["status"] == "INVALID_CONFIGURATION"


@pytest.mark.parametrize("model", ["IEC_60076_7_2018", "IEEE_C57_91_2025", None, "UNKNOWN"])
def test_unverified_or_unselected_models_are_unavailable(model):
    event = sample()
    event = replace(event, selection=replace(event.selection, thermal_model_id=model))
    result = check(PhysicsEstimator().evaluate(event))
    assert result["components"]["hot_spot_temperature"]["status"] == "INVALID_CONFIGURATION"
    assert result["components"]["hot_spot_temperature"]["value"] is None
    assert (
        "EQUATION_UNVERIFIED" in reasons(result)
        if model in ("IEC_60076_7_2018", "IEEE_C57_91_2025")
        else "MODEL_NOT_CONFIGURED" in reasons(result)
    )


def test_no_operational_temperature_from_synthetic_or_unvalidated_model():
    event = replace(sample(), context="OPERATIONAL")
    result = check(PhysicsEstimator().evaluate(event))
    assert "MODEL_NOT_VALIDATED_FOR_EQUIPMENT" in reasons(result)
    assert "SYNTHETIC_NOT_OPERATIONAL" in reasons(result)
    assert all(value["value"] is None for value in result["components"].values())


def test_partial_measured_output_requires_real_origin_sensor_evidence():
    event = sample()
    evidence = Evidence(
        "Hypothetical sensor record",
        "fixture-only sensor document",
        "hypothetical fixture equipment",
        "SENSOR_RECORD",
    )
    record = Quantity(
        40,
        "DEG_C",
        "absolute_temperature",
        "VERIFIED",
        Provenance(
            "sensor", "fixture-sensor", evidence.applicability, "DEG_C", 40, semantics="OIL_SENSOR"
        ),
        T0,
        (-20, 100),
    )

    def verified(item):
        return replace(
            item,
            verification="VERIFIED",
            provenance=replace(
                item.provenance,
                evidence_reference="sensor",
                source_id="fixture-sensor",
                applicability=evidence.applicability,
            ),
        )

    policy = replace(
        event.policy,
        max_sample_age_seconds=verified(event.policy.max_sample_age_seconds),
        max_gap_seconds=verified(event.policy.max_gap_seconds),
        required_history_seconds=verified(event.policy.required_history_seconds),
        initialization_reference="sensor",
        range_policy_reference="sensor",
        forcing_reference="sensor",
    )
    event = replace(
        event,
        context="OPERATIONAL",
        lineage=Lineage(
            "LIVE",
            "LIVE",
            "VERIFIED",
            "fixture-observation",
            evidence_references=("sensor",),
            timezone_status="VERIFIED",
        ),
        policy=policy,
        observed={"oil_temperature": record},
        selection=ModelSelection(),
        model_parameters={},
        equipment={},
        environment={},
        simulation={},
        evidence={"sensor": evidence},
    )
    result = check(PhysicsEstimator().evaluate(event))
    assert result["components"]["measured_oil_temperature"]["value"] == pytest.approx(40)
    assert all(result["components"][name]["value"] is None for name in THERMAL)
    event = changed(event, "observed", "oil_temperature", replace(record, unit="SOURCE_UNIT"))
    assert (
        check(PhysicsEstimator().evaluate(event))["components"]["measured_oil_temperature"]["value"]
        is None
    )


def test_configuration_change_resets_and_same_version_mutation_is_rejected():
    estimator = PhysicsEstimator()
    estimator.evaluate(sample())
    event = sample(10, seed_time=T0 + timedelta(seconds=10))
    parameter = event.model_parameters["oil_thermal_resistance"]
    event = changed(
        event,
        "model_parameters",
        "oil_thermal_resistance",
        replace(parameter, value=2, provenance=replace(parameter.provenance, original_value=2)),
    )
    result = check(estimator.evaluate(event))
    assert "VERSION_CONTENT_CHANGED" in reasons(result)
    assert estimator.state(event.transformer_id) is None
    estimator = PhysicsEstimator()
    estimator.evaluate(sample())
    event = replace(event, versions=replace(event.versions, parameter_version="case-a/params-v2"))
    result = check(estimator.evaluate(event))
    assert "CONFIGURATION_RESET" in reasons(result)
    assert result["components"]["hot_spot_temperature"]["value"] is None


def test_parameter_id_cannot_be_changed_by_only_bumping_configuration_id():
    estimator = PhysicsEstimator()
    estimator.evaluate(sample())
    event = sample(10)
    original = event.model_parameters["oil_thermal_resistance"]
    event = changed(
        event,
        "model_parameters",
        "oil_thermal_resistance",
        replace(original, value=2, provenance=replace(original.provenance, original_value=2)),
    )
    event = replace(
        event, versions=replace(event.versions, configuration_version="case-a/config-v2")
    )
    result = check(estimator.evaluate(event))
    assert "VERSION_CONTENT_CHANGED" in reasons(result)


def test_reused_evidence_id_cannot_change_content():
    estimator = PhysicsEstimator()
    estimator.evaluate(sample())
    event = sample(10)
    event = replace(
        event, evidence={"case-a": replace(event.evidence["case-a"], locator="changed")}
    )
    result = check(estimator.evaluate(event))
    assert "EVIDENCE_CONTENT_CHANGED" in reasons(result)


def test_missing_policy_initial_state_bad_ranges_and_unsupported_uncertainty():
    no_policy = check(PhysicsEstimator().evaluate(replace(sample(), policy=None)))
    assert "POLICY_MISSING" in reasons(no_policy)
    no_seed = changed(sample(), "simulation", "initial_oil_temperature", None)
    result = check(PhysicsEstimator().evaluate(no_seed))
    assert result["components"]["hot_spot_temperature"]["status"] == "INITIALIZING"
    assert "INITIAL_STATE_REQUIRED" in reasons(result)
    base = sample()
    record = base.model_parameters["oil_thermal_resistance"]
    for value in (
        replace(record, valid_range=(5, 1)),
        replace(record, valid_range=None),
        replace(record, uncertainty={"value": 0.1, "unit": "K/W"}),
        replace(record, effective_at=None),
    ):
        result = check(
            PhysicsEstimator().evaluate(
                changed(base, "model_parameters", "oil_thermal_resistance", value)
            )
        )
        assert result["components"]["hot_spot_temperature"]["status"] == "INVALID_CONFIGURATION"


def test_result_uses_utc_and_replay_physical_time_not_wall_clock():
    estimator = PhysicsEstimator()
    event = sample()
    offset = timezone(timedelta(hours=5, minutes=30))
    event = replace(
        event,
        timestamp=event.timestamp.astimezone(offset),
        evaluated_at=event.evaluated_at.astimezone(offset),
    )
    check(estimator.evaluate(event))
    replay = sample(10)
    replay = replace(
        replay,
        evaluated_at=T0 + timedelta(days=30),
        lineage=replace(
            replay.lineage,
            source_kind="REPLAYED",
            origin_transformer_id="fixture-original",
            replay_run_id="fixture-replay",
        ),
    )
    result = check(estimator.evaluate(replay))
    assert result["timestamp"] == "2026-10-10T00:00:10Z"
    assert result["components"]["hot_spot_temperature"]["coverage"]["covered_seconds"] == 10


def test_numeric_overflow_or_model_envelope_violation_is_unavailable():
    estimator = PhysicsEstimator()
    estimator.evaluate(sample())
    event = sample(10)
    # Declared case temperature envelope is valid but excludes the evolved state.
    upper = event.model_parameters["maximum_temperature"]
    event = changed(
        event,
        "model_parameters",
        "maximum_temperature",
        replace(upper, value=301, provenance=replace(upper.provenance, original_value=301)),
    )
    event = replace(event, versions=replace(event.versions, parameter_version="narrow-range-v2"))
    # Reset with explicit conditions, then evaluate a valid time interval.
    event = changed(
        event,
        "simulation",
        "initial_oil_temperature",
        replace(event.simulation["initial_oil_temperature"], effective_at=event.timestamp),
    )
    event = changed(
        event,
        "simulation",
        "initial_winding_temperature",
        replace(event.simulation["initial_winding_temperature"], effective_at=event.timestamp),
    )
    check(estimator.evaluate(event))
    later = replace(
        event,
        timestamp=T0 + timedelta(seconds=20),
        evaluated_at=T0 + timedelta(seconds=20),
        evaluation_time=T0 + timedelta(seconds=20),
        environment={
            key: replace(value, effective_at=T0 + timedelta(seconds=20))
            for key, value in event.environment.items()
        },
        simulation={
            key: replace(value, effective_at=T0 + timedelta(seconds=20))
            if key.endswith("heat_input")
            else value
            for key, value in event.simulation.items()
        },
        observed={
            key: replace(value, effective_at=T0 + timedelta(seconds=20))
            for key, value in event.observed.items()
        },
    )
    result = check(estimator.evaluate(later))
    assert result["components"]["hot_spot_temperature"]["status"] == "MODEL_ERROR"


def test_zero_currents_and_missing_currents_are_distinct_loss_results():
    event = sample()
    zero = replace(
        event,
        observed={
            key: replace(value, value=0, provenance=replace(value.provenance, original_value=0))
            for key, value in event.observed.items()
        },
    )
    assert check(PhysicsEstimator().evaluate(zero))["components"]["total_loss"]["value"] == 10
    missing = changed(event, "observed", "current_l1", None)
    result = check(PhysicsEstimator().evaluate(missing))
    assert result["components"]["total_loss"]["value"] is None
    assert result["components"]["total_loss"]["status"] == "INSUFFICIENT_DATA"


def test_assets_do_not_share_state():
    estimator = PhysicsEstimator()
    estimator.evaluate(sample(case="a"))
    estimator.evaluate(sample(case="b"))
    check(estimator.evaluate(sample(10, case="a")))
    assert estimator.state("fixture-b").timestamp == T0
    assert estimator.state("fixture-a").timestamp == T0 + timedelta(seconds=10)


def test_numerical_failure_is_not_last_ready_value(monkeypatch):
    estimator = PhysicsEstimator()
    estimator.evaluate(sample())
    estimator.evaluate(sample(10))

    def fail(*args):
        raise FloatingPointError("internal diagnostic should not leak")

    monkeypatch.setattr("ml.physics.estimator.two_node_step", fail)
    result = check(estimator.evaluate(sample(20)))
    assert result["components"]["hot_spot_temperature"]["status"] == "MODEL_ERROR"
    assert result["components"]["hot_spot_temperature"]["value"] is None
    assert estimator.state("fixture-case-a") is None
    assert "internal diagnostic" not in str(result)


def test_snapshots_results_and_state_do_not_share_mutable_data():
    event = sample()
    with pytest.raises(TypeError):
        event.model_parameters["oil_thermal_resistance"] = None
    estimator = PhysicsEstimator()
    estimator.evaluate(event)
    result = estimator.evaluate(sample(10))
    untouched = copy.deepcopy(result)
    result["components"]["hot_spot_temperature"]["value"] = -999
    assert estimator.evaluate(sample(10)) == untouched
