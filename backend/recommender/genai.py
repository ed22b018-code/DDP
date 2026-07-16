"""
genai.py
========
The GEN-AI (Large Language Model) part of the recommendation engine. It takes
the live numbers + the rule flags + the model's SHAP explanation and asks
Anthropic's Claude to write ONE short, friendly, prioritized recommendation
with a one-line "why", specific to the current readings.

>>> GRACEFUL FALLBACK <<<
If there is no ANTHROPIC_API_KEY (or the SDK/network fails, or genai is
disabled in config), this module NEVER crashes -- it falls back to the
deterministic rule-based sentence from rules.py. So the system always produces
a recommendation, with or without an API key.

The API key is read from the environment (loaded from a .env file if present).
It is NEVER stored in code or config.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

# --- Make the project root importable (works as script or as a package). ---
import os as _os, sys as _sys
_root = _os.path.dirname(_os.path.abspath(__file__))
while _root != _os.path.dirname(_root) and not _os.path.exists(_os.path.join(_root, "config.yaml")):
    _root = _os.path.dirname(_root)
if _root not in _sys.path:
    _sys.path.insert(0, _root)

from config_loader import load_config
from backend.state import LiveState
from backend.recommender.rules import Flag, rule_based_recommendation, most_severe

# Load variables from a .env file into the environment, if one exists.
# (python-dotenv is optional at runtime; guard the import just in case.)
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass


@dataclass
class Recommendation:
    """The final recommendation shown on the dashboard."""
    text: str            # the main advice sentence(s)
    why: str             # one-line reason
    source: str          # "genai" or "rules" (so the UI can label it)
    severity: str        # highest active severity, for coloring


def _build_prompt(state: LiveState, flags: List[Flag], predicted_soh: Optional[float],
                  top_shap: List[dict]) -> str:
    """
    Turn the current situation into a compact text prompt for the LLM.

    We give it the numbers, the triggered rules, the prediction, and the SHAP
    drivers, then ask for a very short, specific recommendation.
    """
    flag_lines = "\n".join(f"- [{f.severity}] {f.message} ({f.detail})" for f in flags) or "- none"
    shap_lines = "\n".join(
        f"- {s.get('friendly_name', s.get('feature'))}: pushing prediction "
        f"{s.get('direction', '')}" for s in top_shap
    ) or "- not available"

    soh_line = f"{predicted_soh:.1f}%" if predicted_soh is not None else "not available"

    return (
        "You are a battery-care assistant for an electric vehicle dashboard. "
        "Give ONE short, practical recommendation (max 2 sentences) to help the "
        "driver prolong battery life RIGHT NOW, based on the live data below. "
        "Then give a one-line reason starting with 'Why:'. Be specific to the "
        "numbers. Plain, friendly language. Do not use markdown.\n\n"
        f"Live readings:\n"
        f"- Voltage: {state.voltage_v:.2f} V\n"
        f"- Current: {state.current_a:.2f} A\n"
        f"- Temperature: {state.temperature_c:.1f} C\n"
        f"- C-rate: {state.c_rate:.2f}\n"
        f"- State of Charge: {state.soc_pct:.0f}%\n"
        f"- State of Health: {state.soh_pct:.0f}%\n"
        f"- Stress score: {state.stress_score:.0f}/100\n\n"
        f"Predicted future State of Health: {soh_line}\n\n"
        f"Active alerts:\n{flag_lines}\n\n"
        f"What is driving the health prediction (SHAP):\n{shap_lines}\n"
    )


class GenAIRecommender:
    """
    Wraps the Anthropic client. Create one and reuse it. It checks for the API
    key at startup and remembers whether the LLM is usable.
    """

    def __init__(self) -> None:
        self.config = load_config()
        self.genai_cfg = self.config["genai"]
        self.api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        self.client = None
        self.enabled = bool(self.genai_cfg.get("enabled", True)) and bool(self.api_key)

        if self.enabled:
            try:
                import anthropic

                self.client = anthropic.Anthropic(api_key=self.api_key)
            except Exception as exc:  # SDK not installed / bad key format, etc.
                print(f"[genai.py] Could not init Anthropic client ({exc}). Using rules only.")
                self.enabled = False

    @property
    def status(self) -> str:
        """A short label for the UI: is the LLM active or are we on rules?"""
        return "genai" if self.enabled else "rules"

    def recommend(self, state: LiveState, flags: List[Flag],
                  predicted_soh: Optional[float] = None,
                  top_shap: Optional[List[dict]] = None) -> Recommendation:
        """
        Produce a recommendation. Tries the LLM first (if enabled); on ANY
        problem it silently falls back to the rule-based sentence.
        """
        top_shap = top_shap or []
        top_flag = most_severe(flags)
        severity = top_flag.severity if top_flag else "info"

        # --- Fallback path: no LLM available -------------------------------
        if not self.enabled or self.client is None:
            text = rule_based_recommendation(flags)
            return Recommendation(
                text=text,
                why="Based on the safety rules and your live readings.",
                source="rules",
                severity=severity,
            )

        # --- LLM path -------------------------------------------------------
        prompt = _build_prompt(state, flags, predicted_soh, top_shap)
        try:
            message = self.client.messages.create(
                model=self.genai_cfg["model"],
                max_tokens=int(self.genai_cfg["max_tokens"]),
                temperature=float(self.genai_cfg["temperature"]),
                messages=[{"role": "user", "content": prompt}],
            )
            # The response content is a list of blocks; join their text.
            raw = "".join(
                block.text for block in message.content if getattr(block, "type", "") == "text"
            ).strip()

            text, why = _split_why(raw)
            return Recommendation(text=text, why=why, source="genai", severity=severity)

        except Exception as exc:
            # Network error, rate limit, invalid key at call time, etc.
            print(f"[genai.py] LLM call failed ({exc}). Falling back to rules.")
            return Recommendation(
                text=rule_based_recommendation(flags),
                why="Based on the safety rules and your live readings.",
                source="rules",
                severity=severity,
            )


def _split_why(raw: str) -> tuple[str, str]:
    """
    Split the model's reply into the main advice and the 'Why:' line.

    The prompt asks the model to end with 'Why: ...'. We locate that; if it's
    missing we just use the whole reply as the advice.
    """
    lower = raw.lower()
    idx = lower.rfind("why:")
    if idx == -1:
        return raw, ""
    text = raw[:idx].strip()
    why = raw[idx + len("why:"):].strip()
    return (text or raw), why


# A shared instance the backend reuses.
_shared: Optional[GenAIRecommender] = None


def get_recommender() -> GenAIRecommender:
    global _shared
    if _shared is None:
        _shared = GenAIRecommender()
    return _shared


if __name__ == "__main__":
    from backend.recommender.rules import evaluate_rules
    from backend.state import BatteryMetadata

    meta = BatteryMetadata.from_config()
    demo = LiveState(
        voltage_v=3.6, current_a=8.0, temperature_c=46.0, c_rate=2.7,
        soc_pct=55.0, soh_pct=90.0, stress_score=82.0,
        temp_rise_rate_c_per_s=0.6, t=10.0,
    )
    rec = get_recommender()
    print("LLM status:", rec.status)
    out = rec.recommend(demo, evaluate_rules(demo, meta), predicted_soh=88.0)
    print("Source:", out.source)
    print("Advice:", out.text)
    print("Why:", out.why)
