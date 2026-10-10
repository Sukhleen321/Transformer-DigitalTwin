"""Real PostgreSQL persistence/API checks, with explicitly fictional RC inputs."""

import copy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jsonschema
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from ml.physics.types import iso
from ml.validation.cases import read_case
from ml.validation.harness import modal_reference, snapshot
from sqlalchemy import event as sql_event
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import get_db
from app.main import create_app
from app.models.physics import PhysicsEvent, PhysicsRecord
from app.models.telemetry import Telemetry
from app.models.transformer import Transformer
from app.repositories import physics_repo as store
from app.schemas.telemetry import TelemetryIn
from app.services import ingestion_service
from app.services import physics_codec as codec
from app.services import physics_service as service
from tests.test_h02_contracts import example

EPOCH = datetime(2026, 10, 10, tzinfo=UTC)
NOW = EPOCH + timedelta(seconds=10000)


@pytest.fixture
def configured(db, monkeypatch):
    settings = Settings(_env_file=None, physics_enabled=True)
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    monkeypatch.setattr(ingestion_service, "get_settings", lambda: settings)
    monkeypatch.setattr(service, "clock", lambda: NOW)
    case = read_case()
    p = {k: v["value"] for k, v in case["thermal_parameters"].items()}
    asset = "physics-" + uuid4().hex
    template = snapshot(case, p, EPOCH, 0, "persistence")
    ambient = template.environment["ambient_temperature"]
    ambient = replace(
        ambient,
        value=26.85,
        unit="DEG_C",
        valid_range=(-173.15, 726.85),
        provenance=replace(ambient.provenance, original_unit="DEG_C", original_value=26.85),
    )
    template = replace(template, transformer_id=asset, environment={"ambient_temperature": ambient})
    db.add(Transformer(id=asset, name="Explicit synthetic test asset"))
    db.commit()
    service.publish_profile(db, template, source_name="physics-test")
    db.commit()
    return asset, template, p


def raw(asset, template, seconds, **changes):
    payload = example("telemetry-valid")
    payload.update(
        transformer_id=asset,
        timestamp=iso(EPOCH + timedelta(seconds=seconds)),
        source_name="physics-test",
        ambient_temperature=26.85,
    )
    a = payload["acquisition"]
    a.update(
        source_kind="SIMULATED",
        source_name="physics-test",
        origin_kind="SIMULATED",
        origin_transformer_id=None,
        replay_run_id=None,
        timezone_status="DECLARED_UTC",
        timestamp_origin="SOURCE_SNAPSHOT",
        map_version=template.versions.preprocessing_version,
        snapshot_id=None,
    )
    a["field_verification"] = {k: "SYNTHETIC" for k in a["field_verification"]}
    payload.update(changes)
    return payload


def ingest(db, asset, template, seconds, **changes):
    return ingestion_service.ingest_record(
        db, TelemetryIn.model_validate(raw(asset, template, seconds, **changes)), run_ml=False
    )


def result(db, asset, seconds):
    return service.read(db, asset, EPOCH + timedelta(seconds=seconds)).model_dump(mode="json")


def test_controlled_irregular_times_restart_and_contract(db, configured):
    import json
    from pathlib import Path

    asset, template, p = configured
    for seconds in [0, 0.1, 1, 5, 20, 100]:
        ingest(db, asset, template, seconds)
        r = result(db, asset, seconds)
        schema = json.loads(
            (
                Path(__file__).resolve().parents[2] / "docs/contracts/physics-result-v1.schema.json"
            ).read_text()
        )
        jsonschema.Draft202012Validator(schema).validate(r)
        assert r["context"] == "CONTROLLED_SIMULATION"
        for key in (
            "measured_oil_temperature",
            "ageing_acceleration_factor",
            "equivalent_ageing_hours",
            "fem_hot_spot_temperature",
            "hot_spot_difference",
            "total_loss",
        ):
            assert r["components"][key]["value"] is None
        if seconds == 0:
            assert r["components"]["hot_spot_temperature"]["status"] == "INITIALIZING"
        else:
            exact, *_ = modal_reference(p, seconds)
            assert r["components"]["top_oil_temperature"]["value"] == pytest.approx(
                exact[0] - 273.15, abs=1e-9
            )
            assert r["components"]["hot_spot_temperature"]["value"] == pytest.approx(
                exact[1] - 273.15, abs=1e-9
            )
            assert "SIMPLIFIED_NODE_PROXY" in [
                w["code"] for w in r["components"]["hot_spot_temperature"]["warnings"]
            ]
    # No estimator singleton exists. A fresh Session must recover the same head.
    db.flush()
    with Session(bind=db.get_bind(), join_transaction_mode="create_savepoint") as restarted:
        state = service.restore(restarted, store.checkpoint(restarted, asset), asset)
        assert state.timestamp == EPOCH + timedelta(seconds=100)
        assert service.read(restarted, asset, EPOCH + timedelta(seconds=100)).model_dump(
            mode="json"
        ) == result(db, asset, 100)


