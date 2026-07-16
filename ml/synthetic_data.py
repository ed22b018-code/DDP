"""
synthetic_data.py
=================
Generates a TINY, FAKE (synthetic) battery dataset so the whole system can be
wired up and run end-to-end in seconds -- with NO downloads and NO real data.

>>> IMPORTANT <<<
This data is PLACEHOLDER data. Its only job is to let `train.py` produce a
saved model so the dashboard has something to predict with. The numbers are
made to *look* realistic and to have believable relationships (e.g. more
cycles -> lower health), but they are invented. When you have a real dataset,
replace this file (see the README "How to change things" section) and retrain.

The columns mimic a common public battery-degradation dataset layout so that
swapping in real data later is easy.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def generate_synthetic_dataset(n_rows: int = 300, random_state: int = 42) -> pd.DataFrame:
    """
    Build a small DataFrame of fake battery cycle records.

    Parameters
    ----------
    n_rows : int
        How many rows (each row = one charge/discharge cycle snapshot).
    random_state : int
        Seed for the random number generator so results are repeatable.

    Returns
    -------
    pandas.DataFrame
        Columns include raw cycle measurements plus the prediction targets
        `soh_future` (SoH after +horizon cycles) and `rul` (remaining useful
        life in cycles).
    """
    # A random number generator with a fixed seed = same "random" data each run.
    rng = np.random.default_rng(random_state)

    # ---- The independent driver: how many cycles each record is at ----------
    # Spread cycles from a fresh-ish battery (~10) to a worn one (~600).
    cycle_index = rng.integers(low=10, high=600, size=n_rows).astype(float)

    # ---- "True" current State of Health (SoH), as a percentage -------------
    # SoH = current health vs a new battery (100% = new). Real batteries lose
    # health roughly linearly-then-faster with cycles; we approximate that and
    # add mild random noise so the model has something realistic to learn.
    base_soh = 100.0 - 0.03 * cycle_index - 0.00004 * (cycle_index ** 2)
    soh_now = base_soh + rng.normal(loc=0.0, scale=1.2, size=n_rows)
    soh_now = np.clip(soh_now, 60.0, 100.0)  # keep in a believable range

    # ---- Raw per-cycle measurements (correlated with wear) -----------------
    # As a battery ages, discharge takes less time, charging behaves slightly
    # differently, etc. We build each column off cycle_index + noise.
    discharge_time_s = 3600.0 - 3.0 * cycle_index + rng.normal(0, 60, n_rows)
    time_at_415v_s = 400.0 - 0.3 * cycle_index + rng.normal(0, 20, n_rows)
    time_constant_current_s = 1800.0 - 1.5 * cycle_index + rng.normal(0, 40, n_rows)
    decrement_36_34v = 0.15 + 0.0002 * cycle_index + rng.normal(0, 0.01, n_rows)
    max_voltage_discharge = 4.15 - 0.0003 * cycle_index + rng.normal(0, 0.02, n_rows)
    min_voltage_charge = 3.10 + 0.0002 * cycle_index + rng.normal(0, 0.02, n_rows)
    charging_time_s = 5400.0 - 2.0 * cycle_index + rng.normal(0, 90, n_rows)

    # ---- Live-style V/I/T columns ------------------------------------------
    # These represent a representative instantaneous reading for that cycle.
    # features.py will turn these into engineered features (C-rate, etc.).
    voltage_v = max_voltage_discharge + rng.normal(0, 0.05, n_rows)
    current_a = rng.normal(loc=2.5, scale=0.8, size=n_rows)  # discharge current
    temperature_c = 25.0 + 0.02 * cycle_index + rng.normal(0, 3.0, n_rows)

    # ---- Prediction targets -------------------------------------------------
    # 1) soh_future: SoH after a fixed horizon of extra cycles (default 50).
    #    We model the same degradation curve shifted forward by 50 cycles.
    horizon = 50
    future_cycles = cycle_index + horizon
    soh_future = 100.0 - 0.03 * future_cycles - 0.00004 * (future_cycles ** 2)
    soh_future = soh_future + rng.normal(0, 1.2, n_rows)
    soh_future = np.clip(soh_future, 55.0, 100.0)

    # 2) rul: remaining useful life = cycles until SoH would hit 80% (EOL).
    #    We invert the degradation curve to estimate the end-of-life cycle.
    #    (This is a rough estimate purely for demo purposes.)
    eol_cycle = _estimate_eol_cycle(target_soh=80.0)
    rul = np.clip(eol_cycle - cycle_index, 0, None)
    rul = rul + rng.normal(0, 10, n_rows)
    rul = np.clip(rul, 0, None)

    # Assemble everything into a DataFrame (a table).
    df = pd.DataFrame(
        {
            "cycle_index": cycle_index,
            "discharge_time_s": discharge_time_s,
            "time_at_415v_s": time_at_415v_s,
            "time_constant_current_s": time_constant_current_s,
            "decrement_36_34v": decrement_36_34v,
            "max_voltage_discharge": max_voltage_discharge,
            "min_voltage_charge": min_voltage_charge,
            "charging_time_s": charging_time_s,
            # live-style raw signals used to derive features
            "voltage_v": voltage_v,
            "current_a": current_a,
            "temperature_c": temperature_c,
            # current health (handy for reference / plots)
            "soh_now": soh_now,
            # targets
            "soh_future": soh_future,
            "rul": rul,
        }
    )
    return df


def _estimate_eol_cycle(target_soh: float = 80.0) -> float:
    """
    Solve the degradation curve  SoH = 100 - 0.03*c - 0.00004*c^2  for the
    cycle `c` where SoH drops to `target_soh`. Used to build a fake RUL target.

    This is just the quadratic formula; you do not need to follow the algebra.
    """
    a = -0.00004
    b = -0.03
    c = 100.0 - target_soh
    # Solve a*c^2 + b*c + c_const... using the quadratic formula on:
    #   -0.00004*x^2 - 0.03*x + (100 - target) = 0
    disc = b ** 2 - 4 * a * c
    if disc < 0:
        return 600.0  # fallback
    root = (-b - np.sqrt(disc)) / (2 * a)
    return float(abs(root))


if __name__ == "__main__":
    # Quick smoke test: generate the data and show a preview.
    data = generate_synthetic_dataset()
    print("Synthetic dataset shape (rows, columns):", data.shape)
    print("\nFirst 5 rows:")
    print(data.head())
    print("\nColumn summary:")
    print(data.describe().round(2))
