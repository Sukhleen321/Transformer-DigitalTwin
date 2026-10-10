"""One shared operational fleet; no historical identity remapping or seeding."""
from __future__ import annotations
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import httpx
from .schema import TransformerConfig, TransformerRecord

DEFAULT_CONFIG = Path(os.environ.get('SIMULATOR_CONFIG_DIR', '/config' if Path('/config/operational-fleet.json').is_file() else Path(__file__).resolve().parents[1] / 'config'))
DEFAULT_FLEET = DEFAULT_CONFIG / 'operational-fleet.json'


def load_fleet(path=DEFAULT_FLEET):
    from ml.demo_physics.fleet import load_fleet as shared_fleet
    fleet = shared_fleet(path)
    if fleet.get('version') != 'operational-fleet-v1' or not fleet.get('assets'):
        raise ValueError('Unsupported or empty operational fleet')
    ids, units = set(), set()
    for item in fleet['assets']:
        asset, unit = item['transformer_id'], item['unit_id']
        TransformerRecord.asset_id(asset)
        if len(asset.encode('utf-8')) > 64 or asset in ids or type(unit) is not int or not 1 <= unit <= 247 or unit in units:
            raise ValueError('Invalid or duplicate fleet asset/unit mapping')
        TransformerConfig.model_validate(dict(fleet['configuration'], transformer_id=asset))
        ids.add(asset); units.add(unit)
    return fleet


def load_runtime_config(path, role, now=None):
    """Expand a fleet reference; retain existing standalone H03/H06 configs."""
    path = Path(path)
    config = json.loads(path.read_text(encoding='utf-8'))
    if 'fleet_file' not in config:
        return config
    fleet = load_fleet(path.parent / config.pop('fleet_file'))
    if 'assets' in config:
        raise ValueError('Fleet reference cannot override authoritative assets')
    config['map_version'] = fleet['map_version']
    config['assets'] = []
    for entry in fleet['assets']:
        item = dict(transformer_id=entry['transformer_id'], unit_id=entry['unit_id'])
        if role == 'server':
            item.update(seed=entry['seed'], configuration=dict(fleet['configuration'], transformer_id=entry['transformer_id']))
        elif role == 'bridge':
            item.update(host=config['modbus_host'], port=config.get('modbus_port', 1502), expected_interval_seconds=fleet['interval_seconds'])
        else:
            raise ValueError('Unknown fleet configuration role')
        config['assets'].append(item)
    if role == 'server':
        config['interval_seconds'] = fleet['interval_seconds']
        if 'signal_profile' in fleet:
            config['signal_profile'] = fleet['signal_profile']
        # New source sessions resume the live UTC clock, not old accepted times.
        # Generator counters/sequence restart explicitly; energy reset handling
        # and backend accepted-history/checkpoint semantics remain unchanged.
        config['start_utc'] = (now or datetime.now(timezone.utc)).isoformat()
        config.setdefault('timeline', [])
    return config


def registry_payloads(fleet):
    cfg = copy.deepcopy(fleet['configuration'])
    version, status = cfg.pop('configuration_version'), cfg.pop('configuration_status')
    units = {'rated_power_kva': 'kVA', 'rated_voltage_lv': 'V', 'rated_current_a': 'A', 'measurement_side': None}
    metadata = dict(version=version, status=status, field_metadata={
        k: dict(unit=units[k], verification=status, provenance='Declared fictional operational fleet; not a physical nameplate',
                evidence_reference=None, effective_at=None) for k in cfg if cfg[k] is not None})
    return [dict(id=a['transformer_id'], name=a['transformer_id'] + ' · fictional simulator',
                 schema_version='1.1.0', **cfg, configuration_metadata=copy.deepcopy(metadata)) for a in fleet['assets']]


def register_fleet(base_url, path=DEFAULT_FLEET, client=None):
    """Idempotent registration only. Never PATCH, relabel or seed history."""
    owned = client is None
    client = client or httpx.Client(timeout=30)
    try:
        for payload in registry_payloads(load_fleet(path)):
            response = client.post(base_url.rstrip('/') + '/api/v1/transformers', json=payload)
            if response.status_code == 409:
                existing = client.get(base_url.rstrip('/') + '/api/v1/transformers/' + payload['id'])
                existing.raise_for_status()
                if any(existing.json().get(k) != v for k, v in payload.items()):
                    raise ValueError('Existing fleet configuration conflicts: ' + payload['id'])
            else:
                response.raise_for_status()
    finally:
        if owned:
            client.close()
