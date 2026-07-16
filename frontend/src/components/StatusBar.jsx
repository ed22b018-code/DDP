// The top bar: shows the app title and live status badges (connection, whether
// the ML model is loaded, and whether the Gen-AI layer or rule fallback is
// active). Colors use the fixed status palette.
import { COLORS } from "../theme";

function Badge({ label, value, color }) {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-plane border border-hairline">
      <span
        className="inline-block w-2.5 h-2.5 rounded-full"
        style={{ backgroundColor: color }}
        aria-hidden="true"
      />
      <span className="text-xs text-muted">{label}</span>
      <span className="text-xs font-semibold text-ink">{value}</span>
    </div>
  );
}

export default function StatusBar({ connected, health, genaiStatus }) {
  const modelReady = health?.model_ready;
  const genai = genaiStatus || health?.genai_status || "rules";

  return (
    <header className="flex flex-wrap items-center justify-between gap-3 mb-6">
      <div>
        <h1 className="text-xl font-bold text-ink">Battery Health Monitor</h1>
        <p className="text-xs text-muted mt-0.5">
          Live State-of-Charge / State-of-Health estimation, prediction &amp;
          recommendations
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Badge
          label="Stream"
          value={connected ? "connected" : "offline"}
          color={connected ? COLORS.good : COLORS.critical}
        />
        <Badge
          label="Model"
          value={modelReady ? "ready" : "not trained"}
          color={modelReady ? COLORS.good : COLORS.warning}
        />
        <Badge
          label="Advisor"
          value={genai === "genai" ? "Gen-AI" : "rules"}
          color={genai === "genai" ? COLORS.voltage : COLORS.muted}
        />
      </div>
    </header>
  );
}
