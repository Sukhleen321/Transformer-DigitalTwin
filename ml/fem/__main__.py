"""Deterministic reference command: python -m ml.fem [--case path]."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .benchmark import read_case, run_reference
from .solver import FEMError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case", type=Path, help="Explicit synthetic case JSON; default is packaged benchmark."
    )
    args = parser.parse_args(argv)
    try:
        result = run_reference(read_case(args.case))
    except FEMError as exc:
        result = {
            "artifact_version": "1.0.0",
            "result_kind": "SIMULATED_REFERENCE",
            "context": "CONTROLLED_SIMULATION",
            "origin_kind": "SIMULATED",
            "input_verification": "SYNTHETIC",
            "status": exc.status,
            "maximum_temperature": {
                "value": None,
                "unit": "K",
                "quantity_kind": "absolute_temperature",
                "provenance": None,
            },
            "reasons": [{"code": exc.code, "message": str(exc), "paths": ["case"]}],
        }
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0 if result["status"] == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
