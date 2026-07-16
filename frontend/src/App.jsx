// -----------------------------------------------------------------------------
// App.jsx -- the whole dashboard, assembled from the panel components.
// -----------------------------------------------------------------------------
// Flow:
//   1. Show the setup form.
//   2. When the user submits it, POST the metadata and open the live WebSocket.
//   3. Render the live gauges, charts, prediction, recommendations & scenario
//      controls, all fed by the streaming data.
import { useEffect, useState } from "react";
import { api } from "./api";
import { useBatteryStream } from "./useBatteryStream";
import StatusBar from "./components/StatusBar";
import SetupForm from "./components/SetupForm";
import GaugeGrid from "./components/GaugeGrid";
import LiveCharts from "./components/LiveCharts";
import PredictionPanel from "./components/PredictionPanel";
import RecommendationFeed from "./components/RecommendationFeed";
import ScenarioControls from "./components/ScenarioControls";

export default function App() {
  const [started, setStarted] = useState(false);
  const [health, setHealth] = useState(null);
  const [scenarios, setScenarios] = useState([]);
  const [setupError, setSetupError] = useState("");

  // The live stream hook only connects once `started` is true.
  const { connected, latest, history, alerts } = useBatteryStream(started);

  // On first load, check backend health + fetch the scenario list.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const h = await api.health();
      if (!cancelled && h.ok) setHealth(h.data);
      const sc = await api.getScenarios();
      if (!cancelled && sc.ok) setScenarios(sc.data.scenarios || []);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Called by the setup form. Sends metadata, then starts streaming.
  const handleStart = async (metadata) => {
    setSetupError("");
    const res = await api.setupBattery(metadata);
    if (!res.ok) {
      setSetupError(
        "Could not reach the backend. Make sure it is running on port 8000."
      );
      return;
    }
    setStarted(true);
  };

  // Switch the live scenario preset.
  const handleScenario = async (scenario) => {
    await api.setScenario(scenario);
  };

  // Pull the latest pieces out of the newest tick (with safe fallbacks).
  const state = latest?.state;
  const metadata = latest?.metadata;
  const prediction = latest?.prediction;
  const recommendation = latest?.recommendation;
  const currentScenario = latest?.scenario;
  const genaiStatus = latest?.genai_status;

  return (
    <div className="min-h-full bg-plane">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        <StatusBar connected={connected} health={health} genaiStatus={genaiStatus} />

        {!started ? (
          // ---- Pre-session: the setup form ----
          <div className="max-w-xl mx-auto">
            <SetupForm onStart={handleStart} />
            {setupError && (
              <p className="text-xs text-critical mt-3 text-center">{setupError}</p>
            )}
            <p className="text-xs text-muted mt-4 text-center">
              Tip: the system works with or without an Anthropic API key. Without
              one, recommendations use the built-in safety rules.
            </p>
          </div>
        ) : (
          // ---- Live session: the full dashboard grid ----
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Left + middle columns */}
            <div className="lg:col-span-2 flex flex-col gap-4">
              <GaugeGrid state={state} metadata={metadata} />
              <LiveCharts history={history} />
              <ScenarioControls
                scenarios={scenarios}
                current={currentScenario}
                onSelect={handleScenario}
              />
            </div>

            {/* Right column */}
            <div className="flex flex-col gap-4">
              <RecommendationFeed
                recommendation={recommendation}
                alerts={alerts}
              />
              <PredictionPanel prediction={prediction} />
            </div>
          </div>
        )}

        <footer className="text-center text-[10px] text-muted mt-8">
          Battery Health Monitoring System · research prototype · synthetic model
        </footer>
      </div>
    </div>
  );
}