def test_retry_conflict_and_late_do_not_advance_head(db, configured):
    asset, t, _ = configured
    ingest(db, asset, t, 0)
    ingest(db, asset, t, 5)
    before = copy.deepcopy(store.checkpoint(db, asset).body)
    retry = ingest(db, asset, t, 5)
    assert retry.duplicate
    assert (
        db.scalar(
            select(func.count())
            .select_from(PhysicsEvent)
            .where(PhysicsEvent.transformer_id == asset)
        )
        == 2
    )
    with pytest.raises(HTTPException) as exc:
        ingest(db, asset, t, 5, ambient_temperature=30.0)
    assert exc.value.status_code == 409
    ingest(db, asset, t, 1)
    assert store.checkpoint(db, asset).body == before
    assert result(db, asset, 1)["components"]["hot_spot_temperature"]["value"] is None
    assert result(db, asset, 5)["components"]["hot_spot_temperature"]["status"] == "READY"


@pytest.mark.parametrize("change", ["missing", "unit", "unverified"])
def test_bad_inputs_break_continuity_without_zero(db, configured, change):
    asset, t, _ = configured
    ingest(db, asset, t, 0)
    payload = raw(asset, t, 1)
    if change == "missing":
        payload["ambient_temperature"] = None
    if change == "unit":
        payload["acquisition"]["field_units"]["ambient_temperature"] = "SOURCE_UNIT"
        payload["acquisition"]["field_verification"]["ambient_temperature"] = "UNVERIFIED"
    if change == "unverified":
        payload["acquisition"]["field_verification"]["ambient_temperature"] = "UNVERIFIED"
    ingestion_service.ingest_record(db, TelemetryIn.model_validate(payload), run_ml=False)
    r = result(db, asset, 1)
    assert r["components"]["hot_spot_temperature"]["value"] is None
    assert store.checkpoint(db, asset).body["state"] is None
    ingest(db, asset, t, 2)
    assert result(db, asset, 2)["components"]["hot_spot_temperature"]["value"] is None


def test_freshness_gap_and_version_change(db, configured):
    asset, t, _ = configured
    ingest(db, asset, t, 0)
    ingest(db, asset, t, 1)
    assert result(db, asset, 61)["components"]["hot_spot_temperature"]["status"] == "READY"
    assert (
        result(db, asset, 61.1)["components"]["hot_spot_temperature"]["status"]
        == "INSUFFICIENT_DATA"
    )
    ingest(db, asset, t, 102)
    assert result(db, asset, 102)["components"]["hot_spot_temperature"]["value"] is None
    new = replace(
        t,
        timestamp=EPOCH + timedelta(seconds=103),
        versions=replace(t.versions, configuration_version="new-config"),
        simulation={
            k: replace(q, effective_at=EPOCH + timedelta(seconds=103))
            for k, q in t.simulation.items()
        },
    )
    service.publish_profile(db, new, source_name="physics-test")
    db.commit()
    assert "VERSION_PENDING_OBSERVATION" in [
        d["code"] for d in result(db, asset, 103)["components"]["top_oil_temperature"]["reasons"]
    ]
    ingest(db, asset, new, 103)
    assert result(db, asset, 103)["components"]["hot_spot_temperature"]["status"] == "INITIALIZING"
    ingest(db, asset, new, 104)
    assert result(db, asset, 104)["components"]["hot_spot_temperature"]["status"] == "READY"


