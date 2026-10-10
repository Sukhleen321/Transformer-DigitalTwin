"""Synthetic numerical verification, never equipment validation."""

import math
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from scipy.linalg import eigh

from ml.demo_physics.fem import SheetFEM, matrices
from ml.demo_physics.scenario import DemoRun, acceleration, snapshot
from ml.fem.solver import element_geometry, triangle_quadrature
from ml.physics import PhysicsEstimator

EPOCH = datetime(2026, 10, 11, tzinfo=UTC)


def test_initialization_and_live_irregular_history():
    run = DemoRun("DEMO-A", EPOCH, "a" * 32)
    first = run.advance(EPOCH)
    assert first["status"] == "INITIALIZING"
    assert first["components"]["hot_spot_temperature"]["value"] is None
    results = [run.advance(EPOCH + timedelta(seconds=t)) for t in (1.1, 5.7, 9.9, 15, 25, 40, 60)]
    assert all(r["status"] == "READY" for r in results)
    assert all(len(r["components"]) == 10 for r in results)
    assert all(
        c["provenance"] == "SYNTHETIC_SIMULATED" for r in results for c in r["components"].values()
    )
    assert len({r["inputs"]["current_a"] for r in results}) == len(results)
    assert len({r["components"]["hot_spot_temperature"]["value"] for r in results}) == len(results)
    assert all(abs(r["components"]["hot_spot_difference"]["value"]) < 1e-8 for r in results)
    assert all(
        r["components"]["hot_spot_temperature"]["value"]
        >= r["components"]["top_oil_temperature"]["value"]
        for r in results
    )
    hours = [r["components"]["equivalent_ageing_hours"]["value"] for r in results]
    assert hours == sorted(hours) and hours[0] > 0
    result = results[-1]
    assert result["components"]["top_oil_rise"]["value"] == pytest.approx(
        result["components"]["top_oil_temperature"]["value"] - 26.85
    )
    assert result["components"]["total_loss"]["value"] == pytest.approx(
        6 + result["inputs"]["winding_heat_w"]
    )


def test_illustrative_ageing_formula_and_interval():
    assert acceleration(310) == 1
    assert acceleration(330) == pytest.approx(math.e)
    run = DemoRun("DEMO-A", EPOCH, "a" * 32)
    a, b = run.advance(EPOCH), run.advance(EPOCH + timedelta(seconds=4))
    fa, fb = (r["components"]["ageing_acceleration_factor"]["value"] for r in (a, b))
    assert b["components"]["equivalent_ageing_hours"]["value"] == pytest.approx(
        (fa + fb) * 4 / 7200
    )


@pytest.mark.parametrize("value", [None, True, float("nan"), float("inf"), 249, 401])
def test_invalid_ageing_temperature(value):
    with pytest.raises(ValueError):
        acceleration(value)


@pytest.mark.parametrize("seconds", [0, -1, 31])
def test_non_forward_or_gap_rejected(seconds):
    run = DemoRun("DEMO-A", EPOCH, "a" * 32)
    run.advance(EPOCH)
    with pytest.raises(ValueError):
        run.advance(EPOCH + timedelta(seconds=seconds))


def test_production_eligibility_not_bypassed():
    base = snapshot("DEMO-A", EPOCH, EPOCH)
    missing = replace(base, model_parameters={})
    result = PhysicsEstimator().evaluate(missing)
    assert result["components"]["hot_spot_temperature"]["value"] is None
    assert result["components"]["measured_oil_temperature"]["value"] is None
    assert result["components"]["ageing_acceleration_factor"]["value"] is None
    assert result["components"]["fem_hot_spot_temperature"]["value"] is None
    wrong = replace(base, context="OPERATIONAL")
    assert PhysicsEstimator().evaluate(wrong)["components"]["hot_spot_temperature"]["value"] is None


def test_fem_constant_patch_source_conservation_and_spatial_field():
    fem = SheetFEM()
    assert fem.source.sum() == pytest.approx(1, abs=1e-12)
    fields = np.full(2 * fem.count, 300.0)
    assert np.max(np.abs(fem.step(fields, 0, 0, 4) - fields)) < 1e-9
    heated = fem.step(fields, 6, 9.075, 4)
    assert np.ptp(heated[fem.count :]) > 0.005
    assert heated.min() >= 300


@pytest.mark.parametrize(
    "po,pw,dt", [(True, 1, 4), (1, float("nan"), 4), (1, 1, True), (1, 1, 0), (1, 1, 31)]
)
def test_fem_invalid_forcing_or_time(po, pw, dt):
    fem = SheetFEM(2)
    with pytest.raises(ValueError):
        fem.step(np.full(2 * fem.count, 300), po, pw, dt)


def test_fem_mesh_memory_bound():
    with pytest.raises(ValueError):
        SheetFEM(32)


def test_deterministic_thermal_regression():
    run = DemoRun("DEMO-A", EPOCH, "a" * 32)
    run.advance(EPOCH)
    values = run.advance(EPOCH + timedelta(seconds=4))["components"]
    assert values["top_oil_temperature"]["value"] == pytest.approx(27.1882274502334, abs=1e-10)
    assert values["hot_spot_temperature"]["value"] == pytest.approx(27.6342047381362, abs=1e-10)
    assert values["total_loss"]["value"] == pytest.approx(16.78802729718155, abs=1e-10)


