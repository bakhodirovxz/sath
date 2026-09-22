import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { AlarmEvent, Sensor } from "../../api/client";
import AlarmTable from "./AlarmTable";
import { EMPTY_FILTER, FLOOD_PRIORITIES, counters, filterAlarms, groupAlarms, sortAlarms, toRows } from "./alarms";

const PR = ["low", "medium", "high", "critical"] as const;
const mkSensor = (id: number): Sensor => ({ id, project_id: 1, model_id: null, key: id % 2 ? `AGG${id}.VIB` : `RES.H${id}`, name: `S${id}`, kind: id % 2 ? "vibration" : "level", unit: "", element_guid: null, protocol: "http", address: {}, low_alarm: null, high_alarm: null, stale_after_s: 600, enabled: true, last_value: 1, last_ts: null, alarm: "high", stale: false, priority: PR[id % 4], writable: false, alarm_mode: "normal" } as Sensor);
const mkEvent = (i: number, o: Partial<AlarmEvent> = {}): AlarmEvent => ({
  id: i, sensor_id: (i % 20) + 1, sensor_name: `S${(i % 20) + 1}`, sensor_key: `K${(i % 20) + 1}`, unit: "", priority: PR[i % 4], state: i % 7 === 0 ? "highhigh" : "high",
  value: i, started_at: new Date(1_700_000_000_000 + i * 1000).toISOString(), ended_at: null, acked_by: null, acked_at: null, comment: "", alarm_state: "unack", ...o,
});

describe("alarm sahifasi mantig'i (F5)", () => {
  const sensors = Array.from({ length: 20 }, (_, i) => mkSensor(i + 1));
  const flood = Array.from({ length: 200 }, (_, i) => mkEvent(i));
  it("200 ta alarm toshqini: kritiklar birinchi, keyin vaqt bo'yicha yangisi", () => {
    const rows = sortAlarms(toRows(flood, sensors));
    expect(rows).toHaveLength(200);
    const firstNonCritical = rows.findIndex((r) => r.priority !== "critical");
    expect(firstNonCritical).toBe(50); // 200 / 4 kritik
    // kritiklar ichida HH (og'irroq) oldinda, keyin yangisi birinchi
    const crit = rows.slice(0, 50);
    const hhCount = crit.filter((r) => r.state === "highhigh").length;
    expect(crit.slice(0, hhCount).every((r) => r.state === "highhigh")).toBe(true);
    for (let i = hhCount + 1; i < 50; i++) expect(Date.parse(crit[i - 1].started_at)).toBeGreaterThanOrEqual(Date.parse(crit[i].started_at));
    expect(rows[199].priority).toBe("low");
  });
  it("kvitlanmaganlar bir xil ustuvorlikda oldinda", () => {
    const rows = sortAlarms(toRows([mkEvent(1, { priority: "high", acked_at: "x", alarm_state: "acked" }), mkEvent(2, { priority: "high" })], sensors));
    expect(rows.map((r) => r.id)).toEqual([2, 1]);
  });
  it("filtr: ustuvorlik, uchastka, ko'rinish, qidiruv; toshqin taklifi", () => {
    const rows = toRows(flood, sensors);
    expect(filterAlarms(rows, { ...EMPTY_FILTER, priorities: new Set(["critical"]) })).toHaveLength(50);
    expect(filterAlarms(rows, { ...EMPTY_FILTER, priorities: FLOOD_PRIORITIES })).toHaveLength(100);
    expect(filterAlarms(rows, { ...EMPTY_FILTER, area: "powerhouse" }).every((r) => r.sensor?.kind === "vibration")).toBe(true);
    expect(filterAlarms(rows, { ...EMPTY_FILTER, area: "hydro" }).length + filterAlarms(rows, { ...EMPTY_FILTER, area: "powerhouse" }).length).toBe(200);
    expect(filterAlarms(rows, { ...EMPTY_FILTER, q: "s1" }).every((r) => /S1/.test(r.sensor_name))).toBe(true);
    const mixed = toRows([mkEvent(1), mkEvent(2, { acked_at: "x" }), mkEvent(3, { ended_at: "y" }), mkEvent(4, { suppressed: "shelved" })], sensors);
    expect(filterAlarms(mixed, { ...EMPTY_FILTER, view: "active" }).map((r) => r.id)).toEqual([1, 2]);
    expect(filterAlarms(mixed, { ...EMPTY_FILTER, view: "unack" }).map((r) => r.id)).toEqual([1, 3]);
    expect(filterAlarms(mixed, { ...EMPTY_FILTER, view: "acked" }).map((r) => r.id)).toEqual([2]);
    expect(filterAlarms(mixed, { ...EMPTY_FILTER, view: "suppressed" }).map((r) => r.id)).toEqual([4]);
    expect(filterAlarms(mixed, { ...EMPTY_FILTER, view: "history" })).toHaveLength(4);
  });
  it("guruhlash va hisoblagichlar (tarixdan mustaqil)", () => {
    const rows = toRows(flood, sensors);
    expect(groupAlarms(rows, "sensor")).toHaveLength(20);
    expect(groupAlarms(rows, "area").map((g) => g.key).sort()).toEqual(["hydro", "powerhouse"]);
    expect(groupAlarms(rows, "none")[0].rows).toHaveLength(200);
    const c = counters([mkEvent(1), mkEvent(2, { acked_at: "x" }), mkEvent(3, { ended_at: "y" }), mkEvent(4, { suppressed: "shelved" }), mkEvent(5, { priority: "critical" })]);
    expect(c).toEqual({ active: 3, unacked: 3, critical: 1 });
  });
  it("jadval 200 qator bilan chiziladi, birinchi qator kritik, ratsionalizatsiya tafsiloti", () => {
    const rows = sortAlarms(toRows(flood, sensors));
    const html = renderToStaticMarkup(<MemoryRouter><AlarmTable rows={rows} pid={1} canOperate canEngineer onChanged={() => undefined} /></MemoryRouter>);
    expect(html.match(/data-testid="alarm-row"/g)).toHaveLength(200);
    expect(html.indexOf('data-priority="critical"')).toBeLessThan(html.indexOf('data-priority="high"'));
    expect(html).toContain("◆"); // kritik romb
    expect(html).toContain("Kvitlash");
    expect(html).not.toMatch(/#[0-9a-f]{6}/i);
  });
});
