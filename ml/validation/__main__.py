"""Deterministic JSON validation artifact, exit nonzero on failed checks/inputs."""

import argparse
import json
from pathlib import Path

from .cases import ValidationError, read_case
from .harness import run_validation


def main():
    parser = argparse.ArgumentParser(
        description="Independent synthetic numerical verification; comparison unavailable."
    )
    parser.add_argument("--case", type=Path, help="Explicit synthetic validation manifest")
    args = parser.parse_args()
    try:
        result = run_validation(read_case(args.case))
    except ValidationError as exc:
        result = {
            "suite_status": "FAIL",
            "status": exc.status,
            "value": None,
            "context": "CONTROLLED_SIMULATION",
            "origin_kind": "SIMULATED",
            "input_verification": "SYNTHETIC",
            "reasons": [{"code": exc.code, "message": str(exc)}],
        }
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0 if result["suite_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
