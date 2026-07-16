// -----------------------------------------------------------------------------
// api.js -- one place that knows how to reach the backend.
// -----------------------------------------------------------------------------
// If your backend runs somewhere else, change these two constants (or set the
// VITE_API_BASE / VITE_WS_BASE environment variables). Everything else in the
// app imports from here, so there's a single spot to update.

// import.meta.env.* are Vite environment variables (optional).
const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";
const WS_BASE = import.meta.env.VITE_WS_BASE || "ws://127.0.0.1:8000";

export const WS_URL = `${WS_BASE}/stream`;

// A small helper that POSTs JSON and never throws to the caller in a way that
// crashes the UI -- it returns { ok, data, error } instead.
async function postJson(path, body) {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const data = await res.json();
    return { ok: res.ok, data, error: null };
  } catch (err) {
    return { ok: false, data: null, error: String(err) };
  }
}

async function getJson(path) {
  try {
    const res = await fetch(`${API_BASE}${path}`);
    const data = await res.json();
    return { ok: res.ok, data, error: null };
  } catch (err) {
    return { ok: false, data: null, error: String(err) };
  }
}

// The specific API calls the dashboard uses.
export const api = {
  health: () => getJson("/health"),
  setupBattery: (metadata) => postJson("/battery/setup", metadata),
  predict: () => postJson("/predict", {}),
  setScenario: (scenario) => postJson("/simulator/scenario", { scenario }),
  getScenarios: () => getJson("/simulator/scenarios"),
};
