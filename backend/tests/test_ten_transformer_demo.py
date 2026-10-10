"""All ten assets through actual generator, map, MQTT decoder and demo equations."""

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.core.config import Settings
from app.mqtt import message_handler
from app.mqtt.message_handler import MessageRejected, parse_message
from app.schemas.live_physics_demo import LivePhysicsDemoResult
from app.services.demo_telemetry import inputs
from simulator.fleet import load_runtime_config, registry_payloads
from simulator.register_map import decode, encode
from simulator.scheduler import Scheduler
from simulator.streaming import MqttPublisher

from ml.demo_physics.fem import SheetFEM
from ml.demo_physics.fleet import asset_ids, load_fleet
from ml.demo_physics.scenario import DemoRun
from ml.pipeline.identity import serialize

CONFIG = Path(__file__).resolve().parents[2] / "simulator/config"
EPOCH = datetime(2026, 10, 11, tzinfo=UTC)


def pipeline():
    return Scheduler(load_runtime_config(CONFIG / "physics-demo-server.json", "server", EPOCH))


def decoded(clock, record):
    return decode(
        encode(record, clock.unit_id),
        transformer_id=record.transformer_id,
        unit_id=clock.unit_id,
        gateway_id="KA-BLR-SIM-GW",
        expected_interval_seconds=5,
    )


def source(record, identifier=1):
    data = record.model_dump()
    data.update(
        id=identifier, ingestion_outcome="ACCEPTED", payload_hash=data["acquisition"]["snapshot_id"]
    )
    return SimpleNamespace(**data)


def test_all_ten_mqtt_inputs_drive_independent_numeric_demo_results(monkeypatch):
    fleet = load_fleet(CONFIG / "operational-fleet.json")
    assets = asset_ids(CONFIG / "operational-fleet.json")
    assert len(assets) == 10
    assert [a["unit_id"] for a in fleet["assets"]] == list(range(1, 11))
    assert assets == (
        "KA-BLR-KOR-TX01",
        "KA-BLR-KOR-TX02",
        "KA-BLR-KOR-TX03",
        "KA-BLR-KOR-TX04",
        "KA-BLR-HSR-TX05",
        "KA-BLR-HSR-TX06",
        "KA-BLR-HSR-TX07",
        "KA-BLR-HSR-TX08",
        "KA-BLR-BTM-TX09",
        "KA-BLR-BTM-TX10",
    )
    monkeypatch.setattr(message_handler, "get_settings", lambda: Settings(_env_file=None))
    registry = {p["id"]: SimpleNamespace(**p) for p in registry_payloads(fleet)}
    fem = SheetFEM(4)
    runs = {a: DemoRun(a, EPOCH, "a" * 32, fem, variable_ambient=True) for a in assets}
    scheduler, repeat = pipeline(), pipeline()
    published = []

    def publish(topic, payload, *, qos, retain):
        assert qos == 1 and retain is False
        published.append((topic, payload))
        return SimpleNamespace(
            rc=0, mid=1, wait_for_publish=lambda **kwargs: None, is_published=lambda: True
        )

    publisher = MqttPublisher(host="mqtt", port=1883)
    publisher._connected = True
    publisher._client = SimpleNamespace(publish=publish)
    final = {}
    for cycle in range(3):
        records, identical = scheduler.tick(), repeat.tick()
        for asset, generated in records.items():
            assert generated.model_dump() == identical[asset].model_dump()
            wire = decoded(scheduler.assets[asset], generated)
            topic = f"transformer/{asset}/telemetry"
            ack = publisher.publish(wire)
            assert ack["broker_acknowledged"] and not ack["committed"]
            sent_topic, payload = published[-1]
            assert sent_topic == topic
            record = parse_message(sent_topic, payload.encode())[0]
            operating = inputs(source(record), registry[asset], fleet, record.timestamp)
            run = runs[asset]
            raw = run.generate(record.timestamp, operating)
            result = LivePhysicsDemoResult.model_validate(run.advance(record.timestamp, raw))
            assert result.transformer_id == asset
            assert result.inputs.current_a == pytest.approx(
                10
                * sum(getattr(record, f"current_l{i}") for i in (1, 2, 3))
                / (3 * fleet["configuration"]["rated_current_a"])
            )
            assert result.components["measured_oil_temperature"].value == pytest.approx(
                record.oil_temperature
            )
            assert result.components["total_loss"].value == pytest.approx(
                6 + 30 * (result.inputs.current_a / 10) ** 2
            )
            assert abs(result.components["hot_spot_difference"].value) < 1e-8
            if cycle:
                assert all(
                    c.status == "READY" and c.value is not None for c in result.components.values()
                )
                assert (
                    result.components["equivalent_ageing_hours"].value
                    > final[asset].components["equivalent_ageing_hours"].value
                )
            final[asset] = result
    assert len({r.inputs.current_a for r in final.values()}) == 10
    assert len({r.components["hot_spot_temperature"].value for r in final.values()}) == 10
    unaffected = runs[assets[1]].estimator.state(assets[1])
    runs[assets[0]].advance(EPOCH + timedelta(seconds=15))
    assert runs[assets[1]].estimator.state(assets[1]) is unaffected
    assert len({id(r.fields) for r in runs.values()}) == 10
    with pytest.raises(MessageRejected, match="TOPIC_ID_MISMATCH"):
        parse_message(
            f"transformer/{assets[1]}/telemetry", serialize(wire.model_dump(mode="json")).encode()
        )


