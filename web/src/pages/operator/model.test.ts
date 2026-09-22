import { describe, expect, it } from "vitest";
import type { Sensor } from "../../api/client";
import { ageSeconds, areaOf, fmtAge, pickKey, sortByAlarm, summarize, unitOf } from "./model";

const mk = (o: Partial<Sensor>): Sensor => ({
  id: 1, project_id: 1, model_id: null, key: "X", name: "x", kind: "value", unit: "", element_guid: null, protocol: "http", address: {},
  low_alarm: null, high_alarm: null, stale_after_s: 600, enabled: true, last_value: 1, last_ts: null, alarm: "ok", priority: "medium", writable: false,
  ...o,
} as Sensor);

describe("operator model (F2)", () => {
  it("uchastka tasnifi: kalit ustun, keyin tur", () => {
    expect(areaOf(mk({ key: "RES.H", kind: "level" }))).toBe("hydro");
    expect(areaOf(mk({ key: "GATE1.POS", kind: "position" }))).toBe("hydro");
    expect(areaOf(mk({ key: "AGG1.P", kind: "power" }))).toBe("powerhouse");
    expect(areaOf(mk({ key: "AGG2.VIB", kind: "vibration" }))).toBe("powerhouse");
    expect(areaOf(mk({ key: "TR1.OIL", kind: "temperature" }))).toBe("electrical");
    expect(areaOf(mk({ key: "GRID.F", kind: "value" }))).toBe("electrical");
    expect(areaOf(mk({ key: "GW.spool_rows", kind: "value" }))).toBe("aux");
    expect(areaOf(mk({ key: "TWIN.5.DEV", kind: "deviation" }))).toBe("aux");
    expect(areaOf(mk({ key: "X1", kind: "flow" }))).toBe("hydro");
    expect(areaOf(mk({ key: "X2", kind: "value", name: "Transformator harorati" }))).toBe("electrical");
  });
  it("agregat raqami", () => {
    expect(unitOf(mk({ key: "AGG3.SP" }))).toBe(3);
    expect(unitOf(mk({ key: "UNIT12.P" }))).toBe(12);
    expect(unitOf(mk({ key: "RES.H" }))).toBeNull();
  });
  it("alarm jamlanmasi: ustuvorlik bo'yicha, shelved/OOS/stale alohida", () => {
    const ss = [
      mk({ id: 1, alarm: "high", priority: "critical", key: "A" }),
      mk({ id: 2, alarm: "low", priority: "low", key: "B" }),
      mk({ id: 3, alarm: "highhigh", priority: "high", key: "C", alarm_mode: "shelved" }),
      mk({ id: 4, alarm: "ok", stale: true, priority: "critical", key: "D" }),
      mk({ id: 7, alarm: "high", stale: true, priority: "medium", key: "G" }), // aloqa yo'q, lekin faol alarm yashirinmaydi (F4)
      mk({ id: 5, alarm: "ok", key: "E" }),
      mk({ id: 6, alarm: "high", priority: "high", key: "F", enabled: false }),
    ];
    const sm = summarize(ss);
    expect(sm.total).toBe(3);
    expect(sm.byPriority).toEqual({ critical: 1, high: 0, medium: 1, low: 1 });
    expect(sm.stale).toBe(2);
    expect(sm.worst?.key).toBe("A");
    expect(sortByAlarm(ss).map((s) => s.key)).toEqual(["A", "C", "G", "B", "D", "E", "F"]);
  });
  it("yosh va format", () => {
    const now = Date.parse("2026-09-22T10:00:00Z");
    expect(ageSeconds("2026-09-22T09:59:30Z", now)).toBe(30);
    expect(ageSeconds(null)).toBeNull();
    expect(ageSeconds("buzuq")).toBeNull();
    expect(fmtAge(30)).toBe("30 s");
    expect(fmtAge(125)).toBe("2 daq");
    expect(fmtAge(7200)).toBe("2 soat");
    expect(fmtAge(null)).toBe("—");
  });
  it("asosiy ko'rsatkich tanlash", () => {
    const ss = [mk({ key: "TW.H", kind: "level" }), mk({ key: "RES.H", kind: "level" })];
    expect(pickKey(ss, [/^RES\.H/], "level")?.key).toBe("RES.H");
    expect(pickKey(ss, [/^YOQ/], "level")?.key).toBe("TW.H");
    expect(pickKey(ss, [/^YOQ/])).toBeUndefined();
  });
});
