// The battery setup form. The user enters the one-time metadata; on submit we
// POST it to the backend and then start the live session.
import { useState } from "react";
import Card from "./Card";

// Sensible defaults so the form is never empty (match config.yaml defaults).
const DEFAULTS = {
  chemistry: "Li-ion NMC",
  nominal_capacity_ah: 3.0,
  nominal_voltage_v: 3.7,
  max_voltage_v: 4.2,
  min_voltage_v: 3.0,
  max_safe_temp_c: 45.0,
  cell_count: 1,
  current_cycle_count: 300,
};

// One labelled input row.
function Field({ label, name, value, onChange, type = "number", step, hint }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-ink-secondary">{label}</span>
      <input
        className="bg-plane border border-hairline rounded-lg px-3 py-2 text-sm text-ink
                   focus:outline-none focus:border-series-voltage"
        name={name}
        type={type}
        step={step}
        value={value}
        onChange={onChange}
      />
      {hint && <span className="text-[10px] text-muted">{hint}</span>}
    </label>
  );
}

export default function SetupForm({ onStart }) {
  const [form, setForm] = useState(DEFAULTS);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const handleChange = (e) => {
    const { name, value, type } = e.target;
    setForm((f) => ({
      ...f,
      // Number inputs are stored as numbers; text stays text.
      [name]: type === "number" ? (value === "" ? "" : Number(value)) : value,
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    // Basic validation so we never send nonsense to the backend.
    if (form.min_voltage_v >= form.max_voltage_v) {
      setError("Minimum voltage must be below maximum voltage.");
      setBusy(false);
      return;
    }
    if (form.nominal_capacity_ah <= 0) {
      setError("Nominal capacity must be greater than 0.");
      setBusy(false);
      return;
    }
    await onStart(form);
    setBusy(false);
  };

  return (
    <Card
      title="Battery Setup"
      subtitle="Enter your battery's details once, then start monitoring."
    >
      <form onSubmit={handleSubmit} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Field label="Chemistry" name="chemistry" type="text" value={form.chemistry} onChange={handleChange} />
        <Field label="Nominal capacity (Ah)" name="nominal_capacity_ah" step="0.1" value={form.nominal_capacity_ah} onChange={handleChange} hint="Amp-hours the battery holds" />
        <Field label="Nominal voltage (V)" name="nominal_voltage_v" step="0.1" value={form.nominal_voltage_v} onChange={handleChange} />
        <Field label="Max voltage (V)" name="max_voltage_v" step="0.1" value={form.max_voltage_v} onChange={handleChange} hint="Fully-charged limit" />
        <Field label="Min voltage (V)" name="min_voltage_v" step="0.1" value={form.min_voltage_v} onChange={handleChange} hint="Fully-empty limit" />
        <Field label="Max safe temp (°C)" name="max_safe_temp_c" step="0.5" value={form.max_safe_temp_c} onChange={handleChange} />
        <Field label="Cell count" name="cell_count" step="1" value={form.cell_count} onChange={handleChange} />
        <Field label="Current cycle count" name="current_cycle_count" step="1" value={form.current_cycle_count} onChange={handleChange} hint="How many cycles it has lived" />

        {error && (
          <p className="sm:col-span-2 text-xs text-critical">{error}</p>
        )}

        <div className="sm:col-span-2 mt-1">
          <button
            type="submit"
            disabled={busy}
            className="w-full bg-series-voltage hover:brightness-110 disabled:opacity-60
                       text-white font-semibold rounded-lg px-4 py-2.5 text-sm transition"
          >
            {busy ? "Starting…" : "Start Monitoring"}
          </button>
        </div>
      </form>
    </Card>
  );
}
