"""
features.py
===========
Turns a raw battery DataFrame into the exact set of INPUT FEATURES the model
uses, as listed in config.yaml under `features.active`.

Two responsibilities:
  1. Engineer extra features from the raw voltage/current/temperature signals:
       * c_rate          -- how fast we charge/discharge relative to capacity
       * temp_stress     -- how far temperature has pushed into the unsafe band
       * voltage_headroom-- how much voltage room is left before the max limit
  2. Select ONLY the active feature columns (order matters for the model).

Because the feature list lives in config.yaml, you can add/remove features by
editing the config -- no code changes needed (as long as the column exists or
can be engineered here).
"""

from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd

# --- Make the project root importable so `config_loader` can always be found,
# whether this file is run as a script or imported as part of a package. ---
import os as _os, sys as _sys
_root = _os.path.dirname(_os.path.abspath(__file__))
while _root != _os.path.dirname(_root) and not _os.path.exists(_os.path.join(_root, "config.yaml")):
    _root = _os.path.dirname(_root)
if _root not in _sys.path:
    _sys.path.insert(0, _root)

from config_loader import load_config


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add engineered V/I/T-derived columns to a copy of `df` and return it.

    The battery limits (capacity, temperature band, voltage limits) come from
    config.yaml so they stay consistent everywhere. If a raw column needed for
    an engineered feature is missing, we fill it with a safe default so we
    never crash.
    """
    config = load_config()
    battery = config["battery"]

    out = df.copy()

    # --- Make sure the raw signals exist; default them if absent ------------
    # This guards against partial/real datasets that don't have every column.
    out["current_a"] = out.get("current_a", pd.Series(0.0, index=out.index))
    out["temperature_c"] = out.get("temperature_c", pd.Series(25.0, index=out.index))
    out["voltage_v"] = out.get(
        "voltage_v",
        out.get("max_voltage_discharge", pd.Series(battery["nominal_voltage_v"], index=out.index)),
    )

    # --- C-rate -------------------------------------------------------------
    # C-rate = current / nominal_capacity. It expresses charge/discharge speed
    # relative to the battery's size. A "1C" rate would fully use the battery
    # in one hour; "2C" in half an hour (harder on the battery). We use the
    # absolute current so both charging and discharging count as "effort".
    nominal_capacity = float(battery["nominal_capacity_ah"]) or 1.0
    out["c_rate"] = out["current_a"].abs() / nominal_capacity

    # --- Temperature stress -------------------------------------------------
    # 0 when at/below the safe temperature, growing as it exceeds the max safe
    # temperature. Scaled so ~+10 deg C over the limit gives a stress of ~1.0.
    max_safe_temp = float(battery["max_safe_temp_c"])
    out["temp_stress"] = np.clip((out["temperature_c"] - max_safe_temp) / 10.0, 0.0, None)

    # --- Voltage headroom ---------------------------------------------------
    # How many volts remain before hitting the max voltage limit. Small
    # headroom during charging is risky (over-charge stress).
    max_voltage = float(battery["max_voltage_v"])
    out["voltage_headroom"] = np.clip(max_voltage - out["voltage_v"], 0.0, None)

    return out


def get_active_feature_names() -> List[str]:
    """Return the ordered list of feature column names from config.yaml."""
    return list(load_config()["features"]["active"])


def get_target_name() -> str:
    """Return the target column name the model should predict, from config."""
    return str(load_config()["prediction"]["target"])


def build_feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """
    Full pipeline: engineer features, then select the active columns in order.

    Returns a DataFrame containing ONLY the model's input columns. Any missing
    feature is created as a column of zeros with a printed warning, so training
    and prediction never crash on a slightly different dataset.
    """
    engineered = engineer_features(df)
    feature_names = get_active_feature_names()

    for name in feature_names:
        if name not in engineered.columns:
            print(f"[features.py] WARNING: feature '{name}' not found -- filling with 0.")
            engineered[name] = 0.0

    # Return columns in the exact configured order (models care about order).
    return engineered[feature_names].astype(float)


def nominal_raw_for_cycle(cycle_index: float) -> dict:
    """
    Estimate the "slow" per-cycle raw measurements from the cycle count alone.

    WHY THIS EXISTS: live sensors only stream voltage/current/temperature. But
    the model was trained on richer per-cycle columns (discharge time, charging
    time, etc.). For live prediction we approximate those columns from the
    current cycle count using the same gentle relationships used to create the
    synthetic data. These are reasonable stand-ins so the live prediction is
    driven mainly by cycle count + the live V/I/T-derived features.

    When you plug in a real system that DOES measure these per-cycle values,
    pass the real numbers instead and this estimate is no longer needed.
    """
    c = float(cycle_index)
    return {
        "cycle_index": c,
        "discharge_time_s": 3600.0 - 3.0 * c,
        "time_at_415v_s": 400.0 - 0.3 * c,
        "time_constant_current_s": 1800.0 - 1.5 * c,
        "decrement_36_34v": 0.15 + 0.0002 * c,
        "max_voltage_discharge": 4.15 - 0.0003 * c,
        "min_voltage_charge": 3.10 + 0.0002 * c,
        "charging_time_s": 5400.0 - 2.0 * c,
    }


def build_single_sample(raw: dict) -> pd.DataFrame:
    """
    Build a one-row feature matrix from a plain dictionary of raw readings.

    Used by the live backend: it receives a single V/I/T sample plus battery
    metadata and needs the model's feature row. Missing keys are tolerated
    (filled by build_feature_matrix / engineer_features defaults).
    """
    df = pd.DataFrame([raw])
    return build_feature_matrix(df)


if __name__ == "__main__":
    # Smoke test using the synthetic data.
    from synthetic_data import generate_synthetic_dataset

    data = generate_synthetic_dataset(n_rows=5)
    X = build_feature_matrix(data)
    print("Active features:", get_active_feature_names())
    print("Target:", get_target_name())
    print("\nFeature matrix:")
    print(X)
