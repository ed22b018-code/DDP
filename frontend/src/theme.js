// -----------------------------------------------------------------------------
// theme.js -- palette constants for use in JavaScript (Recharts needs hex
// strings, not Tailwind class names). These mirror tailwind.config.js and come
// from the validated data-viz palette (dark mode).
// -----------------------------------------------------------------------------
export const COLORS = {
  surface: "#1a1a19",
  plane: "#0d0d0d",
  ink: "#ffffff",
  inkSecondary: "#c3c2b7",
  muted: "#898781",
  hairline: "#2c2c2a",
  grid: "#2c2c2a",

  // Series identity (each used in its own single-series small-multiple chart)
  voltage: "#3987e5", // blue
  current: "#9085e9", // violet
  temp: "#d95926", // orange

  // Status palette (fixed)
  good: "#0ca30c",
  warning: "#fab219",
  serious: "#ec835a",
  critical: "#d03b3b",
};

// Map a severity string to its status color.
export function severityColor(severity) {
  switch (severity) {
    case "critical":
      return COLORS.critical;
    case "warning":
      return COLORS.warning;
    case "info":
    default:
      return COLORS.good;
  }
}
