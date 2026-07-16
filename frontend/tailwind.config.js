/** Tailwind CSS config. Tailwind gives us utility classes like `p-4`, `flex`,
 *  `rounded-xl` so we can style with class names instead of writing CSS files.
 *  The custom colors below come from the validated data-viz palette so the
 *  whole dashboard reads as one consistent system in dark mode.
 */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Surfaces (dark theme)
        surface: "#1a1a19", // card surface
        plane: "#0d0d0d", // page background
        // Ink
        ink: "#ffffff",
        "ink-secondary": "#c3c2b7",
        muted: "#898781",
        hairline: "#2c2c2a",
        // Data-viz series identity colors (dark-mode steps)
        "series-voltage": "#3987e5", // blue
        "series-current": "#9085e9", // violet
        "series-temp": "#d95926", // orange
        // Status palette (fixed, never themed)
        good: "#0ca30c",
        warning: "#fab219",
        serious: "#ec835a",
        critical: "#d03b3b",
      },
    },
  },
  plugins: [],
};