def test_immutable_publication_is_atomic_and_database_protected(db, configured):
    asset, t, _ = configured
    before = db.scalar(select(func.count()).select_from(PhysicsRecord))
    changed = replace(
        t, versions=replace(t.versions, model_version="new-model"), model_parameters={}
    )
    with pytest.raises(HTTPException) as exc:
        service.publish_profile(db, changed, source_name="physics-test")
    assert exc.value.status_code == 409
    assert db.scalar(select(func.count()).select_from(PhysicsRecord)) == before
    for statement in [
        "UPDATE physics_records SET sha256='bad' WHERE transformer_id=:asset",
        "DELETE FROM physics_records WHERE transformer_id=:asset",
    ]:
        with pytest.raises(SQLAlchemyError), db.begin_nested():
            db.execute(text(statement), {"asset": asset})
    assert store.profile(db, asset).configuration_version == t.versions.configuration_version


def test_checkpoint_quarantine_and_explicit_recovery(db, configured):
    asset, t, _ = configured
    ingest(db, asset, t, 0)
    ingest(db, asset, t, 1)
    head = store.checkpoint(db, asset)
    old_id = head.telemetry_id
    head.sha256 = "0" * 64
    db.commit()
    ingest(db, asset, t, 2)
    assert store.checkpoint(db, asset).telemetry_id == old_id
    assert "CHECKPOINT_UNAVAILABLE" in [
        d["code"] for d in result(db, asset, 2)["components"]["top_oil_temperature"]["reasons"]
    ]
    new = replace(
        t,
        timestamp=EPOCH + timedelta(seconds=3),
        versions=replace(t.versions, configuration_version="recovery-v2"),
        simulation={
            k: replace(q, effective_at=EPOCH + timedelta(seconds=3))
            for k, q in t.simulation.items()
        },
    )
    service.publish_profile(db, new, source_name="physics-test", recover=True)
    db.commit()
    ingest(db, asset, new, 3)
    ingest(db, asset, new, 4)
    assert result(db, asset, 4)["components"]["hot_spot_temperature"]["status"] == "READY"


def test_failed_checkpoint_write_rolls_back_telemetry_and_event(db, configured, monkeypatch):
    asset, t, _ = configured
    ingest(db, asset, t, 0)
    before = copy.deepcopy(store.checkpoint(db, asset).body)

    def fail(*args):
        raise RuntimeError("injected persistence failure")

    monkeypatch.setattr(store, "save_checkpoint", fail)
    with pytest.raises(RuntimeError):
        ingest(db, asset, t, 1)
    assert store.checkpoint(db, asset).body == before
    assert (
        db.scalar(
            select(func.count()).select_from(Telemetry).where(Telemetry.transformer_id == asset)
        )
        == 1
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(PhysicsEvent)
            .where(PhysicsEvent.transformer_id == asset)
        )
        == 1
    )


@pytest.mark.parametrize(
    "field,value", [("source_name", "other"), ("map_version", "other-map"), ("origin_kind", "LIVE")]
)
def test_source_conflict_never_exposes_synthetic_values_as_live(db, configured, field, value):
    asset, t, _ = configured
    payload = raw(asset, t, 0)
    payload["acquisition"][field] = value
    if field == "source_name":
        payload["source_name"] = value
    if field == "origin_kind":
        payload["acquisition"].update(source_kind="LIVE", timezone_status="VERIFIED")
        payload["acquisition"]["field_verification"] = {
            k: "VERIFIED" for k in payload["acquisition"]["field_verification"]
        }
    ingestion_service.ingest_record(db, TelemetryIn.model_validate(payload), run_ml=False)
    with pytest.raises(HTTPException) as exc:
        result(db, asset, 0)
    assert exc.value.status_code == 409
    assert store.checkpoint(db, asset).body["state"] is None
    if field == "origin_kind":
        event = db.scalar(select(PhysicsEvent).where(PhysicsEvent.transformer_id == asset))
        assert event.result["lineage"]["origin_kind"] == "LIVE"
        assert all(c["value"] is None for c in event.result["components"].values())


def test_synthetic_configuration_cannot_publish_as_operational(db, configured):
    asset, t, _ = configured
    with pytest.raises(HTTPException) as exc:
        service.publish_profile(
            db,
            replace(t, context="OPERATIONAL", lineage=replace(t.lineage, origin_kind="LIVE")),
            source_name="physics-test",
        )
    assert exc.value.status_code == 422


