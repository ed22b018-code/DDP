"""
state.py
========
Keeps a running estimate of the battery's live condition from the streaming
V/I/T samples:

  * SoC (State of Charge)  -- how "full" the battery is right now (0-100%),
    like a fuel gauge. We estimate it with "coulomb counting": integrate the
    current over time (charge in/out) and adjust the starting fullness.
  * SoH (State of Health)  -- overall health vs a new battery (0-100%). This
    comes from the ML model, recomputed every few samples (not every tick, to
    save work). Falls back to a config value if the model isn't trained yet.
  * Stress score (0-100)   -- an instantaneous "how hard is life for the
    battery right now" number combining heat, C-rate, and voltage extremes.
    Higher = more degrading conditions.

This module is deliberately framework-free (no FastAPI here) so it's easy to
test and reason about on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd

# --- Make the project root importable (works as script or as a package). ---
import os as _os, sys as _sys
_root = _os.path.dirname(_os.path.abspath(__file__))
while _root != _os.path.dirname(_root) and not _os.path.exists(_os.path.join(_root, "config.yaml")):
    _root = _os.path.dirname(_root)
if _root not in _sys.path:
    _sys.path.insert(0, _root)

from config_loader import load_config
from backend.simulator import Sample


@dataclass
class BatteryMetadata:
    """The one-time setup info entered in the dashboard form."""
    chemistry: str
    nominal_capacity_ah: float
    nominal_voltage_v: float
    max_voltage_v: float
    min_voltage_v: float
    max_safe_temp_c: float
    cell_count: int
    current_cycle_count: int

    @staticmethod
    def from_config() -> "BatteryMetadata":
        """Build default metadata from config.yaml (used before setup)."""
        b = load_config()["battery"]
        return BatteryMetadata(
            chemistry=b["chemistry"],
            nominal_capacity_ah=float(b["nominal_capacity_ah"]),
            nominal_voltage_v=float(b["nominal_voltage_v"]),
            max_voltage_v=float(b["max_voltage_v"]),
            min_voltage_v=float(b["min_voltage_v"]),
            max_safe_temp_c=float(b["max_safe_temp_c"]),
            cell_count=int(b["cell_count"]),
            current_cycle_count=int(b["current_cycle_count"]),
        )


@dataclass
class LiveState:
    """A snapshot of the battery's live condition at one moment."""
    voltage_v: float
    current_a: float
    temperature_c: float
    c_rate: float
    soc_pct: float
    soh_pct: float
    stress_score: float
    temp_rise_rate_c_per_s: float
    t: float

    def as_dict(self) -> dict:
        return {
            "voltage_v": round(self.voltage_v, 4),
            "current_a": round(self.current_a, 4),
            "temperature_c": round(self.temperature_c, 3),
            "c_rate": round(self.c_rate, 3),
            "soc_pct": round(self.soc_pct, 2),
            "soh_pct": round(self.soh_pct, 2),
            "stress_score": round(self.stress_score, 1),
            "temp_rise_rate_c_per_s": round(self.temp_rise_rate_c_per_s, 4),
            "t": round(self.t, 3),
        }


