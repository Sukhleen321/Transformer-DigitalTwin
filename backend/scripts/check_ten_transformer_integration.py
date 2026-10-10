"""Focused automated checks using an owned, ephemeral PostgreSQL test container.

No application Compose stack, retained database, browser or dashboard is started.
Run from the repository root with .venv/Scripts/python.exe.
"""

import json
import os
import socket
import subprocess
import sys
import time
import types
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
FILES = [
    "backend/tests/test_ten_transformer_demo.py",
    "backend/tests/test_ten_transformer_persistence.py",
    "backend/tests/test_physics_demo_compose.py",
    "backend/tests/test_physics_demo_config.py",
    "backend/tests/test_live_physics_demo.py",
    "backend/tests/test_physics_integration.py",
    "backend/tests/test_physics_codec.py",
    "backend/tests/mqtt/test_message_handler.py",
    "backend/tests/mqtt/test_config.py",
    "backend/tests/mqtt/test_consumer.py",
    "ml/tests/test_live_physics_demo.py",
    "simulator/tests/test_physics_demo_stream.py",
    "simulator/tests/test_operational_fleet.py",
    "simulator/tests/test_generation_h03.py",
    "simulator/tests/test_modbus_h03.py",
    "simulator/tests/test_delivery_h03.py",
]


def docker(*args, **kwargs):
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        **kwargs,
    )


def main():
    if docker("info", "--format", "{{.ServerVersion}}").returncode:
        raise RuntimeError("Docker engine unavailable; isolated PostgreSQL tests cannot run")
    identity = uuid4().hex
    name = "fullstack-check-" + identity
    secret = uuid4().hex
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    child_env = dict(os.environ, POSTGRES_PASSWORD=secret)
    launched = docker(
        "run",
        "--detach",
        "--name",
        name,
        "--tmpfs",
        "/var/lib/postgresql/data",
        "--env",
        "POSTGRES_USER=physics_test",
        "--env",
        "POSTGRES_PASSWORD",
        "--publish",
        f"127.0.0.1:{port}:5432",
        "postgres:16",
        env=child_env,
    )
    if launched.returncode:
        raise RuntimeError("Owned disposable PostgreSQL startup failed")
    container_id = launched.stdout.strip()
    try:
        for _ in range(60):
            if docker("exec", container_id, "pg_isready", "-U", "physics_test").returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Owned test database readiness timeout")
        sys.path[:0] = [str(ROOT), str(ROOT / "backend"), str(ROOT / "simulator")]
        # Tests create ONLY new UUID databases; this container contains no retained data.
        os.environ["TEST_DATABASE_URL"] = (
            f"postgresql+psycopg://physics_test:{secret}@127.0.0.1:{port}/postgres"
        )
        os.environ["PYTHONPATH"] = os.pathsep.join(sys.path[:3])
        namespace = types.ModuleType("tests")
        namespace.__path__ = [str(ROOT / "backend/tests"), str(ROOT / "simulator/tests")]
        sys.modules["tests"] = namespace
        import pytest

        evidence = ROOT / "docs/evidence/ten_transformer"
        evidence.mkdir(parents=True, exist_ok=True)
        exit_code = pytest.main(
            ["-q", "--tb=short", "--junitxml=" + str(evidence / "focused.xml"), *FILES]
        )
        (evidence / "focused-run.json").write_text(
            json.dumps(
                {
                    "command": (
                        ".venv/Scripts/python.exe "
                        "backend/scripts/check_ten_transformer_integration.py"
                    ),
                    "files": FILES,
                    "exit_code": int(exit_code),
                    "ephemeral_test_container": name,
                    "database_port": port,
                    "application_stack_started": False,
                },
                indent=2,
            )
            + "\n"
        )
        return int(exit_code)
    finally:
        # Remove only the exact newly returned container ID, without volume deletion.
        stopped = docker("rm", "--force", container_id)
        print("Owned ephemeral PostgreSQL cleanup:", stopped.returncode == 0)
        if "evidence" in locals():
            (evidence / "cleanup.json").write_text(
                json.dumps(
                    {
                        "owned_container": name,
                        "removed": stopped.returncode == 0,
                        "volumes_deleted": False,
                        "retained_services_modified": False,
                    },
                    indent=2,
                )
                + "\n"
            )


if __name__ == "__main__":
    raise SystemExit(main())
