import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// WEB-01: ichki OT tarmoqda internet yo'q — CDN dan import qilinadigan modullar lokal paketga yo'naltiriladi
// (three TTFLoader → @thatopen/components-front orqali). `scripts/check-bundle.mjs` dist da https:// import
// qolmaganini tekshiradi.
const CDN_ALIASES = [
  { find: /^https:\/\/cdn\.jsdelivr\.net\/npm\/opentype\.js@[^/]+\/\+esm$/, replacement: "opentype.js" },
];

export default defineConfig({
  plugins: [react()],
  resolve: { alias: CDN_ALIASES },
  // Bir nechta ishchi nusxa (worktree) umumiy node_modules dan foydalansa — kesh alohida bo'lsin
  ...(process.env.VITE_CACHE_DIR ? { cacheDir: process.env.VITE_CACHE_DIR } : {}),
  server: {
    port: Number(process.env.VITE_PORT ?? 5173),
    // Parallel ishlash/e2e uchun server manzili env orqali (default — lokal 8000)
    proxy: { "/api": { target: process.env.VITE_API_PROXY ?? "http://localhost:8000", ws: true } },
  },
  build: {
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        // Katta kutubxonalar alohida bo'laklarda (F10): faqat model sahifasi yuklaydi
        manualChunks: (id) => {
          if (id.includes("node_modules/three")) return "three";
          if (id.includes("node_modules/@thatopen")) return "thatopen";
          if (id.includes("node_modules/web-ifc")) return "web-ifc";
          if (id.includes("node_modules/react") || id.includes("node_modules/scheduler")) return "react";
          return undefined;
        },
      },
    },
  },
  test: { environment: "jsdom", setupFiles: ["src/test-setup.ts"], exclude: ["e2e/**", "node_modules/**", "dist/**"] },
});
