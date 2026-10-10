"""Controlled local writer. Requires the disposable launcher environment."""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic, sleep

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]


def configured_assets():
    from ml.demo_physics.fleet import asset_ids

    return asset_ids(ROOT / "simulator/config/operational-fleet.json")


ASSETS = configured_assets()


def main():
    from app.db.session import SessionLocal
    from app.services.live_physics_demo import write

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--asset", action="append", help="Explicit synthetic asset; repeat for each asset"
    )
    parser.add_argument("--interval", type=float, default=4)
    parser.add_argument("--stop-file", type=Path)
    args = parser.parse_args()
    if not 1 <= args.interval <= 10:
        parser.error("Demo interval must be 1–10 s")
    assets = tuple(args.asset or ASSETS)
    if len(assets) > 10 or len(set(assets)) != len(assets):
        parser.error("Provide at most ten distinct synthetic assets")
    while True:
        if args.stop_file and args.stop_file.exists():
            return
        started = monotonic()
        for asset in assets:
            try:
                with SessionLocal() as session, session.begin():
                    result = write(session, asset, datetime.now(UTC), args.run_id)
                    print(
                        f"{asset} event={result['timestamp']} "
                        f"sequence={result['sequence']} status={result['status']} "
                        f"synthetic_current_a={result['inputs']['current_a']:.6f}",
                        flush=True,
                    )
            except Exception as exc:
                print(f"{asset} unavailable error_type={type(exc).__name__}", flush=True)
        sleep(max(0.1, args.interval - (monotonic() - started)))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
