"""Independent fictional asset clocks and scenario state; no scale claim."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from ml.pipeline.identity import utc
from .generator import SyntheticGenerator
from .schema import TransformerConfig
from .faults import SCENARIO_CATALOGUE


@dataclass
class AssetClock:
    unit_id: int
    generator: SyntheticGenerator
    event_time: datetime
    timeline: list
    start: datetime

    def advance(self):
        offset = (self.event_time - self.start).total_seconds()
        scenario = "HEALTHY"
        for item in self.timeline:
            if item["from_seconds"] <= offset < item["to_seconds"]:
                scenario = item["scenario"]
                break
        record = self.generator.next_record(self.event_time, scenario)
        self.event_time += timedelta(seconds=self.generator.interval_s)
        return record


class Scheduler:
    def __init__(self, config):
        if config["map_version"] != "fictional-lv-v1":
            raise ValueError("unsupported map version")
        self.start = datetime.fromisoformat(utc(config["start_utc"]).replace("Z", "+00:00"))
        self.assets = {}
        units = set()
        if not config["assets"]:
            raise ValueError("empty asset list")
        for index, item in enumerate(config["assets"]):
            asset = TransformerConfig.model_validate(item["configuration"])
            if asset.transformer_id != item["transformer_id"]:
                raise ValueError("asset/configuration mismatch")
            if len(asset.transformer_id.encode("utf-8")) > 64:
                raise ValueError("map asset ID UTF-8 length exceeds 64 bytes")
            unit = item["unit_id"]
            if type(unit) is not int or not 1 <= unit <= 247 or unit in units or asset.transformer_id in self.assets:
                raise ValueError("invalid or duplicate asset/unit mapping")
            units.add(unit)
            timeline = item.get("timeline", config.get("timeline", []))
            previous_end = 0
            for event in timeline:
                a, b = event["from_seconds"], event["to_seconds"]
                if not math.isfinite(a) or not math.isfinite(b) or a < previous_end or b <= a or event["scenario"] not in SCENARIO_CATALOGUE:
                    raise ValueError("invalid, overlapping or unordered timeline")
                previous_end = b
            generator = SyntheticGenerator(asset, seed=item.get("seed", config.get("seed", 42) + index),
                                           interval_s=item.get("interval_seconds", config.get("interval_seconds", 5)),
                                           signal_profile=config.get('signal_profile'),
                                           phase=2 * math.pi * index / len(config['assets']))
            self.assets[asset.transformer_id] = AssetClock(unit, generator, self.start, timeline, self.start)

    def tick(self):
        return {asset: clock.advance() for asset, clock in self.assets.items()}

    def advance(self, asset_id):
        if asset_id not in self.assets:
            raise ValueError("unsupported asset")
        return self.assets[asset_id].advance()
