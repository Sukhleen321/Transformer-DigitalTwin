"""Launch isolated current-source backend, separate producer and opt-in frontend.

TEST_DATABASE_URL supplies local admin access. Its original database is NEVER
migrated or written. Ctrl+C stops owned children and drops ONLY the new DB.
"""

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from time import monotonic, sleep
from uuid import uuid4

import httpx
import psycopg
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path[:0] = [str(ROOT), str(BACKEND)]


def port_available(preferred):
    for port in range(preferred, preferred + 100):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free local port in requested range")


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def wait_http(url, processes):
    deadline = monotonic() + 40
    while monotonic() < deadline:
        if any(p.poll() is not None for p in processes):
            raise RuntimeError("Owned child exited; inspect output directory")
        try:
            if httpx.get(url, timeout=2).status_code == 200:
                return
        except httpx.TransportError:
            pass
        sleep(0.2)
    raise RuntimeError("Owned service startup timed out")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-port", type=int, default=8002)
    parser.add_argument("--frontend-port", type=int, default=5177)
    parser.add_argument("--interval", type=float, default=4)
    parser.add_argument(
        "--asset",
        action="append",
        help="Register and simulate this synthetic asset; repeat for multiple assets",
    )
    verification = parser.add_mutually_exclusive_group()
    verification.add_argument(
        "--verify", action="store_true", help="HTTP and browser checks, then cleanup"
    )
    verification.add_argument(
        "--verify-api",
        action="store_true",
        help="Real input/DB/API checks without a browser, then cleanup",
    )
    parser.add_argument(
        "--stop-file",
        type=Path,
        help="Create this file to stop all owned demo processes and drop the demo DB",
    )
    parser.add_argument("--browser-module")
    parser.add_argument("--browser-executable")
    parser.add_argument("--verification-view", choices=("thermal", "monitoring"), default="thermal")
    args = parser.parse_args()
    from ml.demo_physics.fleet import asset_ids

    assets = tuple(args.asset or asset_ids(ROOT / "simulator/config/operational-fleet.json"))
    if (
        not 1 <= len(assets) <= 10
        or len(set(assets)) != len(assets)
        or any(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", asset) is None for asset in assets)
    ):
        parser.error(
            "Provide 1–10 distinct synthetic asset IDs (letters, digits, dot, underscore, hyphen)"
        )
    if args.verify_api and len(assets) < 2:
        parser.error("API verification requires two distinct assets")
    if args.verify and assets != ("LIVE-DEMO-A", "LIVE-DEMO-B"):
        parser.error(
            "Historical browser helper requires its original LIVE-DEMO-A/B assets; "
            "use --verify-api for other assets"
        )
    if not 1 <= args.interval <= 10:
        parser.error("Interval must be 1–10 s")
    if args.stop_file and args.stop_file.exists():
        parser.error("Stop file already exists; remove it explicitly before starting a new demo")
    if args.verify and not (args.browser_module and args.browser_executable):
        parser.error("--verify requires both existing browser paths")
    if not shutil.which("node"):
        parser.error("Installed Node and frontend npm dependencies required")
    raw = os.environ.get("TEST_DATABASE_URL")
    if not raw:
        parser.error("Supply TEST_DATABASE_URL securely; only a new disposable database is used")
    base = make_url(raw)
    if base.drivername != "postgresql+psycopg" or base.host not in (
        "localhost",
        "127.0.0.1",
        "::1",
    ):
        parser.error("Only explicitly local PostgreSQL admin URLs are allowed")
    backend_port, frontend_port = (
        port_available(args.backend_port),
        port_available(args.frontend_port),
    )
    if backend_port == frontend_port:
        frontend_port = port_available(frontend_port + 1)
    database = "live_physics_demo_" + uuid4().hex
    target = base.set(database=database).render_as_string(hide_password=False)
    admin = base.set(drivername="postgresql", database="postgres").render_as_string(
        hide_password=False
    )
    out = Path(tempfile.mkdtemp(prefix="live-physics-demo-"))
    api, web = f"http://127.0.0.1:{backend_port}", f"http://127.0.0.1:{frontend_port}"
    env = os.environ.copy()
    env.update(
        DATABASE_URL=target,
        ENV="local-demo",
        PHYSICS_ENABLED="true",
        ENABLE_PHYSICS_DEMO="true",
        PHYSICS_DEMO_INPUT_MODE="standalone",
        MQTT_ENABLED="false",
        ML_BACKEND="stub",
        DEMO_RESET_ENABLED="false",
        WEB_CONCURRENCY="1",
        CORS_ORIGINS=web,
        PYTHONPATH=os.pathsep.join((str(ROOT), str(BACKEND))),
        LOG_LEVEL="WARNING",
    )
    for key in ("OPERATIONAL_FLEET_FILE", "ANALYTICS_POLICY_FILE"):
        env.pop(key, None)
    env.pop("LIVE_PHYSICS_DEMO_ENABLED", None)
    processes, logs = [], []
    created = False
    report = dict(
        database=database,
        backend=api,
        frontend=web,
        output_directory=str(out),
        run_id=uuid4().hex,
        assets=assets,
    )
    effective = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "import json; from app.core.config import get_settings; "
            "s=get_settings(); print(json.dumps(dict("
            "enable_physics_demo=s.live_physics_demo_enabled, "
            "physics_enabled=s.physics_enabled, env=s.env, mqtt_enabled=s.mqtt_enabled, "
            "reset_enabled=s.demo_reset_enabled)))",
        ],
        env=env,
        cwd=out,
        text=True,
    )
    report["effective_settings"] = json.loads(effective)
    assert report["effective_settings"] == {
        "enable_physics_demo": True,
        "physics_enabled": True,
        "env": "local-demo",
        "mqtt_enabled": False,
        "reset_enabled": False,
    }

    def launch(name, command_line):
        log = (out / f"{name}.log").open("w", encoding="utf-8")
        logs.append(log)
        process = subprocess.Popen(
            command_line,
            cwd=out,
            env=env,
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        processes.append(process)
        return process

    try:
        with psycopg.connect(admin, autocommit=True, connect_timeout=5) as connection:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        created = True
        config = Config(str(BACKEND / "alembic.ini"))
        config.attributes["database_url"] = target
        config.set_main_option("script_location", str(BACKEND / "alembic"))
        command.upgrade(config, "head")
        from app.models.transformer import Transformer

        engine = create_engine(target)
        with Session(engine) as session, session.begin():
            for asset in assets:
                session.add(Transformer(id=asset, name="LIVE SIMULATION · " + asset))
        engine.dispose()
        backend_process = launch(
            "backend",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(backend_port),
                "--workers",
                "1",
            ],
        )
        wait_http(api + "/health/ready", processes)
        producer_process = launch(
            "producer",
            [
                sys.executable,
                str(BACKEND / "scripts/live_physics_producer.py"),
                "--run-id",
                report["run_id"],
                "--interval",
                str(args.interval),
                "--stop-file",
                str(out / "stop-producer"),
                *[part for asset in assets for part in ("--asset", asset)],
            ],
        )
        launch(
            "frontend",
            [
                "node",
                str(ROOT / "frontend/scripts/live-physics-vite.cjs"),
                api,
                str(frontend_port),
                str(args.interval * 1000),
            ],
        )
        wait_http(web, processes)
        print(json.dumps(report, indent=2), flush=True)
        print(
            "Ctrl+C stops only these owned processes and drops the disposable demo database.",
            flush=True,
        )
        if args.verify or args.verify_api:
            with httpx.Client(base_url=api, timeout=5) as client:
                paths = client.get("/openapi.json").json()["paths"]
                assert "/api/v1/transformers/{transformer_id}/physics" in paths
                assert "/api/v1/demo/transformers/{transformer_id}/physics" in paths
                report["openapi_routes_present"] = True
                ordinary = client.get(f"/api/v1/transformers/{assets[0]}/physics")
                assert ordinary.status_code == 200
                assert all(c["value"] is None for c in ordinary.json()["components"].values())
                report["production_values_unavailable"] = True
                cors = client.options(
                    f"/api/v1/demo/transformers/{assets[0]}/physics",
                    headers={"Origin": web, "Access-Control-Request-Method": "GET"},
                )
                assert cors.headers["access-control-allow-origin"] == web
                report["cors_origin"] = web
                samples = []
                deadline = monotonic() + 35
                while len(samples) < 2 and monotonic() < deadline:
                    response = client.get(f"/api/v1/demo/transformers/{assets[0]}/physics")
                    if response.status_code == 200:
                        data = response.json()
                        if (
                            data["status"] == "READY"
                            and data["sequence"] >= 3
                            and (not samples or data["sequence"] > samples[-1]["sequence"])
                        ):
                            assert all(c["value"] is not None for c in data["components"].values())
                            samples.append(data)
                    sleep(0.5)
                assert len(samples) == 2, "No two changing live events"
                assert samples[1]["timestamp"] > samples[0]["timestamp"]
                assert (
                    samples[1]["components"]["hot_spot_temperature"]["value"]
                    != samples[0]["components"]["hot_spot_temperature"]["value"]
                )
                (out / "api-samples.json").write_text(
                    json.dumps(samples, indent=2), encoding="utf-8"
                )
                report["samples"] = samples
            if args.verify_api:
                from verify_live_physics_pipeline import verify_pipeline

                report["pipeline"] = verify_pipeline(
                    api, web, target, samples, out, args.interval, producer_process, assets
                )
                stop(backend_process)
                env["ENABLE_PHYSICS_DEMO"] = "false"
                disabled = launch(
                    "backend-disabled",
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "app.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(backend_port),
                        "--workers",
                        "1",
                    ],
                )
                wait_http(api + "/health/ready", [disabled])
                response = httpx.get(api + f"/api/v1/demo/transformers/{assets[0]}/physics")
                assert response.status_code == 404
                report["pipeline"]["disabled_response"] = response.json()
            else:
                subprocess.run(
                    [
                        "node",
                        str(
                            ROOT
                            / "frontend/scripts"
                            / (
                                "verify-physics-dashboard.cjs"
                                if args.verification_view == "monitoring"
                                else "verify-live-physics.cjs"
                            )
                        ),
                        api,
                        web,
                        str(out),
                        args.browser_module,
                        args.browser_executable,
                    ],
                    check=True,
                    cwd=ROOT,
                )
                report["browser"] = json.loads((out / "browser.json").read_text(encoding="utf-8"))
            if args.verify and args.verification_view == "monitoring":
                stop(backend_process)
                env["ENABLE_PHYSICS_DEMO"] = "false"
                disabled = launch(
                    "backend-disabled",
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "app.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(backend_port),
                        "--workers",
                        "1",
                    ],
                )
                wait_http(api + "/health/ready", [disabled])
                assert (
                    httpx.get(api + "/api/v1/demo/transformers/LIVE-DEMO-A/physics").status_code
                    == 404
                )
                subprocess.run(
                    [
                        "node",
                        str(ROOT / "frontend/scripts/verify-physics-dashboard.cjs"),
                        api,
                        web,
                        str(out),
                        args.browser_module,
                        args.browser_executable,
                        "disabled",
                    ],
                    check=True,
                    cwd=ROOT,
                )
                report["disabled_browser"] = json.loads(
                    (out / "browser-disabled.json").read_text(encoding="utf-8")
                )
            with psycopg.connect(
                target.replace("postgresql+psycopg:", "postgresql:")
            ) as connection:
                report["isolated_table_counts"] = {
                    table: connection.execute(
                        sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
                    ).fetchone()[0]
                    for table in (
                        "live_physics_demo_events",
                        "telemetry",
                        "physics_profiles",
                        "physics_events",
                        "physics_records",
                        "physics_checkpoints",
                        "ml_checkpoints",
                    )
                }
                assert report["isolated_table_counts"]["live_physics_demo_events"] > 0
                assert all(
                    count == 0
                    for table, count in report["isolated_table_counts"].items()
                    if table != "live_physics_demo_events"
                )
        else:
            while True:
                if args.stop_file and args.stop_file.exists():
                    report["stopped_by_file"] = True
                    break
                if any(p.poll() is not None for p in processes):
                    raise RuntimeError("Owned demo service stopped; inspect output directory")
                sleep(1)
    except KeyboardInterrupt:
        report["stopped_by_user"] = True
    finally:
        for process in reversed(processes):
            stop(process)
        for log in logs:
            log.close()
        if created:
            assert database.startswith("live_physics_demo_") and len(database) == 50
            with psycopg.connect(admin, autocommit=True, connect_timeout=5) as connection:
                connection.execute(
                    sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database))
                )
            report["database_dropped"] = True
        report["owned_children_stopped"] = all(p.poll() is not None for p in processes)
        (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("Cleanup report: " + str(out / "report.json"), flush=True)


if __name__ == "__main__":
    main()
