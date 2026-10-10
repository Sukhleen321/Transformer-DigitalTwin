"""P1 triangular FEM for -div(k grad(T)) = q''' with full Dirichlet data.

SI inputs are explicit; no physical constants, parameter defaults or telemetry
interpretation. Derivation and applicability: docs/fem_reference.md, F1--F4.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
from numpy.polynomial.legendre import leggauss
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import MatrixRankWarning, spsolve

MAX_SUBDIVISIONS = 128  # resource bound, not a physical resolution claim


class FEMError(ValueError):
    def __init__(self, code, message, status="INVALID_CONFIGURATION"):
        super().__init__(message)
        self.code = code
        self.status = status


def number(value, name, *, positive=False, nonnegative=False):
    if type(value) not in (int, float):
        raise FEMError("INVALID_NUMBER", f"{name} requires a finite numeric value.")
    try:
        value = float(value)
    except (OverflowError, ValueError) as exc:
        raise FEMError("INVALID_NUMBER", f"{name} requires a finite numeric value.") from exc
    if not np.isfinite(value):
        raise FEMError("INVALID_NUMBER", f"{name} requires a finite numeric value.")
    if (positive and value <= 0) or (nonnegative and value < 0):
        raise FEMError("OUT_OF_RANGE", f"{name} is outside its supported range.")
    return float(value)


def integer(value, name, lower, upper):
    if type(value) is not int or not lower <= value <= upper:
        raise FEMError("INVALID_INTEGER", f"{name} requires an integer in [{lower}, {upper}].")
    return value


def readonly(array):
    result = np.array(array, copy=True)
    result.flags.writeable = False
    return result


@dataclass(frozen=True)
class Mesh:
    coordinates_m: np.ndarray
    triangles: np.ndarray
    boundary_nodes: np.ndarray


@dataclass(frozen=True)
class Solution:
    mesh: Mesh
    temperature_k: np.ndarray
    gradient_k_m: np.ndarray
    source_power_w: float
    outward_reaction_power_w: float
    scaled_residual: float
    balance_error_w: float
    result_kind: str = field(default="SIMULATED_REFERENCE", init=False)
    origin_kind: str = field(default="SIMULATED", init=False)
    context: str = field(default="CONTROLLED_SIMULATION", init=False)


def rectangle_mesh(length_x_m, length_y_m, nx, ny):
    lx = number(length_x_m, "length_x_m", positive=True)
    ly = number(length_y_m, "length_y_m", positive=True)
    integer(nx, "nx", 2, MAX_SUBDIVISIONS)
    integer(ny, "ny", 2, MAX_SUBDIVISIONS)
    xx, yy = np.meshgrid(np.linspace(0, lx, nx + 1), np.linspace(0, ly, ny + 1))
    coordinates = np.column_stack((xx.ravel(), yy.ravel()))
    base = (np.arange(ny)[:, None] * (nx + 1) + np.arange(nx)).ravel()
    triangles = np.stack(
        (
            np.column_stack((base, base + 1, base + nx + 2)),
            np.column_stack((base, base + nx + 2, base + nx + 1)),
        ),
        axis=1,
    ).reshape(-1, 3)
    ids = np.arange(len(coordinates)).reshape(ny + 1, nx + 1)
    boundary = np.unique(np.concatenate((ids[0], ids[-1], ids[:, 0], ids[:, -1])))
    return Mesh(readonly(coordinates), readonly(triangles), readonly(boundary))


def element_geometry(mesh):
    vertices = mesh.coordinates_m[mesh.triangles]
    jacobian = np.stack((vertices[:, 1] - vertices[:, 0], vertices[:, 2] - vertices[:, 0]), axis=-1)
    det = np.linalg.det(jacobian)
    if not np.all(np.isfinite(det)) or np.any(det <= 0):
        raise FEMError(
            "INVALID_MESH", "Triangle areas must be finite, positive and counterclockwise."
        )
    gradients = np.array([[-1.0, -1.0], [1.0, 0.0], [0.0, 1.0]]) @ np.linalg.inv(jacobian)
    if not np.all(np.isfinite(gradients)):
        raise FEMError("INVALID_MESH", "Shape gradients must be finite.")
    return vertices, det / 2, gradients


def triangle_quadrature(order):
    integer(order, "quadrature_order", 2, 10)
    roots, weights = leggauss(order)
    nodes = (roots + 1) / 2
    weights = weights / 2
    u, v = np.meshgrid(nodes, nodes, indexing="ij")
    wu, wv = np.meshgrid(weights, weights, indexing="ij")
    r = u.ravel()
    s = ((1 - u) * v).ravel()
    shapes = np.column_stack((1 - r - s, r, s))
    reference_weights = (wu * wv * (1 - u)).ravel()
    return shapes, reference_weights


def sample_field(function, points, name, *, nonnegative=False):
    if not callable(function):
        raise FEMError("FIELD_MISSING", f"{name} requires an explicit function.")
    raw = np.asarray(function(points))
    if raw.shape != points.shape[:-1] or raw.dtype.kind not in "fiu":
        raise FEMError("INVALID_FIELD", f"{name} must return one numeric value per point.")
    values = raw.astype(float)
    if not np.all(np.isfinite(values)) or (nonnegative and np.any(values < 0)):
        raise FEMError(
            "INVALID_FIELD", f"{name} contains nonfinite or unsupported negative values."
        )
    return values


def assemble(mesh, conductivity_w_m_k, thickness_m, source_w_m3, quadrature_order):
    k = number(conductivity_w_m_k, "conductivity_w_m_k", positive=True)
    thickness = number(thickness_m, "thickness_m", positive=True)
    vertices, areas, gradients = element_geometry(mesh)
    shapes, weights = triangle_quadrature(quadrature_order)
    points = np.einsum("qi,eid->eqd", shapes, vertices)
    sources = sample_field(source_w_m3, points, "source_w_m3", nonnegative=True)
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        element_k = (
            k * thickness * areas[:, None, None] * (gradients @ gradients.transpose(0, 2, 1))
        )
        element_f = (
            2 * thickness * areas[:, None] * np.einsum("eq,q,qi->ei", sources, weights, shapes)
        )
    rows = np.repeat(mesh.triangles, 3, axis=1).ravel()
    cols = np.tile(mesh.triangles, (1, 3)).ravel()
    matrix = coo_matrix(
        (element_k.ravel(), (rows, cols)), shape=(len(mesh.coordinates_m),) * 2
    ).tocsr()
    load = np.zeros(len(mesh.coordinates_m))
    np.add.at(load, mesh.triangles.ravel(), element_f.ravel())
    if not np.all(np.isfinite(matrix.data)) or not np.all(np.isfinite(load)):
        raise FEMError("NUMERICAL_FAILURE", "Nonfinite assembly.", "MODEL_ERROR")
    return matrix, load


def solve_steady(
    mesh,
    conductivity_w_m_k,
    thickness_m,
    source_w_m3,
    boundary_temperature_k,
    *,
    quadrature_order,
    residual_tolerance,
):
    """Solve the explicit case; the caller owns numerical acceptance policies."""
    tolerance = number(residual_tolerance, "residual_tolerance", positive=True)
    try:
        matrix, load = assemble(
            mesh, conductivity_w_m_k, thickness_m, source_w_m3, quadrature_order
        )
        boundary = mesh.boundary_nodes
        boundary_values = sample_field(
            boundary_temperature_k,
            mesh.coordinates_m[boundary],
            "boundary_temperature_k",
            nonnegative=True,
        )
        free = np.setdiff1d(np.arange(len(load)), boundary)
        if not len(boundary) or not len(free):
            raise FEMError("INVALID_MESH", "Prescribed boundary and interior nodes are required.")
        anchor = boundary_values[0]
        theta = np.zeros(len(load))
        theta[boundary] = boundary_values - anchor
        ff = matrix[free][:, free].tocsc()
        rhs = load[free] - matrix[free][:, boundary] @ theta[boundary]
        with warnings.catch_warnings():
            warnings.simplefilter("error", MatrixRankWarning)
            theta[free] = spsolve(ff, rhs, permc_spec="COLAMD", use_umfpack=False)
        temperatures = theta + anchor
        if not np.all(np.isfinite(temperatures)) or np.any(temperatures < 0):
            raise FEMError("NUMERICAL_FAILURE", "Unsupported temperature solution.", "MODEL_ERROR")
        residual = ff @ theta[free] - rhs
        scale = np.max(np.asarray(abs(ff).sum(axis=1))) * np.max(np.abs(theta[free])) + np.max(
            np.abs(rhs)
        )
        scaled = (
            float(np.max(np.abs(residual)) / scale)
            if scale > 0
            else float(np.max(np.abs(residual)))
        )
        if not np.isfinite(scaled) or scaled > tolerance:
            raise FEMError(
                "RESIDUAL_FAILED", "Free-equation residual exceeds policy.", "MODEL_ERROR"
            )
        reactions = matrix @ theta - load
        source = float(np.sum(load))
        outward = -float(np.sum(reactions[boundary]))
        _, _, gradients = element_geometry(mesh)
        gradient = np.einsum("ei,eid->ed", theta[mesh.triangles], gradients)
        return Solution(
            mesh,
            readonly(temperatures),
            readonly(gradient),
            source,
            outward,
            scaled,
            abs(outward - source),
        )
    except FEMError:
        raise
    except (ArithmeticError, RuntimeError, MatrixRankWarning, np.linalg.LinAlgError) as exc:
        raise FEMError("NUMERICAL_FAILURE", "FEM assembly or solve failed.", "MODEL_ERROR") from exc


def error_norms(solution, exact_temperature_k, exact_gradient_k_m, quadrature_order):
    """Spatial error norms, independent of the solver's residual calculation."""
    vertices, areas, _ = element_geometry(solution.mesh)
    shapes, weights = triangle_quadrature(quadrature_order)
    points = np.einsum("qi,eid->eqd", shapes, vertices)
    exact = sample_field(exact_temperature_k, points, "exact_temperature_k", nonnegative=True)
    gradient = np.asarray(exact_gradient_k_m(points), dtype=float)
    if gradient.shape != points.shape or not np.all(np.isfinite(gradient)):
        raise FEMError("INVALID_FIELD", "Exact gradients require finite vectors per point.")
    approximate = np.einsum("qi,ei->eq", shapes, solution.temperature_k[solution.mesh.triangles])
    difference = approximate - exact
    gradient_difference = solution.gradient_k_m[:, None, :] - gradient
    l2 = np.sqrt(np.sum(2 * areas[:, None] * weights * difference**2))
    h1 = np.sqrt(np.sum(2 * areas[:, None] * weights * np.sum(gradient_difference**2, axis=-1)))
    return float(l2), float(h1)
