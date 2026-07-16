"""
model.py
========
Loads the trained model artifacts and provides two things the rest of the
system needs:
  * predict(...)  -> a health/life number (SoH or RUL, per config)
  * explain(...)  -> SHAP explanations: which features pushed the prediction
                     up or down, in plain language.

SHAP (SHapley Additive exPlanations) is a technique that attributes a
prediction to each input feature -- like splitting the "credit" for the answer
among the inputs. A positive SHAP value means that feature pushed the estimate
UP; negative means it pushed it DOWN.

Everything here is defensive: if the model artifacts are missing (e.g. you
haven't run `python ml/train.py` yet), the functions raise a clear error or
return a safe fallback so the backend never crashes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd

# --- Make the project root importable (works as script or as a package). ---
import os as _os, sys as _sys
_root = _os.path.dirname(_os.path.abspath(__file__))
while _root != _os.path.dirname(_root) and not _os.path.exists(_os.path.join(_root, "config.yaml")):
    _root = _os.path.dirname(_root)
if _root not in _sys.path:
    _sys.path.insert(0, _root)

from config_loader import artifact_path, load_config

# joblib loads/saves Python objects (our model, scaler, etc.) to disk.
import joblib


# A friendly, human-readable label for each feature name. Used to phrase the
# SHAP explanation in plain English on the dashboard.
FRIENDLY_FEATURE_LABELS = {
    "cycle_index": "Cycle count",
    "discharge_time_s": "Discharge time",
    "time_at_415v_s": "Time near 4.15V",
    "time_constant_current_s": "Constant-current time",
    "decrement_36_34v": "Voltage drop (3.6-3.4V)",
    "max_voltage_discharge": "Max discharge voltage",
    "min_voltage_charge": "Min charge voltage",
    "charging_time_s": "Charging time",
    "c_rate": "C-rate (charge/discharge speed)",
    "temp_stress": "Temperature stress",
    "voltage_headroom": "Voltage headroom",
}


@dataclass
class FeatureExplanation:
    """One feature's contribution to a single prediction."""
    feature: str
    friendly_name: str
    value: float          # the feature's actual value for this sample
    shap_value: float     # how much it pushed the prediction (+up / -down)
    direction: str        # "up" or "down"
    plain_text: str       # beginner-friendly sentence


@dataclass
class PredictionResult:
    """The full result of one prediction, including explanations."""
    prediction: float
    target_name: str                       # "soh_future" or "rul"
    unit: str                              # "%" or "cycles"
    top_features: List[FeatureExplanation] = field(default_factory=list)
    model_loaded: bool = True
    note: str = ""


