import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setToken } from "../api/client";
import { configureLive, resetLive } from "../store/live";
import { alignNearest, lowerBound } from "../ui/trendMath";
import DashboardPage from "./DashboardPage";

/** FE-04: trend moslash — binar qidiruv; dispetcher paneli ma'lumotni BIR marta yuklaydi. */

describe("alignNearest / lowerBound", () => {
  it("eng yaqin nuqta (teng masofada — oldingisi; 4 → 5 ga yaqin), chegaralardan tashqari — chetki qiymat", () => {
    expect(lowerBound([1, 3, 5, 7], 4)).toBe(2);
    expect(lowerBound([1, 3, 5, 7], 0)).toBe(0);
    expect(lowerBound([1, 3, 5, 7], 9)).toBe(4);
    expect(alignNearest([0, 2, 4, 6, 8, 10], [1, 5, 9], [10, 50, 90])).toEqual([10, 10, 50, 50, 90, 90]);
    expect(alignNearest([1, 2], [], [])).toEqual([NaN, NaN]);
  });
  it("katta davr: 10 000 × 10 000 nuqta tez (O(n log m))", () => {
    const base = Array.from({ length: 10_000 }, (_, i) => i * 60_000);
    const times = Array.from({ length: 10_000 }, (_, i) => i * 60_000 + 7_000);
    const vals = times.map((_, i) => i);
    const t0 = performance.now();
    const out = alignNearest(base, times, vals);
    expect(performance.now() - t0).toBeLessThan(200);
    expect(out[5000]).toBe(5000);
  });
});

describe("DashboardPage", () => {
  const calls: string[] = [];
  beforeEach(() => {
    calls.length = 0;
    setToken("t");
    resetLive();
    configureLive({ socket: () => ({ close() { /* */ } }) as unknown as WebSocket });
    const sensors = [{ id: 1, project_id: 1, model_id: null, key: "AGG1.P", name: "Agregat 1", kind: "power", unit: "MW", element_guid: null, protocol: "http", address: {}, low_alarm: null, high_alarm: 30, stale_after_s: 600, enabled: true, last_value: 12, last_ts: new Date().toISOString(), alarm: "ok", priority: "medium", writable: false }];
    const body: Record<string, unknown> = {
      "/api/projects/1": { id: 1, name: "GES", description: "", location: "", my_role: "operator", model_count: 0 },
      "/api/projects/1/dashboard": { sensors, units: [], mimic: {}, slots: [], tiles: [], scheme: null, pen_groups: [], active_alarms: 0, energy_24h_mwh: 5, alarms_24h: { count: 0, by_state: {}, unacked: 0 }, alarm_flood: false, live_clients: 1 },
      "/api/projects/1/members": [],
      "/api/notifications/count": { unread: 0 },
    };
    vi.stubGlobal("fetch", vi.fn((u: string) => {
      const path = String(u).split("?")[0];
      calls.push(path);
      const b = path.startsWith("/api/projects/1/alarm-events") ? [] : body[path];
      return Promise.resolve(new Response(JSON.stringify(b ?? {}), { status: 200, headers: { "Content-Type": "application/json" } }));
    }));
  });
  afterEach(() => { resetLive(); vi.unstubAllGlobals(); });

  it("birinchi ochilishda dashboard bir marta so'raladi (FE-04: ikki marta yuklash yo'q)", async () => {
    render(<MemoryRouter initialEntries={["/projects/1/dashboard"]}><Routes><Route path="/projects/:projectId/dashboard" element={<DashboardPage />} /></Routes></MemoryRouter>);
    await act(async () => { await new Promise((r) => setTimeout(r, 50)); });
    expect((await screen.findAllByText("Faol alarmlar", {}, { timeout: 2000 })).length).toBeGreaterThan(0);
    expect(calls.filter((c) => c === "/api/projects/1/dashboard")).toHaveLength(1);
    expect(calls.filter((c) => c === "/api/projects/1")).toHaveLength(1);
  });
});
