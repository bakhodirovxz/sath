import { stateLabel } from "../i18n/labels";

/** Yagona vaqt formatlagichi (UX-09): stansiya vaqti Asia/Tashkent, 24 soat, kk.oo.yyyy — brauzer tili va
 * soat mintaqasidan mustaqil (dispetcher va muhandis bir xil vaqtni ko'radi). */
export const TIME_ZONE = "Asia/Tashkent";

const FMT = new Intl.DateTimeFormat("en-GB", {
  timeZone: TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
});

interface Parts { y: string; mo: string; d: string; h: string; mi: string; s: string }
function parts(ms: number): Parts {
  const o: Record<string, string> = {};
  for (const p of FMT.formatToParts(new Date(ms))) o[p.type] = p.value;
  return { y: o.year, mo: o.month, d: o.day, h: o.hour === "24" ? "00" : o.hour, mi: o.minute, s: o.second };
}
function toMs(v: string | number | Date | null | undefined): number | null {
  if (v == null || v === "") return null;
  const ms = v instanceof Date ? v.getTime() : typeof v === "number" ? v : Date.parse(v);
  return Number.isFinite(ms) ? ms : null;
}

/** kk.oo.yyyy ss:dd */
export function fmtDate(v: string | number | Date | null | undefined): string {
  const ms = toMs(v);
  if (ms == null) return "—";
  const p = parts(ms);
  return `${p.d}.${p.mo}.${p.y} ${p.h}:${p.mi}`;
}
/** kk.oo.yyyy */
export function fmtDay(v: string | number | Date | null | undefined): string {
  const ms = toMs(v);
  if (ms == null) return "—";
  const p = parts(ms);
  return `${p.d}.${p.mo}.${p.y}`;
}
/** ss:dd (yoki ss:dd:ss) */
export function fmtTime(v: string | number | Date | null | undefined, seconds = false): string {
  const ms = toMs(v);
  if (ms == null) return "—";
  const p = parts(ms);
  return seconds ? `${p.h}:${p.mi}:${p.s}` : `${p.h}:${p.mi}`;
}
/** kk.oo ss:dd — grafik o'qlari va qisqa jadval ustunlari */
export function fmtShort(v: string | number | Date | null | undefined): string {
  const ms = toMs(v);
  if (ms == null) return "—";
  const p = parts(ms);
  return `${p.d}.${p.mo} ${p.h}:${p.mi}`;
}
/** kk.oo.yyyy ss:dd:ss.mmm — SOE (millisekund aniqlik) */
export function fmtDateMs(v: string | number | Date | null | undefined): string {
  const ms = toMs(v);
  if (ms == null) return "—";
  const p = parts(ms);
  return `${p.d}.${p.mo}.${p.y} ${p.h}:${p.mi}:${p.s}.${String(((ms % 1000) + 1000) % 1000).padStart(3, "0")}`;
}

/** Soat mintaqasi siljishi (ms) berilgan UTC lahzada. */
function tzOffset(utcMs: number): number {
  const p = parts(utcMs);
  return Date.UTC(+p.y, +p.mo - 1, +p.d, +p.h, +p.mi, +p.s) - Math.floor(utcMs / 1000) * 1000;
}
/** Stansiya vaqtidagi (Asia/Tashkent) devor soati → ISO (UTC). */
export function zonedToIso(y: number, mo: number, d: number, h = 0, mi = 0): string {
  const guess = Date.UTC(y, mo - 1, d, h, mi);
  return new Date(guess - tzOffset(guess)).toISOString();
}

/** "kk.oo.yyyy" → "yyyy-mm-dd" (server `date` parametri) yoki null. */
export function parseDay(s: string): string | null {
  const m = /^\s*(\d{1,2})[./-](\d{1,2})[./-](\d{4})\s*$/.exec(s);
  if (!m) return null;
  const [d, mo, y] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const dt = new Date(Date.UTC(y, mo - 1, d));
  if (dt.getUTCFullYear() !== y || dt.getUTCMonth() !== mo - 1 || dt.getUTCDate() !== d) return null;
  return `${y}-${String(mo).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}
/** "yyyy-mm-dd" → "kk.oo.yyyy" */
export function isoDayToText(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : "";
}
/** "kk.oo.yyyy ss:dd" (stansiya vaqti) → ISO (UTC) yoki null. */
export function parseDateTime(s: string): string | null {
  const m = /^\s*(\d{1,2})[./-](\d{1,2})[./-](\d{4})(?:[ T]+(\d{1,2}):(\d{2}))?\s*$/.exec(s);
  if (!m || !parseDay(`${m[1]}.${m[2]}.${m[3]}`)) return null;
  const h = m[4] ? Number(m[4]) : 0, mi = m[5] ? Number(m[5]) : 0;
  if (h > 23 || mi > 59) return null;
  return zonedToIso(Number(m[3]), Number(m[2]), Number(m[1]), h, mi);
}

export function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** Holat yorlig'i (versiya, tasdiqlash so'rovi, muammo, ustuvorlik, rol) — i18n enum lug'atidan. */
export const label = (s: string) => stateLabel(s);

const IFC_UZ: Record<string, string> = {
  WALL: "Devor", SLAB: "Plita", BEAM: "To'sin", COLUMN: "Ustun", DOOR: "Eshik", WINDOW: "Deraza",
  ROOF: "Tom", STAIR: "Zina", PIPESEGMENT: "Quvur", PIPEFITTING: "Quvur fitingi", FLOWMOVINGDEVICE: "Nasos/Turbina",
  ELECTRICGENERATOR: "Generator", TRANSFORMER: "Transformator", SITE: "Maydon", BUILDING: "Bino",
  BUILDINGSTOREY: "Qavat", SPACE: "Xona", FOOTING: "Poydevor", COVERING: "Qoplama", RAILING: "To'siq",
  MEMBER: "Element", PLATE: "Plastina", TANK: "Rezervuar", VALVE: "Zadvijka", DUCTSEGMENT: "Havo quvuri",
  BUILDINGELEMENTPROXY: "Element", FURNITURE: "Mebel", CURTAINWALL: "Vitraj", OPENINGELEMENT: "Ochiq joy",
};
/** IFCPIPESEGMENT / IfcPipeSegment → "Quvur" (yoki "Pipe Segment"). */
export function ifcLabel(category: string): string {
  const key = category.replace(/^Ifc/i, "").toUpperCase();
  if (IFC_UZ[key]) return IFC_UZ[key];
  // CamelCase bo'lsa so'zlarga ajratamiz, UPPER bo'lsa bosh harf
  const raw = category.replace(/^Ifc/i, "");
  return raw === raw.toUpperCase() ? raw.charAt(0) + raw.slice(1).toLowerCase() : raw.replace(/([a-z])([A-Z])/g, "$1 $2");
}

/** O'lchov qiymati: kattaligiga qarab 0–2 kasr. */
export function fmtValue(v: number): string {
  const a = Math.abs(v);
  return a >= 1000 ? v.toFixed(0) : a >= 100 ? v.toFixed(1) : v.toFixed(2);
}
/** Katta son (minglik bo'luvchi — bo'shliq, kasr — nuqta): 12 345 */
export function fmtInt(v: number): string {
  return Math.round(v).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}
/** Faol alarm (ok/stale emas) */
export const isAlarm = (a: string | undefined | null) => !!a && a !== "ok" && a !== "stale";
