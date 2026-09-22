/** Alarm sahifasi mantig'i (F5): saralash (ustuvorlik → holat og'irligi → vaqt), filtr, guruhlash, qidiruv. */
import type { AlarmEvent, Sensor } from "../../api/client";
import { alarmRank } from "../../ui/tokens";
import { areaOf, type AreaId } from "./model";

export type ViewMode = "active" | "unack" | "acked" | "suppressed" | "history";

export interface AlarmFilter {
  priorities: Set<string>; // bo'sh — hammasi
  area: AreaId | "";
  view: ViewMode;
  q: string;
}

export const EMPTY_FILTER: AlarmFilter = { priorities: new Set(), area: "", view: "active", q: "" };

export interface AlarmRow extends AlarmEvent {
  sensor?: Sensor;
  area: AreaId | "aux";
}

export function toRows(events: AlarmEvent[], sensors: Sensor[]): AlarmRow[] {
  const by = new Map(sensors.map((s) => [s.id, s]));
  return events.map((e) => {
    const s = by.get(e.sensor_id);
    return { ...e, sensor: s, area: s ? areaOf(s) : "aux", priority: e.priority ?? s?.priority ?? "medium" };
  });
}

/** Ustuvorlik → holat og'irligi → yangisi birinchi. Kvitlanmagan faol alarmlar bir xil ustuvorlikda oldinda. */
export function sortAlarms<T extends AlarmEvent>(rows: T[]): T[] {
  return [...rows].sort((a, b) => {
    const r = alarmRank(a.state, a.priority ?? "medium") - alarmRank(b.state, b.priority ?? "medium");
    if (r) return r;
    const ua = a.acked_at ? 1 : 0, ub = b.acked_at ? 1 : 0;
    if (ua !== ub) return ua - ub;
    return Date.parse(b.started_at) - Date.parse(a.started_at);
  });
}

export function filterAlarms(rows: AlarmRow[], f: AlarmFilter): AlarmRow[] {
  const q = f.q.trim().toLowerCase();
  return rows.filter((r) => {
    if (f.priorities.size && !f.priorities.has(r.priority ?? "medium")) return false;
    if (f.area && r.area !== f.area) return false;
    switch (f.view) {
      case "active": if (r.ended_at || r.suppressed) return false; break;
      case "unack": if (r.acked_at || r.suppressed) return false; break;
      case "acked": if (!r.acked_at || r.ended_at || r.suppressed) return false; break;
      case "suppressed": if (!r.suppressed) return false; break;
      case "history": break;
    }
    if (q && !`${r.sensor_name} ${r.sensor_key} ${r.state} ${r.comment ?? ""}`.toLowerCase().includes(q)) return false;
    return true;
  });
}

/** Guruhlash kaliti: sensor (chattering ko'rinadi) yoki uchastka. */
export function groupAlarms(rows: AlarmRow[], by: "none" | "sensor" | "area"): { key: string; title: string; rows: AlarmRow[] }[] {
  if (by === "none") return [{ key: "all", title: "", rows }];
  const m = new Map<string, AlarmRow[]>();
  for (const r of rows) {
    const k = by === "sensor" ? `${r.sensor_id}` : r.area;
    m.set(k, [...(m.get(k) ?? []), r]);
  }
  return [...m.entries()].map(([key, rs]) => ({ key, title: by === "sensor" ? `${rs[0].sensor_name} (${rs[0].sensor_key}) · ${rs.length}` : `${key} · ${rs.length}`, rows: rs }));
}

/** Faol alarm hisoblagichlari — tarix ko'rinishidan mustaqil (faqat faol hodisalar ro'yxatidan). */
export function counters(active: AlarmEvent[]): { active: number; unacked: number; critical: number } {
  const a = active.filter((e) => !e.ended_at && !e.suppressed);
  return { active: a.length, unacked: active.filter((e) => !e.acked_at && !e.suppressed).length, critical: a.filter((e) => e.priority === "critical").length };
}

/** Toshqin rejimida taklif: faqat yuqori/kritik. */
export const FLOOD_PRIORITIES = new Set(["critical", "high"]);
