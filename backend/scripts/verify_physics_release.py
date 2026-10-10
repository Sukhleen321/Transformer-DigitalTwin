"""Verify real HTTP/browser boundaries using only a newly created disposable DB.

No telemetry, equipment parameters or physics profiles are installed. The
optional browser check requires an existing Playwright module and browser.
"""

import argparse
import json
import os
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
from alembic.config import Config
from jsonschema import Draft202012Validator, FormatChecker
from psycopg import sql
from sqlalchemy.engine import make_url

from alembic import command

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND))

ASSETS = ("PHASE7-EMPTY-A", "PHASE7-EMPTY-B")


def free_port(port):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", port))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--frontend-port", type=int, default=5177)
    parser.add_argument("--browser-module", help="Existing Playwright module path")
    parser.add_argument("--browser-executable", help="Existing Chromium/Edge executable")
    args = parser.parse_args()
    if bool(args.browser_module) != bool(args.browser_executable):
        parser.error("Both browser options are required together")
    raw = os.environ.get("TEST_DATABASE_URL")
    if not raw:
        parser.error("TEST_DATABASE_URL is required; only a NEW database is migrated")
    base = make_url(raw)
    if base.drivername != "postgresql+psycopg":
        parser.error("TEST_DATABASE_URL must use postgresql+psycopg")
    free_port(args.port)
    if args.browser_module:
        free_port(args.frontend_port)
        if not shutil.which("node"):
            parser.error("Existing Node installation required")
    database = "transformer_phase7_" + uuid4().hex
    admin = base.set(drivername="postgresql", database="postgres").render_as_string(
        hide_password=False
    )
    target = base.set(database=database).render_as_string(hide_password=False)
    out = Path(tempfile.mkdtemp(prefix="transformer-phase7-live-"))
    report = {"database": database, "output_directory": str(out), "runs": []}
    environment = os.environ.copy()
    environment.update(
        DATABASE_URL=target,
        MQTT_ENABLED="false",
        ML_BACKEND="stub",
        DEMO_RESET_ENABLED="false",
        SCHEMA_VERSION="1.1.0",
        WEB_CONCURRENCY="1",
        CORS_ORIGINS=f"http://127.0.0.1:{args.frontend_port}",
        PYTHONPATH=os.pathsep.join((str(ROOT), str(BACKEND))),
        LOG_LEVEL="WARNING",
    )
    # An empty fleet path means the current directory, not "no fleet". Remove
    # inherited file settings and start outside backend/.env to select None.
    for setting in ("OPERATIONAL_FLEET_FILE", "ANALYTICS_POLICY_FILE"):
        environment.pop(setting, None)
    with psycopg.connect(admin, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    try:
        config = Config(str(BACKEND / "alembic.ini"))
        config.attributes["database_url"] = target
        config.set_main_option("script_location", str(BACKEND / "alembic"))
        command.upgrade(config, "head")
        from app.schemas.physics import PhysicsResult

        validator = Draft202012Validator(
            json.loads((ROOT / "docs/contracts/physics-result-v1.schema.json").read_text()),
            format_checker=FormatChecker(),
        )
        origin = f"http://127.0.0.1:{args.port}"
        for enabled in (False, True):
            mode = "no-profile" if enabled else "disabled"
            environment["PHYSICS_ENABLED"] = str(enabled).lower()
            with (out / f"backend-{mode}.log").open("w", encoding="utf-8") as log:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "app.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(args.port),
                        "--workers",
                        "1",
                    ],
                    cwd=out,
                    env=environment,
                    stdout=log,
                    stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                try:
                    with httpx.Client(base_url=origin, timeout=5) as client:
                        deadline = monotonic() + 30
                        while True:
                            if process.poll() is not None:
                                raise RuntimeError(f"Owned backend exited; see {log.name}")
                            try:
                                ready = client.get("/health/ready")
                                if ready.status_code == 200:
                                    break
                            except httpx.TransportError:
                                pass
                            if monotonic() > deadline:
                                raise RuntimeError(f"Startup timed out; see {log.name}")
                            sleep(0.2)
                        if not enabled:
                            for asset in ASSETS:
                                response = client.post(
                                    "/api/v1/transformers",
                                    json={
                                        "id": asset,
                                        "name": "Empty release-verification asset " + asset,
                                    },
                                )
                                assert response.status_code == 201, response.text
                                assert response.json()["rated_current_a"] is None
                        route = "/api/v1/transformers/{transformer_id}/physics"
                        registry = client.get("/api/v1/transformers?limit=50&offset=0")
                        assert registry.status_code == 200, registry.text
                        assert registry.json()["total"] == 2, registry.text
                        (out / f"registry-{mode}.json").write_text(registry.text, encoding="utf-8")
                        operation = client.get("/openapi.json").json()["paths"][route]["get"]
                        assert "200" in operation["responses"]
                        run = {
                            "mode": mode,
                            "ready_http": 200,
                            "route_registered": True,
                            "responses": [],
                            "error_paths": [],
                        }
                        for asset in ASSETS:
                            response = client.get(
                                f"/api/v1/transformers/{asset}/physics",
                                headers={"X-Request-ID": "phase7-" + mode},
                            )
                            assert response.status_code == 200, response.text
                            body = response.json()
                            PhysicsResult.model_validate(body)
                            validator.validate(body)
                            assert body["transformer_id"] == asset
                            assert body["timestamp"] is None
                            assert len(body["components"]) == 10
                            expected = (
                                "PHYSICS_RESULT_UNAVAILABLE" if enabled else "PHYSICS_DISABLED"
                            )
                            for component in body["components"].values():
                                assert component["value"] is None
                                assert component["status"] != "READY"
                                assert expected in [r["code"] for r in component["reasons"]]
                            run["responses"].append(
                                {
                                    "asset": asset,
                                    "http": 200,
                                    "all_values_null": True,
                                    "reason": expected,
                                }
                            )
                            (out / f"{mode}-{asset}.json").write_text(
                                json.dumps(body, indent=2), encoding="utf-8"
                            )
                        for suffix, expected in (
                            ("MISSING/physics", 404),
                            (ASSETS[0] + "/physics?unknown=1", 422),
                            (ASSETS[0] + "/physics?at=2030-01-01T00:00:00Z", 422),
                            (ASSETS[0] + "/physics?at=2026-01-01T00:00:00", 422),
                            (
                                ASSETS[0]
                                + "/physics?at=2026-01-01T00:00:00Z&at=2026-01-01T00:00:00Z",
                                422,
                            ),
                        ):
                            response = client.get("/api/v1/transformers/" + suffix)
                            assert response.status_code == expected, response.text
                            run["error_paths"].append({"suffix": suffix, "http": expected})
                        cors = client.options(
                            f"/api/v1/transformers/{ASSETS[0]}/physics",
                            headers={
                                "Origin": f"http://127.0.0.1:{args.frontend_port}",
                                "Access-Control-Request-Method": "GET",
                            },
                        )
                        assert cors.status_code == 200
                        assert cors.headers["access-control-allow-origin"] == (
                            f"http://127.0.0.1:{args.frontend_port}"
                        )
                        run["cors_preflight"] = 200
                    report["runs"].append(run)
                    if args.browser_module:
                        subprocess.run(
                            [
                                "node",
                                str(ROOT / "frontend/scripts/verify-physics-release.cjs"),
                                origin,
                                str(args.frontend_port),
                                mode,
                                str(out),
                                str(Path(args.browser_module).resolve()),
                                str(Path(args.browser_executable).resolve()),
                            ],
                            check=True,
                            cwd=ROOT,
                        )
                        run["browser"] = json.loads((out / f"browser-{mode}.json").read_text())
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=10)
        with psycopg.connect(target.replace("postgresql+psycopg:", "postgresql:")) as connection:
            for table in (
                "telemetry",
                "physics_profiles",
                "physics_records",
                "physics_events",
                "physics_checkpoints",
            ):
                count = connection.execute(
                    sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
                ).fetchone()[0]
                assert count == 0, (table, count)
        report["no_telemetry_or_profiles_installed"] = True
        report["status"] = "PASS"
    finally:
        # Only this exact UUID database, created above, may be dropped.
        assert database.startswith("transformer_phase7_") and len(database) == 51
        with psycopg.connect(admin, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database))
            )
        report["database_dropped"] = True
        (out / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
