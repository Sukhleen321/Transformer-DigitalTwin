"""Sourced general heat balances; project approximations, never IEEE/IEC claims.

Eligibility is enforced by PhysicsEstimator, not these scalar numerical kernels.
See docs/physics_references.md for exact source locators and assumptions.
"""

from __future__ import annotations

import numpy as np
from scipy.linalg import expm

from .units import finite


def current_squared_loss(currents_a, rated_current_a, no_load_w, rated_load_w):
    currents = tuple(finite(value) for value in currents_a)
    rating, no_load, rated_load = map(finite, (rated_current_a, no_load_w, rated_load_w))
    if len(currents) != 3 or any(value < 0 for value in currents):
        raise ValueError("Three nonnegative RMS magnitudes are required.")
    if rating <= 0 or no_load < 0 or rated_load < 0:
        raise ValueError("Invalid reference loss parameters.")
    load = rated_load * sum((value / rating) ** 2 for value in currents) / 3
    return finite(no_load + load)


def two_node_rates(
    oil_k,
    winding_k,
    ambient_k,
    oil_heat_w,
    winding_heat_w,
    oil_resistance,
    winding_resistance,
    oil_capacitance,
    winding_capacitance,
):
    values = tuple(
        map(
            finite,
            (
                oil_k,
                winding_k,
                ambient_k,
                oil_heat_w,
                winding_heat_w,
                oil_resistance,
                winding_resistance,
                oil_capacitance,
                winding_capacitance,
            ),
        )
    )
    to, tw, ta, po, pw, ro, rw, co, cw = values
    if min(to, tw, ta) < 0 or min(po, pw) < 0 or min(ro, rw, co, cw) <= 0:
        raise ValueError("Unsupported thermal values.")
    winding_to_oil = (tw - to) / rw
    return (finite((po + winding_to_oil - (to - ta) / ro) / co), finite((pw - winding_to_oil) / cw))


def two_node_step(
    oil_k,
    winding_k,
    ambient_k,
    oil_heat_w,
    winding_heat_w,
    oil_resistance,
    winding_resistance,
    oil_capacitance,
    winding_capacitance,
    dt_seconds,
):
    two_node_rates(
        oil_k,
        winding_k,
        ambient_k,
        oil_heat_w,
        winding_heat_w,
        oil_resistance,
        winding_resistance,
        oil_capacitance,
        winding_capacitance,
    )
    dt = finite(dt_seconds)
    if dt <= 0:
        raise ValueError("Elapsed event time must be positive.")
    ro, rw, co, cw = map(
        finite, (oil_resistance, winding_resistance, oil_capacitance, winding_capacitance)
    )
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        matrix = np.array(
            [
                [-(1 / ro + 1 / rw) / co, 1 / (rw * co), (oil_heat_w + ambient_k / ro) / co],
                [1 / (rw * cw), -1 / (rw * cw), winding_heat_w / cw],
                [0, 0, 0],
            ]
        )
        result = expm(matrix * dt) @ np.array([oil_k, winding_k, 1])
    oil, winding = finite(result[0].item()), finite(result[1].item())
    if min(oil, winding) < 0:
        raise ValueError("Numerical temperature below absolute zero.")
    return oil, winding
