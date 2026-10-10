"""Phase 1 contract checks only. No application model, estimator or solver.

Requires the already-used jsonschema 4.x dependency. Run from any directory.
Fixtures labelled READY/LIVE/VERIFIED are hypothetical structural examples.
"""

from __future__ import annotations

import copy
import json
import math
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f"nonfinite JSON constant: {value}")


def load(path):
    return json.loads(
        path.read_text(encoding="utf-8"),
        parse_float=Decimal,
        object_pairs_hook=unique_pairs,
        parse_constant=reject_constant,
    )


def put(record, path, value):
    target = record
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = copy.deepcopy(value)


def result_case(fixtures, case):
    result = copy.deepcopy(fixtures["base_envelope"])
    result["components"] = {
        name: {**copy.deepcopy(fixtures["component_defaults"]), **copy.deepcopy(values)}
        for name, values in fixtures["components"].items()
    }
    for change in case["changes"]:
        put(result, change["path"], change["value"])
    return result


def check_result(validator, result):
    """Structural and cross-field contract invariants, not input/model eligibility."""
    validator.validate(result)
    # JSON Schema format checking can lack optional date-time dependencies.
    # Validate calendar dates explicitly with the standard library as well.
    datetime.fromisoformat(result["evaluated_at"])
    if result["timestamp"] is not None:
        datetime.fromisoformat(result["timestamp"])
    for component in result["components"].values():
        value = component["value"]
        require(value is None or math.isfinite(value), "nonfinite output")
        coverage = component["coverage"]
        start, end = coverage["start"], coverage["end"]
        if start is not None:
            datetime.fromisoformat(start)
        if end is not None:
            datetime.fromisoformat(end)
        covered, expected = coverage["covered_seconds"], coverage["expected_seconds"]
        fraction = coverage["fraction"]
        require((start is None) == (end is None), "coverage needs both time bounds")
        require(
            (covered is None) == (expected is None), "coverage needs both durations"
        )
        if expected is None:
            require(fraction is None, "unknown duration cannot have fraction")
        else:
            require(start is not None, "known coverage needs bounds")
            duration = Decimal(
                str(
                    (
                        datetime.fromisoformat(end) - datetime.fromisoformat(start)
                    ).total_seconds()
                )
            )
            require(duration >= 0 and expected <= duration, "invalid coverage window")
            require(covered <= expected, "covered exceeds expected duration")
            if expected == 0:
                require(fraction is None and start == end, "instantaneous coverage")
            else:
                require(
                    fraction is not None
                    and abs(Decimal(fraction) - Decimal(covered) / Decimal(expected))
                    <= Decimal("1e-12"),
                    "incorrect coverage fraction",
                )


def conversion_vector(rules, rule_id, value, source_unit, kind, verification, context):
    """Evaluate declarative unit vectors only; production adapters belong to Phase 2."""
    rule = rules[rule_id]
    require(source_unit == rule["source_unit"], "unsupported source unit")
    require(kind == rule["quantity_kind"], "incompatible quantity kind")
    require(
        verification == "VERIFIED"
        or (verification == "SYNTHETIC" and context == "CONTROLLED_SIMULATION"),
        "unsupported verification/context",
    )
    require(type(value) in (int, float, Decimal), "not a numeric measurement")
    require(math.isfinite(value), "nonfinite measurement")
    result = Decimal(str(value)) * Decimal(rule["scale"]) + Decimal(rule["offset"])
    if kind == "absolute_temperature":
        require(result >= 0, "below absolute zero")
    return result


def must_reject(action, label):
    try:
        action()
    except (ValueError, KeyError):
        return
    # jsonschema ValidationError is distinct from ValueError.
    except Exception as exc:
        from jsonschema.exceptions import ValidationError

        if isinstance(exc, ValidationError):
            return
        raise
    raise AssertionError(f"accepted invalid contract case: {label}")


