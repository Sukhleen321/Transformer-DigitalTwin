"""Real PostgreSQL ingestion/GET checks, only on a newly named demo database."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.core.config import get_settings
from app.db.session import get_db
from app.main import create_app
from app.models.live_physics_demo import LivePhysicsDemoEvent
from app.models.telemetry import Telemetry
from app.models.transformer import Transformer
from app.mqtt.message_handler import parse_message
from app.services import demo_telemetry, ingestion_service
from fastapi.testclient import TestClient
from simulator.fleet import load_runtime_config, registry_payloads
from simulator.scheduler import Scheduler
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from tests.test_live_physics_demo import demo_engine  # noqa: F401 -- pytest fixture
from tests.test_ten_transformer_demo import decoded

from ml.demo_physics.fleet import load_fleet
from ml.pipeline.identity import serialize

CONFIG = Path(__file__).resolve().parents[2] / "simulator/config"


@pytest.fixture
def fleet_environment(request, monkeypatch):
    engine = request.getfixturevalue("demo_engine")
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("ENV", "local-demo")
    monkeypatch.setenv("PHYSICS_ENABLED", "true")
    monkeypatch.setenv("ENABLE_PHYSICS_DEMO", "true")
    monkeypatch.setenv("PHYSICS_DEMO_INPUT_MODE", "accepted-telemetry")
    monkeypatch.setenv("OPERATIONAL_FLEET_FILE", str(CONFIG / "operational-fleet.json"))
    monkeypatch.setenv("ML_BACKEND", "stub")
    monkeypatch.setenv("MQTT_ENABLED", "false")
    get_settings.cache_clear()
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                fleet = load_fleet(CONFIG / "operational-fleet.json")
                for payload in registry_payloads(fleet):
                    db.add(Transformer(**payload))
                db.flush()
                app = create_app()
                app.dependency_overrides[get_db] = lambda: db
                with TestClient(app) as client:
                    yield db, client, fleet
            transaction.rollback()
    finally:
        get_settings.cache_clear()


def mqtt_record(scheduler, asset):
    wire = decoded(scheduler.assets[asset], scheduler.advance(asset))
    return parse_message(
        f"transformer/{asset}/telemetry", serialize(wire.model_dump(mode="json")).encode()
    )[0]


def test_ten_assets_ingestion_atomic_checkpoint_identity_api_and_failure_isolation(
    fleet_environment,
):
    db, client, fleet = fleet_environment
    start = datetime.now(UTC) - timedelta(seconds=10)
    scheduler = Scheduler(load_runtime_config(CONFIG / "physics-demo-server.json", "server", start))
    ids = [a["transformer_id"] for a in fleet["assets"]]
    last = {}
    # Individual real MQTT-shaped records go through the canonical ingestion path.
    for _ in range(2):
        for asset in ids:
            record = mqtt_record(scheduler, asset)
            ingestion_service.ingest_record(db, record, run_ml=False)
            last[asset] = record
    assert db.scalar(select(func.count()).select_from(Telemetry)) == 20
    assert db.scalar(select(func.count()).select_from(LivePhysicsDemoEvent)) == 20
    results = {}
    for asset in ids:
        response = client.get(f"/api/v1/demo/transformers/{asset}/physics")
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["transformer_id"] == asset and result["sequence"] == 2
        assert all(
            c["status"] == "READY" and c["value"] is not None for c in result["components"].values()
        )
        row = db.scalar(
            select(LivePhysicsDemoEvent)
            .where(LivePhysicsDemoEvent.transformer_id == asset)
            .order_by(LivePhysicsDemoEvent.timestamp.desc())
            .limit(1)
        )
        telemetry = db.get(Telemetry, row.checkpoint["source_telemetry"]["id"])
        assert telemetry.transformer_id == asset
        assert telemetry.payload_hash == row.checkpoint["source_telemetry"]["payload_hash"]
        assert result["components"]["measured_oil_temperature"]["value"] == pytest.approx(
            telemetry.oil_temperature
        )
        results[asset] = result
        standard = client.get(f"/api/v1/transformers/{asset}/physics")
        assert standard.status_code == 200
        assert all(c["value"] is None for c in standard.json()["components"].values())
    assert len({r["inputs"]["current_a"] for r in results.values()}) == 10
    assert len({r["run_id"] for r in results.values()}) == 10
    evidence = CONFIG.parents[1] / "docs/evidence/ten_transformer"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "postgres-asgi-results.json").write_text(
        json.dumps(
            {
                "verification_kind": "AUTOMATED_POSTGRES_ASGI_TEST_NOT_RUNNING_COMPOSE",
                "all_ten_numeric": True,
                "asset_results": results,
            },
            indent=2,
        )
        + "\n"
    )
    ingestion_service.ingest_record(db, last[ids[0]], run_ml=False)
    assert db.scalar(select(func.count()).select_from(LivePhysicsDemoEvent)) == 20
    # One accepted raw row with missing input must not show its earlier result as current.
    missing = mqtt_record(scheduler, ids[0]).model_dump(mode="json")
    missing["oil_temperature"] = None
    from app.schemas.telemetry import TelemetryIn

    from ml.pipeline.identity import payload_hash

    missing["acquisition"]["snapshot_id"] = payload_hash(missing)
    ingestion_service.ingest_record(db, TelemetryIn.model_validate(missing), run_ml=False)
    bad = client.get(f"/api/v1/demo/transformers/{ids[0]}/physics").json()
    assert bad["status"] == "UNAVAILABLE" and "Latest accepted telemetry" in bad["reason"]
    assert all(c["value"] is None for c in bad["components"].values())
    for asset in ids[1:]:
        ingestion_service.ingest_record(db, mqtt_record(scheduler, asset), run_ml=False)
        healthy = client.get(f"/api/v1/demo/transformers/{asset}/physics").json()
        assert healthy["status"] == "READY" and healthy["sequence"] == 3
        assert (
            healthy["components"]["equivalent_ageing_hours"]["value"]
            > results[asset]["components"]["equivalent_ageing_hours"]["value"]
        )
    get_settings().live_physics_demo_enabled = False
    assert client.get(f"/api/v1/demo/transformers/{ids[1]}/physics").status_code == 404
    assert client.get("/api/v1/demo/transformers/UNKNOWN/physics").status_code == 404


def test_demo_savepoint_failure_does_not_rollback_canonical_telemetry(
    fleet_environment, monkeypatch
):
    db, _, fleet = fleet_environment
    scheduler = Scheduler(
        load_runtime_config(CONFIG / "physics-demo-server.json", "server", datetime.now(UTC))
    )

    def fail(*args, **kwargs):
        raise RuntimeError("Synthetic solver failure")

    monkeypatch.setattr(demo_telemetry.demo, "persist", fail)
    for asset in (a["transformer_id"] for a in fleet["assets"]):
        ingestion_service.ingest_record(db, mqtt_record(scheduler, asset), run_ml=False)
    assert db.scalar(select(func.count()).select_from(Telemetry)) == 10
    assert db.scalar(select(func.count()).select_from(LivePhysicsDemoEvent)) == 0


def test_explicit_gap_reset_starts_new_run_with_no_fabricated_history(
    fleet_environment, monkeypatch
):
    db, client, fleet = fleet_environment
    asset = fleet["assets"][0]["transformer_id"]
    now = datetime.now(UTC)
    past = now - timedelta(seconds=40)
    clock = SimpleNamespace(now=lambda zone: past)
    monkeypatch.setattr(demo_telemetry, "datetime", clock)
    old = Scheduler(load_runtime_config(CONFIG / "physics-demo-server.json", "server", past))
    ingestion_service.ingest_record(db, mqtt_record(old, asset), run_ml=False)
    first = db.scalar(
        select(LivePhysicsDemoEvent).where(LivePhysicsDemoEvent.transformer_id == asset)
    )
    first_run = first.run_id
    clock.now = lambda zone: now
    restarted = Scheduler(load_runtime_config(CONFIG / "physics-demo-server.json", "server", now))
    ingestion_service.ingest_record(db, mqtt_record(restarted, asset), run_ml=False)
    response = client.get(f"/api/v1/demo/transformers/{asset}/physics")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "INITIALIZING" and body["run_id"] != first_run
    assert "history reset" in body["reason"] and body["sequence"] == 1
    assert body["components"]["top_oil_temperature"]["value"] is None
    assert body["components"]["equivalent_ageing_hours"]["value"] == 0
