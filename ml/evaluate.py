"""
evaluate.py
===========
Re-checks the trained model's quality and saves an "actual vs predicted" plot
you can put in a report. Run it AFTER training:

    python ml/evaluate.py

It reloads the saved model + scaler, rebuilds the same synthetic dataset,
recomputes MAE / RMSE / R2 on a held-out test split, and saves a scatter plot
to ml/artifacts/actual_vs_predicted.png.

On a perfect model every point would sit on the diagonal dashed line (predicted
== actual). The closer the dots hug that line, the better.
"""

from __future__ import annotations

import os

import joblib
import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

# --- Make the project root importable (this file is run as a script). ---
import os as _os, sys as _sys
_root = _os.path.dirname(_os.path.abspath(__file__))
while _root != _os.path.dirname(_root) and not _os.path.exists(_os.path.join(_root, "config.yaml")):
    _root = _os.path.dirname(_root)
if _root not in _sys.path:
    _sys.path.insert(0, _root)

from config_loader import artifact_path, load_config
from features import build_feature_matrix, get_target_name
from synthetic_data import generate_synthetic_dataset

# Use a non-interactive plotting backend so it works on any machine/server
# (no display window needed -- it just saves a PNG file).
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def main() -> None:
    config = load_config()

    # --- Load the trained artifacts ----------------------------------------
    try:
        model = joblib.load(artifact_path("model_file"))
        scaler = joblib.load(artifact_path("scaler_file"))
    except FileNotFoundError:
        print("No trained model found. Run `python ml/train.py` first.")
        return

    # --- Rebuild the exact same dataset + split ----------------------------
    df = generate_synthetic_dataset(
        n_rows=300, random_state=config["model"]["random_state"]
    )
    target_name = get_target_name()
    X = build_feature_matrix(df)
    y = df[target_name].astype(float)

    _, X_test, _, y_test = train_test_split(
        X, y,
        test_size=config["model"]["test_size"],
        random_state=config["model"]["random_state"],
    )

    # --- Predict + score ----------------------------------------------------
    y_pred = model.predict(scaler.transform(X_test))
    mae = mean_absolute_error(y_test, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
    r2 = r2_score(y_test, y_pred)

    unit = "%" if target_name == "soh_future" else "cycles"
    print("--- Evaluation on held-out test set ---")
    print(f"MAE : {mae:.3f} {unit}")
    print(f"RMSE: {rmse:.3f} {unit}")
    print(f"R2  : {r2:.3f}")

    # --- Plot actual vs predicted ------------------------------------------
    plot_path = os.path.join(load_config()["paths"]["artifacts_dir"], "actual_vs_predicted.png")
    plot_path = artifact_path_for_plot()

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(y_test, y_pred, alpha=0.7, edgecolors="k", linewidths=0.4)

    # Diagonal reference line (perfect predictions land here).
    lo = float(min(y_test.min(), y_pred.min()))
    hi = float(max(y_test.max(), y_pred.max()))
    ax.plot([lo, hi], [lo, hi], "--", color="red", label="perfect prediction")

    ax.set_xlabel(f"Actual {target_name} ({unit})")
    ax.set_ylabel(f"Predicted {target_name} ({unit})")
    ax.set_title(f"Actual vs Predicted\nMAE={mae:.2f}  RMSE={rmse:.2f}  R2={r2:.2f}")
    ax.legend()
    fig.tight_layout()

    os.makedirs(os.path.dirname(plot_path), exist_ok=True)
    fig.savefig(plot_path, dpi=120)
    print(f"\nSaved plot to: {plot_path}")


def artifact_path_for_plot() -> str:
    """Absolute path for the evaluation plot, based on config paths."""
    from config_loader import REPO_ROOT

    rel = load_config()["paths"]["eval_plot_file"]
    return os.path.join(REPO_ROOT, rel)


if __name__ == "__main__":
    main()
