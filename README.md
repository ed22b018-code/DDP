# Battery Health Monitoring, Life-Prediction & Recommendation System

A complete, runnable research prototype that:

1. **PREDICTS** battery **State of Health (SoH)** / remaining life using a small
   machine-learning model.
2. **MONITORS** a live stream of voltage / current / temperature and continuously
   estimates **State of Charge (SoC)**, **SoH**, and a **stress score**.
3. **RECOMMENDS** — in real time — how to prolong battery life, combining a
   deterministic **rule engine** with a **Gen-AI (LLM)** layer, all shown on one
   live dashboard.

> **Beginner note — the glossary you'll need:**
> - **SoC** (State of Charge): how *full* the battery is right now, 0–100% (like a fuel gauge).
> - **SoH** (State of Health): overall *health* vs a brand-new battery, 0–100%.
> - **RUL** (Remaining Useful Life): how many charge/discharge *cycles* remain before end-of-life.
> - **C-rate**: charge/discharge speed relative to battery size (`current ÷ capacity`).
> - **MAE / RMSE / R²**: how we score the model (defined in `ml/train.py`).
> - **SHAP**: a method that explains *which inputs pushed a prediction up or down*.

> ⚠️ **The ML model is trained on a TINY built-in SYNTHETIC dataset** so everything
> runs in seconds with no downloads. It is a placeholder to wire up the system.
> See **[How to change things](#how-to-change-things)** to plug in real data later.

---

## What's in the box

```
battery-health-system/
  config.yaml            # THE single control panel (features, horizon, model, thresholds)
  .env.example           # copy to .env and add your ANTHROPIC_API_KEY (optional)
  config_loader.py       # shared config reader
  requirements.txt       # Python dependencies
  ml/
    synthetic_data.py    # generates the tiny fake training dataset
    features.py          # feature engineering (reads config.yaml)
    train.py             # trains + saves model, scaler, SHAP explainer; prints MAE/RMSE/R2
    evaluate.py          # metrics + actual-vs-predicted plot
    model.py             # load model, predict, explain (SHAP)
    artifacts/           # saved model.joblib, scaler, explainer (created by train.py)
  backend/
    main.py              # FastAPI: REST + WebSocket + the AGENTIC LOOP
    simulator.py         # streams realistic V/I/T with scenario presets
    state.py             # running SoC / SoH / stress from the live stream
    recommender/
      rules.py           # threshold rules -> flags with severity
      genai.py           # LLM turns flags+state+SHAP into plain-language advice
  frontend/              # React + Vite + Tailwind + Recharts dashboard
  tests/                 # unit tests for features, rules, model I/O
  scripts/
    run_dev.sh           # one command starts backend + frontend (macOS/Linux/Git Bash)
    run_dev.ps1          # same, for Windows PowerShell
```

---

## Requirements

- **Python 3.11+** (tested on 3.11 and 3.14). If a package wheel is missing for
  your exact Python version, use Python 3.11 — see [Troubleshooting](#troubleshooting).
- **Node.js 18+** and **npm** (for the dashboard).

---

## Quick start

### 1. Set up Python

```bash
cd battery-health-system

# Create and activate a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. (Optional) add your Anthropic API key

```bash
cp .env.example .env
# then edit .env and paste your key after ANTHROPIC_API_KEY=
```

> **No key? No problem.** The system automatically falls back to clear
> rule-based recommendation text and keeps working.

### 3. Train the tiny model (runs in seconds, no downloads)

```bash
python ml/train.py
```

You'll see something like:

```
MAE : 0.99 %   (avg absolute error -- lower is better)
RMSE: 1.25 %
R2  : 0.98     (1.0 = perfect)
Saved artifacts to: ml/artifacts
```

### 4. Start everything with one command

```bash
# macOS / Linux / Git Bash on Windows:
bash scripts/run_dev.sh

# Windows PowerShell:
powershell -ExecutionPolicy Bypass -File scripts\run_dev.ps1
```

Then open the dashboard: **http://localhost:5173**
Backend API docs (auto-generated): **http://127.0.0.1:8000/docs**

### 5. Use the dashboard

1. Fill in the **Battery Setup** form and click **Start Monitoring**.
2. Watch the **live gauges** and **rolling V/I/T charts**.
3. See the **prediction** (SoH/RUL) with a **SHAP "What's driving this?"** breakdown.
4. Read the **recommendation** and **color-coded alerts** update live.
5. Click **Scenario** buttons (e.g. *Aggressive*, *Hot Day*) and watch the
   readings and recommendations visibly change.

---

## Running the pieces individually

```bash
python ml/train.py           # train + save the model
python ml/evaluate.py        # metrics + actual-vs-predicted plot (ml/artifacts/)
python -m uvicorn backend.main:app --port 8000    # backend only
cd frontend && npm install && npm run dev          # dashboard only
python -m pytest             # run the unit tests
```

---

## The "agentic AI" loop (the heart of the project)

Each streamed sample runs one **gather → reason → decide → act** cycle in
`backend/main.py` (WebSocket `/stream`):

1. **GATHER** — read the next V/I/T sample; update SoC / SoH / stress.
2. **PREDICT** — periodically recompute the ML SoH + SHAP explanation.
3. **REASON** — run the deterministic rules to get alert flags.
4. **DECIDE** — decide whether the situation is worth escalating to the LLM
   (severity changed, or throttle window elapsed) — this avoids spamming the API.
5. **ACT** — produce the single most important recommendation and push
   everything to the dashboard.

This continuous sense-and-decide behaviour is what makes it *agentic*.

---

## How the real-sensor swap works (no hardware today)

The backend only ever calls `DataSource.next_sample()`. Today that returns a
**simulated** reading. To use real hardware later, write a `DataSource` subclass
whose `next_sample()` reads your sensor, and return it from **`build_data_source()`
in `backend/main.py`** — the ONE swap point. Nothing else changes; simulated and
real data are handled identically.

---

## How to change things

Everything tunable lives in **`config.yaml`** — you should rarely need to touch
code logic.

### Plug in a REAL dataset later
1. Put your CSV somewhere and load it in `ml/train.py` **instead of**
   `generate_synthetic_dataset(...)`:
   ```python
   import pandas as pd
   df = pd.read_csv("path/to/your_data.csv")
   ```
2. Make sure your CSV has the raw columns listed in `config.yaml` under
   `features.active` (or that `ml/features.py` can engineer them), plus your
   target column.
3. Retrain: `python ml/train.py`.

### Change the feature list
Edit `config.yaml` → `features.active`. Add/remove column names. Engineered
features (`c_rate`, `temp_stress`, `voltage_headroom`) are built in
`ml/features.py`; add new ones there if needed. Retrain afterwards.

### Change the prediction horizon
Edit `config.yaml` → `prediction.horizon_cycles` (default `50`). Retrain.

### Switch SoH-prediction ↔ RUL-prediction
Edit `config.yaml` → `prediction.target`:
- `"soh_future"` → predict SoH at +horizon cycles (default)
- `"rul"` → predict Remaining Useful Life in cycles
Retrain. The dashboard labels/units update automatically.

### Switch the model
Edit `config.yaml` → `model.type`: `"xgboost"` (default) or `"random_forest"`.
Fixed parameters for each live under `model.xgboost` / `model.random_forest`.
Retrain.

### Tune the recommendation sensitivity
Edit `config.yaml` → `thresholds` (temperature, C-rate, voltage margins, stress
levels). Takes effect on the next backend restart — no retraining needed.

### Change the Gen-AI behaviour
Edit `config.yaml` → `genai` (`enabled`, `model`, `max_tokens`, `temperature`).
The API key always comes from the `ANTHROPIC_API_KEY` environment variable,
never from config.

---

## Troubleshooting

- **`python ml/train.py` says a package is missing / a wheel won't install:**
  Use Python 3.11 (best-supported for `xgboost`/`shap`). Recreate the venv with
  `py -3.11 -m venv .venv` (Windows) and reinstall.
- **Dashboard shows "Model: not trained":** run `python ml/train.py`.
- **Dashboard shows "Stream: offline":** make sure the backend is running on
  port 8000. It auto-reconnects once the backend is back.
- **Recommendations say "rule-based" not "Gen-AI":** that means no valid
  `ANTHROPIC_API_KEY` was found. This is expected and fine — add a key in `.env`
  to enable the LLM.
- **Backend on a different host/port:** set `VITE_API_BASE` and `VITE_WS_BASE`
  for the frontend (see `frontend/src/api.js`).

---

## Notes for the report

- The model is intentionally tiny and trained on synthetic data — swap in a real
  dataset (see above) and retrain to get meaningful accuracy.
- `ml/artifacts/actual_vs_predicted.png` (from `python ml/evaluate.py`) is a
  ready-made figure for your write-up.
- No secrets are stored in code; the LLM key is read only from the environment.
