// The recommendation area: the single most important Gen-AI (or rule-based)
// recommendation shown prominently at the top, plus a scrolling, color-coded
// alert list below it.
import Card from "./Card";
import { COLORS, severityColor } from "../theme";

// Small colored pill showing a severity with an icon + word (never color-alone).
function SeverityPill({ severity }) {
  const color = severityColor(severity);
  const icon = severity === "critical" ? "⛔" : severity === "warning" ? "⚠" : "ℹ";
  return (
    <span
      className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full"
      style={{ color, border: `1px solid ${color}` }}
    >
      <span aria-hidden="true">{icon}</span>
      {severity}
    </span>
  );
}

export default function RecommendationFeed({ recommendation, alerts }) {
  const rec = recommendation || {};
  const hasRec = rec.text && rec.text.length > 0;
  const recColor = severityColor(rec.severity || "info");
  const list = alerts || [];

  return (
    <Card
      title="Recommendation & Alerts"
      subtitle="Live advice to prolong battery life"
      right={
        <span className="text-[10px] text-muted uppercase tracking-wide">
          {rec.source === "genai" ? "Gen-AI" : "rule-based"}
        </span>
      }
    >
      {/* --- The headline recommendation --- */}
      <div
        className="rounded-lg p-3 mb-4 border"
        style={{ borderColor: recColor, backgroundColor: "rgba(255,255,255,0.02)" }}
      >
        {hasRec ? (
          <>
            <p className="text-sm text-ink leading-snug">{rec.text}</p>
            {rec.why && (
              <p className="text-xs text-muted mt-2">
                <span className="font-semibold text-ink-secondary">Why: </span>
                {rec.why}
              </p>
            )}
          </>
        ) : (
          <p className="text-sm text-muted">Waiting for the first recommendation…</p>
        )}
      </div>

      {/* --- The scrolling alert list --- */}
      <h3 className="text-xs font-semibold text-ink-secondary mb-2">
        Alert history
      </h3>
      {list.length === 0 ? (
        <p className="text-xs text-muted flex items-center gap-2">
          <span
            className="inline-block w-2 h-2 rounded-full"
            style={{ backgroundColor: COLORS.good }}
          />
          All readings healthy — no alerts.
        </p>
      ) : (
        <ul className="flex flex-col gap-2 max-h-64 overflow-y-auto pr-1">
          {list.map((a) => (
            <li
              key={a.id}
              className="flex items-start gap-2 bg-plane border border-hairline rounded-lg p-2.5"
            >
              <span
                className="mt-1 inline-block w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: severityColor(a.severity) }}
                aria-hidden="true"
              />
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <SeverityPill severity={a.severity} />
                  <span className="text-[10px] text-muted">{a.time}</span>
                </div>
                <p className="text-xs text-ink mt-1">{a.message}</p>
                <p className="text-[10px] text-muted">{a.detail}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