def test_api_errors_bounded_reads_and_no_read_side_effects(db, configured, client):
    asset, t, _ = configured
    ingest(db, asset, t, 0)
    ingest(db, asset, t, 1)
    path = f"/api/v1/transformers/{asset}/physics"
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    sql_event.listen(db.get_bind(), "before_cursor_execute", capture)
    try:
        first = client.get(path, params={"at": iso(EPOCH + timedelta(seconds=1))})
        second = client.get(path, params={"at": "2026-10-10T05:30:01+05:30"})
    finally:
        sql_event.remove(db.get_bind(), "before_cursor_execute", capture)
    assert first.status_code == 200, first.text
    assert first.json() == second.json()
    assert not any(
        s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for s in statements
    )
    telemetry_reads = [s for s in statements if "FROM telemetry" in s]
    assert telemetry_reads and all("LIMIT" in s and "timestamp >=" in s for s in telemetry_reads)
    assert client.get("/api/v1/transformers/unknown/physics").status_code == 404
    for params in [
        {"at": "2026-10-10T00:00:00"},
        {"at": "garbage"},
        {"at": "2027-01-01T00:00:00Z"},
        {"bad": "1"},
    ]:
        r = client.get(path, params=params, headers={"X-Request-ID": "physics-invalid"})
        assert r.status_code == 422
        assert r.headers["X-Request-ID"] == "physics-invalid"
    assert client.post(path, json={}).status_code == 405


def test_missing_profile_disabled_and_newer_unprocessed_never_reuse_old_value(
    db, configured, monkeypatch
):
    asset, t, _ = configured
    ingest(db, asset, t, 0)
    ingest(db, asset, t, 1)
    monkeypatch.setattr(
        ingestion_service, "get_settings", lambda: Settings(_env_file=None, physics_enabled=False)
    )
    ingest(db, asset, t, 2)
    r = result(db, asset, 2)
    assert all(c["value"] is None for c in r["components"].values())
    assert r["timestamp"] == iso(EPOCH + timedelta(seconds=2))
    monkeypatch.setattr(
        ingestion_service, "get_settings", lambda: Settings(_env_file=None, physics_enabled=True)
    )
    ingest(db, asset, t, 3)
    assert "UNPROCESSED_INTERVAL" in [
        d["code"] for d in result(db, asset, 3)["components"]["hot_spot_temperature"]["reasons"]
    ]
    monkeypatch.setattr(
        service, "get_settings", lambda: Settings(_env_file=None, physics_enabled=False)
    )
    assert all(c["value"] is None for c in result(db, asset, 1)["components"].values())
    other = "unconfigured-" + uuid4().hex
    db.add(Transformer(id=other, name="No equipment data"))
    db.commit()
    assert result(db, other, 0)["timestamp"] is None


def test_internal_failure_is_sanitized_and_correlated(db, configured, monkeypatch):
    asset, _, _ = configured

    def fail(*args, **kwargs):
        raise RuntimeError("SECRET-TEST-INTERNAL")

    monkeypatch.setattr(service, "read", fail)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get(
            f"/api/v1/transformers/{asset}/physics", headers={"X-Request-ID": "physics-failure"}
        )
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "SECRET-TEST-INTERNAL" not in r.text
    assert r.headers["X-Request-ID"] == "physics-failure"


@pytest.mark.parametrize("cap", [1, 3])
def test_event_and_record_caps_are_asset_local(db, configured, monkeypatch, cap):
    asset, t, _ = configured
    monkeypatch.setattr(store, "MAX_EVENTS", cap)
    for seconds in range(8):
        ingest(db, asset, t, seconds)
    assert (
        db.scalar(
            select(func.count())
            .select_from(PhysicsEvent)
            .where(PhysicsEvent.transformer_id == asset)
        )
        == cap
    )
    assert store.checkpoint(db, asset).event_time == EPOCH + timedelta(seconds=7)
    assert result(db, asset, 0)["components"]["hot_spot_temperature"]["value"] is None
    monkeypatch.setattr(store, "MAX_RECORDS", 1)
    new = replace(
        t,
        timestamp=EPOCH + timedelta(seconds=8),
        versions=replace(t.versions, configuration_version="over-cap"),
    )
    with pytest.raises(HTTPException) as exc:
        service.publish_profile(db, new, source_name="physics-test")
    assert exc.value.status_code == 422
    assert store.profile(db, asset).configuration_version == t.versions.configuration_version


