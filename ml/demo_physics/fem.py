"""Independent transient two-sheet P1 FEM; common target is an area mean."""

import numpy as np
from scipy.linalg import block_diag, eigh

from ml.fem.solver import element_geometry, rectangle_mesh, triangle_quadrature


def matrices(n):
    if type(n) is not int or not 2 <= n <= 16:
        raise ValueError("Demo dense FEM supports 2–16 subdivisions only")
    mesh = rectangle_mesh(0.5, 0.5, n, n)
    vertices, areas, gradients = element_geometry(mesh)
    count = len(mesh.coordinates_m)
    mass, stiffness = np.zeros((count, count)), np.zeros((count, count))
    source = np.zeros(count)
    shapes, weights = triangle_quadrature(4)
    for ids, points, area, grad in zip(mesh.triangles, vertices, areas, gradients, strict=True):
        mass[np.ix_(ids, ids)] += area / 12 * (np.ones((3, 3)) + np.eye(3))
        stiffness[np.ix_(ids, ids)] += area * grad @ grad.T
        xy = shapes @ points
        profile = 1 + 0.15 * np.cos(np.pi * xy[:, 0] / 0.5) * np.cos(np.pi * xy[:, 1] / 0.5)
        source[ids] += 2 * area * shapes.T @ (weights * profile)
    source /= source.sum()  # total heat is prescribed independently of mesh
    return mesh, mass, stiffness, source


class SheetFEM:
    def __init__(self, n=6):
        self.mesh, self.mass, stiffness, self.source = matrices(n)
        self.count = len(self.source)
        area = 0.25
        self.capacity = block_diag(80 / area * self.mass, 40 / area * self.mass)
        coupling, rejection = self.mass / (0.2 * area), self.mass / (0.35 * area)
        self.operator = np.block(
            [
                [0.04 * stiffness + coupling + rejection, -coupling],
                [-coupling, 0.04 * stiffness + coupling],
            ]
        )
        self.values, self.vectors = eigh(self.operator, self.capacity)
        self.mean_weights = self.mass @ np.ones(self.count) / area

    def step(self, fields, po, pw, dt, *, ambient_k=300):
        fields = np.asarray(fields, dtype=float)
        if (
            fields.shape != (2 * self.count,)
            or not np.all(np.isfinite(fields))
            or type(dt) not in (int, float)
            or not np.isfinite(dt)
            or dt <= 0
            or dt > 30
            or type(ambient_k) not in (int, float)
            or not np.isfinite(ambient_k)
            or not 250 <= ambient_k <= 400
            or any(
                type(v) not in (int, float) or not np.isfinite(v) or v < 0 or v > 100
                for v in (po, pw)
            )
        ):
            raise ValueError("Invalid demo FEM state/forcing/interval")
        forcing = np.r_[
            po * self.source + (ambient_k / (0.35 * 0.25)) * self.mass.sum(axis=1), pw * self.source
        ]
        modes = self.vectors.T @ (self.capacity @ fields)
        heat = self.vectors.T @ forcing
        decay = np.exp(-self.values * dt)
        result = self.vectors @ (decay * modes - np.expm1(-self.values * dt) / self.values * heat)
        if not np.all(np.isfinite(result)) or result.min() < 250 or result.max() > 400:
            raise ValueError("Demo FEM outside fictional envelope")
        return result

    def means(self, fields):
        return (
            float(self.mean_weights @ fields[: self.count]),
            float(self.mean_weights @ fields[self.count :]),
        )
