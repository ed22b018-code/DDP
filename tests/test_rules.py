"""
Tests for the deterministic rule engine (backend/recommender/rules.py).

We build fake LiveState snapshots and check the right flags fire.
"""

from backend.state import LiveState, BatteryMetadata
from backend.recommender.rules import evaluate_rules, most_severe, rule_based_recommendation


def _state(**overrides):
    """Helper: a healthy LiveState with fields overridable per test."""
    base = dict(
        voltage_v=3.8,
        current_a=2.0,
        temperature_c=25.0,
        c_rate=0.5,
        soc_pct=80.0,
        soh_pct=95.0,
        stress_score=5.0,
        temp_rise_rate_c_per_s=0.0,
        t=1.0,
    )
    base.update(overrides)
    return LiveState(**base)


META = BatteryMetadata.from_config()


def test_healthy_state_has_no_flags():
    flags = evaluate_rules(_state(), META)
    assert flags == []
    assert "healthy" in rule_based_recommendation(flags).lower()


def test_hot_temperature_raises_warning():
    flags = evaluate_rules(_state(temperature_c=42.0), META)
    codes = [f.code for f in flags]
    assert "TEMP_HIGH" in codes


def test_critical_temperature_raises_critical():
    flags = evaluate_rules(_state(temperature_c=50.0), META)
    top = most_severe(flags)
    assert top is not None
    assert top.severity == "critical"


def test_high_c_rate_flagged():
    flags = evaluate_rules(_state(c_rate=2.8), META)
    codes = [f.code for f in flags]
    assert "CRATE_CRITICAL" in codes


def test_low_soc_is_info():
    flags = evaluate_rules(_state(soc_pct=10.0), META)
    codes = [f.code for f in flags]
    assert "SOC_LOW" in codes


def test_most_severe_orders_correctly():
    flags = evaluate_rules(_state(temperature_c=50.0, soc_pct=10.0), META)
    # critical temperature should outrank the info-level low SoC
    assert most_severe(flags).severity == "critical"


def test_recommendation_is_nonempty_string():
    flags = evaluate_rules(_state(temperature_c=42.0), META)
    text = rule_based_recommendation(flags)
    assert isinstance(text, str) and len(text) > 0
