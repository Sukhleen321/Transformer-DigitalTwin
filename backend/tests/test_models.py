from datetime import UTC, datetime

import pytest
from sqlalchemy import BigInteger, DateTime, SmallInteger, inspect, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import Alert, Analytics, IngestionRun, MaintenanceRecord, Telemetry, Transformer

NOW = datetime(2026, 10, 6, tzinfo=UTC)
EXCLUDED = {"vl12", "vl23", "vl31"}


def test_metadata_contract() -> None:
    assert set(Base.metadata.tables) == {
        "transformers",
        "telemetry",
        "analytics",
        "alerts",
        "maintenance_records",
        "ingestion_runs",
        "ingestion_receipts",
        "ml_checkpoints",
        "physics_records",
        "physics_profiles",
        "physics_events",
        "physics_checkpoints",
        "live_physics_demo_events",
    }
    for table in Base.metadata.tables.values():
        assert EXCLUDED.isdisjoint(column.name.lower() for column in table.columns)
        for column in table.columns:
            if isinstance(column.type, DateTime):
                assert column.type.timezone is True
    assert isinstance(Telemetry.__table__.c.id.type, BigInteger)
    assert isinstance(Telemetry.__table__.c.oil_temp_alarm.type, SmallInteger)
    assert isinstance(Analytics.__table__.c.health_components.type, JSONB)
    assert all(
        Telemetry.__table__.c[name].nullable
        for name in [
            "oil_temperature",
            "winding_temperature",
            "oil_level",
            "oil_temp_alarm",
        ]
    )
    for name in ["rated_power_kva", "rated_voltage_hv", "rated_voltage_lv", "rated_current_a"]:
        assert Transformer.__table__.c[name].nullable
        assert Transformer.__table__.c[name].default is None


@pytest.mark.postgres
def test_live_columns(db: Session) -> None:
    inspector = inspect(db.connection())
    for table in Base.metadata.tables:
        assert EXCLUDED.isdisjoint(c["name"].lower() for c in inspector.get_columns(table))
    columns = {c["name"]: c for c in inspector.get_columns("telemetry")}
    assert columns["timestamp"]["type"].timezone is True
    analytics_columns = {c["name"]: c for c in inspector.get_columns("analytics")}
    assert isinstance(analytics_columns["health_components"]["type"], JSONB)
    assert db.scalar(text("SHOW server_version_num")) is not None


def add_telemetry(db: Session) -> Telemetry:
    db.add(Transformer(id="TX-test", name="Test asset"))
    db.flush()
    record = Telemetry(transformer_id="TX-test", timestamp=NOW, schema_version="1.0.0")
    db.add(record)
    db.flush()
    return record


@pytest.mark.postgres
def test_all_models_round_trip(db: Session) -> None:
    telemetry = add_telemetry(db)
    assert telemetry.current_l1 is None
    assert telemetry.is_duplicate is False
    assert telemetry.timestamp.utcoffset().total_seconds() == 0
    analytics = Analytics(
        telemetry_id=telemetry.id,
        transformer_id="TX-test",
        timestamp=NOW,
        inference_status="INSUFFICIENT_DATA",
        missing_features=["oil_temperature"],
        schema_version="1.0.0",
        feature_version="1.0.0",
        model_version="stub",
    )
    db.add(analytics)
    db.flush()
    assert analytics.health_index is None
    assert analytics.health_components is None
    alert = Alert(
        transformer_id="TX-test",
        analytics_id=analytics.id,
        telemetry_id=telemetry.id,
        timestamp=NOW,
        severity="WARNING",
        alert_type="DATA_QUALITY",
        trigger="missing",
        evidence={"missing_features": ["oil_temperature"]},
        threshold_or_reason="Missing value",
        recommended_action="Inspect source",
    )
    maintenance = MaintenanceRecord(
        transformer_id="TX-test",
        analytics_id=analytics.id,
        timestamp=NOW,
        priority="WATCH",
        recommendation="Inspect source",
        reason_codes=[],
    )
    run = IngestionRun(source_name="simulator", status="COMPLETED", schema_version="1.0.0")
    db.add_all([alert, maintenance, run])
    db.flush()
    db.expire_all()
    assert db.get(Telemetry, telemetry.id).oil_temperature is None
    assert db.get(Analytics, analytics.id).missing_features == ["oil_temperature"]
    assert db.get(Alert, alert.id).status == "OPEN"
    assert db.get(MaintenanceRecord, maintenance.id).status == "OPEN"
    assert db.get(IngestionRun, run.id).row_count == 0


@pytest.mark.postgres
def test_duplicate_timestamp_rejected(db: Session) -> None:
    add_telemetry(db)
    db.add(Telemetry(transformer_id="TX-test", timestamp=NOW, schema_version="1.0.0"))
    with pytest.raises(IntegrityError):
        db.flush()


@pytest.mark.postgres
@pytest.mark.parametrize("field", ["oil_temp_alarm", "oil_temp_trip", "magnetic_oil_gauge_alarm"])
def test_protection_checks(db: Session, field: str) -> None:
    telemetry = add_telemetry(db)
    setattr(telemetry, field, 2)
    with pytest.raises(IntegrityError):
        db.flush()


@pytest.mark.postgres
@pytest.mark.parametrize(
    "field,value",
    [
        ("anomaly_score", 1.1),
        ("fault_risk", -0.1),
        ("prediction_confidence", 1.1),
        ("health_index", 101),
        ("inference_status", "INVALID"),
        ("maintenance_priority", "INVALID"),
    ],
)
def test_analytics_checks(db: Session, field: str, value: object) -> None:
    telemetry = add_telemetry(db)
    row = Analytics(
        telemetry_id=telemetry.id,
        transformer_id="TX-test",
        timestamp=NOW,
        inference_status="OK",
        schema_version="1.0.0",
        feature_version="1.0.0",
        model_version="stub",
    )
    setattr(row, field, value)
    db.add(row)
    with pytest.raises(IntegrityError):
        db.flush()


@pytest.mark.postgres
def test_analytics_unique_telemetry(db: Session) -> None:
    telemetry = add_telemetry(db)
    for _ in range(2):
        db.add(
            Analytics(
                telemetry_id=telemetry.id,
                transformer_id="TX-test",
                timestamp=NOW,
                inference_status="OK",
                schema_version="1.0.0",
                feature_version="1.0.0",
                model_version="stub",
            )
        )
    with pytest.raises(IntegrityError):
        db.flush()


@pytest.mark.postgres
def test_foreign_key_rejected(db: Session) -> None:
    db.add(Telemetry(transformer_id="unknown", timestamp=NOW, schema_version="1.0.0"))
    with pytest.raises(IntegrityError):
        db.flush()


@pytest.mark.postgres
def test_nullable_json_is_sql_null(db: Session) -> None:
    telemetry = add_telemetry(db)
    row = Analytics(
        telemetry_id=telemetry.id,
        transformer_id="TX-test",
        timestamp=NOW,
        inference_status="INSUFFICIENT_DATA",
        schema_version="1.0.0",
        feature_version="1.0.0",
        model_version="stub",
        health_components=None,
    )
    db.add(row)
    db.flush()
    assert (
        db.scalar(
            text("SELECT health_components IS NULL FROM analytics WHERE id = :id"), {"id": row.id}
        )
        is True
    )
