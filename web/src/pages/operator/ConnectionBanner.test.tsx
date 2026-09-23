import { act, cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Sensor } from "../../api/client";
import { CONNECT_GRACE_MS, configureLive, putSensors, resetLive, useProjectLive } from "../../store/live";
import ConnectionBanner, { LiveBadge } from "./ConnectionBanner";
import ValueCard from "./ValueCard";

/** UX-04: aloqa uzilishi aniq ko'rinadi — katta banner, oxirgi ma'lumot yoshi, qiymatlar eskirgan. */
class FakeWS {
  static all: FakeWS[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: ((ev: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  constructor() { FakeWS.all.push(this); }
  send(m: object) { this.onmessage?.({ data: JSON.stringify(m) }); }
  close(code = 1006) { this.onclose?.({ code }); }
}
const sensor = { id: 1, project_id: 1, model_id: null, key: "RES.H", name: "Sath", kind: "level", unit: "m", element_guid: null, protocol: "http", address: {}, low_alarm: null, high_alarm: null, stale_after_s: 600, enabled: true, last_value: 900, last_ts: new Date().toISOString(), alarm: "ok", priority: "medium", writable: false } as unknown as Sensor;

function Page() {
  useProjectLive(1);
  return <MemoryRouter><LiveBadge pid={1} /><ConnectionBanner pid={1} /><ValueCard s={sensor} pid={1} /></MemoryRouter>;
}

beforeEach(() => {
  vi.useFakeTimers();
  FakeWS.all = [];
  resetLive();
  configureLive({ socket: () => new FakeWS() as unknown as WebSocket, tickMs: 500 });
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("[]", { status: 200 }))));
  putSensors(1, [sensor]);
});
afterEach(() => { cleanup(); resetLive(); vi.useRealTimers(); vi.unstubAllGlobals(); });

describe("aloqa banneri (UX-04)", () => {
  it("ulanish muhlatida banner yo'q; ulangan — yo'q; uzilgan — ALOQA YO'Q, yoshi, qiymat eskirgan", () => {
    render(<Page />);
    expect(screen.queryByTestId("conn-banner")).toBeNull(); // hali ulanmoqda — "aloqa yo'q" emas
    expect(screen.getByTestId("vcard").className).not.toContain("stale");
    const ws = FakeWS.all[0];
    act(() => { ws.onopen?.(); ws.send({ type: "ping" }); vi.advanceTimersByTime(600); });
    expect(screen.getByTestId("live-state").dataset.state).toBe("LIVE");
    expect(screen.getByTestId("live-state")).toHaveTextContent("Jonli");
    expect(screen.queryByTestId("conn-banner")).toBeNull();
    act(() => { ws.close(1006); vi.advanceTimersByTime(1100); });
    const b = screen.getByTestId("conn-banner");
    expect(b.dataset.state).toBe("OFFLINE");
    expect(b.getAttribute("role")).toBe("alert");
    expect(b).toHaveTextContent("ALOQA YO'Q");
    expect(b).toHaveTextContent(/oxirgi ma'lum holat \(\d+ s oldin\)/);
    expect(screen.getByTestId("vcard").className).toContain("stale");
    expect(screen.getByTestId("vcard")).toHaveTextContent("ESKIRGAN");
  });

  it("hech qachon ulanmagan — muhlatdan keyin banner", () => {
    render(<Page />);
    act(() => { FakeWS.all[0].close(1006); vi.advanceTimersByTime(CONNECT_GRACE_MS + 100); });
    expect(screen.getByTestId("conn-banner")).toHaveTextContent("Jonli ma'lumot hali kelmadi");
  });
});