@pytest.mark.parametrize("blocked", [None, "rating", "reference", "rms", "current"])
def test_optional_loss_requires_all_explicit_inputs(db, configured, blocked):
    from ml.physics import Provenance, Quantity

    asset, t, _ = configured
    ref = t.lineage.evidence_references[0]

    def q(value, unit, kind, semantics=None, bounds=None):
        return Quantity(
            value,
            unit,
            kind,
            "SYNTHETIC",
            Provenance(ref, ref, t.evidence[ref].applicability, unit, value, semantics=semantics),
            EPOCH,
            bounds,
        )

    observed = {
        f"current_l{i}": q(10.0, "A", "current", "RMS_LINE_CURRENT_LV", (0.0, 100.0))
        for i in (1, 2, 3)
    }
    params = dict(t.model_parameters) | {
        "no_load_loss": q(10.0, "W", "active_power"),
        "rated_load_loss": q(30.0, "W", "active_power"),
        "loss_reference_temperature": q(300.0, "K", "absolute_temperature"),
    }
    equipment = {"rated_current_a": q(10.0, "A", "current")}
    selection = replace(
        t.selection,
        loss_enabled=True,
        measurement_side="LV",
        current_basis="RMS_LINE_CURRENT",
        loss_basis_reference=ref,
        energized=True,
    )
    if blocked == "rating":
        equipment = {}
    if blocked == "reference":
        params.pop("loss_reference_temperature")
    if blocked == "rms":
        selection = replace(selection, current_basis=None)
    if blocked == "current":
        observed.pop("current_l3")
    new = replace(
        t,
        versions=replace(
            t.versions,
            configuration_version="loss-config",
            parameter_version="loss-params",
            preprocessing_version="loss-map",
        ),
        observed=observed,
        model_parameters=params,
        equipment=equipment,
        selection=selection,
    )
    service.publish_profile(db, new, source_name="physics-test")
    db.commit()
    payload = raw(asset, new, 0, current_l1=10.0, current_l2=10.0, current_l3=10.0)
    payload["acquisition"]["measurement_side"] = "LV"
    ingestion_service.ingest_record(db, TelemetryIn.model_validate(payload), run_ml=False)
    c = result(db, asset, 0)["components"]["total_loss"]
    if blocked is None:
        assert c["value"] == 40.0, c["reasons"]
    else:
        assert c["value"] is None


@pytest.mark.parametrize("missing", ["evidence", "parameters", "configuration", "map"])
def test_missing_identity_is_unavailable(db, configured, monkeypatch, missing):
    asset, t, _ = configured
    original = store.resolve
    kinds = {
        "evidence": "EVIDENCE",
        "parameters": "PARAMETERS",
        "configuration": "CONFIGURATION",
        "map": "SOURCE_MAP",
    }

    def unavailable(session, asset, kind, version):
        if kind == kinds[missing]:
            raise ValueError("deliberately absent identity")
        return original(session, asset, kind, version)

    monkeypatch.setattr(store, "resolve", unavailable)
    ingest(db, asset, t, 0)
    assert all(c["value"] is None for c in result(db, asset, 0)["components"].values())


def test_unverified_parameters_and_missing_evidence_do_not_get_defaults(db, configured):
    asset, t, _ = configured
    parameters = {k: replace(q, verification="UNVERIFIED") for k, q in t.model_parameters.items()}
    new = replace(
        t,
        versions=replace(
            t.versions, configuration_version="unverified", parameter_version="unverified-params"
        ),
        model_parameters=parameters,
    )
    service.publish_profile(db, new, source_name="physics-test")
    db.commit()
    ingest(db, asset, new, 0)
    assert result(db, asset, 0)["components"]["hot_spot_temperature"]["value"] is None
    assert store.checkpoint(db, asset).body["state"] is None


