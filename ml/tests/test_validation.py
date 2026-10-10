"""Independent synthetic validation, metric gates and negative-path regression."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator, FormatChecker

from ml.validation import run_validation
from ml.validation.cases import ValidationError, read_case, validate_case
from ml.validation.harness import modal_reference
from ml.validation.metrics import blocked_comparison, operand, temperature_rise_errors

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = "docs/validation_reference.md"


@pytest.fixture(scope="module")
def artifact():
    return run_validation()


def metric(a, b, floor=0.001):
    return temperature_rise_errors(
        operand(a, "same-rise", REFERENCE),
        operand(b, "same-rise", REFERENCE),
        near_zero_k=floor,
        evidence_reference=REFERENCE,
    )


def test_default_independent_suite_and_unavailable_capabilities(artifact):
    assert artifact["suite_status"] == "PASS"
    assert artifact["context"] == "CONTROLLED_SIMULATION"
    assert artifact["input_verification"] == "SYNTHETIC"
    assert artifact["origin_kind"] == "SIMULATED"
    assert artifact["thermal"]["result_kind"] == "CALCULATED_ESTIMATE"
    assert artifact["fem"]["result_kind"] == "SIMULATED_REFERENCE"
    assert all(artifact["thermal"]["checks"].values())
    assert all(artifact["fem"]["checks"].values())
    assert artifact["fem"]["transient_validation"]["value"] is None
    assert artifact["fem"]["transient_validation"]["status"] != "READY"
    for key in ("hot_spot_difference", "absolute_error", "relative_error"):
        component = artifact["comparison"][key]
        assert component["value"] is None
        assert component["status"] == "INVALID_CONFIGURATION"
        assert component["reasons"][0]["code"] == "INCOMPATIBLE_COMPARISON"
    json.dumps(artifact, allow_nan=False)


def test_real_estimator_envelopes_and_blocked_component_match_frozen_schema(artifact):
    schema = json.loads((ROOT / "docs/contracts/physics-result-v1.schema.json").read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    thermal = artifact["thermal"]
    for envelope in [
        thermal["cold_start_envelope"],
        thermal["missing_heat_envelope"],
        *(row["estimator_envelope"] for row in thermal["records"]),
    ]:
        validator.validate(envelope)
        assert envelope["components"]["fem_hot_spot_temperature"]["value"] is None
        assert envelope["components"]["hot_spot_difference"]["value"] is None
        assert envelope["components"]["ageing_acceleration_factor"]["value"] is None
        assert envelope["components"]["equivalent_ageing_hours"]["value"] is None
    envelope = copy.deepcopy(thermal["records"][-1]["estimator_envelope"])
    envelope["components"]["hot_spot_difference"] = blocked_comparison()["hot_spot_difference"]
    validator.validate(envelope)


def test_modal_reference_initial_derivative_steady_and_modes():
    p = validate_case(read_case())[0]
    initial, steady, energy, taus = modal_reference(p, 0)
    np.testing.assert_allclose(initial, [300, 300], atol=1e-12, rtol=0)
    np.testing.assert_allclose(steady, [330, 350], atol=0, rtol=0)
    assert abs(energy) < 1e-12
    assert taus[0] + taus[1] == pytest.approx(3)
    assert taus[0] * taus[1] == pytest.approx(1)
    tiny = modal_reference(p, 1e-5)[0]
    np.testing.assert_allclose((tiny - initial) / 1e-5, [10, 20], atol=2e-4, rtol=0)
    np.testing.assert_allclose(modal_reference(p, 100)[0], steady, atol=1e-12, rtol=0)


def test_numeric_regression_fixture(artifact):
    fixture = json.loads((ROOT / "tests/fixtures/validation/reference_v1.json").read_text())
    assert fixture["scope"] == "SYNTHETIC_NUMERICAL_REGRESSION"
    assert artifact["case_sha256"] == fixture["case_sha256"]
    for row, expected in zip(
        artifact["thermal"]["records"], fixture["thermal_records"], strict=True
    ):
        assert row["elapsed_time"]["value"] == expected["elapsed_seconds"]
        for i, key in enumerate(("top_oil_temperature", "hot_spot_temperature")):
            actual = row["estimator_envelope"]["components"][key]["value"] + 273.15
            assert actual == pytest.approx(expected["temperature_k"][i], abs=1e-8, rel=0)
    assert artifact["fem"]["benchmark"]["maximum_temperature"]["value"] == pytest.approx(
        fixture["fem_maximum_k"], abs=1e-8, rel=0
    )
    assert artifact["fem"]["maximum_rise_metrics"]["relative_error"]["value"] == pytest.approx(
        fixture["fem_maximum_rise_relative_error"], abs=1e-9, rel=0
    )


def test_signed_absolute_and_relative_rise_metrics():
    result = metric(8, 10)
    assert result["signed_error"]["value"] == -2
    assert result["absolute_error"]["value"] == 2
    assert result["relative_error"]["value"] == 0.2
    assert metric(-8, -10)["relative_error"]["value"] == 0.2
    assert result["relative_error"]["unit"] == "1"


@pytest.mark.parametrize("reference", [0, 0.0001, 0.001, -0.001])
def test_near_zero_relative_unavailable_absolute_valid(reference):
    result = metric(reference + 0.1, reference)
    assert result["absolute_error"]["status"] == "READY"
    assert result["relative_error"]["value"] is None
    assert result["relative_error"]["status"] == "INSUFFICIENT_DATA"
    assert result["relative_error"]["reasons"][0]["code"] == "NEAR_ZERO_REFERENCE"


@pytest.mark.parametrize("value", [None, True, "10", float("nan"), float("inf"), 10**1000])
def test_invalid_numeric_operands_never_zero(value):
    result = metric(value, 10)
    assert all(c["value"] is None and c["status"] == "INSUFFICIENT_DATA" for c in result.values())


@pytest.mark.parametrize(
    "field,value",
    [
        ("unit", "DEG_C"),
        ("unit", None),
        ("quantity_kind", "absolute_temperature"),
        ("context", "OPERATIONAL"),
        ("verification", "UNVERIFIED"),
        ("evidence_reference", None),
        ("evidence_reference", True),
        ("target_id", "other-target"),
        ("target_id", 123),
    ],
)
def test_incompatible_or_unsourced_operands_unavailable(field, value):
    a, b = operand(8, "target", REFERENCE), operand(10, "target", REFERENCE)
    a[field] = value
    result = temperature_rise_errors(a, b, near_zero_k=0.001, evidence_reference=REFERENCE)
    assert all(
        c["value"] is None and c["status"] == "INVALID_CONFIGURATION" for c in result.values()
    )


@pytest.mark.parametrize("floor", [None, 0, -1, True, float("nan"), 10**1000])
def test_missing_or_invalid_metric_floor_unavailable(floor):
    assert metric(8, 10, floor)["absolute_error"]["value"] is None


def test_unavailable_status_and_arithmetic_overflow():
    a, b = operand(8, "target", REFERENCE), operand(10, "target", REFERENCE)
    a["status"] = "INITIALIZING"
    result = temperature_rise_errors(a, b, near_zero_k=0.001, evidence_reference=REFERENCE)
    assert result["absolute_error"]["value"] is None
    overflow = metric(1e308, -1e308)
    assert all(c["status"] == "MODEL_ERROR" and c["value"] is None for c in overflow.values())
    relative_overflow = metric(1e308, 1e-100, floor=1e-101)
    assert relative_overflow["absolute_error"]["value"] == 1e308
    assert relative_overflow["relative_error"]["value"] is None
    assert relative_overflow["relative_error"]["status"] == "MODEL_ERROR"


@pytest.mark.parametrize(
    "key", ["thermal_parameters", "policy", "epoch", "sample_times", "fem_case_sha256"]
)
def test_missing_manifest_fields_are_not_defaults(key):
    case = read_case()
    del case[key]
    with pytest.raises(ValidationError, match="All explicit"):
        run_validation(case)


@pytest.mark.parametrize(
    "mutation",
    [
        "physical-missing",
        "unit-missing",
        "unverified",
        "range-missing",
        "gap",
        "seed",
        "epoch",
        "unknown",
    ],
)
def test_manifest_rejections(mutation):
    case = read_case()
    if mutation == "physical-missing":
        del case["thermal_parameters"]["oil_heat_input"]
    elif mutation == "unit-missing":
        case["thermal_parameters"]["oil_heat_input"]["unit"] = None
    elif mutation == "unverified":
        case["thermal_parameters"]["oil_heat_input"]["verification"] = "UNVERIFIED"
    elif mutation == "range-missing":
        case["thermal_parameters"]["oil_heat_input"]["valid_range"] = None
    elif mutation == "gap":
        case["sample_times"][-1]["value"] = 101
    elif mutation == "seed":
        case["thermal_parameters"]["initial_oil_temperature"]["value"] = 301
    elif mutation == "epoch":
        case["epoch"] = "2026-10-10T00:00:00"
    else:
        case["transformer_geometry"] = "invented"
    with pytest.raises(ValidationError):
        run_validation(case)


@pytest.mark.parametrize("raw", ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', "{"])
def test_json_rejections(tmp_path, raw):
    path = tmp_path / "case.json"
    path.write_text(raw)
    with pytest.raises(ValidationError):
        read_case(path)


def test_failed_sanity_check_retains_diagnostics(monkeypatch):
    from ml.validation import harness

    original = harness.PhysicsEstimator.evaluate

    def colder_high_heat(self, snapshot):
        result = original(self, snapshot)
        if snapshot.transformer_id == "validation-high-heat":
            for key in ("top_oil_temperature", "hot_spot_temperature"):
                component = result["components"][key]
                if component["value"] is not None:
                    component["value"] -= 200
        return result

    monkeypatch.setattr(harness.PhysicsEstimator, "evaluate", colder_high_heat)
    result = run_validation()
    assert result["suite_status"] == "FAIL"
    assert not result["thermal"]["checks"]["more_heat_higher_temperature"]
    assert result["thermal"]["records"]
    assert result["reasons"]
    assert result["comparison"]["absolute_error"]["value"] is None


def test_unavailable_estimator_cannot_pass(monkeypatch):
    from ml.validation import harness

    original = harness.PhysicsEstimator.evaluate

    def unavailable(self, snapshot):
        result = original(self, snapshot)
        result["components"]["top_oil_temperature"].update(value=None, status="MODEL_ERROR")
        return result

    monkeypatch.setattr(harness.PhysicsEstimator, "evaluate", unavailable)
    with pytest.raises(ValidationError) as error:
        run_validation()
    assert error.value.status == "MODEL_ERROR"


def test_failed_fem_verification_retains_diagnostics_and_withholds_metrics(monkeypatch):
    from ml.validation import harness

    original = harness.run_reference

    def failed_reference(case):
        result = original(case)
        result["checks"]["final_l2"] = False
        result["status"] = "MODEL_ERROR"
        result["maximum_temperature"]["value"] = None
        return result

    monkeypatch.setattr(harness, "run_reference", failed_reference)
    result = run_validation()
    assert result["suite_status"] == "FAIL"
    assert result["fem"]["benchmark"]["mesh_records"]
    assert not result["fem"]["checks"]["approved_numerical_verification"]
    assert all(c["value"] is None for c in result["fem"]["maximum_rise_metrics"].values())
    assert result["comparison"]["relative_error"]["value"] is None


def test_case_not_modified_and_approved_fem_digest_gate():
    case = read_case()
    before = copy.deepcopy(case)
    run_validation(case)
    assert case == before
    case["fem_case_sha256"] = "0" * 64
    with pytest.raises(ValidationError) as error:
        run_validation(case)
    assert error.value.code == "REFERENCE_CHANGED"


def test_cli_deterministic_and_nonzero_for_bad_case(tmp_path):
    command = [sys.executable, "-m", "ml.validation"]
    first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    assert json.loads(first.stdout)["suite_status"] == "PASS"
    missing = subprocess.run(
        [*command, "--case", str(tmp_path / "missing.json")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing.returncode == 1
    result = json.loads(missing.stdout)
    assert result["value"] is None and result["suite_status"] == "FAIL"
    case = read_case()
    case["policy"]["analytic_temperature_tolerance"]["value"] = 1e-20
    path = tmp_path / "too-strict.json"
    path.write_text(json.dumps(case))
    failed = subprocess.run(
        [*command, "--case", str(path)], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert failed.returncode == 1
    result = json.loads(failed.stdout)
    assert result["suite_status"] == "FAIL"
    assert not result["thermal"]["checks"]["analytic_temperatures"]
    assert result["thermal"]["records"]
