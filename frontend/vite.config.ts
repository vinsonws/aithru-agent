import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: process.env.AITHRU_AGENT_FRONTEND_BASE ?? "/",
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Backend has no CORS; proxy in dev so the browser talks same-origin.
      "/api": {
        target: process.env.AITHRU_AGENT_BACKEND ?? "http://127.0.0.1:8000",
        changeOrigin: true,
        // SSE streaming endpoints need to keep the connection open without buffering.
        ws: false,
      },
    },
  },
});
