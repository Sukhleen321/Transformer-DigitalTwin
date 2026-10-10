"""Docker Compose/source configuration checks; never start any service."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from app.core.config import Settings
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]


def test_isolated_compose_hosts_profiles_flags_images_and_ephemeral_storage():
    if not shutil.which("docker"):
        pytest.skip("Docker Compose CLI required for static configuration validation")
    env = dict(
        os.environ,
        PHYSICS_DEMO_TAG="automated-config-check",
        PHYSICS_DEMO_DB_NAME="live_physics_demo_" + "a" * 32,
        PHYSICS_DEMO_DB_PASSWORD="not-a-real-credential",
        PHYSICS_DEMO_HTTP_PORT="18002",
        PHYSICS_DEMO_FRONTEND_PORT="15177",
        PHYSICS_DEMO_DB_PORT="55434",
        PHYSICS_DEMO_MQTT_PORT="51886",
        PHYSICS_DEMO_MODBUS_PORT="1503",
    )
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            "physicsdemo-config-test",
            "-f",
            str(ROOT / "docker-compose.physics-demo.yml"),
            "--profile",
            "physics-demo",
            "config",
            "--format",
            "json",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    config = json.loads(result.stdout)
    services = config["services"]
    assert set(services) == {
        "db",
        "mqtt",
        "backend",
        "frontend",
        "modbus-simulator",
        "modbus-bridge",
    }
    assert not config.get("volumes")
    for service in services.values():
        assert service["profiles"] == ["physics-demo"]
        assert not service.get("container_name")
        for volume in service.get("volumes", []):
            assert volume["type"] == "bind" and volume["read_only"]
        for port in service.get("ports", []):
            assert port["host_ip"] == "127.0.0.1"
    backend = services["backend"]["environment"]
    assert "@db:5432/live_physics_demo_" in backend["DATABASE_URL"]
    assert backend["ENV"] == "local-demo" and backend["ENABLE_PHYSICS_DEMO"] == "true"
    assert backend["PHYSICS_ENABLED"] == "true"
    assert backend["PHYSICS_DEMO_INPUT_MODE"] == "accepted-telemetry"
    assert backend["MQTT_HOST"] == "mqtt" and backend["MQTT_PORT"] == "1883"
    assert backend["MQTT_TOPIC"] == "transformer/+/telemetry" and backend["MQTT_QOS"] == "1"
    assert backend["DEMO_RESET_ENABLED"] == "false" and backend["WEB_CONCURRENCY"] == "1"
    assert backend["CORS_ORIGINS"] == "http://127.0.0.1:15177"
    for name in ("backend", "frontend", "modbus-simulator", "modbus-bridge"):
        assert services[name]["image"].endswith(":automated-config-check")
        assert "build" in services[name]
    frontend = services["frontend"]["build"]["args"]
    assert frontend["VITE_API_BASE_URL"] == "/"
    assert frontend["VITE_LIVE_PHYSICS_DEMO_ENABLED"] == "true"
    assert frontend["VITE_LIVE_PHYSICS_POLL_INTERVAL_MS"] == "5000"
    assert services["db"]["tmpfs"] and services["modbus-bridge"]["tmpfs"]
    for dependency in services["modbus-bridge"]["depends_on"].values():
        assert dependency["condition"] == "service_healthy"
    assert services["modbus-simulator"]["command"][-1] == "/config/physics-demo-server.json"
    proxy = (ROOT / "frontend/docker/physics-demo.conf").read_text()
    assert "proxy_pass http://backend:8000;" in proxy
    dockerfile = (ROOT / "frontend/Dockerfile").read_text()
    assert "ARG VITE_LIVE_PHYSICS_DEMO_ENABLED=false" in dockerfile


def test_input_mode_is_typed_opt_in_and_invalid_value_is_configuration_error(monkeypatch):
    monkeypatch.delenv("ENABLE_PHYSICS_DEMO", raising=False)
    monkeypatch.delenv("LIVE_PHYSICS_DEMO_ENABLED", raising=False)
    monkeypatch.delenv("PHYSICS_DEMO_INPUT_MODE", raising=False)
    assert Settings(_env_file=None).physics_demo_input_mode == "standalone"
    monkeypatch.setenv("PHYSICS_DEMO_INPUT_MODE", "accepted-telemetry")
    assert Settings(_env_file=None).physics_demo_input_mode == "accepted-telemetry"
    monkeypatch.setenv("PHYSICS_DEMO_INPUT_MODE", "guess")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_enabled_telemetry_mode_requires_explicit_supported_fleet(monkeypatch):
    monkeypatch.delenv("OPERATIONAL_FLEET_FILE", raising=False)
    with pytest.raises(ValidationError, match="requires OPERATIONAL_FLEET_FILE"):
        Settings(
            _env_file=None,
            live_physics_demo_enabled=True,
            physics_demo_input_mode="accepted-telemetry",
        )
