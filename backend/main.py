"""
main.py  --  FastAPI backend (REST + WebSocket)
===============================================
This is the "brain server" the dashboard talks to. It:
  * accepts one-time battery setup metadata           (POST /battery/setup)
  * returns an ML prediction with SHAP explanation    (POST /predict)
  * streams live V/I/T + SoC/SoH/stress + advice       (WebSocket /stream)
  * switches the live simulator scenario               (POST /simulator/scenario)

THE AGENTIC LOOP lives in the WebSocket handler. Each "tick" it:
    1. GATHER   -> read the next sample and update SoC/SoH/stress
    2. PREDICT  -> periodically recompute the ML SoH + SHAP
    3. REASON   -> run the deterministic rules to get alert flags
    4. DECIDE   -> decide whether this situation is worth escalating to the LLM
    5. ACT      -> produce the single most important recommendation and push
                   everything to the dashboard
This gather->reason->decide->act cycle is what makes it "agentic": it
continuously senses the world and chooses what to surface.

Everything is defensive: missing model, missing API key, bad input, or a
dropped WebSocket are all handled without crashing the server.
"""

from __future__ import annotations

import asyncio
import time
from typing import List, Optional

# --- Make the project root importable (works with `uvicorn backend.main:app`
# and `python backend/main.py` alike). ---
import os as _os, sys as _sys
_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _root not in _sys.path:
    _sys.path.insert(0, _root)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config_loader import load_config
from ml.features import build_single_sample, nominal_raw_for_cycle
from ml.model import get_model
from backend.simulator import SimulatedDataSource, DataSource, list_scenarios
from backend.state import BatteryStateTracker, BatteryMetadata, LiveState
from backend.recommender.rules import evaluate_rules, most_severe, Flag
from backend.recommender.genai import get_recommender, Recommendation


# =============================================================================
# App setup
# =============================================================================
config = load_config()
app = FastAPI(title="Battery Health Monitoring System", version="1.0")

# Allow the React dev server (any localhost port) to talk to us during
# development. This is what lets the browser call our API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # fine for a local research project
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# The current session (single-user research app -> one shared session is fine)
# =============================================================================
class Session:
    """
    Holds everything about the current monitoring session: the battery
    metadata, the live-state tracker, and the data source (simulator now, real
    hardware later).
    """

    def __init__(self) -> None:
        self.metadata: BatteryMetadata = BatteryMetadata.from_config()
        self.tracker: BatteryStateTracker = BatteryStateTracker(self.metadata)
        self.data_source: DataSource = build_data_source(
            config["stream"]["default_scenario"]
        )
        self.scenario: str = config["stream"]["default_scenario"]

    def reset_with_metadata(self, metadata: BatteryMetadata) -> None:
        """Restart the tracker when the user submits new battery metadata."""
        self.metadata = metadata
        self.tracker = BatteryStateTracker(metadata)


def build_data_source(scenario: str) -> DataSource:
    """
    >>> THE SINGLE SWAP POINT FOR REAL HARDWARE <<<
    Today this returns the simulator. To use real sensors later, return your
    own DataSource subclass here (one that reads the sensor in next_sample()).
    Nothing else in the backend needs to change.
    """
    return SimulatedDataSource(scenario=scenario)


# The one shared session for this server process.
session = Session()

# Shared, reusable helpers (loaded once).
battery_model = get_model()
recommender = get_recommender()


# =============================================================================
# Request/response shapes (pydantic validates incoming JSON for us)
# =============================================================================
class BatterySetup(BaseModel):
    """Battery metadata from the dashboard setup form."""
    chemistry: str = Field(default="Li-ion NMC")
    nominal_capacity_ah: float = Field(default=3.0, gt=0)
    nominal_voltage_v: float = Field(default=3.7, gt=0)
    max_voltage_v: float = Field(default=4.2, gt=0)
    min_voltage_v: float = Field(default=3.0, gt=0)
    max_safe_temp_c: float = Field(default=45.0)
    cell_count: int = Field(default=1, ge=1)
    current_cycle_count: int = Field(default=300, ge=0)


class ScenarioRequest(BaseModel):
    scenario: str


