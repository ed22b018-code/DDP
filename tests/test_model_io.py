"""
Tests for model input/output (ml/model.py) and the live state tracker.

The model test is SKIPPED automatically if you haven't trained yet (so the test
suite passes on a fresh checkout). Run `python ml/train.py` first to exercise it.
"""

import math

import pytest

from ml.model import get_model
from ml.features import build_single_sample, nominal_raw_for_cycle
from backend.state import BatteryStateTracker, BatteryMetadata
from backend.simulator import Sample


def test_prediction_runs_or_reports_untrained():
    """
    predict() must ALWAYS return a PredictionResult -- either a real number
    (if trained) or a safe 'not trained' result (never a crash).
    """
    model = get_model()
    raw = nominal_raw_for_cycle(300)
    raw.update({"voltage_v": 3.7, "current_a": 2.0, "temperature_c": 25.0})
    row = build_single_sample(raw)
    result = model.predict(row)

    if model.is_ready:
        assert not math.isnan(result.prediction)
        # SoH predictions should be a sensible percentage-ish value.
        assert 0 <= result.prediction <= 120
        # SHAP top features should be present when the explainer exists.
        assert isinstance(result.top_features, list)
    else:
        assert result.model_loaded is False
        assert "train" in result.note.lower()


def test_soc_decreases_on_discharge():
    """
    Coulomb counting: a positive (discharge) current should lower SoC over time.
    """
    tracker = BatteryStateTracker(BatteryMetadata.from_config(), start_soc_pct=90.0)
    # Feed several discharge samples spaced 1 second apart.
    last = None
    for i in range(1, 6):
        last = tracker.update(Sample(voltage_v=3.7, current_a=5.0, temperature_c=25.0, t=float(i)))
    assert last.soc_pct < 90.0


def test_soc_increases_on_charge():
    """A negative (charging) current should raise SoC over time."""
    tracker = BatteryStateTracker(BatteryMetadata.from_config(), start_soc_pct=50.0)
    last = None
    for i in range(1, 6):
        last = tracker.update(Sample(voltage_v=4.0, current_a=-5.0, temperature_c=25.0, t=float(i)))
    assert last.soc_pct > 50.0


def test_stress_score_within_bounds():
    """The stress score must always stay in the 0-100 range."""
    tracker = BatteryStateTracker(BatteryMetadata.from_config())
    s = tracker.update(Sample(voltage_v=3.6, current_a=9.0, temperature_c=55.0, t=1.0))
    assert 0.0 <= s.stress_score <= 100.0
