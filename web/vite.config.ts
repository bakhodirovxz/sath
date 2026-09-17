import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://localhost:8000", ws: true } },
  },
  build: { chunkSizeWarningLimit: 4000 },
  test: { environment: "jsdom", exclude: ["e2e/**", "node_modules/**", "dist/**"] },
});
