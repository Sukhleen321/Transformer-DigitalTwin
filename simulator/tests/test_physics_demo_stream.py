"""Opt-in correlated profile and failure isolation; no broker/retained stack."""

from datetime import UTC, datetime
from pathlib import Path

from simulator.fleet import load_runtime_config
from simulator.modbus_server import SimulationServer
from simulator.scheduler import Scheduler

CONFIG = Path(__file__).resolve().parents[1] / "config"


def test_correlated_profile_all_ten_streams_bounded_smooth_and_reproducible():
    config = load_runtime_config(
        CONFIG / "physics-demo-server.json", "server", datetime(2026, 10, 11, tzinfo=UTC)
    )
    left, right = Scheduler(config), Scheduler(config)
    previous = {}
    for _ in range(40):
        a, b = left.tick(), right.tick()
        assert len(a) == 10
        for asset, row in a.items():
            assert row.model_dump() == b[asset].model_dump()
            assert 0 < row.current_l1 < 45
            assert 200 < row.phase_voltage_l1 < 250
            assert 20 < row.ambient_temperature < 45
            assert 20 < row.oil_temperature < 60
            if asset in previous:
                assert abs(row.current_l1 - previous[asset].current_l1) < 8
                assert abs(row.ambient_temperature - previous[asset].ambient_temperature) < 2
                assert row.timestamp > previous[asset].timestamp
                assert row.acquisition["snapshot_id"] != previous[asset].acquisition["snapshot_id"]
            previous[asset] = row
    ordinary = load_runtime_config(CONFIG / "operational-server.json", "server")
    assert "signal_profile" not in ordinary


def test_server_asset_failure_keeps_other_register_blocks_updating(monkeypatch):
    config = load_runtime_config(CONFIG / "physics-demo-server.json", "server")
    server = SimulationServer(config)
    ids = list(server.snapshots)
    before = server.snapshots[ids[1]].timestamp

    def invalid(*args, **kwargs):
        raise ValueError("invalid synthetic asset")

    monkeypatch.setattr(server.scheduler.assets[ids[0]].generator, "next_record", invalid)
    assert server.advance_asset(ids[0]) is None
    for asset in ids[1:]:
        assert server.advance_asset(asset).timestamp > before
        assert server.snapshots[asset].timestamp > before
