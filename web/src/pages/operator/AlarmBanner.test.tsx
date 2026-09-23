import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AlarmEvent } from "../../api/client";
import { setToken } from "../../api/client";
import { configureLive, resetLive } from "../../store/live";
import { annunciator } from "../../ui/annunciator";
import AlarmBanner from "./AlarmBanner";
import { unackedTop } from "./alarms";

/** UX-03: har sahifada doimiy alarm banneri — kvitlanmagan top-3, ustuvorlik bo'yicha, sahifa ichida kvitlash. */
class FakeWS {
  static all: FakeWS[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: ((ev: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  constructor() { FakeWS.all.push(this); }
  send(m: object) { this.onmessage?.({ data: JSON.stringify(m) }); }
  close() { this.onclose?.({ code: 1000 }); }
}

const ev = (id: number, priority: string, state = "high", extra: Partial<AlarmEvent> = {}): AlarmEvent => ({
  id, sensor_id: id, sensor_name: `Sensor ${id}`, sensor_key: `S${id}`, unit: "m", priority, state, value: 1, started_at: `2026-01-01T00:0${id % 10}:00Z`,
  ended_at: null, acked_by: null, acked_at: null, comment: "", ...extra,
} as AlarmEvent);

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  setToken("t");
  FakeWS.all = [];
  resetLive();
  configureLive({ socket: () => new FakeWS() as unknown as WebSocket });
  vi.spyOn(annunciator, "alarm").mockImplementation(() => undefined);
  vi.spyOn(annunciator, "ack").mockImplementation(() => undefined);
  const events = [ev(1, "low"), ev(2, "critical", "highhigh"), ev(3, "high"), ev(4, "medium"), ev(5, "critical", "high", { acked_at: "x" }), ev(6, "critical", "high", { suppressed: "shelved" })];
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.includes("/ack")) return Promise.resolve(new Response(JSON.stringify({ ...ev(2, "critical", "highhigh"), acked_at: "2026-01-01T00:10:00Z", acked_by: 1, comment: JSON.parse(String(init?.body ?? "{}")).comment }), { status: 200, headers: { "Content-Type": "application/json" } }));
    return Promise.resolve(new Response(JSON.stringify(events), { status: 200, headers: { "Content-Type": "application/json" } }));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => { cleanup(); resetLive(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("alarm banneri (UX-03)", () => {
  it("tartib: ustuvorlik, keyin yangisi; kvitlangan va shelved chiqmaydi", () => {
    const out = unackedTop([ev(1, "low"), ev(2, "critical"), ev(3, "high"), ev(7, "critical"), ev(5, "critical", "high", { acked_at: "x" }), ev(6, "high", "high", { suppressed: "shelved" })]);
    expect(out.map((e) => e.id)).toEqual([7, 2, 3, 1]);
  });

  it("top-3 kvitlanmagan, miltillovchi belgi, soni; operator sahifa ichida izoh bilan kvitlaydi", async () => {
    render(<MemoryRouter><AlarmBanner pid={1} role="operator" /></MemoryRouter>);
    await waitFor(() => expect(screen.getByTestId("alarm-banner")).toBeTruthy());
    const banner = screen.getByTestId("alarm-banner");
    expect(banner.className).toContain("prio-critical");
    expect(screen.getByTestId("alarm-banner-count")).toHaveTextContent("4");
    const items = screen.getAllByTestId("alarm-banner-item");
    expect(items.map((i) => i.dataset.prio)).toEqual(["critical", "high", "medium"]);
    expect(items[0].querySelector(".alarm-mark.unacked")).toBeTruthy();
    expect(banner).toHaveTextContent("+1 boshqa");
    fireEvent.click(screen.getAllByTestId("alarm-banner-ack")[0]);
    fireEvent.change(screen.getByTestId("dlg-text"), { target: { value: "tekshirildi" } });
    await act(async () => { fireEvent.click(screen.getByTestId("dlg-ok")); });
    await waitFor(() => expect(screen.getByTestId("alarm-banner-count")).toHaveTextContent("3"));
    const ackCall = fetchMock.mock.calls.find(([u]) => String(u).includes("/api/alarm-events/2/ack"));
    expect(JSON.parse(String(ackCall?.[1]?.body))).toEqual({ comment: "tekshirildi" });
  });

  it("ko'ruvchi (viewer) — kvitlash tugmasi yo'q, faqat havola; alarm yo'q — banner yo'q", async () => {
    render(<MemoryRouter><AlarmBanner pid={1} role="viewer" /></MemoryRouter>);
    await waitFor(() => expect(screen.getByTestId("alarm-banner")).toBeTruthy());
    expect(screen.queryByTestId("alarm-banner-ack")).toBeNull();
    expect(screen.getAllByRole("link", { name: /Alarm sahifasi/ })[0].getAttribute("href")).toBe("/projects/1/ops/alarms");
    cleanup();
    resetLive();
    fetchMock.mockImplementation(() => Promise.resolve(new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } })));
    const r = render(<MemoryRouter><AlarmBanner pid={2} role="operator" /></MemoryRouter>);
    await act(async () => { await Promise.resolve(); });
    expect(r.container.innerHTML).toBe("");
  });
});
