"""Within-model temperature-rise errors and the current blocked comparison.

No operands from different model families are passed to the error function.
See docs/validation_reference.md for target and near-zero policies.
"""

from __future__ import annotations

import copy
import math

from .cases import finite


def operand(value, target, reference):
    return {
        "value": value,
        "unit": "K",
        "quantity_kind": "temperature_difference",
        "target_id": target,
        "status": "READY",
        "context": "CONTROLLED_SIMULATION",
        "verification": "SYNTHETIC",
        "evidence_reference": reference,
    }


def temperature_rise_errors(numerical, analytical, *, near_zero_k, evidence_reference):
    """Explicit matched-target K rises; unavailable relative denominator stays null."""
    reasons = []
    status = "READY"
    for value in (numerical, analytical):
        if (
            not isinstance(value, dict)
            or value.get("unit") != "K"
            or value.get("quantity_kind") != "temperature_difference"
        ):
            status = "INVALID_CONFIGURATION"
            reasons.append(
                {
                    "code": "UNSUPPORTED_UNIT",
                    "message": "Explicit K temperature rises required.",
                    "paths": ["operands"],
                }
            )
            continue
        if (
            value.get("context") != "CONTROLLED_SIMULATION"
            or value.get("verification") != "SYNTHETIC"
            or not isinstance(value.get("evidence_reference"), str)
            or not value["evidence_reference"].strip()
        ):
            status = "INVALID_CONFIGURATION"
            reasons.append(
                {
                    "code": "PROVENANCE_REQUIRED",
                    "message": "Sourced controlled-case operands required.",
                    "paths": ["operands"],
                }
            )
        if value.get("status") != "READY" or not finite(value.get("value")):
            if status != "INVALID_CONFIGURATION":
                status = "INSUFFICIENT_DATA"
            reasons.append(
                {
                    "code": "OPERAND_UNAVAILABLE",
                    "message": "Finite READY operands required.",
                    "paths": ["operands"],
                }
            )
    if isinstance(numerical, dict) and isinstance(analytical, dict):
        if (
            not isinstance(numerical.get("target_id"), str)
            or not numerical["target_id"].strip()
            or numerical.get("target_id") != analytical.get("target_id")
        ):
            status = "INVALID_CONFIGURATION"
            reasons.append(
                {
                    "code": "INCOMPATIBLE_TARGET",
                    "message": "Numerical and analytic targets differ.",
                    "paths": ["target_id"],
                }
            )
    if (
        not finite(near_zero_k)
        or near_zero_k <= 0
        or not isinstance(evidence_reference, str)
        or not evidence_reference.strip()
    ):
        status = "INVALID_CONFIGURATION"
        reasons.append(
            {
                "code": "METRIC_POLICY_REQUIRED",
                "message": "Positive sourced K denominator floor required.",
                "paths": ["near_zero_k"],
            }
        )

    def metric(value, unit, kind, output_status=status, output_reasons=reasons):
        return {
            "value": value,
            "unit": unit,
            "quantity_kind": kind,
            "result_kind": "CALCULATED_ESTIMATE",
            "status": output_status,
            "reasons": copy.deepcopy(output_reasons),
            "provenance": {
                "evidence_reference": evidence_reference,
                "context": "CONTROLLED_SIMULATION",
                "origin_kind": "SIMULATED",
                "input_verification": "SYNTHETIC",
                "scope": "WITHIN_MODEL_ANALYTIC_VERIFICATION",
            },
        }

    if status != "READY":
        return {
            "signed_error": metric(None, "K", "temperature_difference"),
            "absolute_error": metric(None, "K", "temperature_difference"),
            "relative_error": metric(None, "1", "dimensionless"),
        }
    signed = float(numerical["value"]) - float(analytical["value"])
    if not math.isfinite(signed):
        status = "MODEL_ERROR"
        reasons = [
            {
                "code": "NUMERICAL_FAILURE",
                "message": "Error subtraction overflow.",
                "paths": ["operands"],
            }
        ]
        return {
            name: metric(None, unit, kind, status, reasons)
            for name, unit, kind in (
                ("signed_error", "K", "temperature_difference"),
                ("absolute_error", "K", "temperature_difference"),
                ("relative_error", "1", "dimensionless"),
            )
        }
    absolute = abs(signed)
    denominator = abs(analytical["value"])
    if denominator <= near_zero_k:
        relative = metric(
            None,
            "1",
            "dimensionless",
            "INSUFFICIENT_DATA",
            [
                {
                    "code": "NEAR_ZERO_REFERENCE",
                    "message": "Relative error withheld at the declared denominator floor.",
                    "paths": ["analytical.value"],
                }
            ],
        )
    else:
        ratio = absolute / denominator
        relative = metric(
            ratio if math.isfinite(ratio) else None,
            "1",
            "dimensionless",
            "READY" if math.isfinite(ratio) else "MODEL_ERROR",
            []
            if math.isfinite(ratio)
            else [
                {
                    "code": "NUMERICAL_FAILURE",
                    "message": "Relative error overflow.",
                    "paths": ["analytical.value"],
                }
            ],
        )
    return {
        "signed_error": metric(signed, "K", "temperature_difference"),
        "absolute_error": metric(absolute, "K", "temperature_difference"),
        "relative_error": relative,
    }