class BatteryStateTracker:
    """
    Maintains the running SoC/SoH/stress as samples arrive.

    Call `update(sample)` once per incoming reading; it returns the new
    LiveState. The tracker holds the battery metadata and a little history.
    """

    def __init__(self, metadata: Optional[BatteryMetadata] = None, start_soc_pct: float = 80.0) -> None:
        self.config = load_config()
        self.metadata = metadata or BatteryMetadata.from_config()
        self.thresholds = self.config["thresholds"]

        # SoC starts at a reasonable "mostly full" value; coulomb counting
        # updates it from there.
        self.soc_pct = float(start_soc_pct)

        # SoH starts from a config-based estimate and is refreshed by the model.
        self.soh_pct = 100.0

        # Remember the previous sample so we can compute rates (e.g. temp rise).
        self._prev_sample: Optional[Sample] = None
        self._sample_count = 0

        # Keep a short history of live states for charts / debugging.
        self.history: List[LiveState] = []
        self.history_length = int(self.config["stream"]["history_length"])

    # ---- Core update -------------------------------------------------------
    def update(self, sample: Sample, model_soh: Optional[float] = None) -> LiveState:
        """
        Fold one new sample into the running estimates and return the LiveState.

        `model_soh` (optional): the latest SoH% from the ML model. Pass it in
        when you recompute it (e.g. every N samples); otherwise the last known
        SoH is kept.
        """
        self._sample_count += 1

        # --- Time step since previous sample -------------------------------
        if self._prev_sample is not None:
            dt = max(sample.t - self._prev_sample.t, 1e-6)
        else:
            dt = 1.0 / float(self.config["stream"]["sample_rate_hz"] or 2.0)

        # --- SoC via coulomb counting --------------------------------------
        # Charge moved = current (A) * time (h). We convert dt seconds to hours.
        # Positive current = discharge = SoC goes DOWN; negative = charge = UP.
        # SoC change (%) = (amp-hours moved / capacity) * 100.
        capacity_ah = self.metadata.nominal_capacity_ah or 1.0
        amp_hours = sample.current_a * (dt / 3600.0)
        delta_soc = -(amp_hours / capacity_ah) * 100.0
        self.soc_pct = _clamp(self.soc_pct + delta_soc, 0.0, 100.0)

        # --- Temperature rise rate -----------------------------------------
        if self._prev_sample is not None:
            temp_rise_rate = (sample.temperature_c - self._prev_sample.temperature_c) / dt
        else:
            temp_rise_rate = 0.0

        # --- C-rate --------------------------------------------------------
        c_rate = abs(sample.current_a) / capacity_ah

        # --- SoH (from model if provided) ----------------------------------
        if model_soh is not None and not _is_nan(model_soh):
            self.soh_pct = _clamp(model_soh, 0.0, 100.0)

        # --- Stress score --------------------------------------------------
        stress = self._compute_stress(sample, c_rate, temp_rise_rate)

        state = LiveState(
            voltage_v=sample.voltage_v,
            current_a=sample.current_a,
            temperature_c=sample.temperature_c,
            c_rate=c_rate,
            soc_pct=self.soc_pct,
            soh_pct=self.soh_pct,
            stress_score=stress,
            temp_rise_rate_c_per_s=temp_rise_rate,
            t=sample.t,
        )

        # Save history (bounded so memory doesn't grow forever).
        self.history.append(state)
        if len(self.history) > self.history_length:
            self.history.pop(0)

        self._prev_sample = sample
        return state

    # ---- Stress score ------------------------------------------------------
    def _compute_stress(self, sample: Sample, c_rate: float, temp_rise_rate: float) -> float:
        """
        Combine several "hardness" signals into a single 0-100 stress score.

        Each component contributes a share; we cap the total at 100. The exact
        weights are a reasonable default -- tune the underlying thresholds in
        config.yaml if you want different sensitivity.
        """
        th = self.thresholds
        meta = self.metadata

        # 1) Heat: how far above the warning temperature we are.
        temp_over = sample.temperature_c - th["temp_warning_c"]
        temp_component = _clamp(temp_over / 10.0, 0.0, 1.0) * 40.0  # up to 40 pts

        # 2) C-rate: how far above the warning C-rate we are.
        c_over = c_rate - th["c_rate_warning"]
        c_component = _clamp(c_over / 2.0, 0.0, 1.0) * 30.0        # up to 30 pts

        # 3) Voltage extremes: near max (charge) or near min (discharge).
        near_max = (meta.max_voltage_v - sample.voltage_v) < th["voltage_high_margin_v"]
        near_min = (sample.voltage_v - meta.min_voltage_v) < th["voltage_low_margin_v"]
        voltage_component = 20.0 if (near_max or near_min) else 0.0  # up to 20 pts

        # 4) Rapid temperature rise.
        rise_component = 10.0 if temp_rise_rate > th["temp_rise_rate_c_per_s"] else 0.0

        return _clamp(temp_component + c_component + voltage_component + rise_component, 0.0, 100.0)

    def latest(self) -> Optional[LiveState]:
        """Return the most recent LiveState, or None if none yet."""
        return self.history[-1] if self.history else None


# ---- Small numeric helpers -------------------------------------------------
def _clamp(x: float, lo: float, hi: float) -> float:
    """Force x into the range [lo, hi]."""
    return max(lo, min(hi, x))


def _is_nan(x: float) -> bool:
    """True if x is a NaN (not-a-number), used to ignore missing model output."""
    return x != x


if __name__ == "__main__":
    # Quick demo: feed a few simulated samples through the tracker.
    from backend.simulator import SimulatedDataSource

    tracker = BatteryStateTracker()
    src = SimulatedDataSource(scenario="aggressive_acceleration")
    for _ in range(5):
        s = src.next_sample()
        print(tracker.update(s).as_dict())