class BatteryModel:
    """
    Wraps the trained model + scaler + SHAP explainer.

    Create ONE of these and reuse it (loading from disk each prediction would
    be slow). The backend keeps a single shared instance.
    """

    def __init__(self) -> None:
        self.config = load_config()
        self.model = None
        self.scaler = None
        self.explainer = None
        self.feature_names: List[str] = []
        self.target_name: str = self.config["prediction"]["target"]
        self.unit: str = "%" if self.target_name == "soh_future" else "cycles"
        self._load()

    # ---- Loading -----------------------------------------------------------
    def _load(self) -> None:
        """
        Try to load all artifacts from disk. If anything is missing we DON'T
        crash -- we leave model=None and the backend will report that training
        is needed.
        """
        try:
            self.model = joblib.load(artifact_path("model_file"))
            self.scaler = joblib.load(artifact_path("scaler_file"))
            self.feature_names = joblib.load(artifact_path("feature_names_file"))
            # The SHAP explainer is optional; predictions still work without it.
            explainer_file = artifact_path("explainer_file")
            if os.path.isfile(explainer_file):
                self.explainer = joblib.load(explainer_file)
        except FileNotFoundError:
            self.model = None
            print(
                "[model.py] No trained model found. "
                "Run `python ml/train.py` first. The API will keep running and "
                "report that a model is needed."
            )

    @property
    def is_ready(self) -> bool:
        """True only if we have a usable model + scaler + feature list."""
        return self.model is not None and self.scaler is not None and bool(self.feature_names)

    # ---- Prediction --------------------------------------------------------
    def predict(self, feature_row: pd.DataFrame, top_k: int = 5) -> PredictionResult:
        """
        Predict SoH/RUL for a single already-built feature row and explain it.

        `feature_row` should be a one-row DataFrame with the model's features
        (build it with ml.features.build_single_sample). Returns a
        PredictionResult (never raises for a missing model -- returns a safe
        fallback instead).
        """
        if not self.is_ready:
            # Safe fallback so the live dashboard keeps working pre-training.
            return PredictionResult(
                prediction=float("nan"),
                target_name=self.target_name,
                unit=self.unit,
                model_loaded=False,
                note="Model not trained yet. Run `python ml/train.py`.",
            )

        # Make sure the columns are in the exact order the model expects.
        X = feature_row.reindex(columns=self.feature_names, fill_value=0.0).astype(float)

        # Scale the features the same way we did during training.
        X_scaled = self.scaler.transform(X)

        # The model returns an array; we predict one row so take element 0.
        prediction = float(self.model.predict(X_scaled)[0])

        # Build SHAP explanations (top features driving this prediction).
        top_features = self._explain(X, X_scaled, top_k=top_k)

        return PredictionResult(
            prediction=prediction,
            target_name=self.target_name,
            unit=self.unit,
            top_features=top_features,
        )

    # ---- Explainability ----------------------------------------------------
    def _explain(self, X: pd.DataFrame, X_scaled: np.ndarray, top_k: int) -> List[FeatureExplanation]:
        """
        Compute SHAP values for one sample and return the top_k most influential
        features as friendly explanations. If the explainer is unavailable we
        return an empty list (predictions still work).
        """
        if self.explainer is None:
            return []

        try:
            # SHAP returns an array of contributions, one per feature.
            shap_values = self.explainer.shap_values(X_scaled)
            shap_row = np.array(shap_values).reshape(-1)  # flatten to 1D
        except Exception as exc:  # be defensive; never break a prediction
            print(f"[model.py] SHAP explanation failed: {exc}")
            return []

        explanations: List[FeatureExplanation] = []
        for name, shap_val, raw_val in zip(self.feature_names, shap_row, X.iloc[0].tolist()):
            direction = "up" if shap_val >= 0 else "down"
            friendly = FRIENDLY_FEATURE_LABELS.get(name, name)
            explanations.append(
                FeatureExplanation(
                    feature=name,
                    friendly_name=friendly,
                    value=float(raw_val),
                    shap_value=float(shap_val),
                    direction=direction,
                    plain_text=self._phrase(friendly, direction),
                )
            )

        # Sort by absolute impact (biggest movers first) and keep the top_k.
        explanations.sort(key=lambda e: abs(e.shap_value), reverse=True)
        return explanations[:top_k]

    def _phrase(self, friendly_name: str, direction: str) -> str:
        """Turn a feature + direction into a plain-language sentence."""
        health_word = "raising" if direction == "up" else "lowering"
        thing = "predicted health" if self.target_name == "soh_future" else "predicted remaining life"
        return f"{friendly_name} is {health_word} the {thing}."


# A module-level singleton the backend can import and reuse.
_shared_model: Optional[BatteryModel] = None


def get_model() -> BatteryModel:
    """Return a shared, lazily-created BatteryModel instance."""
    global _shared_model
    if _shared_model is None:
        _shared_model = BatteryModel()
    return _shared_model


def reload_model() -> BatteryModel:
    """Force a fresh reload from disk (call after retraining)."""
    global _shared_model
    _shared_model = BatteryModel()
    return _shared_model


if __name__ == "__main__":
    # Smoke test: load the model and predict on one synthetic sample.
    from synthetic_data import generate_synthetic_dataset
    from features import build_feature_matrix

    m = get_model()
    if not m.is_ready:
        print("Train the model first: python ml/train.py")
    else:
        sample = build_feature_matrix(generate_synthetic_dataset(n_rows=1))
        result = m.predict(sample)
        print(f"Prediction: {result.prediction:.2f} {result.unit}")
        for f in result.top_features:
            print(f"  - {f.plain_text}  (shap={f.shap_value:+.3f})")