# =============================================================================
# Helper: run the ML model on the current situation
# =============================================================================
def predict_now(state: Optional[LiveState] = None) -> dict:
    """
    Build a feature row from the battery metadata + latest live reading and run
    the model. Returns a JSON-friendly dict including the top SHAP features.

    Never raises: if the model isn't trained it returns a clear 'not ready'
    payload so the dashboard can show a helpful message.
    """
    meta = session.metadata

    # Start from the estimated per-cycle values for this battery's cycle count.
    raw = nominal_raw_for_cycle(meta.current_cycle_count)

    # Overlay the latest live V/I/T if we have one (so the derived features
    # like c_rate / temp_stress reflect the live conditions).
    latest = state or session.tracker.latest()
    if latest is not None:
        raw["voltage_v"] = latest.voltage_v
        raw["current_a"] = latest.current_a
        raw["temperature_c"] = latest.temperature_c
    else:
        raw["voltage_v"] = meta.nominal_voltage_v
        raw["current_a"] = 1.0
        raw["temperature_c"] = 25.0

    feature_row = build_single_sample(raw)
    result = battery_model.predict(feature_row, top_k=5)

    # Convert SHAP explanations into plain dicts for JSON.
    shap_list = [
        {
            "feature": f.feature,
            "friendly_name": f.friendly_name,
            "value": round(f.value, 4),
            "shap_value": round(f.shap_value, 4),
            "direction": f.direction,
            "plain_text": f.plain_text,
        }
        for f in result.top_features
    ]

    return {
        "model_loaded": result.model_loaded,
        "target": result.target_name,
        "unit": result.unit,
        "prediction": None if _is_nan(result.prediction) else round(result.prediction, 2),
        "horizon_cycles": config["prediction"]["horizon_cycles"],
        "top_features": shap_list,
        "note": result.note,
    }


def _is_nan(x: float) -> bool:
    return x != x


# =============================================================================
# REST endpoints
# =============================================================================
@app.get("/")
def root():
    """Simple health check + a summary of what the server offers."""
    return {
        "status": "ok",
        "message": "Battery Health Monitoring System backend is running.",
        "model_ready": battery_model.is_ready,
        "genai_status": recommender.status,
        "scenarios": list_scenarios(),
    }


@app.get("/health")
def health():
    """Liveness probe used by the dashboard/status badge."""
    return {
        "model_ready": battery_model.is_ready,
        "genai_status": recommender.status,   # "genai" or "rules"
        "current_scenario": session.scenario,
    }


@app.post("/battery/setup")
def battery_setup(setup: BatterySetup):
    """
    Save the one-time battery metadata and (re)start the live tracker.

    Returns the accepted metadata so the UI can confirm it.
    """
    metadata = BatteryMetadata(
        chemistry=setup.chemistry,
        nominal_capacity_ah=setup.nominal_capacity_ah,
        nominal_voltage_v=setup.nominal_voltage_v,
        max_voltage_v=setup.max_voltage_v,
        min_voltage_v=setup.min_voltage_v,
        max_safe_temp_c=setup.max_safe_temp_c,
        cell_count=setup.cell_count,
        current_cycle_count=setup.current_cycle_count,
    )
    session.reset_with_metadata(metadata)
    return {"status": "ok", "metadata": setup.model_dump()}


@app.post("/predict")
def predict_endpoint():
    """Return the current ML prediction + SHAP explanation (on demand)."""
    return predict_now()


@app.post("/simulator/scenario")
def set_scenario(req: ScenarioRequest):
    """
    Switch the live scenario (only affects the simulator data source). Returns
    the active scenario, or an error message for an unknown name.
    """
    if req.scenario not in list_scenarios():
        return {
            "status": "error",
            "message": f"Unknown scenario '{req.scenario}'.",
            "available": list_scenarios(),
        }
    # If the current data source is the simulator, update it in place.
    if isinstance(session.data_source, SimulatedDataSource):
        session.data_source.set_scenario(req.scenario)
    session.scenario = req.scenario
    return {"status": "ok", "scenario": req.scenario}


@app.get("/simulator/scenarios")
def get_scenarios():
    """List the available scenario presets for the UI buttons."""
    return {"scenarios": list_scenarios(), "current": session.scenario}


