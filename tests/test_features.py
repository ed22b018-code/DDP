"""
Tests for the feature engineering (ml/features.py).

These check that:
  * the engineered features (c_rate, temp_stress, voltage_headroom) are computed
    correctly, and
  * the final feature matrix has exactly the columns config.yaml asks for.
"""

import pandas as pd

from config_loader import load_config
from ml.features import (
    engineer_features,
    build_feature_matrix,
    get_active_feature_names,
    nominal_raw_for_cycle,
)


def test_c_rate_is_current_over_capacity():
    """C-rate should equal |current| / nominal_capacity."""
    capacity = load_config()["battery"]["nominal_capacity_ah"]
    df = pd.DataFrame([{"current_a": capacity * 2.0, "temperature_c": 25, "voltage_v": 3.7}])
    out = engineer_features(df)
    # current = 2 * capacity -> C-rate should be 2.0
    assert abs(out["c_rate"].iloc[0] - 2.0) < 1e-6


def test_temp_stress_zero_when_cool():
    """Temperature stress should be 0 at a safe temperature."""
    df = pd.DataFrame([{"current_a": 1.0, "temperature_c": 20.0, "voltage_v": 3.7}])
    out = engineer_features(df)
    assert out["temp_stress"].iloc[0] == 0.0


def test_temp_stress_positive_when_hot():
    """Temperature stress should be > 0 above the max safe temperature."""
    max_temp = load_config()["battery"]["max_safe_temp_c"]
    df = pd.DataFrame([{"current_a": 1.0, "temperature_c": max_temp + 10, "voltage_v": 3.7}])
    out = engineer_features(df)
    assert out["temp_stress"].iloc[0] > 0.0


def test_voltage_headroom_never_negative():
    """Voltage headroom is clamped to be >= 0 even above the max voltage."""
    max_v = load_config()["battery"]["max_voltage_v"]
    df = pd.DataFrame([{"current_a": 1.0, "temperature_c": 25, "voltage_v": max_v + 0.5}])
    out = engineer_features(df)
    assert out["voltage_headroom"].iloc[0] >= 0.0


def test_feature_matrix_columns_match_config():
    """The built matrix must have exactly the configured feature columns, in order."""
    raw = nominal_raw_for_cycle(300)
    raw.update({"voltage_v": 3.7, "current_a": 2.0, "temperature_c": 25.0})
    X = build_feature_matrix(pd.DataFrame([raw]))
    assert list(X.columns) == get_active_feature_names()
    assert len(X) == 1


def test_missing_feature_is_filled_not_crashed():
    """A dataframe missing raw columns should still produce a full matrix."""
    X = build_feature_matrix(pd.DataFrame([{"cycle_index": 100}]))
    # All configured features exist (missing ones filled), no exception raised.
    assert list(X.columns) == get_active_feature_names()
