"""Independent numerical verification on fictional cases, never equipment data."""

from __future__ import annotations

import copy
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from ml.fem import FEMError, Mesh, rectangle_mesh, solve_steady
from ml.fem.__main__ import main
from ml.fem.benchmark import read_case, run_reference, validate_case
from ml.fem.solver import assemble, element_geometry, error_norms, triangle_quadrature

ROOT = Path(__file__).resolve().parents[2]


def constant(value):
    return lambda points: np.full(points.shape[:-1], value)


def solve(mesh, k, thickness, source, boundary):
    return solve_steady(
        mesh, k, thickness, source, boundary, quadrature_order=6, residual_tolerance=1e-10
    )


@pytest.fixture(scope="module")
def reference():
    return run_reference(read_case())


def test_element_matrix_load_and_energy_on_single_triangle():
    mesh = Mesh(np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]]), np.array([[0, 1, 2]]), np.arange(3))
    matrix, load = assemble(mesh, 2, 3, constant(12), 6)
    expected = np.array([[6.0, -3.0, -3.0], [-3.0, 3.0, 0.0], [-3.0, 0.0, 3.0]])
    np.testing.assert_allclose(matrix.toarray(), expected, atol=1e-14)
    np.testing.assert_allclose(load, [6, 6, 6], atol=1e-13)
    np.testing.assert_allclose(matrix @ np.ones(3), 0, atol=1e-14)
    temperature = np.array([300.0, 301.0, 302.0])
    assert temperature @ matrix @ temperature == pytest.approx(15)


def test_rectangle_mesh_geometry_orientation_and_resource_limit():
    mesh = rectangle_mesh(2, 3, 4, 6)
    _, areas, gradients = element_geometry(mesh)
    assert len(mesh.coordinates_m) == 35
    assert len(mesh.triangles) == 48
    assert len(mesh.boundary_nodes) == 20
    assert np.sum(areas) == pytest.approx(6)
    assert np.all(areas > 0)
    np.testing.assert_allclose(np.sum(gradients, axis=1), 0, atol=1e-14)
    with pytest.raises(ValueError):
        mesh.coordinates_m[0, 0] = 99
    with pytest.raises(FEMError, match="integer"):
        rectangle_mesh(1, 1, 129, 8)


@pytest.mark.parametrize("nx", [None, True, 1, 3.5, "8"])
def test_invalid_mesh_counts_are_not_converted(nx):
    with pytest.raises(FEMError):
        rectangle_mesh(1, 1, nx, 8)


@pytest.mark.parametrize("length", [None, True, 0, -1, "1", float("inf"), float("nan")])
def test_invalid_geometry_is_not_defaulted(length):
    with pytest.raises(FEMError):
        rectangle_mesh(length, 1, 8, 8)


def test_inverted_and_degenerate_triangles_rejected():
    mesh = rectangle_mesh(1, 1, 2, 2)
    for triangle in (np.array([[0, 4, 1]]), np.array([[0, 1, 2]])):
        with pytest.raises(FEMError) as caught:
            assemble(Mesh(mesh.coordinates_m, triangle, mesh.boundary_nodes), 1, 1, constant(1), 6)
        assert caught.value.code == "INVALID_MESH"


@pytest.mark.parametrize("powers", [(0, 0), (1, 0), (0, 1), (2, 3), (4, 4)])
def test_duffy_quadrature_against_exact_polynomial_integrals(powers):
    shapes, weights = triangle_quadrature(6)
    a, b = powers
    integral = np.sum(weights * shapes[:, 1] ** a * shapes[:, 2] ** b)
    exact = math.factorial(a) * math.factorial(b) / math.factorial(a + b + 2)
    assert integral == pytest.approx(exact, rel=2e-13, abs=1e-15)
    assert np.all(weights > 0)
    np.testing.assert_allclose(np.sum(shapes, axis=1), 1, atol=2e-16)