def blocked_comparison():
    """Current model pair has no approved mapping; numbers cannot bypass this gate."""
    paths = [
        "comparison.target_mapping",
        "comparison.geometry_material_reduction",
        "comparison.source_partition",
        "comparison.equivalent_boundary",
        "comparison.time_window",
    ]
    reasons = [
        {
            "code": "INCOMPATIBLE_COMPARISON",
            "message": "Node proxy and spatial FEM maximum lack an evidenced common target.",
            "paths": paths,
        }
    ]
    component = {
        "value": None,
        "unit": "K",
        "result_kind": "CALCULATED_ESTIMATE",
        "status": "INVALID_CONFIGURATION",
        "reasons": reasons,
        "missing_inputs": paths,
        "warnings": [],
        "assumptions": [
            {
                "message": "No model reduction or cross-model calibration is assumed.",
                "reference": "docs/validation_reference.md#compatibility-decision",
            }
        ],
        "coverage": {
            "start": None,
            "end": None,
            "covered_seconds": None,
            "expected_seconds": None,
            "fraction": None,
            "gap_count": 0,
            "missing_fields": paths,
        },
        "provenance": {
            "model_id": None,
            "equation_ids": [],
            "input_paths": paths,
            "evidence_references": ["docs/validation_reference.md#compatibility-decision"],
            "case_id": None,
            "comparison_id": None,
            "numerical_verification_reference": None,
            "mesh_convergence_reference": None,
        },
    }

    def diagnostic(unit, kind):
        return {
            "value": None,
            "unit": unit,
            "quantity_kind": kind,
            "result_kind": "CALCULATED_ESTIMATE",
            "status": "INVALID_CONFIGURATION",
            "reasons": copy.deepcopy(reasons),
            "provenance": {
                "evidence_reference": "docs/validation_reference.md#compatibility-decision",
                "context": "CONTROLLED_SIMULATION",
                "origin_kind": "SIMULATED",
                "input_verification": "SYNTHETIC",
                "scope": "BLOCKED_MODEL_TO_MODEL_COMPARISON",
            },
        }

    return {
        "hot_spot_difference": component,
        "absolute_error": diagnostic("K", "temperature_difference"),
        "relative_error": diagnostic("1", "dimensionless"),
        "left_target": "IDEALIZED_UNIFORM_WINDING_NODE_PROXY",
        "right_target": "SYNTHETIC_RECTANGLE_DOMAIN_MAXIMUM",
    }