def test_raw_operating_stream_reproducible_and_sensor_lag():
    a, b = (DemoRun("DEMO-A", EPOCH, "a" * 32) for _ in range(2))
    raws = []
    for seconds in (0, 1.1, 5.7, 9.9):
        event = EPOCH + timedelta(seconds=seconds)
        raw_a, raw_b = a.generate(event), b.generate(event)
        assert raw_a == raw_b
        previous = a.estimator.state(a.asset)
        old_sensor = a.sensor_k
        r = a.advance(event, raw_a)
        assert r == b.advance(event, raw_b)
        assert raw_a["provenance"] == "SYNTHETIC_SIMULATED"
        assert raw_a["values"]["ambient_k"] == {"value": 300.0, "unit": "K"}
        assert 0.3 <= raw_a["values"]["load_fraction"]["value"] <= 0.8
        if previous:
            dt = (event - previous.timestamp).total_seconds()
            assert raw_a["values"]["oil_sensor_k"]["value"] == pytest.approx(
                previous.oil_k + (old_sensor - previous.oil_k) * math.exp(-dt / 5)
            )
        assert r["components"]["measured_oil_temperature"]["value"] == pytest.approx(
            raw_a["values"]["oil_sensor_k"]["value"] - 273.15
        )
        raws.append(raw_a)
    assert len({r["event_id"] for r in raws}) == len(raws)
    assert raws[-1]["values"]["oil_sensor_k"]["value"] > 300
    reset = DemoRun("DEMO-A", EPOCH, "b" * 32)
    assert reset.generate(EPOCH)["event_id"] != raws[0]["event_id"]
    assert reset.advance(EPOCH)["status"] == "INITIALIZING"


@pytest.mark.parametrize(
    "flaw",
    [
        "missing",
        "extra",
        "null",
        "bool",
        "nan",
        "inf",
        "unit",
        "range",
        "loss",
        "rating",
        "ambient",
        "asset",
        "time",
        "sequence",
        "source",
        "provenance",
    ],
)
def test_invalid_raw_inputs_rejected_before_advancing_state(flaw):
    run = DemoRun("DEMO-A", EPOCH, "a" * 32)
    run.advance(EPOCH)
    event = EPOCH + timedelta(seconds=4)
    raw = run.generate(event)
    values = raw["values"]
    if flaw == "missing":
        del values["current_a"]
    elif flaw == "extra":
        values["guessed"] = {"value": 0, "unit": "K"}
    elif flaw in ("null", "bool", "nan", "inf", "range"):
        values["current_a"]["value"] = {
            "null": None,
            "bool": True,
            "nan": float("nan"),
            "inf": float("inf"),
            "range": -1,
        }[flaw]
    elif flaw == "unit":
        values["oil_sensor_k"]["unit"] = "DEG_C"
    elif flaw == "loss":
        values["winding_heat_w"]["value"] += 1
    elif flaw == "rating":
        values["load_fraction"]["value"] = 0
    elif flaw == "ambient":
        values["ambient_k"]["value"] = 301
    else:
        key = {"asset": "transformer_id", "time": "timestamp"}.get(flaw, flaw)
        raw[key] = "MEASURED" if flaw == "provenance" else "wrong"
    with pytest.raises(ValueError):
        run.advance(event, raw)
    assert run.sequence == 1
    assert run.estimator.state(run.asset).timestamp == EPOCH


def test_estimator_uses_raw_current_with_supported_loss_partition():
    run = DemoRun("DEMO-A", EPOCH, "a" * 32)
    run.advance(EPOCH)
    event = EPOCH + timedelta(seconds=4)
    raw = run.generate(event)
    raw["values"]["current_a"]["value"] = 3
    raw["values"]["load_fraction"]["value"] = 0.3
    raw["values"]["winding_heat_w"]["value"] = 2.7
    result = run.advance(event, raw)
    assert result["inputs"]["current_a"] == 3
    assert result["components"]["total_loss"]["value"] == pytest.approx(8.7)
    assert run.estimator.state(run.asset).winding_heat_w == pytest.approx(2.7)


def cosine_error(n):
    mesh, mass, stiffness, _ = matrices(n)
    xy = mesh.coordinates_m
    initial = np.cos(2 * np.pi * xy[:, 0]) * np.cos(2 * np.pi * xy[:, 1])
    values, vectors = eigh(stiffness, mass)
    diffusivity, t = 0.01, 0.7
    field = vectors @ (np.exp(-diffusivity * values * t) * (vectors.T @ mass @ initial))
    shapes, weights = triangle_quadrature(6)
    vertices, areas, _ = element_geometry(mesh)
    error = 0.0
    for ids, points, area in zip(mesh.triangles, vertices, areas, strict=True):
        locations = shapes @ points
        exact = (
            np.cos(2 * np.pi * locations[:, 0])
            * np.cos(2 * np.pi * locations[:, 1])
            * np.exp(-0.01 * 8 * np.pi**2 * t)
        )
        error += float(2 * area * weights @ ((shapes @ field[ids] - exact) ** 2))
    return math.sqrt(error / 0.25)


def test_independent_insulated_cosine_mesh_convergence():
    errors = [cosine_error(n) for n in (4, 8, 16)]
    orders = [math.log(a / b, 2) for a, b in zip(errors[:-1], errors[1:], strict=True)]
    print("Cosine FEM RMS K errors:", errors, "orders:", orders)
    assert errors[0] > errors[1] > errors[2]
    assert orders[-1] > 1.5
