"""
simulator.py
============
Pretends to be real battery hardware by generating realistic voltage (V),
current (A), and temperature (deg C) readings over time. This lets the whole
dashboard work with NO physical sensors attached.

>>> WHERE REAL SENSORS PLUG IN LATER <<<
The backend only ever calls `DataSource.next_sample()`. Today that returns a
simulated reading. To use real hardware later, write a class with the same
`next_sample()` method that reads your sensor, and swap it in at the ONE place
noted in backend/main.py (see `build_data_source`). Nothing else changes --
simulated and real data are handled identically.

SCENARIO PRESETS shape the numbers so recommendations visibly trigger:
  * normal_drive          -- calm, healthy readings
  * aggressive_acceleration-- high discharge current, rising temperature
  * fast_charge           -- charging current, voltage climbing toward the max
  * hot_day               -- ambient temperature already high
  * deep_discharge        -- voltage sagging toward the minimum limit
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Dict

# --- Make the project root importable (works as script or as a package). ---
import os as _os, sys as _sys
_root = _os.path.dirname(_os.path.abspath(__file__))
while _root != _os.path.dirname(_root) and not _os.path.exists(_os.path.join(_root, "config.yaml")):
    _root = _os.path.dirname(_root)
if _root not in _sys.path:
    _sys.path.insert(0, _root)

from config_loader import load_config


# The list of scenarios the UI can switch between. Each is a set of "targets"
# the simulator gently steers the live numbers toward, plus some jitter.
SCENARIOS: Dict[str, Dict[str, float]] = {
    "normal_drive": {
        "voltage": 3.8,
        "current": 2.0,     # positive = discharging (driving)
        "temperature": 28.0,
        "noise": 0.4,
    },
    "aggressive_acceleration": {
        "voltage": 3.6,
        "current": 7.5,     # heavy discharge current -> high C-rate
        "temperature": 43.0,  # heats up quickly
        "noise": 0.8,
    },
    "fast_charge": {
        "voltage": 4.15,    # pushing near the max voltage limit
        "current": -6.0,    # negative = charging
        "temperature": 38.0,
        "noise": 0.5,
    },
    "hot_day": {
        "voltage": 3.75,
        "current": 2.5,
        "temperature": 47.0,  # above the safe band
        "noise": 0.6,
    },
    "deep_discharge": {
        "voltage": 3.05,    # sagging toward the min voltage limit
        "current": 4.0,
        "temperature": 33.0,
        "noise": 0.5,
    },
}


@dataclass
class Sample:
    """One instantaneous sensor reading."""
    voltage_v: float
    current_a: float
    temperature_c: float
    t: float  # seconds since the source started (a simple clock)

    def as_dict(self) -> dict:
        return {
            "voltage_v": round(self.voltage_v, 4),
            "current_a": round(self.current_a, 4),
            "temperature_c": round(self.temperature_c, 3),
            "t": round(self.t, 3),
        }


class DataSource:
    """
    Base interface for anything that produces battery samples.

    Real hardware: subclass this and implement `next_sample()` to read your
    sensor. The rest of the backend depends ONLY on this interface.
    """

    def next_sample(self) -> Sample:  # pragma: no cover - interface method
        raise NotImplementedError


class SimulatedDataSource(DataSource):
    """
    Produces smooth, realistic-looking fake samples. Each call nudges the
    current values toward the active scenario's targets and adds small random
    jitter, so charts look natural (not jumpy). Switching scenarios makes the
    values smoothly drift to the new targets.
    """

    def __init__(self, scenario: str | None = None) -> None:
        self.config = load_config()
        battery = self.config["battery"]

        # Physical limits (used only to keep simulated values believable).
        self.max_voltage = float(battery["max_voltage_v"])
        self.min_voltage = float(battery["min_voltage_v"])

        # Start from calm values.
        self.voltage = float(battery["nominal_voltage_v"])
        self.current = 1.0
        self.temperature = 25.0
        self.t = 0.0

        # How many seconds between samples (from the configured sample rate).
        rate = float(self.config["stream"]["sample_rate_hz"]) or 2.0
        self.dt = 1.0 / rate

        self.scenario = scenario or self.config["stream"]["default_scenario"]
        if self.scenario not in SCENARIOS:
            self.scenario = "normal_drive"

    def set_scenario(self, scenario: str) -> bool:
        """Switch the active scenario. Returns True if it was a known scenario."""
        if scenario in SCENARIOS:
            self.scenario = scenario
            return True
        return False

    def next_sample(self) -> Sample:
        """
        Advance the clock by one step and return the next reading.

        We use "exponential smoothing": new = old + fraction*(target - old).
        This makes values glide toward the scenario target instead of jumping,
        which looks like a real battery responding to conditions.
        """
        target = SCENARIOS[self.scenario]
        noise = target["noise"]

        # Smoothing factor: 0.15 = move 15% of the way to the target each step.
        alpha = 0.15

        self.voltage += alpha * (target["voltage"] - self.voltage)
        self.current += alpha * (target["current"] - self.current)
        self.temperature += alpha * (target["temperature"] - self.temperature)

        # Add gentle random jitter so the lines aren't perfectly smooth.
        self.voltage += random.uniform(-noise, noise) * 0.05
        self.current += random.uniform(-noise, noise) * 0.5
        self.temperature += random.uniform(-noise, noise) * 0.5

        # A tiny sine wobble on temperature for a lifelike feel.
        self.temperature += 0.2 * math.sin(self.t / 3.0)

        # Keep voltage within believable physical bounds.
        self.voltage = max(self.min_voltage - 0.1, min(self.max_voltage + 0.1, self.voltage))

        self.t += self.dt
        return Sample(
            voltage_v=self.voltage,
            current_a=self.current,
            temperature_c=self.temperature,
            t=self.t,
        )


def list_scenarios() -> list[str]:
    """Return the names of all available scenario presets (for the UI)."""
    return list(SCENARIOS.keys())


if __name__ == "__main__":
    # Print a few samples from each scenario as a quick check.
    for name in list_scenarios():
        src = SimulatedDataSource(scenario=name)
        print(f"\nScenario: {name}")
        for _ in range(3):
            print("  ", src.next_sample().as_dict())
