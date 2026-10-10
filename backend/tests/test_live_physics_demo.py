"""PostgreSQL/API tests using ONLY a newly named demo database."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.main import create_app
from app.models.live_physics_demo import LivePhysicsDemoEvent
from app.models.transformer import Transformer
from app.schemas.live_physics_demo import LivePhysicsDemoResult
from app.services import live_physics_demo as demo
from app.services import physics_codec as codec
from tests.conftest import migration_config


@pytest.fixture(scope="module")
def demo_engine():
    raw = os.environ.get("TEST_DATABASE_URL")
    if not raw:
        pytest.skip("TEST_DATABASE_URL required")
    base = make_url(raw)
    name = "live_physics_demo_" + uuid4().hex
    admin = base.set(drivername="postgresql", database="postgres").render_as_string(
        hide_password=False
    )
    target = base.set(database=name).render_as_string(hide_password=False)
    with psycopg.connect(admin, autocommit=True) as db:
        db.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    engine = create_engine(target)
    try:
        command.upgrade(migration_config(target), "head")
        yield engine
    finally:
        engine.dispose()
        with psycopg.connect(admin, autocommit=True) as db:
            db.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def environment(demo_engine, monkeypatch):
    with demo_engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
            settings = Settings(
                _env_file=None,
                database_url=demo_engine.url.render_as_string(hide_password=False),
                env="local-demo",
                physics_enabled=True,
                live_physics_demo_enabled=True,
            )
            monkeypatch.setattr(demo, "get_settings", lambda: settings)
            asset = "DEMO-" + uuid4().hex[:8]
            db.add(Transformer(id=asset, name="LIVE SIMULATION · " + asset))
            db.flush()
            app = create_app()
            app.dependency_overrides[get_settings] = lambda: settings
            app.dependency_overrides[get_db] = lambda: db
            with TestClient(app) as client:
                yield db, client, settings, asset
        transaction.rollback()


def events(db, asset, offset=10):
    run_id = uuid4().hex
    epoch = datetime.now(UTC) - timedelta(seconds=offset)
    a = demo.write(db, asset, epoch, run_id)
    b = demo.write(db, asset, epoch + timedelta(seconds=4), run_id)
    return a, b, epoch, run_id


def test_real_numeric_api_and_checkpoint_resume(environment):
    db, client, _, asset = environment
    a, b, epoch, run_id = events(db, asset)
    assert a["status"] == "INITIALIZING" and b["status"] == "READY"
    response = client.get(f"/api/v1/demo/transformers/{asset}/physics")
    assert response.status_code == 200
    parsed = LivePhysicsDemoResult.model_validate(response.json())
    assert all(c.value is not None for c in parsed.components.values())
    before = db.scalar(select(func.count()).select_from(LivePhysicsDemoEvent))
    client.get(f"/api/v1/demo/transformers/{asset}/physics")
    assert db.scalar(select(func.count()).select_from(LivePhysicsDemoEvent)) == before
    c = demo.write(db, asset, epoch + timedelta(seconds=8), run_id)
    assert c["sequence"] == 3
    for key in ("hot_spot_temperature", "measured_oil_temperature", "equivalent_ageing_hours"):
        assert c["components"][key]["value"] > b["components"][key]["value"]
    production = client.get(f"/api/v1/transformers/{asset}/physics")
    assert production.status_code == 200
    assert all(c["value"] is None for c in production.json()["components"].values())


def test_router_passes_effective_dependency_to_service(environment, monkeypatch):
    db, client, settings, asset = environment
    events(db, asset)
    # Dependency override is authoritative; a second service lookup must not
    # accidentally replace it with an unrelated disabled settings instance.
    monkeypatch.setattr(demo, "get_settings", lambda: Settings(_env_file=None))
    response = client.get(f"/api/v1/demo/transformers/{asset}/physics")
    assert response.status_code == 200
    assert response.json()["status"] == "READY"
    settings.live_physics_demo_enabled = False
    assert client.get(f"/api/v1/demo/transformers/{asset}/physics").status_code == 404


def test_known_fictional_asset_identity_uses_existing_synthetic_case(environment):
    db, client, _, _ = environment
    asset = "KA-BLR-KOR-TX01"
    db.add(Transformer(id=asset, name="LIVE SIMULATION · " + asset))
    db.flush()
    events(db, asset)
    response = client.get(f"/api/v1/demo/transformers/{asset}/physics")
    assert response.status_code == 200
    parsed = LivePhysicsDemoResult.model_validate(response.json())
    assert parsed.transformer_id == asset
    assert all(c.status == "READY" and c.value is not None for c in parsed.components.values())


def test_raw_event_atomic_persistence_and_result_link(environment):
    db, client, _, asset = environment
    _, b, epoch, run_id = events(db, asset)
    head = demo.latest(db, asset)
    raw = head.checkpoint["raw_event"]
    assert raw["sequence"] == b["sequence"] == head.sequence
    assert raw["transformer_id"] == asset and raw["run_id"] == run_id
    assert raw["timestamp"] == b["timestamp"]
    assert raw["values"]["current_a"]["value"] == b["inputs"]["current_a"]
    assert (
        raw["values"]["oil_sensor_k"]["value"] - 273.15
        == b["components"]["measured_oil_temperature"]["value"]
    )
    assert codec.digest(dict(result=head.result, checkpoint=head.checkpoint)) == head.sha256
    demo.write(db, asset, epoch + timedelta(seconds=8), run_id)
    assert demo.latest(db, asset).checkpoint["raw_event"]["event_id"] != raw["event_id"]
    assert client.get(f"/api/v1/demo/transformers/{asset}/physics").status_code == 200


@pytest.mark.parametrize("damage", ["missing", "null", "unit", "identity", "result-link"])
def test_raw_corruption_rejected_even_with_recomputed_digest(environment, damage):
    import copy

    db, client, _, asset = environment
    events(db, asset)
    head = demo.latest(db, asset)
    cp = copy.deepcopy(head.checkpoint)
    raw = cp["raw_event"]
    if damage == "missing":
        del raw["values"]["ambient_k"]
    elif damage == "null":
        raw["values"]["current_a"]["value"] = None  # JSON null must not become zero
    elif damage == "unit":
        raw["values"]["oil_sensor_k"]["unit"] = "DEG_C"
    elif damage == "identity":
        raw["transformer_id"] = "OTHER"
    else:
        raw["values"]["oil_sensor_k"]["value"] += 1
    head.checkpoint = cp
    head.sha256 = codec.digest(dict(result=head.result, checkpoint=cp))
    db.flush()
    assert client.get(f"/api/v1/demo/transformers/{asset}/physics").status_code == 503


@pytest.mark.parametrize(
    "setting,value",
    [
        ("physics_enabled", False),
        ("live_physics_demo_enabled", False),
        ("env", "production"),
        ("database_url", "postgresql+psycopg://x:x@localhost/retained"),
    ],
)
def test_disabled_and_retained_environment_rejected(environment, setting, value):
    db, client, settings, asset = environment
    setattr(settings, setting, value)
    assert client.get(f"/api/v1/demo/transformers/{asset}/physics").status_code == 404
    with pytest.raises(ValueError, match="restricted"):
        demo.write(db, asset, datetime.now(UTC), uuid4().hex)


def test_no_event_unknown_asset_and_query(environment):
    _, client, _, asset = environment
    assert client.get(f"/api/v1/demo/transformers/{asset}/physics").status_code == 404
    assert client.get("/api/v1/demo/transformers/MISSING/physics").status_code == 404
    assert client.get(f"/api/v1/demo/transformers/{asset}/physics?at=x").status_code == 422


def test_stale_values_withheld(environment):
    db, client, _, asset = environment
    events(db, asset, offset=25)
    response = client.get(f"/api/v1/demo/transformers/{asset}/physics")
    assert response.status_code == 200
    assert response.json()["status"] == "UNAVAILABLE"
    assert all(c["value"] is None for c in response.json()["components"].values())


@pytest.mark.parametrize("damage", ["digest", "checkpoint", "identity", "model"])
def test_corruption_withheld(environment, damage):
    db, client, _, asset = environment
    events(db, asset)
    head = demo.latest(db, asset)
    if damage == "digest":
        head.sha256 = "0" * 64
    else:
        if damage == "model":
            head.checkpoint = dict(head.checkpoint, model_digest="0" * 64)
        elif damage == "checkpoint":
            head.checkpoint = dict(head.checkpoint, fields=[300])
        else:
            head.result = dict(head.result, transformer_id="WRONG-ASSET")
        head.sha256 = codec.digest(dict(result=head.result, checkpoint=head.checkpoint))
    db.flush()
    assert client.get(f"/api/v1/demo/transformers/{asset}/physics").status_code == 503


def test_transaction_rollback_late_event_and_producer_identity(environment):
    db, _, _, asset = environment
    _, _, epoch, run_id = events(db, asset)
    with db.begin_nested() as transaction:
        demo.write(db, asset, epoch + timedelta(seconds=8), run_id)
        transaction.rollback()
    assert demo.latest(db, asset).sequence == 2
    for time, owner in [(epoch, run_id), (epoch + timedelta(seconds=8), uuid4().hex)]:
        with pytest.raises(ValueError):
            demo.write(db, asset, time, owner)
    assert demo.latest(db, asset).sequence == 2
