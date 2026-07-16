// Vite config -- Vite is the fast dev server + build tool for the React app.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,       // the dashboard opens at http://localhost:5173
    strictPort: false,
  },
});