# =============================================================================
# WebSocket stream  --  THE AGENTIC LOOP
# =============================================================================
@app.websocket("/stream")
async def stream(websocket: WebSocket):
    """
    Push live samples + estimates + recommendations to the dashboard.

    Runs the gather->reason->decide->act loop once per sample. Handles the
    client disconnecting at any time without crashing the server.
    """
    await websocket.accept()

    sample_rate = float(config["stream"]["sample_rate_hz"]) or 2.0
    period = 1.0 / sample_rate
    soh_refresh_every = int(config["stream"]["soh_refresh_every_n_samples"])
    genai_min_gap = float(config["stream"]["genai_min_seconds_between_calls"])

    sample_count = 0
    last_prediction: dict = predict_now()
    last_genai_time = 0.0
    last_severity = "info"
    last_recommendation: Optional[Recommendation] = None

    try:
        while True:
            # ---- STEP 1: GATHER -------------------------------------------
            # Read the next reading from the data source (simulator or, later,
            # real hardware). Then fold it into the running SoC/stress.
            sample = session.data_source.next_sample()

            # ---- STEP 2: PREDICT (periodically) ---------------------------
            # Recomputing the ML model every single tick is wasteful, so we do
            # it every N samples and reuse the result in between.
            model_soh = None
            if sample_count % soh_refresh_every == 0:
                last_prediction = predict_now(session.tracker.latest())
                if last_prediction.get("prediction") is not None:
                    model_soh = last_prediction["prediction"]

            state = session.tracker.update(sample, model_soh=model_soh)

            # ---- STEP 3: REASON (deterministic rules) ---------------------
            flags: List[Flag] = evaluate_rules(state, session.metadata)
            top_flag = most_severe(flags)
            current_severity = top_flag.severity if top_flag else "info"

            # ---- STEP 4: DECIDE (whether to escalate to the LLM) ----------
            # We call the (slower, costlier) LLM only when it's worth it:
            #   * the severity changed (situation got better/worse), OR
            #   * enough time passed since the last call (throttle), OR
            #   * we have no recommendation yet.
            # Otherwise we reuse the previous recommendation. This keeps the
            # loop responsive and avoids spamming the API.
            now = time.time()
            severity_changed = current_severity != last_severity
            throttle_ok = (now - last_genai_time) >= genai_min_gap
            should_escalate = (
                last_recommendation is None
                or severity_changed
                or (bool(flags) and throttle_ok)
            )

            # ---- STEP 5: ACT (produce + push the recommendation) ----------
            if should_escalate:
                # run_in_executor keeps the (possibly slow, network) LLM call
                # from blocking the async event loop / other clients.
                loop = asyncio.get_event_loop()
                last_recommendation = await loop.run_in_executor(
                    None,
                    lambda: recommender.recommend(
                        state,
                        flags,
                        predicted_soh=last_prediction.get("prediction"),
                        top_shap=last_prediction.get("top_features", []),
                    ),
                )
                last_genai_time = now
                last_severity = current_severity

            rec = last_recommendation

            # Build the message the dashboard receives each tick.
            payload = {
                "type": "tick",
                "state": state.as_dict(),
                "metadata": {
                    "chemistry": session.metadata.chemistry,
                    "nominal_capacity_ah": session.metadata.nominal_capacity_ah,
                    "max_voltage_v": session.metadata.max_voltage_v,
                    "min_voltage_v": session.metadata.min_voltage_v,
                    "max_safe_temp_c": session.metadata.max_safe_temp_c,
                    "current_cycle_count": session.metadata.current_cycle_count,
                },
                "prediction": last_prediction,
                "flags": [f.as_dict() for f in flags],
                "recommendation": {
                    "text": rec.text if rec else "",
                    "why": rec.why if rec else "",
                    "source": rec.source if rec else "rules",
                    "severity": rec.severity if rec else "info",
                },
                "scenario": session.scenario,
                "genai_status": recommender.status,
            }

            await websocket.send_json(payload)

            sample_count += 1
            await asyncio.sleep(period)

    except WebSocketDisconnect:
        # The browser closed the connection (navigated away / refreshed). This
        # is normal -- just stop the loop quietly.
        print("[main.py] WebSocket client disconnected.")
    except Exception as exc:
        # Any other error: log it and close gracefully so the server survives.
        print(f"[main.py] Stream error: {exc}")
        try:
            await websocket.close()
        except Exception:
            pass


if __name__ == "__main__":
    # Allow `python backend/main.py` to run the server directly.
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=False)
