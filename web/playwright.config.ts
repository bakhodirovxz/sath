import { defineConfig } from "@playwright/test";

// E2E: ishlayotgan server + web kerak (E2E_BASE_URL, default http://localhost:5173 — vite dev proxy).
// Brauzer: o'rnatilgan Chrome/Edge (channel), Playwright brauzerlarini yuklab olish shart emas.
export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  retries: 0,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    // E2E_CHANNEL=chromium — Playwright ning o'z brauzeri (CI); default — o'rnatilgan Chrome
    channel: process.env.E2E_CHANNEL === "chromium" ? undefined : (process.env.E2E_CHANNEL ?? "chrome"),
    headless: true,
    viewport: { width: 1400, height: 900 },
    screenshot: "only-on-failure",
  },
  reporter: [["list"]],
});