@pytest.mark.parametrize(
    "flaw",
    [
        "missing",
        "nan",
        "inf",
        "bool",
        "unit",
        "unverified",
        "measured",
        "wrong_asset",
        "wrong_registry",
        "stale",
        "future",
        "hash",
        "negative",
        "out_of_range",
    ],
)
def test_invalid_source_is_rejected_without_affecting_other_assets(flaw):
    fleet = load_fleet(CONFIG / "operational-fleet.json")
    scheduler = pipeline()
    asset, generated = next(iter(scheduler.tick().items()))
    row = source(decoded(scheduler.assets[asset], generated))
    registry = SimpleNamespace(**registry_payloads(fleet)[0])
    now = row.timestamp
    if flaw in ("missing", "nan", "inf", "bool", "negative", "out_of_range"):
        row.current_l1 = {
            "missing": None,
            "nan": float("nan"),
            "inf": float("inf"),
            "bool": True,
            "negative": -1,
            "out_of_range": 1000,
        }[flaw]
    elif flaw == "unit":
        row.acquisition["field_units"]["ambient_temperature"] = "K"
    elif flaw == "unverified":
        row.acquisition["field_verification"]["oil_temperature"] = "UNVERIFIED"
    elif flaw == "measured":
        row.acquisition["source_kind"] = "MEASURED"
    elif flaw == "wrong_asset":
        row.transformer_id = "UNKNOWN"
    elif flaw == "wrong_registry":
        registry.rated_current_a = 10
    elif flaw == "stale":
        now += timedelta(seconds=16)
    elif flaw == "future":
        now -= timedelta(seconds=1)
    elif flaw == "hash":
        row.payload_hash = "wrong"
    with pytest.raises(ValueError):
        inputs(row, registry, fleet, now)


def test_variable_ambient_requires_explicit_mode_and_fem_tracks_previous_forcing():
    run = DemoRun("SYNTHETIC", EPOCH, "b" * 32, variable_ambient=True)
    for i in range(4):
        event = EPOCH + timedelta(seconds=5 * i)
        raw = run.generate(
            event, dict(current_a=5 + i / 10, ambient_k=302 + i / 5, oil_sensor_k=310)
        )
        result = run.advance(event, raw)
        assert abs(result["components"]["hot_spot_difference"]["value"]) < 1e-8
    baseline = DemoRun("SYNTHETIC", EPOCH, "b" * 32)
    with pytest.raises(ValueError):
        baseline.generate(EPOCH, dict(current_a=5, ambient_k=302, oil_sensor_k=310))
    with pytest.raises(ValueError):
        run.generate(EPOCH + timedelta(seconds=100))


def test_shared_fleet_loader_rejects_duplicate_and_non_synthetic_configuration(tmp_path):
    fleet = load_fleet(CONFIG / "operational-fleet.json")
    for flaw in ("duplicate", "rating", "real"):
        invalid = copy.deepcopy(fleet)
        if flaw == "duplicate":
            invalid["assets"][1]["unit_id"] = 1
        elif flaw == "rating":
            invalid["configuration"]["rated_current_a"] = 0
        else:
            invalid["configuration"]["configuration_status"] = "VERIFIED"
        path = tmp_path / "fleet.json"
        path.write_text(json.dumps(invalid))
        with pytest.raises(ValueError):
            load_fleet(path)
