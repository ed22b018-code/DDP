"""
rules.py
========
The DETERMINISTIC part of the recommendation engine. "Deterministic" means:
same inputs -> same outputs, every time, with no AI involved. It simply
compares the live readings against the thresholds in config.yaml and raises
structured "flags".

Each flag has:
  * code       -- a short machine id (e.g. "TEMP_HIGH")
  * severity   -- "info", "warning", or "critical"
  * message    -- a short human-readable description
  * detail     -- the specific numbers that triggered it

These flags feed two things:
  1. The dashboard's color-coded alert list (green/amber/red).
  2. The Gen-AI layer (genai.py), which turns them into friendly advice.

Keeping this logic separate and rule-based means the system ALWAYS gives
sensible safety guidance even with no API key and no LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List

# --- Make the project root importable (works as script or as a package). ---
import os as _os, sys as _sys
_root = _os.path.dirname(_os.path.abspath(__file__))
while _root != _os.path.dirname(_root) and not _os.path.exists(_os.path.join(_root, "config.yaml")):
    _root = _os.path.dirname(_root)
if _root not in _sys.path:
    _sys.path.insert(0, _root)

from config_loader import load_config
from backend.state import LiveState, BatteryMetadata


# Severity ordering so we can find the "most serious" flag easily.
SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}


@dataclass
class Flag:
    """One rule finding."""
    code: str
    severity: str      # "info" | "warning" | "critical"
    message: str
    detail: str

    def as_dict(self) -> dict:
        return asdict(self)


def evaluate_rules(state: LiveState, metadata: BatteryMetadata) -> List[Flag]:
    """
    Run all rules against the current LiveState and return a list of Flags.

    Returns an empty list when everything is healthy (the UI shows an "all
    good" message in that case).
    """
    th = load_config()["thresholds"]
    flags: List[Flag] = []

    # --- Rule 1: Temperature above safe band --------------------------------
    if state.temperature_c >= th["temp_critical_c"]:
        flags.append(Flag(
            code="TEMP_CRITICAL",
            severity="critical",
            message="Battery temperature is dangerously high.",
            detail=f"{state.temperature_c:.1f} deg C (critical limit {th['temp_critical_c']:.0f}).",
        ))
    elif state.temperature_c >= th["temp_warning_c"]:
        flags.append(Flag(
            code="TEMP_HIGH",
            severity="warning",
            message="Battery is running hot.",
            detail=f"{state.temperature_c:.1f} deg C (warning above {th['temp_warning_c']:.0f}).",
        ))

    # --- Rule 2: High discharge/charge current (C-rate) ---------------------
    if state.c_rate >= th["c_rate_critical"]:
        flags.append(Flag(
            code="CRATE_CRITICAL",
            severity="critical",
            message="Current draw is very high for this battery's size.",
            detail=f"C-rate {state.c_rate:.2f} (critical above {th['c_rate_critical']}).",
        ))
    elif state.c_rate >= th["c_rate_warning"]:
        flags.append(Flag(
            code="CRATE_HIGH",
            severity="warning",
            message="Current draw is high.",
            detail=f"C-rate {state.c_rate:.2f} (warning above {th['c_rate_warning']}).",
        ))

    # --- Rule 3: Voltage near limits ----------------------------------------
    near_max = (metadata.max_voltage_v - state.voltage_v) <= th["voltage_high_margin_v"]
    near_min = (state.voltage_v - metadata.min_voltage_v) <= th["voltage_low_margin_v"]
    if near_max and state.current_a < 0:  # charging toward the top
        flags.append(Flag(
            code="VOLTAGE_NEAR_MAX",
            severity="warning",
            message="Voltage is near the maximum while charging.",
            detail=f"{state.voltage_v:.2f} V (max {metadata.max_voltage_v:.2f} V).",
        ))
    if near_min and state.current_a > 0:  # discharging toward the bottom
        flags.append(Flag(
            code="VOLTAGE_NEAR_MIN",
            severity="warning",
            message="Voltage is near the minimum while discharging.",
            detail=f"{state.voltage_v:.2f} V (min {metadata.min_voltage_v:.2f} V).",
        ))

    # --- Rule 4: Rapid temperature rise -------------------------------------
    if state.temp_rise_rate_c_per_s > th["temp_rise_rate_c_per_s"]:
        flags.append(Flag(
            code="TEMP_RISE_FAST",
            severity="warning",
            message="Temperature is rising quickly.",
            detail=f"{state.temp_rise_rate_c_per_s:.2f} deg C/s "
                   f"(fast above {th['temp_rise_rate_c_per_s']}).",
        ))

    # --- Rule 5: Low state of charge ----------------------------------------
    if state.soc_pct <= th["soc_low_warning_pct"]:
        flags.append(Flag(
            code="SOC_LOW",
            severity="info",
            message="State of charge is getting low.",
            detail=f"SoC {state.soc_pct:.0f}% (warning at/below {th['soc_low_warning_pct']:.0f}%).",
        ))

    # --- Rule 6: Combined high-stress state ---------------------------------
    if state.stress_score >= th["stress_score_critical"]:
        flags.append(Flag(
            code="STRESS_CRITICAL",
            severity="critical",
            message="Overall battery stress is very high right now.",
            detail=f"Stress score {state.stress_score:.0f}/100.",
        ))
    elif state.stress_score >= th["stress_score_warning"]:
        flags.append(Flag(
            code="STRESS_HIGH",
            severity="warning",
            message="Overall battery stress is elevated.",
            detail=f"Stress score {state.stress_score:.0f}/100.",
        ))

    return flags


def most_severe(flags: List[Flag]) -> Flag | None:
    """Return the single most serious flag (critical > warning > info)."""
    if not flags:
        return None
    return max(flags, key=lambda f: SEVERITY_ORDER.get(f.severity, 0))


def rule_based_recommendation(flags: List[Flag]) -> str:
    """
    Build a plain-English recommendation using ONLY the rules (no AI). This is
    the fallback used when there's no API key, and also a safe default the LLM
    can improve on.
    """
    if not flags:
        return "All readings look healthy. Keep operating normally."

    top = most_severe(flags)

    # Map each flag code to concrete advice.
    advice = {
        "TEMP_CRITICAL": "Stop and let the battery cool down now -- high heat "
                         "permanently degrades it.",
        "TEMP_HIGH": "The battery is hot. Reduce load or improve cooling to slow "
                     "degradation.",
        "CRATE_CRITICAL": "Ease off hard acceleration/charging -- the current draw "
                          "is very high for this battery.",
        "CRATE_HIGH": "Try smoother acceleration to lower the current and reduce wear.",
        "VOLTAGE_NEAR_MAX": "Consider stopping the charge soon; holding near the max "
                            "voltage stresses the cells.",
        "VOLTAGE_NEAR_MIN": "Recharge soon; running near the minimum voltage shortens "
                            "battery life.",
        "TEMP_RISE_FAST": "Temperature is climbing fast -- reduce load to prevent "
                          "overheating.",
        "SOC_LOW": "Charge is getting low -- plan to recharge, and avoid deep discharge.",
        "STRESS_CRITICAL": "Multiple stress factors are high -- reduce load and cool "
                           "the battery immediately.",
        "STRESS_HIGH": "Overall stress is elevated -- gentler operation will help the "
                       "battery last longer.",
    }
    return advice.get(top.code, top.message)


if __name__ == "__main__":
    # Demo with a made-up stressed state.
    meta = BatteryMetadata.from_config()
    demo = LiveState(
        voltage_v=3.6, current_a=8.0, temperature_c=46.0, c_rate=2.7,
        soc_pct=55.0, soh_pct=90.0, stress_score=82.0,
        temp_rise_rate_c_per_s=0.6, t=10.0,
    )
    fs = evaluate_rules(demo, meta)
    for f in fs:
        print(f"[{f.severity.upper()}] {f.message} -- {f.detail}")
    print("\nRecommendation:", rule_based_recommendation(fs))