def test_affine_patch_nonconstant_dirichlet_and_gradient():
    mesh = rectangle_mesh(2, 3, 8, 12)

    def exact(points):
        return 300 + 3 * points[..., 0] - 2 * points[..., 1]

    def gradient(points):
        return np.broadcast_to([3.0, -2.0], points.shape)

    result = solve(mesh, 2.5, 0.7, constant(0), exact)
    np.testing.assert_allclose(result.temperature_k, exact(mesh.coordinates_m), atol=1e-11)
    l2, h1 = error_norms(result, exact, gradient, 6)
    assert l2 < 1e-11
    assert h1 < 1e-10
    assert result.source_power_w == 0
    assert result.balance_error_w < 1e-11
    assert result.result_kind == "SIMULATED_REFERENCE"
    assert result.context == "CONTROLLED_SIMULATION"


def test_quadratic_manufactured_solution_independent_of_sine_case():
    # Unequal lengths, nonunit k/thickness, positive uniform source and
    # nonconstant boundary values exercise independent assembly and lifting.
    lx, ly, amplitude, conductivity = 2.0, 3.0, 10.0, 3.0

    def exact(points):
        x, y = points[..., 0], points[..., 1]
        return 300 + amplitude * (x * (lx - x) / lx**2 + y * (ly - y) / ly**2)

    def gradient(points):
        return amplitude * np.stack(
            ((lx - 2 * points[..., 0]) / lx**2, (ly - 2 * points[..., 1]) / ly**2), axis=-1
        )

    source = constant(2 * conductivity * amplitude * (lx**-2 + ly**-2))
    errors = []
    for n in (4, 8, 16, 32):
        mesh = rectangle_mesh(lx, ly, n, n)
        result = solve(mesh, conductivity, 0.7, source, exact)
        np.testing.assert_allclose(
            result.temperature_k[mesh.boundary_nodes],
            exact(mesh.coordinates_m[mesh.boundary_nodes]),
            atol=1e-13,
        )
        l2, h1 = error_norms(result, exact, gradient, 6)
        # Sampling nodes alone can hide quadratic interpolation error.
        assert l2 > 1e-8
        assert result.source_power_w == pytest.approx(
            2 * conductivity * amplitude * (lx**-2 + ly**-2) * lx * ly * 0.7
        )
        assert result.balance_error_w < 1e-9
        errors.append((l2, h1))
    for coarse, fine in zip(errors[:-1], errors[1:], strict=True):
        assert math.log2(coarse[0] / fine[0]) > 1.8
        assert math.log2(coarse[1] / fine[1]) > 0.9


def test_declared_sine_verification_and_refinement_criteria(reference):
    assert reference["status"] == "READY"
    assert all(reference["checks"].values())
    rows = reference["mesh_records"]
    assert [row["elements"]["value"] for row in rows] == [128, 512, 2048, 8192]
    assert rows[-1]["l2_error"]["value"] < 0.005
    assert reference["maximum_error"]["value"] < 0.01
    assert reference["exact_maximum_temperature"]["value"] == 310
    assert reference["exact_power"]["value"] == 80
    assert reference["quadrature_l2_difference"]["value"] < 1e-8
    for order in reference["l2_orders"]:
        assert order["value"] >= 1.8
    for order in reference["h1_orders"]:
        assert order["value"] >= 0.9
    for row in rows:
        assert row["balance_error"]["value"] < 1e-8
        assert row["scaled_residual"]["value"] < 1e-10
        assert row["source_power"]["value"] == pytest.approx(80, abs=1e-6)


def test_frozen_regression_fixture_is_labelled_and_matches(reference):
    fixture = json.loads((ROOT / "tests/fixtures/fem/reference_v1.json").read_text())
    assert fixture["kind"] == "SYNTHETIC_NUMERICAL_REGRESSION"
    assert fixture["case_sha256"] == reference["provenance"]["case_sha256"]
    for expected, actual in zip(fixture["meshes"], reference["mesh_records"], strict=True):
        for key, value in expected.items():
            assert fixture["units"][key] == actual[key]["unit"]
            assert actual[key]["value"] == pytest.approx(value, rel=1e-8, abs=1e-11)


