"""Loopback-only read-only FC04 fictional simulator (pymodbus 3.6.9)."""
from __future__ import annotations
import asyncio
import ipaddress
import json
import threading
import time
import signal
from datetime import datetime, timezone
from pathlib import Path
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSlaveContext, ModbusServerContext
from pymodbus.server import ModbusTcpServer
from .register_map import encode, decode, load_map
from .scheduler import Scheduler


class AtomicInputBlock(ModbusSequentialDataBlock):
    """Swap whole snapshots; a request sees one immutable list under a lock."""
    def __init__(self, values):
        self._lock = threading.Lock()
        super().__init__(0, values)

    def getValues(self, address, count=1):
        with self._lock:
            return super().getValues(address, count)

    def install(self, values):
        with self._lock:
            self.values = list(values)


class ReadOnlySlave(ModbusSlaveContext):
    def validate(self, fc_as_hex, address, count=1):
        return fc_as_hex == 4 and super().validate(fc_as_hex, address, count)


class SimulationServer:
    def __init__(self, config):
        self.host = config.get("host", "127.0.0.1")
        if not ipaddress.ip_address(self.host).is_loopback and not (self.host == '0.0.0.0' and config.get('container_network') is True):
            raise ValueError("demo Modbus must bind to a loopback IP")
        self.port = config.get("port", 1502)
        if type(self.port) is not int or not 0 <= self.port <= 65535:
            raise ValueError("invalid server port")
        self.audit_gateway = config.get("audit_gateway_id")
        self.scheduler = Scheduler(config)
        self.spec = load_map()
        self.blocks, slaves = {}, {}
        pre_roll = config.get('pre_roll_steps', 0)
        if type(pre_roll) is not int or not 0 <= pre_roll <= 10000:
            raise ValueError('bounded pre-roll required')
        cadence = config.get('pre_roll_interval_seconds', config.get('interval_seconds', 5))
        if not isinstance(cadence, (int,float)) or not 0 < cadence <= 3600:
            raise ValueError('bounded declared pre-roll cadence required')
        for clock in self.scheduler.assets.values():
            clock.generator.interval_s = cadence
        for _ in range(pre_roll):
            self.scheduler.tick()
        for clock in self.scheduler.assets.values():
            clock.generator.interval_s = config.get('interval_seconds', 5)
        self.snapshots = self.scheduler.tick()
        for asset, clock in self.scheduler.assets.items():
            block = AtomicInputBlock(encode(self.snapshots[asset], clock.unit_id, self.spec))
            self.blocks[asset] = block
            slaves[clock.unit_id] = ReadOnlySlave(ir=block, zero_mode=True)
        self.context = ModbusServerContext(slaves=slaves, single=False)
        self.server = None
        for asset, record in self.snapshots.items():
            self.audit(asset, record)

    def audit(self, asset, record):
        if self.audit_gateway:
            decoded = decode(encode(record, self.scheduler.assets[asset].unit_id, self.spec),
                transformer_id=asset, unit_id=self.scheduler.assets[asset].unit_id,
                gateway_id=self.audit_gateway, expected_interval_seconds=self.scheduler.assets[asset].generator.interval_s)
            print(json.dumps({"generated_snapshot": {"asset": asset, "timestamp": decoded.timestamp.isoformat(),
                "sequence": decoded.acquisition["sequence"], "snapshot": decoded.acquisition["snapshot_id"],
                "generated_at": datetime.now(timezone.utc).isoformat()}}), flush=True)

    async def update(self):
        deadlines = {asset: time.monotonic() + clock.generator.interval_s for asset, clock in self.scheduler.assets.items()}
        while True:
            await asyncio.sleep(max(0, min(deadlines.values()) - time.monotonic()))
            now = time.monotonic()
            for asset, deadline in deadlines.items():
                if now >= deadline:
                    self.advance_asset(asset)
                    # If delayed, catch up incrementally, preserving each event-time step.
                    deadlines[asset] += self.scheduler.assets[asset].generator.interval_s

    def advance_asset(self, asset):
        try:
            record = self.scheduler.advance(asset)
            self.audit(asset, record)
            self.blocks[asset].install(encode(record, self.scheduler.assets[asset].unit_id, self.spec))
            self.snapshots[asset] = record
            return record
        except Exception as exc:
            # The bridge will observe an unchanged/stale snapshot for this
            # asset. Other independent clocks and register blocks keep moving.
            print(json.dumps({'synthetic_asset_unavailable': asset,
                              'error_type': type(exc).__name__}), flush=True)
            return None

    async def run(self):
        self.server = ModbusTcpServer(self.context, address=(self.host, self.port), ignore_missing_slaves=False)
        updater = asyncio.create_task(self.update())
        try:
            await self.server.serve_forever()
        finally:
            updater.cancel()
            await asyncio.gather(updater, return_exceptions=True)
            await self.server.shutdown()


def run_server(config_file):
    from .fleet import load_runtime_config, register_fleet
    config = load_runtime_config(config_file, 'server')
    if config.get('registry_url'):
        raw = json.loads(Path(config_file).read_text(encoding='utf-8'))
        register_fleet(config['registry_url'], Path(config_file).parent / raw['fleet_file'])
    async def supervised():
        server = SimulationServer(config)
        running = asyncio.create_task(server.run())
        try:
            asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, running.cancel)
        except NotImplementedError:
            pass  # Windows console uses its normal KeyboardInterrupt handling.
        try:
            await running
        except asyncio.CancelledError:
            pass
    asyncio.run(supervised())
