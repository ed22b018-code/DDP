"""
train.py
========
Trains the battery health/life model on the TINY synthetic dataset and saves
everything the rest of the system needs:
  * model.joblib          -- the trained regressor (XGBoost or RandomForest)
  * scaler.joblib         -- scales features to a similar range for training
  * explainer.joblib      -- the SHAP explainer for "what drove this prediction"
  * feature_names.joblib  -- the exact feature order the model expects

Run it with:   python ml/train.py
It finishes in seconds and needs NO internet and NO external files.

--- Beginner glossary of the metrics we print ---
  MAE  (Mean Absolute Error): on average, how far off predictions are, in the
       target's units. Lower is better. E.g. MAE=1.5 for SoH% means we're off
       by about 1.5 percentage points on average.
  RMSE (Root Mean Squared Error): like MAE but punishes big misses more. Also
       lower-is-better and in the target's units.
  R2   (R-squared): fraction of the variation the model explains, from 0 to 1
       (can go negative if the model is worse than guessing the average).
       1.0 = perfect, 0.0 = no better than always guessing the mean.
"""

from __future__ import annotations

import os

import joblib
import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

# --- Make the project root importable (this file is run as a script). ---
import os as _os, sys as _sys
_root = _os.path.dirname(_os.path.abspath(__file__))
while _root != _os.path.dirname(_root) and not _os.path.exists(_os.path.join(_root, "config.yaml")):
    _root = _os.path.dirname(_root)
if _root not in _sys.path:
    _sys.path.insert(0, _root)

from config_loader import artifact_path, load_config, REPO_ROOT
from features import build_feature_matrix, get_active_feature_names, get_target_name
from synthetic_data import generate_synthetic_dataset


def build_model(config: dict):
    """
    Create the regression model chosen in config.yaml, with FIXED parameters
    (no hyperparameter search -- kept intentionally light).

    Returns an unfitted scikit-learn-compatible regressor.
    """
    model_cfg = config["model"]
    model_type = model_cfg["type"].lower()
    random_state = model_cfg["random_state"]

    if model_type == "random_forest":
        from sklearn.ensemble import RandomForestRegressor

        rf = model_cfg["random_forest"]
        return RandomForestRegressor(
            n_estimators=rf["n_estimators"],
            max_depth=rf["max_depth"],
            min_samples_leaf=rf["min_samples_leaf"],
            random_state=random_state,
            n_jobs=-1,
        )

    # Default: XGBoost gradient-boosted trees (strong, fast tabular model).
    from xgboost import XGBRegressor

    xgb = model_cfg["xgboost"]
    return XGBRegressor(
        n_estimators=xgb["n_estimators"],
        max_depth=xgb["max_depth"],
        learning_rate=xgb["learning_rate"],
        subsample=xgb["subsample"],
        colsample_bytree=xgb["colsample_bytree"],
        random_state=random_state,
        n_jobs=-1,
        objective="reg:squarederror",
    )


def build_explainer(model, X_scaled_background: np.ndarray):
    """
    Build a SHAP explainer for the trained model. For tree models SHAP has a
    fast exact method (TreeExplainer). If anything goes wrong we return None so
    training still succeeds (explanations are a bonus, not a requirement).
    """
    try:
        import shap

        # TreeExplainer works for both XGBoost and RandomForest (tree models).
        return shap.TreeExplainer(model)
    except Exception as exc:
        print(f"[train.py] Could not build SHAP explainer ({exc}). Continuing without it.")
        return None


def main() -> None:
    config = load_config()

    print("=" * 70)
    print("TRAINING BATTERY HEALTH MODEL (on tiny synthetic data)")
    print("=" * 70)

    # 1) Get the data --------------------------------------------------------
    df = generate_synthetic_dataset(
        n_rows=300, random_state=config["model"]["random_state"]
    )
    target_name = get_target_name()
    if target_name not in df.columns:
        raise ValueError(
            f"Configured target '{target_name}' is not in the dataset columns. "
            f"Available: {list(df.columns)}"
        )

    # 2) Build features (X) and target (y) -----------------------------------
    X = build_feature_matrix(df)
    y = df[target_name].astype(float)
    feature_names = get_active_feature_names()
    print(f"\nTarget: {target_name}")
    print(f"Features ({len(feature_names)}): {feature_names}")
    print(f"Dataset rows: {len(df)}")

    # 3) Split into train/test (so we can measure real performance) ----------
    test_size = config["model"]["test_size"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=config["model"]["random_state"]
    )

    # 4) Scale features ------------------------------------------------------
    # StandardScaler shifts/scales each feature to mean 0, std 1. Trees don't
    # strictly need it, but it keeps the pipeline consistent and helps SHAP
    # comparisons. We fit ONLY on training data to avoid "peeking" at test data.
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # 5) Train the model -----------------------------------------------------
    model = build_model(config)
    print(f"\nModel type: {config['model']['type']}")
    model.fit(X_train_scaled, y_train)

    # 6) Evaluate on the held-out test set -----------------------------------
    y_pred = model.predict(X_test_scaled)
    mae = mean_absolute_error(y_test, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
    r2 = r2_score(y_test, y_pred)

    unit = "%" if target_name == "soh_future" else "cycles"
    print("\n--- Test-set performance ---")
    print(f"MAE : {mae:.3f} {unit}   (avg absolute error -- lower is better)")
    print(f"RMSE: {rmse:.3f} {unit}   (error, big misses count more -- lower is better)")
    print(f"R2  : {r2:.3f}          (1.0 = perfect, 0.0 = no better than the mean)")

    # 7) Build the SHAP explainer -------------------------------------------
    explainer = build_explainer(model, X_train_scaled)

    # 8) Save all artifacts --------------------------------------------------
    artifacts_dir = os.path.join(REPO_ROOT, config["paths"]["artifacts_dir"])
    os.makedirs(artifacts_dir, exist_ok=True)

    joblib.dump(model, artifact_path("model_file"))
    joblib.dump(scaler, artifact_path("scaler_file"))
    joblib.dump(feature_names, artifact_path("feature_names_file"))
    if explainer is not None:
        joblib.dump(explainer, artifact_path("explainer_file"))

    print("\nSaved artifacts to:", artifacts_dir)
    print("  - model.joblib")
    print("  - scaler.joblib")
    print("  - feature_names.joblib")
    if explainer is not None:
        print("  - explainer.joblib (SHAP)")
    print("\nDone. You can now run the backend, or `python ml/evaluate.py`.")


if __name__ == "__main__":
    main()
