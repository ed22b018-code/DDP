// Live rolling time-series charts for Voltage, Current, and Temperature.
//
// DESIGN NOTE (data-viz best practice): these three signals have DIFFERENT
// scales (volts vs amps vs degrees), so we NEVER put them on one chart with two
// y-axes. Instead we use three separate "small-multiple" charts stacked
// vertically -- each single-series, each titled, each with its own axis. This
// is both correct and easier to read.
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import Card from "./Card";
import { COLORS } from "../theme";

// A single titled small-multiple line chart.
function SignalChart({ title, data, dataKey, color, unit, domain }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-xs font-semibold text-ink-secondary">{title}</h3>
        <span className="text-[10px] text-muted">{unit}</span>
      </div>
      <ResponsiveContainer width="100%" height={110}>
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
          <CartesianGrid stroke={COLORS.grid} strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="t"
            tick={{ fill: COLORS.muted, fontSize: 10 }}
            tickFormatter={(v) => `${Math.round(v)}s`}
            stroke={COLORS.hairline}
            minTickGap={30}
          />
          <YAxis
            tick={{ fill: COLORS.muted, fontSize: 10 }}
            stroke={COLORS.hairline}
            domain={domain || ["auto", "auto"]}
            width={40}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: COLORS.surface,
              border: `1px solid ${COLORS.hairline}`,
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: COLORS.muted }}
            labelFormatter={(v) => `t = ${Number(v).toFixed(1)} s`}
            formatter={(value) => [`${Number(value).toFixed(2)} ${unit}`, title]}
          />
          {/* 2px line, no per-point dots -> thin, clean mark. */}
          <Line
            type="monotone"
            dataKey={dataKey}
            stroke={color}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function LiveCharts({ history }) {
  const data = history || [];
  return (
    <Card title="Live Signals" subtitle="Rolling voltage, current & temperature">
      {data.length === 0 ? (
        <p className="text-xs text-muted py-8 text-center">
          Waiting for live data…
        </p>
      ) : (
        <div className="flex flex-col gap-4">
          <SignalChart
            title="Voltage"
            data={data}
            dataKey="voltage_v"
            color={COLORS.voltage}
            unit="V"
          />
          <SignalChart
            title="Current"
            data={data}
            dataKey="current_a"
            color={COLORS.current}
            unit="A"
          />
          <SignalChart
            title="Temperature"
            data={data}
            dataKey="temperature_c"
            color={COLORS.temp}
            unit="°C"
          />
        </div>
      )}
    </Card>
  );
}
