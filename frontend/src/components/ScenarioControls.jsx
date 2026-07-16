// Buttons to switch the live simulator scenario. Changing scenarios makes the
// live numbers (and therefore the recommendations) visibly change.
import Card from "./Card";
import { COLORS } from "../theme";

// Friendly labels + one-line descriptions for each scenario preset.
const LABELS = {
  normal_drive: { name: "Normal Drive", desc: "Calm, healthy operation" },
  aggressive_acceleration: { name: "Aggressive", desc: "High current, heats up" },
  fast_charge: { name: "Fast Charge", desc: "Charging near max voltage" },
  hot_day: { name: "Hot Day", desc: "High ambient temperature" },
  deep_discharge: { name: "Deep Discharge", desc: "Voltage sags toward min" },
};

export default function ScenarioControls({ scenarios, current, onSelect }) {
  const list = scenarios && scenarios.length ? scenarios : Object.keys(LABELS);

  return (
    <Card title="Scenario" subtitle="Switch the live conditions to see advice change">
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-2">
        {list.map((key) => {
          const info = LABELS[key] || { name: key, desc: "" };
          const active = key === current;
          return (
            <button
              key={key}
              onClick={() => onSelect(key)}
              className="text-left rounded-lg px-3 py-2 border transition"
              style={{
                borderColor: active ? COLORS.voltage : COLORS.hairline,
                backgroundColor: active ? "rgba(57,135,229,0.12)" : COLORS.plane,
              }}
            >
              <div className="text-xs font-semibold text-ink">{info.name}</div>
              <div className="text-[10px] text-muted">{info.desc}</div>
            </button>
          );
        })}
      </div>
    </Card>
  );
}
