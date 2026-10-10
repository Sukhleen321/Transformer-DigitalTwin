"""Browser-free acceptance against owned current-source processes and their DB."""

import json
from datetime import UTC, datetime
from time import sleep
from types import SimpleNamespace

import httpx
import psycopg
from ml.demo_physics.scenario import validate_raw
from sqlalchemy.engine import make_url

from app.schemas.live_physics_demo import UNITS, LivePhysicsDemoResult
from app.services.live_physics_demo import restore


def verify_pipeline(api, web, target, samples, out, interval, producer, assets):
    assert make_url(target).database.startswith("live_physics_demo_")
    report = {"checks": [], "raw_events": []}
    primary, secondary = assets[:2]
    for sample in samples:
        parsed = LivePhysicsDemoResult.model_validate(sample)
        assert parsed.transformer_id == primary
        assert all(c.status == "READY" and c.value is not None for c in parsed.components.values())
        assert all(c.unit == UNITS[name] for name, c in parsed.components.items())
        assert all(c.provenance == "SYNTHETIC_SIMULATED" for c in parsed.components.values())
    for name in UNITS:
        if name != "hot_spot_difference":
            assert (
                samples[0]["components"][name]["value"] != samples[1]["components"][name]["value"]
            ), name
    assert abs(samples[1]["components"]["hot_spot_difference"]["value"]) < 1e-8
    connection_url = target.replace("postgresql+psycopg:", "postgresql:")
    with psycopg.connect(connection_url, connect_timeout=5) as db:
        for sample in samples:
            row = db.execute(
                "SELECT transformer_id, run_id, sequence, timestamp, result, checkpoint, sha256 "
                "FROM live_physics_demo_events "
                "WHERE transformer_id=%s AND run_id=%s AND sequence=%s",
                (sample["transformer_id"], sample["run_id"], sample["sequence"]),
            ).fetchone()
            assert row is not None
            stored = SimpleNamespace(
                **dict(
                    zip(
                        (
                            "transformer_id",
                            "run_id",
                            "sequence",
                            "timestamp",
                            "result",
                            "checkpoint",
                            "sha256",
                        ),
                        row,
                        strict=True,
                    )
                )
            )
            restored = restore(stored)
            raw = stored.checkpoint["raw_event"]
            numbers = validate_raw(
                raw, stored.transformer_id, stored.run_id, stored.sequence, stored.timestamp
            )
            assert numbers == {
                **sample["inputs"],
                "load_fraction": numbers["load_fraction"],
                "oil_sensor_k": numbers["oil_sensor_k"],
            }
            assert restored.sequence == stored.sequence
            assert restored.estimator.state(stored.transformer_id).timestamp == stored.timestamp
            for name in UNITS:
                assert stored.result["components"][name] == sample["components"][name]
            report["raw_events"].append(
                {"raw_event": raw, "thermal_state": stored.checkpoint["thermal"]}
            )
        assert (
            report["raw_events"][0]["raw_event"]["event_id"]
            != report["raw_events"][1]["raw_event"]["event_id"]
        )
        db.execute(
            "INSERT INTO transformers (id, name) VALUES (%s, %s)",
            ("LIVE-DEMO-EMPTY", "LIVE SIMULATION · LIVE-DEMO-EMPTY"),
        )
        db.commit()
    report["checks"].append(
        "Two changing raw events, estimator checkpoints and ten numeric API components "
        "match atomic persisted records"
    )

    with httpx.Client(base_url=api, timeout=5) as client:
        b = client.get(f"/api/v1/demo/transformers/{secondary}/physics")
        assert b.status_code == 200
        second = LivePhysicsDemoResult.model_validate(b.json())
        assert second.transformer_id == secondary
        report["second_asset_response"] = b.json()
        with psycopg.connect(connection_url, connect_timeout=5) as db:
            raw = db.execute(
                "SELECT checkpoint->'raw_event' FROM live_physics_demo_events "
                "WHERE transformer_id=%s ORDER BY timestamp DESC LIMIT 1",
                (secondary,),
            ).fetchone()[0]
            assert raw["transformer_id"] == secondary
            assert raw["event_id"] != report["raw_events"][-1]["raw_event"]["event_id"]
            report["second_asset_raw_event"] = raw
        assert client.get("/api/v1/demo/transformers/MISSING/physics").status_code == 404
        missing = client.get("/api/v1/demo/transformers/LIVE-DEMO-EMPTY/physics")
        assert missing.status_code == 404
        report["no_event_response"] = missing.json()
        assert client.get(f"/api/v1/demo/transformers/{primary}/physics?at=x").status_code == 422
        transformed = httpx.get(web + "/src/hooks/usePhysics.ts", timeout=5)
        assert transformed.status_code == 200
        served_env, _ = json.JSONDecoder().raw_decode(
            transformed.text.split("import.meta.env =", 1)[1].lstrip()
        )
        assert served_env["VITE_API_BASE_URL"] == api
        assert served_env["VITE_LIVE_PHYSICS_DEMO_ENABLED"] == "true"
        assert float(served_env["VITE_LIVE_PHYSICS_POLL_INTERVAL_MS"]) == interval * 1000
        report["frontend_configuration"] = {
            "api": api,
            "demo_enabled": True,
            "poll_interval_ms": interval * 1000,
        }
        report["checks"].append(
            "Actual served Vite module has explicit demo flag, API origin and configured cadence; "
            "B identity and missing/query errors verified"
        )
        (out / "stop-producer").write_text("Stop only the owned producer", encoding="utf-8")
        producer.wait(timeout=interval + 5)
        # Read requests must not write or advance state. Keep deliberate corruption
        # in this disposable DB after its sole producer has stopped.
        with psycopg.connect(connection_url, connect_timeout=5) as db:
            count = db.execute("SELECT count(*) FROM live_physics_demo_events").fetchone()[0]
            for _ in range(3):
                assert client.get(f"/api/v1/demo/transformers/{primary}/physics").status_code == 200
            assert (
                db.execute("SELECT count(*) FROM live_physics_demo_events").fetchone()[0] == count
            )
            head = db.execute(
                "SELECT run_id, sequence, sha256 FROM live_physics_demo_events "
                "WHERE transformer_id=%s ORDER BY timestamp DESC LIMIT 1",
                (primary,),
            ).fetchone()
            db.execute(
                "UPDATE live_physics_demo_events SET sha256=%s "
                "WHERE transformer_id=%s AND run_id=%s AND sequence=%s",
                ("0" * 64, primary, head[0], head[1]),
            )
            db.commit()
            invalid = client.get(f"/api/v1/demo/transformers/{primary}/physics")
            assert invalid.status_code == 503
            report["invalid_response"] = invalid.json()
            db.execute(
                "UPDATE live_physics_demo_events SET sha256=%s "
                "WHERE transformer_id=%s AND run_id=%s AND sequence=%s",
                (head[2], primary, head[0], head[1]),
            )
            db.commit()
            event = db.execute(
                "SELECT max(timestamp) FROM live_physics_demo_events WHERE transformer_id=%s",
                (primary,),
            ).fetchone()[0]
        sleep(max(0, 15.5 - (datetime.now(UTC) - event).total_seconds()))
        stale = client.get(f"/api/v1/demo/transformers/{primary}/physics")
        assert stale.status_code == 200
        body = LivePhysicsDemoResult.model_validate(stale.json())
        assert body.status == "UNAVAILABLE" and "stale" in body.reason
        assert all(c.value is None for c in body.components.values())
        report["stale_response"] = stale.json()
        report["checks"].append(
            "GET is read-only; corrupt stored event gives 503 without fallback; "
            "stopped producer expires all numeric values"
        )
    return report