def main():
    registry = load(ROOT / "docs/contracts/physics-units-v1.json")
    schema = load(ROOT / "docs/contracts/physics-result-v1.schema.json")
    fixtures = load(HERE / "cases.json")
    require(registry["physics_contract_version"] == "1.0.0", "registry version")
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    rules = {rule["id"]: rule for rule in registry["rules"]}
    require(len(rules) == len(registry["rules"]), "duplicate conversion ID")
    exercised = set()
    for vector in fixtures["conversion_vectors"]:
        rule = rules[vector["rule"]]
        actual = conversion_vector(
            rules,
            rule["id"],
            Decimal(vector["source"]),
            rule["source_unit"],
            rule["quantity_kind"],
            "VERIFIED",
            "OPERATIONAL",
        )
        require(actual == Decimal(vector["expected"]), f"conversion vector: {vector}")
        inverse = (actual - Decimal(rule["offset"])) / Decimal(rule["scale"])
        require(inverse == Decimal(vector["source"]), "inverse conversion")
        exercised.add(rule["id"])
    require(exercised == set(rules), "untested conversion")

    def temperature(
        value=20,
        unit="DEG_C",
        kind="absolute_temperature",
        verification="VERIFIED",
        context="OPERATIONAL",
    ):
        return conversion_vector(
            rules, "absolute_deg_c_to_k", value, unit, kind, verification, context
        )

    rejected_units = [
        lambda: temperature(value=None),
        lambda: temperature(value=True),
        lambda: temperature(value="20"),
        lambda: temperature(value=float("nan")),
        lambda: temperature(value=float("inf")),
        lambda: temperature(value=-273.16),
        lambda: temperature(unit="SOURCE_UNIT"),
        lambda: temperature(unit="UNKNOWN"),
        lambda: temperature(unit="STATUS"),
        lambda: temperature(unit="V"),
        lambda: temperature(kind="temperature_difference"),
        lambda: temperature(verification="UNVERIFIED"),
        lambda: temperature(verification="SYNTHETIC"),
    ]
    for index, action in enumerate(rejected_units):
        must_reject(action, f"unit eligibility {index}")
    require(
        temperature(value=0, verification="SYNTHETIC", context="CONTROLLED_SIMULATION")
        == Decimal("273.15"),
        "declared synthetic unit vector",
    )

    examples = {
        case["name"]: result_case(fixtures, case) for case in fixtures["positive_cases"]
    }
    require(len(examples) == len(fixtures["positive_cases"]), "duplicate example name")
    for result in examples.values():
        check_result(validator, result)

    mutations = [
        ("unavailable", ["components", "hot_spot_temperature", "value"], 0),
        ("unavailable", ["components", "hot_spot_temperature", "reasons"], []),
        ("unavailable", ["components", "hot_spot_temperature", "unit"], "SOURCE_UNIT"),
        ("partial-measured", ["components", "measured_oil_temperature", "value"], None),
        ("partial-measured", ["components", "measured_oil_temperature", "value"], True),
        ("partial-measured", ["components", "measured_oil_temperature", "value"], "40"),
        (
            "partial-measured",
            ["components", "measured_oil_temperature", "value"],
            float("inf"),
        ),
        ("partial-measured", ["components", "measured_oil_temperature", "value"], -274),
        ("partial-measured", ["lineage", "input_verification"], "UNVERIFIED"),
        ("partial-measured", ["lineage", "origin_kind"], "SIMULATED"),
        ("partial-measured", ["timestamp"], "2026-10-10T00:00:00"),
        ("partial-measured", ["timestamp"], "2026-02-30T00:00:00Z"),
        ("partial-measured", ["versions", "preprocessing_version"], None),
        (
            "partial-measured",
            [
                "components",
                "measured_oil_temperature",
                "provenance",
                "evidence_references",
            ],
            [],
        ),
        ("simulated-comparison-without-ageing", ["context"], "OPERATIONAL"),
        (
            "simulated-comparison-without-ageing",
            ["components", "hot_spot_temperature", "result_kind"],
            "MEASURED_TELEMETRY",
        ),
        (
            "simulated-comparison-without-ageing",
            ["versions", "parameter_version"],
            None,
        ),
        (
            "simulated-comparison-without-ageing",
            ["components", "hot_spot_temperature", "provenance", "equation_ids"],
            [],
        ),
        (
            "simulated-comparison-without-ageing",
            ["components", "hot_spot_temperature", "provenance", "case_id"],
            None,
        ),
        (
            "simulated-comparison-without-ageing",
            [
                "components",
                "fem_hot_spot_temperature",
                "provenance",
                "mesh_convergence_reference",
            ],
            None,
        ),
        (
            "simulated-comparison-without-ageing",
            [
                "components",
                "fem_hot_spot_temperature",
                "provenance",
                "numerical_verification_reference",
            ],
            None,
        ),
        (
            "simulated-comparison-without-ageing",
            ["components", "hot_spot_difference", "provenance", "comparison_id"],
            None,
        ),
        (
            "simulated-comparison-without-ageing",
            ["components", "hot_spot_difference", "unit"],
            "percent",
        ),
        (
            "simulated-comparison-without-ageing",
            ["components", "hot_spot_temperature", "status"],
            "INITIALIZING",
        ),
        (
            "simulated-comparison-without-ageing",
            ["components", "equivalent_ageing_hours", "value"],
            0,
        ),
        (
            "partial-measured",
            ["components", "measured_oil_temperature", "coverage", "covered_seconds"],
            1,
        ),
        (
            "partial-measured",
            ["components", "measured_oil_temperature", "coverage", "fraction"],
            1,
        ),
        (
            "partial-measured",
            ["components", "measured_oil_temperature", "coverage", "end"],
            None,
        ),
        ("replayed-measured", ["lineage", "replay_run_id"], None),
        ("unavailable", ["components", "hot_spot_temperature", "extra"], 1),
    ]
    for name, path, value in mutations:
        candidate = copy.deepcopy(examples[name])
        put(candidate, path, value)
        must_reject(
            lambda candidate=candidate: check_result(validator, candidate),
            "/".join(path),
        )
    missing = copy.deepcopy(examples["unavailable"])
    del missing["components"]["hot_spot_temperature"]
    must_reject(lambda: check_result(validator, missing), "omitted component")

    invalid_json = ['{"value":NaN}', '{"value":Infinity}', '{"value":0,"value":1}']
    for text in invalid_json:
        must_reject(
            lambda text=text: json.loads(
                text, object_pairs_hook=unique_pairs, parse_constant=reject_constant
            ),
            "invalid JSON",
        )

    docs = [
        "docs/physics_contract.md",
        "docs/architecture_current.md",
        "docs/phase0_report.md",
        "docs/phase1_report.md",
        "tests/fixtures/physics/README.md",
    ]
    link_count = 0
    for name in docs:
        path = ROOT / name
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            require(
                (path.parent / target.split("#")[0]).resolve().exists(),
                f"broken local link: {name} -> {target}",
            )
            link_count += 1
    print(
        f"PASS: {len(rules)} unit rules; {len(fixtures['conversion_vectors'])} exact "
        f"vectors and inverses; {len(rejected_units)} unit rejection cases; "
        f"{len(examples)} result fixtures; {len(mutations) + 1} result rejection "
        f"cases; {len(invalid_json)} JSON rejection cases; {link_count} local links."
    )
    print(
        "Contract checks only: no production physics, FEM, standards equations "
        "or field accuracy tested."
    )


if __name__ == "__main__":
    main()
