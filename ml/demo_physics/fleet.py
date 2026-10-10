"""Shared fictional fleet loader; identities live only in the existing manifest."""

import json
import math
from pathlib import Path


def load_fleet(path):
    fleet = json.loads(Path(path).read_text(encoding="utf-8"))
    if fleet.get("version") != "operational-fleet-v1" or fleet.get("source_kind") != "SIMULATED":
        raise ValueError("An explicitly simulated operational-fleet-v1 manifest is required")
    assets = fleet.get("assets", [])
    if not 1 <= len(assets) <= 10:
        raise ValueError("One to ten fictional assets are required")
    ids, units = set(), set()
    for item in assets:
        asset, unit = item["transformer_id"], item["unit_id"]
        if (
            not isinstance(asset, str)
            or not asset
            or asset != asset.strip()
            or len(asset.encode("utf-8")) > 64
            or any(c in asset for c in "/+#")
            or any(ord(c) < 32 for c in asset)
            or asset in ids
            or type(unit) is not int
            or not 1 <= unit <= 247
            or unit in units
            or type(item["seed"]) is not int
        ):
            raise ValueError("Invalid fictional asset/unit/seed mapping")
        ids.add(asset)
        units.add(unit)
    cfg = fleet["configuration"]
    if cfg.get("configuration_status") != "SYNTHETIC_CONFIG" or cfg.get("measurement_side") != "LV":
        raise ValueError("Fictional LV configuration is required")
    for name in ("rated_current_a", "rated_voltage_lv", "rated_power_kva"):
        value = cfg.get(name)
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError("Explicit finite fictional rating required: " + name)
    return fleet


def asset_ids(path):
    return tuple(item["transformer_id"] for item in load_fleet(path)["assets"])
