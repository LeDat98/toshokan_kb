import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // real backend arrives with P1 — the UI runs on the mock layer until then
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