def test_all_artifact_quantities_have_units_and_reference_provenance(reference):
    assert reference["result_kind"] == "SIMULATED_REFERENCE"
    assert reference["origin_kind"] == "SIMULATED"
    assert reference["input_verification"] == "SYNTHETIC"
    assert reference["provenance"]["comparison_id"] is None
    assert reference["target_definition"] == "SYNTHETIC_RECTANGLE_DOMAIN_MAXIMUM"
    assert "fem_hot_spot_temperature" not in reference
    assert "hot_spot_difference" not in reference

    def visit(value):
        if isinstance(value, dict):
            if "value" in value:
                assert value["unit"] and value["quantity_kind"]
                if "verification" in value:  # echoed input policy quantities
                    assert value["verification"] == "SYNTHETIC"
                    assert value["evidence_reference"] == reference["provenance"]["case_id"]
                else:
                    assert value["provenance"]["case_id"] == reference["provenance"]["case_id"]
                    assert value["provenance"]["numerical_verification_reference"]
                    assert value["provenance"]["mesh_convergence_reference"]
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(reference)


def test_reference_repeat_is_deterministic_and_case_input_unchanged(reference):
    case = read_case()
    original = copy.deepcopy(case)
    again = run_reference(case)
    assert case == original
    assert json.dumps(again, sort_keys=True, allow_nan=False) == json.dumps(
        reference, sort_keys=True, allow_nan=False
    )


def test_zero_heat_heating_conductivity_and_thickness_scaling():
    mesh = rectangle_mesh(2, 1, 12, 8)
    boundary = constant(300)
    zero = solve(mesh, 2, 0.5, constant(0), boundary)
    a = solve(mesh, 2, 0.5, constant(100), boundary)
    b = solve(mesh, 2, 0.5, constant(200), boundary)
    c = solve(mesh, 4, 0.5, constant(100), boundary)
    d = solve(mesh, 2, 1, constant(100), boundary)
    np.testing.assert_allclose(zero.temperature_k, 300, atol=1e-13)
    assert np.min(a.temperature_k) >= 300
    assert np.max(a.temperature_k) > 300
    np.testing.assert_allclose(b.temperature_k - 300, 2 * (a.temperature_k - 300), atol=1e-12)
    np.testing.assert_allclose(c.temperature_k - 300, (a.temperature_k - 300) / 2, atol=1e-12)
    np.testing.assert_allclose(d.temperature_k, a.temperature_k, atol=1e-12)
    assert d.source_power_w == pytest.approx(2 * a.source_power_w)
    assert a.outward_reaction_power_w == pytest.approx(a.source_power_w, abs=1e-10)
    with pytest.raises(ValueError):
        a.temperature_k[0] = 0


@pytest.mark.parametrize("value", [None, True, 0, -1, "1", float("nan"), float("inf")])
def test_missing_invalid_material_properties_are_not_defaulted(value):
    mesh = rectangle_mesh(1, 1, 4, 4)
    with pytest.raises(FEMError):
        solve(mesh, value, 1, constant(1), constant(300))
    with pytest.raises(FEMError):
        solve(mesh, 1, value, constant(1), constant(300))


@pytest.mark.parametrize(
    "field", [None, constant(True), constant(-1), constant(float("nan")), lambda points: 0]
)
def test_invalid_source_is_not_zero_filled(field):
    with pytest.raises(FEMError):
        solve(rectangle_mesh(1, 1, 4, 4), 1, 1, field, constant(300))


@pytest.mark.parametrize(
    "field", [None, constant(True), constant(-1), constant(float("inf")), lambda points: "300"]
)
def test_invalid_boundary_is_not_replaced(field):
    with pytest.raises(FEMError):
        solve(rectangle_mesh(1, 1, 4, 4), 1, 1, constant(1), field)


@pytest.mark.parametrize(
    "path,value",
    [
        (("parameters", "conductivity", "unit"), "SOURCE_UNIT"),
        (("parameters", "conductivity", "verification"), "VERIFIED"),
        (("parameters", "conductivity", "evidence_reference"), "OEM_UNKNOWN"),
        (("parameters", "conductivity", "value"), None),
        (("parameters", "boundary_temperature", "value"), -1),
        (("context",), "OPERATIONAL"),
        (("material",), "REAL_TRANSFORMER_COPPER"),
        (("initial_condition",), "AMBIENT_DEFAULT"),
        (("evidence", "reference"), ""),
        (("numerical_policy", "quadrature_order", "value"), True),
        (("numerical_policy", "check_quadrature_order", "value"), 6),
        (("numerical_policy", "subdivisions", 0, "value"), 0),
    ],
)
def test_case_units_evidence_scope_and_numerical_inputs_are_required(path, value):
    case = read_case()
    target = case
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(FEMError) as caught:
        run_reference(case)
    assert caught.value.status == "INVALID_CONFIGURATION"


