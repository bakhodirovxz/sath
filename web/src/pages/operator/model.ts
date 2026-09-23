/** Operator ekranlari (ISA-101 L1–L4) uchun toza mantiq: uchastka tasnifi, alarm jamlanmasi, eskirish. */
import type { Sensor } from "../../api/client";
import { alarmRank, isActiveAlarm } from "../../ui/tokens";

export type AreaId = "hydro" | "powerhouse" | "electrical" | "aux";

export const AREAS: { id: AreaId; title: string; short: string }[] = [
  { id: "hydro", title: "Gidrotexnik qism", short: "Gidro" },
  { id: "powerhouse", title: "Mashina zali", short: "Zal" },
  { id: "electrical", title: "Elektr qismi", short: "Elektr" },
  { id: "aux", title: "Yordamchi / diagnostika", short: "Yordamchi" },
];

/** Uchastka nomi (id → foydalanuvchi matni); noma'lum — o'zgarishsiz. */
export function areaTitle(id: string): string {
  return AREAS.find((a) => a.id === id)?.title ?? id;
}

const HYDRO_KEYS = /^(RES|TW|GATE|SPILL|INFLOW|HEAD|NET|PEN|PENSTOCK|SURGE|DAM|PIEZ|SEEP)[._]/i;
const ELEC_KEYS = /^(TR|GRID|LINE|CB|BUS|SW)[._\d]|^(GEN|AGG|UNIT)\d*\.(V|I|F|Q|CB|CIRC)$/i;
const UNIT_KEYS = /^(AGG|UNIT|G|GEN)\d+/i;
const AUX_KEYS = /^(GW|TWIN|ML|HEALTH|SYS)\./i;

/** Sensor qaysi uchastkaga tegishli — kalit va turdan (ISA-101 Level 2 ekranlari). */
export function areaOf(s: Pick<Sensor, "key" | "kind" | "name">): AreaId {
  const key = s.key.toUpperCase();
  if (AUX_KEYS.test(key)) return "aux";
  if (ELEC_KEYS.test(key)) return "electrical";
  if (HYDRO_KEYS.test(key)) return "hydro";
  if (UNIT_KEYS.test(key)) return "powerhouse";
  switch (s.kind) {
    case "level":
    case "flow":
    case "position":
    case "pressure":
      return "hydro";
    case "power":
    case "vibration":
    case "temperature":
    case "status":
      return "powerhouse";
    default:
      return /transformator|tarmoq|liniya|uzgich|shina/i.test(s.name) ? "electrical" : "aux";
  }
}

/** Agregat raqami (AGG1.P → 1); yo'q — null. */
export function unitOf(s: Pick<Sensor, "key">): number | null {
  const m = /^(?:AGG|UNIT|G|GEN)(\d+)[._]/i.exec(s.key);
  return m ? Number(m[1]) : null;
}

export interface AlarmSummary {
  total: number;
  byPriority: Record<"critical" | "high" | "medium" | "low", number>;
  stale: number;
  worst: Sensor | null;
}

export function summarize(sensors: Sensor[]): AlarmSummary {
  const out: AlarmSummary = { total: 0, byPriority: { critical: 0, high: 0, medium: 0, low: 0 }, stale: 0, worst: null };
  let worstRank = Infinity;
  for (const s of sensors) {
    if (!s.enabled) continue;
    if (s.stale) out.stale++;  // aloqa yo'q — alohida sanaladi, lekin faol alarm yashirinmaydi (F4)
    if (!isActiveAlarm(s.alarm)) continue;
    if ((s.alarm_mode ?? "normal") !== "normal" || s.suppressed) continue; // shelved/OOS/bostirilgan — ko'rsatilmaydi
    out.total++;
    out.byPriority[s.priority] = (out.byPriority[s.priority] ?? 0) + 1;
    const r = alarmRank(s.alarm, s.priority);
    if (r < worstRank) { worstRank = r; out.worst = s; }
  }
  return out;
}

/** Qiymat yoshi (soniya) — muzlagan qiymat xavfi uchun har doim ko'rsatiladi. */
export function ageSeconds(ts: string | null | undefined, now = Date.now()): number | null {
  if (!ts) return null;
  // Offsetsiz ISO (eski server javobi) — UTC deb o'qiladi, lokal vaqt emas
  const t = Date.parse(/[zZ]|[+-]\d\d:?\d\d$/.test(ts) ? ts : ts + "Z");
  return Number.isFinite(t) ? Math.max(0, Math.round((now - t) / 1000)) : null;
}

export function fmtAge(sec: number | null): string {
  if (sec == null) return "—";
  if (sec < 60) return `${sec} s`;
  if (sec < 3600) return `${Math.floor(sec / 60)} daq`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} soat`;
  return `${Math.floor(sec / 86400)} kun`;
}

/** Ustuvorlik → vaqt bo'yicha saralangan sensorlar (faol alarmlar birinchi). */
export function sortByAlarm(sensors: Sensor[]): Sensor[] {
  return [...sensors].sort((a, b) => Number(!a.enabled) - Number(!b.enabled) || alarmRank(a.alarm, a.priority) - alarmRank(b.alarm, b.priority) || a.name.localeCompare(b.name));
}

/** L1 uchun asosiy ko'rsatkichlar: birinchi mos sensor (kalit/tur bo'yicha). */
export function pickKey(sensors: Sensor[], patterns: RegExp[], kind?: Sensor["kind"]): Sensor | undefined {
  for (const p of patterns) {
    const s = sensors.find((x) => p.test(x.key.toUpperCase()));
    if (s) return s;
  }
  return kind ? sensors.find((x) => x.kind === kind) : undefined;
}
