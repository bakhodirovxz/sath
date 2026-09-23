import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AlarmEvent, Sensor } from "../api/client";
import { annunciator } from "../ui/annunciator";
import { configureLive, liveDebug, putSensors, resetLive, useAlarmEvents, useLiveSelector, useProjectLive, useSensor, useSensorsByIds } from "./live";

/** UX-11: loyiha uchun bitta soket, komponentlar faqat o'z sensorlariga obuna. */

class FakeWS {
  static all: FakeWS[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: ((ev: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  constructor() { FakeWS.all.push(this); }
  open() { this.onopen?.(); }
  send(m: object) { this.onmessage?.({ data: JSON.stringify(m) }); }
  close(code = 1000) { if (this.closed) return; this.closed = true; this.onclose?.({ code }); }
}
const mk = (id: number, extra: Partial<Sensor> = {}): Sensor => ({ id, project_id: 1, model_id: null, key: `S${id}`, name: `S${id}`, kind: "value", unit: "", element_guid: null, protocol: "http", address: {}, low_alarm: null, high_alarm: null, stale_after_s: 600, enabled: true, last_value: 0, last_ts: null, alarm: "ok", priority: "medium", writable: false, ...extra } as Sensor);

beforeEach(() => {
  vi.useFakeTimers();
  FakeWS.all = [];
  resetLive();
  configureLive({ socket: () => new FakeWS() as unknown as WebSocket, tickMs: 500 });
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("[]", { status: 200 }))));
});
afterEach(() => { resetLive(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("umumiy jonli store", () => {
  it("bir nechta komponent — bitta soket; oxirgisi ketgach kechikib yopiladi", () => {
    function A() { useProjectLive(1); return null; }
    const r = render(<><A /><A /><A /></>);
    expect(FakeWS.all.length).toBe(1);
    expect(liveDebug(1).refs).toBe(3);
    r.unmount();
    expect(FakeWS.all[0].closed).toBe(false); // sahifalar orasida o'tish — darhol yopilmaydi
    act(() => { vi.advanceTimersByTime(3500); });
    expect(FakeWS.all[0].closed).toBe(true);
  });

  it("o'qish faqat o'sha sensorga obuna komponentni qayta chizadi (50 ms to'plam)", () => {
    putSensors(1, [mk(1), mk(2)]);
    const renders = { a: 0, b: 0, both: 0 };
    function One({ id, k }: { id: number; k: "a" | "b" }) { useSensor(1, id); renders[k]++; return null; }
    function Both() { useSensorsByIds(1, [1, 2]); renders.both++; return null; }
    function Root() { useProjectLive(1); return <><One id={1} k="a" /><One id={2} k="b" /><Both /></>; }
    render(<Root />);
    const ws = FakeWS.all[0];
    act(() => { ws.open(); });
    const before = { ...renders };
    act(() => {
      for (let i = 0; i < 5; i++) ws.send({ type: "reading", sensor_id: 1, value: i + 1, ts: `2026-01-01T00:00:0${i}Z`, alarm: "ok" });
      vi.advanceTimersByTime(60);
    });
    expect(renders.a - before.a).toBe(1); // 5 ta o'qish → bitta qayta chizish
    expect(renders.b - before.b).toBe(0); // boshqa sensor — qayta chizilmaydi
    expect(renders.both - before.both).toBe(1);
  });

  it("selektor natija o'zgarmasa qayta chizmaydi (KPI)", () => {
    putSensors(1, [mk(1, { alarm: "ok" }), mk(2)]);
    let n = 0;
    function Kpi() { useLiveSelector(1, (ss) => ss.filter((s) => s.alarm !== "ok").length); n++; return null; }
    function Root() { useProjectLive(1); return <Kpi />; }
    render(<Root />);
    const ws = FakeWS.all[0];
    act(() => { ws.open(); });
    const before = n;
    act(() => { ws.send({ type: "reading", sensor_id: 2, value: 7, ts: "t", alarm: "ok" }); vi.advanceTimersByTime(60); });
    expect(n - before).toBe(0);
    act(() => { ws.send({ type: "reading", sensor_id: 1, value: 99, ts: "t2", alarm: "high" }); vi.advanceTimersByTime(60); });
    expect(n - before).toBe(1);
  });

  it("alarm xabari — faol ro'yxatga, annunciator bir marta; kvitlash — ovoz to'xtaydi", () => {
    const alarm = vi.spyOn(annunciator, "alarm").mockImplementation(() => undefined);
    const ack = vi.spyOn(annunciator, "ack").mockImplementation(() => undefined);
    putSensors(1, [mk(5)]);
    let seen: AlarmEvent[] = [];
    function Ev() { useProjectLive(1); seen = useAlarmEvents(1); return null; }
    render(<Ev />);
    const ws = FakeWS.all[0];
    const ev = { id: 11, sensor_id: 5, sensor_name: "S5", state: "high", value: 9, started_at: "2026-01-01T00:00:00Z", ended_at: null, acked_by: null, acked_at: null, priority: "critical" };
    act(() => { ws.open(); ws.send({ type: "alarm", event: ev }); ws.send({ type: "alarm", event: ev }); });
    expect(seen.map((e) => e.id)).toEqual([11]);
    expect(seen[0].sensor_key).toBe("S5");
    expect(alarm).toHaveBeenCalledTimes(1);
    act(() => { ws.send({ type: "alarm", event: { ...ev, acked_at: "2026-01-01T00:01:00Z", acked_by: 1 } }); });
    expect(ack).toHaveBeenCalledWith(11);
    act(() => { ws.send({ type: "alarm", event: { ...ev, acked_at: "x", ended_at: "y" } }); });
    expect(seen).toEqual([]);
  });
});
