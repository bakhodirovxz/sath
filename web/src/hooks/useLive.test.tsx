import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LiveMessage, Sensor } from "../api/client";
import { NO_RETRY_CODES, OFFLINE_AFTER_MS, STALE_AFTER_MS, applyLiveMessage, backoffMs, liveState, useLive, type LiveState } from "./useLive";

/** Soxta WebSocket: ochish/xabar/yopishni test boshqaradi. */
class FakeWS {
  static instances: FakeWS[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: ((ev: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  constructor() { FakeWS.instances.push(this); }
  open() { this.onopen?.(); }
  send(m: object) { this.onmessage?.({ data: JSON.stringify(m) }); }
  close(code = 1006) { if (this.closed) return; this.closed = true; this.onclose?.({ code }); }
}

const mk = (id: number): Sensor => ({ id, project_id: 1, model_id: null, key: `S${id}`, name: "", kind: "value", unit: "", element_guid: null, protocol: "http", address: {}, low_alarm: null, high_alarm: null, stale_after_s: 600, enabled: true, last_value: null, last_ts: null, alarm: "ok", stale: true, priority: "medium", writable: false } as Sensor);

describe("liveState / backoff (F4)", () => {
  it("LIVE → STALE → OFFLINE xabar yoshi bo'yicha; soket yopiq — OFFLINE", () => {
    const t0 = 1_000_000;
    expect(liveState(t0, t0 + 1000, true)).toBe("LIVE");
    expect(liveState(t0, t0 + STALE_AFTER_MS, true)).toBe("STALE");
    expect(liveState(t0, t0 + OFFLINE_AFTER_MS, true)).toBe("OFFLINE");
    expect(liveState(t0, t0 + 1000, false)).toBe("OFFLINE");
    expect(liveState(null, t0, true)).toBe("OFFLINE");
  });
  it("eksponensial + jitter, chegara 60 s", () => {
    expect(backoffMs(0, () => 0.5)).toBe(1000);
    expect(backoffMs(3, () => 0.5)).toBe(8000);
    expect(backoffMs(0, () => 0)).toBe(700);
    expect(backoffMs(0, () => 1)).toBe(1300);
    expect(backoffMs(20, () => 0.5)).toBe(60_000);
    expect(NO_RETRY_CODES.has(4401)).toBe(true);
  });
  it("snapshot/reading xabarlari stale va sifatni ko'chiradi", () => {
    const prev = [mk(1), mk(2)];
    const snap: LiveMessage = { type: "snapshot", sensors: [{ sensor_id: 1, key: "S1", value: 5, ts: "t", alarm: "high", stale: false, quality: "uncertain", element_guid: null, unit: "" }] };
    const a = applyLiveMessage(prev, snap);
    expect(a[0]).toMatchObject({ last_value: 5, alarm: "high", stale: false, last_quality: "uncertain" });
    expect(a[1].stale).toBe(true);
    const b = applyLiveMessage(a, { type: "reading", sensor_id: 2, value: 7, ts: "t2", alarm: "ok", stale: false });
    expect(b[1]).toMatchObject({ last_value: 7, stale: false });
    expect(applyLiveMessage(b, { type: "ping" })).toBe(b);
  });
});

describe("useLive hook", () => {
  let root: Root;
  let el: HTMLDivElement;
  const states: LiveState[] = [];
  function Probe({ factory }: { factory: () => WebSocket }) {
    const [, setSensors] = useState<Sensor[]>([]);
    const st = useLive(1, setSensors, undefined, { socket: factory as unknown as (pid: number) => WebSocket, tickMs: 500 });
    states.push(st);
    return <span data-state={st}>{st}</span>;
  }
  beforeEach(() => {
    vi.useFakeTimers();
    FakeWS.instances = [];
    states.length = 0;
    el = document.createElement("div");
    document.body.appendChild(el);
    root = createRoot(el);
  });
  afterEach(() => { act(() => root.unmount()); el.remove(); vi.useRealTimers(); });
  const last = () => el.querySelector("span")!.getAttribute("data-state");

  it("jim uzilish: 30 s ichida OFFLINE; keyin qayta ulanadi (eksponensial)", () => {
    act(() => { root.render(<Probe factory={() => new FakeWS() as unknown as WebSocket} />); });
    const ws = FakeWS.instances[0];
    act(() => { ws.open(); ws.send({ type: "snapshot", sensors: [] }); });
    expect(last()).toBe("LIVE");
    act(() => { vi.advanceTimersByTime(STALE_AFTER_MS + 500); });
    expect(last()).toBe("STALE");
    act(() => { vi.advanceTimersByTime(OFFLINE_AFTER_MS - STALE_AFTER_MS); });
    expect(last()).toBe("OFFLINE");
    expect(ws.closed).toBe(true); // yarim ochiq soket yopildi
    act(() => { vi.advanceTimersByTime(1500); }); // birinchi kechikish ≤ 1.3 s
    expect(FakeWS.instances.length).toBe(2);
    act(() => { FakeWS.instances[1].open(); FakeWS.instances[1].send({ type: "ping" }); });
    expect(last()).toBe("LIVE");
  });

  it("ping xabari LIVE ni saqlaydi; 4401 yopilishida qayta urinmaydi", () => {
    act(() => { root.render(<Probe factory={() => new FakeWS() as unknown as WebSocket} />); });
    const ws = FakeWS.instances[0];
    act(() => { ws.open(); });
    for (let i = 0; i < 5; i++) act(() => { vi.advanceTimersByTime(10_000); ws.send({ type: "ping" }); });
    expect(last()).toBe("LIVE");
    act(() => { ws.close(4401); });
    expect(last()).toBe("OFFLINE");
    act(() => { vi.advanceTimersByTime(120_000); });
    expect(FakeWS.instances.length).toBe(1); // qayta ulanish yo'q
  });

  it("qayta ulanish kechikishi o'sadi (server o'lganda bir vaqtda urmaslik)", () => {
    vi.spyOn(Math, "random").mockReturnValue(0.5);
    act(() => { root.render(<Probe factory={() => new FakeWS() as unknown as WebSocket} />); });
    act(() => { FakeWS.instances[0].close(); });
    act(() => { vi.advanceTimersByTime(1000); });
    expect(FakeWS.instances.length).toBe(2);
    act(() => { FakeWS.instances[1].close(); });
    act(() => { vi.advanceTimersByTime(1000); });
    expect(FakeWS.instances.length).toBe(2); // 2 s kutadi
    act(() => { vi.advanceTimersByTime(1000); });
    expect(FakeWS.instances.length).toBe(3);
  });
});
