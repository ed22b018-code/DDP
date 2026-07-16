// The prediction panel: shows the ML model's predicted SoH (or RUL) at the
// configured horizon, plus a plain-language "What's driving this?" breakdown
// built from SHAP values (which features push the estimate up or down).
import Card from "./Card";
import { COLORS } from "../theme";

// One SHAP row: a label, a direction arrow, and a bar sized by its impact.
function ShapRow({ item, maxAbs }) {
  const up = item.direction === "up";
  const color = up ? COLORS.good : COLORS.critical;
  const widthPct = maxAbs > 0 ? (Math.abs(item.shap_value) / maxAbs) * 100 : 0;
  return (
    <li className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-ink-secondary">
          {/* Arrow + label so direction is never color-alone. */}
          <span aria-hidden="true" className="mr-1" style={{ color }}>
            {up ? "▲" : "▼"}
          </span>
          {item.friendly_name}
        </span>
        <span className="text-muted" style={{ fontVariantNumeric: "tabular-nums" }}>
          {up ? "raises" : "lowers"} health
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-hairline overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{ width: `${widthPct}%`, backgroundColor: color }}
        />
      </div>
    </li>
  );
}

export default function PredictionPanel({ prediction }) {
  const p = prediction || {};
  const notReady = !p.model_loaded;

  const target = p.target === "rul" ? "Remaining Useful Life" : "State of Health";
  const unit = p.unit || (p.target === "rul" ? "cycles" : "%");
  const horizon = p.horizon_cycles;

  const shap = p.top_features || [];
  const maxAbs = shap.reduce((m, f) => Math.max(m, Math.abs(f.shap_value)), 0);

  return (
    <Card
      title="Prediction"
      subtitle={
        p.target === "rul"
          ? "Estimated remaining life"
          : `Predicted health at +${horizon ?? "?"} cycles`
      }
    >
      {notReady ? (
        <p className="text-xs text-warning">
          {p.note || "Model not trained yet. Run `python ml/train.py`."}
        </p>
      ) : (
        <>
          <div className="flex items-baseline gap-2 mb-4">
            <span
              className="text-4xl font-bold text-ink"
              style={{ fontVariantNumeric: "tabular-nums" }}
            >
              {p.prediction ?? "—"}
            </span>
            <span className="text-sm text-ink-secondary">{unit}</span>
            <span className="text-xs text-muted ml-1">{target}</span>
          </div>

          <h3 className="text-xs font-semibold text-ink-secondary mb-2">
            What's driving this?
          </h3>
          {shap.length === 0 ? (
            <p className="text-xs text-muted">
              Explanation not available (SHAP explainer missing).
            </p>
          ) : (
            <ul className="flex flex-col gap-2.5">
              {shap.map((f) => (
                <ShapRow key={f.feature} item={f} maxAbs={maxAbs} />
              ))}
            </ul>
          )}
          <p className="text-[10px] text-muted mt-3">
            Bars show each feature's relative influence (SHAP). Longer bar = more
            influence on the estimate.
          </p>
        </>
      )}
    </Card>
  );
}