def test_missing_policy_unknown_case_fields_and_nonrefining_meshes():
    for fault in ("parameter", "policy", "unknown", "mesh"):
        case = read_case()
        if fault == "parameter":
            del case["parameters"]["conductivity"]
        if fault == "policy":
            del case["numerical_policy"]["balance_tolerance"]
        if fault == "unknown":
            case["inferred_rating"] = 100
        if fault == "mesh":
            case["numerical_policy"]["subdivisions"][1]["value"] = 8
        with pytest.raises(FEMError):
            validate_case(case)


def test_failed_convergence_does_not_publish_ready_reference():
    case = read_case()
    case["numerical_policy"]["minimum_l2_order"]["value"] = 3
    result = run_reference(case)
    assert result["status"] == "MODEL_ERROR"
    assert result["maximum_temperature"]["value"] is None
    assert not result["checks"]["l2_orders"]
    assert result["reasons"]


@pytest.mark.parametrize("fault", ["wrong_solution", "nonfinite", "factorization_failure"])
def test_solver_failure_or_bad_residual_is_explicit(monkeypatch, fault):
    def failed(matrix, rhs, **kwargs):
        if fault == "factorization_failure":
            raise RuntimeError("private solver details")
        return np.zeros(len(rhs)) if fault == "wrong_solution" else np.full(len(rhs), float("nan"))

    monkeypatch.setattr("ml.fem.solver.spsolve", failed)
    with pytest.raises(FEMError) as caught:
        solve(rectangle_mesh(1, 1, 4, 4), 1, 1, constant(10), constant(300))
    assert caught.value.status == "MODEL_ERROR"
    assert "private" not in str(caught.value)


@pytest.mark.parametrize("text", ['{"case_id":"a","case_id":"b"}', '{"value":NaN}', "not json"])
def test_strict_json_rejects_duplicates_nonfinite_and_invalid_text(tmp_path, text):
    path = tmp_path / "case.json"
    path.write_text(text)
    with pytest.raises(FEMError):
        read_case(path)


def test_cli_invalid_case_returns_unavailable_json(tmp_path, capsys):
    assert main(["--case", str(tmp_path / "absent.json")]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "INVALID_CONFIGURATION"
    assert result["maximum_temperature"]["value"] is None
    assert result["result_kind"] == "SIMULATED_REFERENCE"


def test_reproducible_module_command_and_no_estimator_import(reference):
    process = subprocess.run(
        [sys.executable, "-c", "import sys; import ml.fem; assert 'ml.physics' not in sys.modules"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0, process.stderr
    process = subprocess.run(
        [sys.executable, "-m", "ml.fem"], cwd=ROOT, capture_output=True, text=True
    )
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout) == reference


def test_declared_case_has_traceable_fictional_parameters():
    case = read_case()
    assert case["evidence"]["kind"] == "SYNTHETIC_CASE"
    assert (ROOT / case["evidence"]["reference"].split("#")[0]).exists()
    assert set(case["parameters"]) == {
        "length_x",
        "length_y",
        "thickness",
        "conductivity",
        "boundary_temperature",
        "temperature_amplitude",
    }
    assert "density" not in case["parameters"]
    assert "specific_heat" not in case["parameters"]


@pytest.mark.parametrize("amplitude", [1e-250, 1e308])
def test_extreme_finite_case_cannot_publish_zero_error_as_success(amplitude):
    case = read_case()
    case["parameters"]["temperature_amplitude"]["value"] = amplitude
    with pytest.raises(FEMError) as caught:
        run_reference(case)
    assert caught.value.status == "MODEL_ERROR"


def test_integer_overflow_is_invalid_input_and_result_policy_is_a_snapshot(reference):
    case = read_case()
    case["parameters"]["conductivity"]["value"] = 10**1000
    with pytest.raises(FEMError) as caught:
        validate_case(case)
    assert caught.value.status == "INVALID_CONFIGURATION"
    case = read_case()
    # A failed-criterion run still snapshots policy before publishing diagnostics.
    case["numerical_policy"]["minimum_l2_order"]["value"] = 3
    result = run_reference(case)
    case["numerical_policy"]["minimum_l2_order"]["value"] = 1
    assert result["solver"]["policy"]["minimum_l2_order"]["value"] == 3
