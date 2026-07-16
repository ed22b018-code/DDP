// Live "gauges" for the key numbers. Each is a stat tile with a big value and a
// thin meter bar showing where the value sits in its range. Colors use the
// fixed status palette so red/amber/green always mean the same thing.
import Card from "./Card";
import { COLORS } from "../theme";

// A single stat tile with an optional colored meter bar underneath.
function StatTile({ label, value, unit, fraction, color, hint }) {
  const pct = Math.max(0, Math.min(1, fraction ?? 0)) * 100;
  const display =
    value === null || value === undefined || Number.isNaN(value) ? "—" : value;
  return (
    <div className="bg-plane border border-hairline rounded-lg p-3 flex flex-col gap-2">
      <span className="text-xs text-muted">{label}</span>
      <div className="flex items-baseline gap-1">
        <span
          className="text-2xl font-bold text-ink"
          style={{ fontVariantNumeric: "tabular-nums" }}
        >
          {display}
        </span>
        {unit && <span className="text-xs text-ink-secondary">{unit}</span>}
      </div>
      {/* Meter track + fill (the fill width and color carry the reading). */}
      <div className="h-1.5 rounded-full bg-hairline overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      {hint && <span className="text-[10px] text-muted">{hint}</span>}
    </div>
  );
}

// Pick a color for "level" style gauges (higher = better: SoC, SoH).
function levelColor(pct) {
  if (pct >= 60) return COLORS.good;
  if (pct >= 30) return COLORS.warning;
  return COLORS.critical;
}

export default function GaugeGrid({ state, metadata }) {
  // Safe fallbacks so the grid renders even before the first tick arrives.
  const s = state || {};
  const meta = metadata || {};

  const vMin = meta.min_voltage_v ?? 3.0;
  const vMax = meta.max_voltage_v ?? 4.2;
  const maxTemp = meta.max_safe_temp_c ?? 45.0;

  // Voltage: position within the [min, max] range (neutral identity color).
  const vFrac = (Number(s.voltage_v) - vMin) / (vMax - vMin || 1);

  // Temperature: fraction toward the safe limit; color escalates near/over it.
  const tFrac = Number(s.temperature_c) / (maxTemp * 1.2 || 1);
  const tColor =
    s.temperature_c >= maxTemp
      ? COLORS.critical
      : s.temperature_c >= maxTemp - 5
      ? COLORS.warning
      : COLORS.good;

  // C-rate: 0..3 range for the meter; escalate above config-ish thresholds.
  const cFrac = Number(s.c_rate) / 3;
  const cColor =
    s.c_rate >= 2.5 ? COLORS.critical : s.c_rate >= 1.5 ? COLORS.warning : COLORS.good;

  return (
    <Card title="Live Readings">
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        <StatTile
          label="Voltage"
          value={fmt(s.voltage_v, 2)}
          unit="V"
          fraction={vFrac}
          color={COLORS.voltage}
          hint={`range ${vMin}–${vMax} V`}
        />
        <StatTile
          label="Current"
          value={fmt(s.current_a, 2)}
          unit="A"
          fraction={Math.abs(Number(s.current_a)) / 8}
          color={COLORS.current}
          hint={s.current_a < 0 ? "charging" : "discharging"}
        />
        <StatTile
          label="Temperature"
          value={fmt(s.temperature_c, 1)}
          unit="°C"
          fraction={tFrac}
          color={tColor}
          hint={`safe ≤ ${maxTemp} °C`}
        />
        <StatTile
          label="C-rate"
          value={fmt(s.c_rate, 2)}
          unit="C"
          fraction={cFrac}
          color={cColor}
          hint="charge/discharge speed"
        />
        <StatTile
          label="State of Charge"
          value={fmt(s.soc_pct, 0)}
          unit="%"
          fraction={Number(s.soc_pct) / 100}
          color={levelColor(Number(s.soc_pct))}
          hint="how full (fuel gauge)"
        />
        <StatTile
          label="State of Health"
          value={fmt(s.soh_pct, 0)}
          unit="%"
          fraction={Number(s.soh_pct) / 100}
          color={levelColor(Number(s.soh_pct))}
          hint="overall health"
        />
      </div>
    </Card>
  );
}

// Format a number to n decimals, or "—" if it's missing.
function fmt(x, n) {
  const num = Number(x);
  if (x === null || x === undefined || Number.isNaN(num)) return null;
  return num.toFixed(n);
}