def test_committed_restart_and_failed_commit(db_engine, monkeypatch):
    # Unlike the regular rollback fixture, this commits to the disposable DB.
    settings = Settings(_env_file=None, physics_enabled=True)
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    monkeypatch.setattr(ingestion_service, "get_settings", lambda: settings)
    monkeypatch.setattr(service, "clock", lambda: NOW)
    case = read_case()
    p = {k: v["value"] for k, v in case["thermal_parameters"].items()}
    asset = "durable-" + uuid4().hex
    t = replace(snapshot(case, p, EPOCH, 0, "durable"), transformer_id=asset)
    q = t.environment["ambient_temperature"]
    t = replace(
        t,
        environment={
            "ambient_temperature": replace(
                q,
                value=26.85,
                unit="DEG_C",
                valid_range=(-173.15, 726.85),
                provenance=replace(q.provenance, original_unit="DEG_C", original_value=26.85),
            )
        },
    )
    with Session(db_engine) as first:
        first.add(Transformer(id=asset, name="Synthetic committed restart"))
        first.commit()
        service.publish_profile(first, t, source_name="physics-test")
        first.commit()
        ingest(first, asset, t, 0)
        ingest(first, asset, t, 1)
        before = copy.deepcopy(store.checkpoint(first, asset).body)
    with Session(db_engine) as second:
        assert service.restore(
            second, store.checkpoint(second, asset), asset
        ).timestamp == EPOCH + timedelta(seconds=1)

        def fail_commit(session):
            raise RuntimeError("injected commit failure")

        sql_event.listen(second, "before_commit", fail_commit)
        try:
            with pytest.raises(RuntimeError):
                ingest(second, asset, t, 2)
        finally:
            sql_event.remove(second, "before_commit", fail_commit)
    with Session(db_engine) as third:
        assert store.checkpoint(third, asset).body == before
        assert (
            third.scalar(
                select(func.count()).select_from(Telemetry).where(Telemetry.transformer_id == asset)
            )
            == 2
        )
        ingest(third, asset, t, 2)
        assert result(third, asset, 2)["components"]["hot_spot_temperature"]["status"] == "READY"


def test_asset_ownership_and_incompatible_codec_quarantine(db, configured):
    asset, t, _ = configured
    ingest(db, asset, t, 0)
    head = store.checkpoint(db, asset)
    body = copy.deepcopy(head.body)
    body["owner"] = "different-asset"
    head.body = body
    head.sha256 = codec.digest(body)
    db.commit()
    ingest(db, asset, t, 1)
    assert result(db, asset, 1)["components"]["hot_spot_temperature"]["value"] is None
    assert store.checkpoint(db, asset).telemetry_id == head.telemetry_id


def test_receipt_retention_keeps_checkpoint_and_unbounded_time_is_not_queried(
    db, configured, monkeypatch
):
    asset, t, _ = configured
    # Server clock is already later than event time. Retention is by receipt,
    # not an invented timestamp-derived receipt time.
    ingest(db, asset, t, 0)
    ingest(db, asset, t, 1)
    first = db.scalar(
        select(PhysicsEvent)
        .where(PhysicsEvent.transformer_id == asset)
        .order_by(PhysicsEvent.event_time)
    )
    assert first.received_at != first.event_time
    monkeypatch.setattr(service, "clock", lambda: datetime.now(UTC) + timedelta(days=32))
    ingest(db, asset, t, 2)
    assert (
        db.scalar(
            select(func.count())
            .select_from(PhysicsEvent)
            .where(PhysicsEvent.transformer_id == asset)
        )
        == 1
    )
    assert store.checkpoint(db, asset).event_time == EPOCH + timedelta(seconds=2)
    assert service.read(db, asset).timestamp is None  # outside explicit 31-day event window


def test_legacy_public_schema_and_no_fem_execution(db, configured, client, monkeypatch):
    from ml.fem import solver

    asset, t, _ = configured

    def forbidden(*args, **kwargs):
        raise AssertionError("FEM must not run in the server")

    monkeypatch.setattr(solver, "solve_steady", forbidden)
    before = set(client.get(f"/api/v1/transformers/{asset}/latest").json())
    ingest(db, asset, t, 0)
    ingest(db, asset, t, 1)
    after = client.get(f"/api/v1/transformers/{asset}/latest")
    assert after.status_code == 200
    assert set(after.json()) == before
    assert "physics" not in after.json()
    assert result(db, asset, 1)["components"]["fem_hot_spot_temperature"]["value"] is None


