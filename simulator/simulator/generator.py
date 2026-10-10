"""Incremental fictional LV simulation; no fitted-model or physical claim."""
from __future__ import annotations
import datetime as dt
import math
import numpy as np
from .schema import TransformerConfig, TransformerRecord, acquisition, identify
from .faults import FaultInjector, SCENARIO_CATALOGUE


def coherent_power(record):
    """Phase-neutral V × line A; equivalent Q satisfies S²=P²+Q².

    Synthetic phases have lagging PF; this is not a validated network solver.
    Missing inputs stay null.
    """
    triples = [(getattr(record, f"phase_voltage_l{i}"), getattr(record, f"current_l{i}"),
                getattr(record, f"power_factor_l{i}")) for i in (1, 2, 3)]
    if any(v is None or i is None or p is None for v, i, p in triples):
        record.active_power_total = record.apparent_power_total = record.reactive_power_total = None
        return
    apparent = sum(v * i for v, i, _ in triples) / 1000
    active = sum(v * i * p for v, i, p in triples) / 1000
    record.apparent_power_total = apparent
    record.active_power_total = active
    record.reactive_power_total = math.sqrt(max(0, apparent * apparent - active * active))


def thermal_step(previous, target, elapsed_seconds, time_constant_seconds=1200):
    if elapsed_seconds < 0 or time_constant_seconds <= 0:
        raise ValueError("invalid thermal elapsed time")
    return target + (previous - target) * math.exp(-elapsed_seconds / time_constant_seconds)


class SyntheticGenerator:
    def __init__(self, config=None, seed=42, interval_s=60, signal_profile=None, phase=0):
        if not math.isfinite(interval_s) or interval_s <= 0:
            raise ValueError("positive cadence required")
        cfg = (config or TransformerConfig()).model_copy(deep=True)
        # Fictional compatibility defaults, never verified ratings.
        cfg.rated_power_kva = cfg.rated_power_kva or 500.0
        cfg.rated_voltage_lv = cfg.rated_voltage_lv or 415.0  # line-line V
        cfg.rated_current_a = cfg.rated_current_a or cfg.rated_power_kva * 1000 / (math.sqrt(3) * cfg.rated_voltage_lv)
        self.config = cfg
        self.rng = np.random.default_rng(seed)
        self.injector = FaultInjector(seed=seed, config=cfg)
        self.interval_s = interval_s
        self._oil_temp = 42.0
        self._energy_kwh = 0.0
        self._step = 0
        self._last_time = None
        self._last_power = None
        self.signal_profile = signal_profile
        self.phase = phase
        self._noise = {}
        self._epoch = None
        if signal_profile is not None and (
            set(signal_profile) != {"version", "load_period_seconds", "noise_time_constant_seconds"}
            or signal_profile["version"] != "CORRELATED_DEMO_V1"
            or any(type(signal_profile[k]) not in (float, int)
                   or not math.isfinite(signal_profile[k]) or signal_profile[k] <= 0
                   for k in ("load_period_seconds", "noise_time_constant_seconds"))
        ):
            raise ValueError("Explicit supported synthetic signal profile required")

    def filtered_noise(self, channel, sigma, elapsed):
        rho = math.exp(-elapsed / self.signal_profile["noise_time_constant_seconds"])
        value = rho * self._noise.get(channel, 0) + math.sqrt(1 - rho * rho) * self.rng.normal(0, sigma)
        self._noise[channel] = float(np.clip(value, -3 * sigma, 3 * sigma))
        return self._noise[channel]

    def iter_records(self, start, count=None, scenario="HEALTHY"):
        if count is not None and count < 0:
            raise ValueError("negative count")
        ts = start
        n = 0
        while count is None or n < count:
            yield self.next_record(ts, scenario)
            ts += dt.timedelta(seconds=self.interval_s)
            n += 1

    def generate(self, start, count=1, scenario="HEALTHY"):
        return list(self.iter_records(start, count, scenario))

    def next_record(self, ts, scenario="HEALTHY"):
        from ml.pipeline.identity import utc
        ts = dt.datetime.fromisoformat(utc(ts).replace("Z", "+00:00"))
        elapsed = 0 if self._last_time is None else (ts - self._last_time).total_seconds()
        if self._last_time is not None and elapsed <= 0:
            raise ValueError("simulation event time must advance")
        rng, cfg = self.rng, self.config
        if self._epoch is None:
            self._epoch = ts
        noise = (lambda channel, sigma: self.filtered_noise(channel, sigma, elapsed)) if self.signal_profile else (lambda channel, sigma: rng.normal(0, sigma))
        hour = ts.hour + ts.minute / 60 + ts.second / 3600
        ambient = 32 + 6 * math.sin(math.pi * (hour - 6) / 12) + noise('ambient', .5)
        load_angle = (
            2 * math.pi * (ts - self._epoch).total_seconds() / self.signal_profile['load_period_seconds'] + self.phase
            if self.signal_profile else math.pi * (hour - 8) / 12
        )
        load = float(np.clip(.55 + .25 * math.sin(load_angle) + noise('load', .05), .15, 1))
        values = {}
        for phase in (1, 2, 3):
            values[f"current_l{phase}"] = round(float(load * cfg.rated_current_a * (1 + noise(f'current{phase}', .01))), 2)
            values[f"phase_voltage_l{phase}"] = round(float(cfg.rated_voltage_lv / math.sqrt(3) * (1 + noise(f'voltage{phase}', .005))), 2)
            values[f"power_factor_l{phase}"] = round(float(np.clip(.92 + noise(f'pf{phase}', .02), .8, 1)), 4)
        previous_oil = self._oil_temp
        record = TransformerRecord(transformer_id=cfg.transformer_id, timestamp=ts,
            schema_version="1.1.0", source_name="fictional-simulator",
            scenario_id=SCENARIO_CATALOGUE[scenario].scenario_id,
            acquisition=acquisition(sequence=self._step, interval=self.interval_s),
            neutral_current=abs(values["current_l1"] - values["current_l2"]) * .2,
            oil_temperature=previous_oil, winding_temperature=None,
            ambient_temperature=round(float(ambient), 1), oil_level=round(float(85 + noise('oil_level', .3)), 1),
            oil_temp_alarm=0, oil_temp_trip=0, magnetic_oil_gauge_alarm=0, **values)
        record, _ = self.injector.inject(record, scenario, elapsed_s=elapsed)
        coherent_power(record)
        loading = record.apparent_power_total / cfg.rated_power_kva
        target = record.ambient_temperature + 25 * loading * loading
        self._oil_temp = thermal_step(previous_oil, target, elapsed)
        record.oil_temperature += self._oil_temp - previous_oil
        if self._last_power is not None:
            self._energy_kwh += (self._last_power + record.active_power_total) / 2 * elapsed / 3600
        record.energy_kwh = self._energy_kwh
        self._last_power = record.active_power_total
        self._last_time = ts
        self._step += 1
        return identify(record)