def test_parameter_change_and_recovery_require_new_identity(db, configured):
    asset, t, _ = configured
    ingest(db, asset, t, 0)
    with pytest.raises(HTTPException) as exc:
        service.publish_profile(db, t, source_name="physics-test", recover=True)
    assert exc.value.status_code == 409
    parameters = dict(t.model_parameters)
    q = parameters["oil_thermal_resistance"]
    parameters["oil_thermal_resistance"] = replace(
        q, value=2.0, provenance=replace(q.provenance, original_value=2.0)
    )
    changed = replace(
        t,
        model_parameters=parameters,
        versions=replace(t.versions, configuration_version="param-change"),
        timestamp=EPOCH + timedelta(seconds=1),
    )
    with pytest.raises(HTTPException) as exc:
        service.publish_profile(db, changed, source_name="physics-test")
    assert exc.value.status_code == 409
    changed = replace(
        changed,
        versions=replace(changed.versions, parameter_version="params-v2"),
        simulation={
            k: replace(q, effective_at=changed.timestamp) for k, q in changed.simulation.items()
        },
    )
    service.publish_profile(db, changed, source_name="physics-test")
    db.commit()
    ingest(db, asset, changed, 1)
    ingest(db, asset, changed, 2)
    assert result(db, asset, 2)["versions"]["parameter_version"] == "params-v2"
    assert result(db, asset, 2)["components"]["hot_spot_temperature"]["status"] == "READY"


def test_corrupt_current_checkpoint_is_withheld_on_read(db, configured):
    asset, t, _ = configured
    ingest(db, asset, t, 0)
    ingest(db, asset, t, 1)
    head = store.checkpoint(db, asset)
    head.sha256 = "0" * 64
    db.commit()
    c = result(db, asset, 1)["components"]["hot_spot_temperature"]
    assert c["value"] is None
    assert "CHECKPOINT_UNAVAILABLE" in [d["code"] for d in c["reasons"]]


def test_startup_readiness_and_openapi_include_separate_resource(client):
    assert client.get("/health").status_code == 200
    assert client.get("/health/ready").status_code == 200
    operations = client.get("/openapi.json").json()["paths"]
    path = "/api/v1/transformers/{transformer_id}/physics"
    assert set(operations[path]) == {"get"}
    assert {"200", "404", "409", "422", "500"} <= set(operations[path]["get"]["responses"])


def test_quarantined_head_counts_toward_retention_cap(db, configured, monkeypatch):
    asset, t, _ = configured
    monkeypatch.setattr(store, "MAX_EVENTS", 3)
    ingest(db, asset, t, 0)
    head = store.checkpoint(db, asset)
    protected_id = head.telemetry_id
    head.sha256 = "0" * 64
    db.commit()
    for seconds in range(1, 8):
        ingest(db, asset, t, seconds)
    assert (
        db.scalar(
            select(func.count())
            .select_from(PhysicsEvent)
            .where(PhysicsEvent.transformer_id == asset)
        )
        == 3
    )
    assert db.get(PhysicsEvent, protected_id) is not None
    assert store.checkpoint(db, asset).telemetry_id == protected_id


def test_concurrent_exact_retries_share_one_durable_advance(db_engine, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    settings = Settings(_env_file=None, physics_enabled=True)
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    monkeypatch.setattr(ingestion_service, "get_settings", lambda: settings)
    monkeypatch.setattr(service, "clock", lambda: NOW)
    case = read_case()
    p = {k: v["value"] for k, v in case["thermal_parameters"].items()}
    asset = "concurrent-" + uuid4().hex
    t = replace(snapshot(case, p, EPOCH, 0, "concurrent"), transformer_id=asset)
    q = t.environment["ambient_temperature"]
    t = replace(
        t,
        environment={
            "ambient_temperature": replace(
                q,
                value=26.85,
                unit="DEG_C",
                valid_range=(-173.15, 726.85),
                provenance=replace(q.provenance, original_unit="DEG_C", original_value=26.85),
            )
        },
    )
    with Session(db_engine) as session:
        session.add(Transformer(id=asset, name="Synthetic concurrent retries"))
        session.commit()
        service.publish_profile(session, t, source_name="physics-test")
        session.commit()
        ingest(session, asset, t, 0)

    def worker():
        with Session(db_engine) as session:
            return ingest(session, asset, t, 1).duplicate

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(lambda _: worker(), range(2))) == [False, True]
    with Session(db_engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(PhysicsEvent)
                .where(PhysicsEvent.transformer_id == asset)
            )
            == 2
        )
        assert result(session, asset, 1)["components"]["hot_spot_temperature"]["status"] == "READY"
