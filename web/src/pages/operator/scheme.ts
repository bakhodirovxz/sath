/** Mimika sxemasi ma'lumot sifatida (F3): elementlar, koordinatalar (viewBox 1260×500 / 620), turlar, sensor bog'lanishi.
 * Agregatlar soni loyiha konfiguratsiyasidan (`units`); `defaultScheme(n)` 1…12 agregat uchun joylashuvni hisoblaydi.
 * Bog'lanmagan element yashirilmaydi — "ma'lumot yo'q" holatida chiziladi. */

export type ElementType =
  | "reservoir" | "dam" | "spillway" | "penstock" | "unit" | "breaker" | "bus" | "transformer" | "line"
  | "gate" | "valve" | "tailwater" | "value";

export interface SchemeElement {
  id: string;
  type: ElementType;
  x: number;
  y: number;
  w?: number;
  h?: number;
  label?: string;
  /** Asosiy sensor (qiymat / holat) */
  sensor_id?: number | null;
  /** Agregat raqami (unit/breaker) */
  unit?: number | undefined;
  /** Qo'shimcha bog'lanishlar: unit — RUN/CB; gate — POS; breaker — holat */
  extra?: Record<string, number | null>;
}

export interface Scheme {
  version: 1;
  units: number;
  elements: SchemeElement[];
}

/** viewBox (UX-01): kenglik 1260 birlik — mimika konteyneri min-width 1260 px, ya'ni 1 birlik ≥ 1 px
 * (yorliq 14, qiymat 18 px hech qachon kichraymaydi; tor ekranda gorizontal suriladi). 7+ agregat — ikki qator, balandroq. */
export const VIEW = { w: 1260, h: 500 };
export const VIEW_TALL_H = 620;
export const MAX_UNITS = 12;

export function viewOf(s: Pick<Scheme, "units">): { w: number; h: number } {
  return { w: VIEW.w, h: s.units > 6 ? VIEW_TALL_H : VIEW.h };
}

/** Standart GES sxemasi: ombor → to'g'on/tashlama → quvur → mashina zali (n agregat, har birida uzgich) →
 * shina → transformator → liniya → quyi byef. Uch zona: gidrotexnika (0–530), mashina zali (540–1040),
 * elektr/quyi byef (1050–1260). Qiymat katagi 180 birlik (qiymat + birlik + sifat + yosh bir qatorda). */
export function defaultScheme(units: number): Scheme {
  const n = Math.max(1, Math.min(MAX_UNITS, Math.round(units || 1)));
  const hallX = 540;
  // 6 tagacha bitta qator, ko'proq — ikki qator (qator balandligi 170: agregat, qiymat, yosh, keyingi uzgich)
  const rows = n <= 6 ? 1 : 2;
  const cols = Math.ceil(n / rows);
  const hallW = Math.max(260, Math.min(40 + cols * 92, VIEW.w - hallX - 220));
  const step = hallW / cols;
  const hallH = 220 + (rows - 1) * 170;
  const els: SchemeElement[] = [
    { id: "reservoir", type: "reservoir", x: 0, y: 190, w: 240, h: 160, label: "SUV OMBORI" },
    { id: "inflow", type: "value", x: 110, y: 84, label: "Kiruvchi sarf" },
    { id: "upstream_level", type: "value", x: 110, y: 150, label: "Yuqori byef sathi" },
    { id: "dam", type: "dam", x: 240, y: 150, w: 90, h: 200, label: "TO'G'ON" },
    { id: "spillway", type: "spillway", x: 240, y: 118, w: 110, h: 40 },
    { id: "spillway_flow", type: "value", x: 430, y: 84, label: "Suv tashlagich sarfi" },
    { id: "gate1", type: "gate", x: 265, y: 180, w: 40, h: 60, label: "Zatvor" },
    { id: "penstock", type: "penstock", x: 310, y: 310, w: 170, h: 50, label: "BOSIMLI QUVUR" },
    { id: "valve1", type: "valve", x: 420, y: 310, label: "Ventil" },
    { id: "penstock_flow", type: "value", x: 430, y: 250, label: "Quvur sarfi" },
    { id: "penstock_pressure", type: "value", x: 430, y: 410, label: "Quvur bosimi" },
    { id: "hall", type: "line", x: hallX, y: 200, w: hallW, h: hallH, label: "MASHINA ZALI" },
  ];
  for (let i = 1; i <= n; i++) {
    const r = Math.floor((i - 1) / cols);
    const c = (i - 1) % cols;
    const cx = Math.round(hallX + step * (c + 0.5));
    const cy = 300 + r * 170;
    els.push({ id: `unit${i}`, type: "unit", x: cx, y: cy, w: Math.min(84, Math.round(step - 10)), label: `G${i}`, unit: i });
    els.push({ id: `cb${i}`, type: "breaker", x: cx, y: cy - 50, label: `Q${i}`, unit: i });
  }
  const busX = hallX + hallW + 10;
  els.push(
    { id: "bus", type: "bus", x: hallX + 10, y: 225, w: hallW - 20, label: "Shina" },
    { id: "total_power", type: "value", x: Math.round(hallX + hallW / 2), y: 164, label: "Umumiy quvvat" },
    { id: "transformer", type: "transformer", x: busX + 30, y: 276, label: "Transformator" },
    { id: "line", type: "line", x: busX + 30, y: 150, w: 60, h: 0, label: "TARMOQ" },
    { id: "grid_freq", type: "value", x: busX + 110, y: 84, label: "Chastota" },
    { id: "tailwater", type: "tailwater", x: busX, y: 360, w: Math.max(120, VIEW.w - busX), h: 140, label: "QUYI BYEF" },
    { id: "downstream_level", type: "value", x: busX + 110, y: 430, label: "Quyi byef sathi" },
    { id: "bearing_temp", type: "value", x: 100, y: 462, label: "Podshipnik harorati" },
    { id: "vibration", type: "value", x: 300, y: 462, label: "Tebranish" },
  );
  return { version: 1, units: n, elements: els };
}

/** Eski slot bog'lanishini (dashboard.mimic: slot → sensor_id) sxemaga ko'chirish. */
export function bindFromSlots(scheme: Scheme, mimic: Record<string, number | null | undefined>): Scheme {
  const map: Record<string, string> = {
    inflow: "inflow", upstream_level: "upstream_level", spillway_flow: "spillway_flow", penstock_flow: "penstock_flow",
    penstock_pressure: "penstock_pressure", total_power: "total_power", downstream_level: "downstream_level",
    bearing_temp: "bearing_temp", vibration: "vibration", unit1_power: "unit1", unit2_power: "unit2", unit3_power: "unit3",
  };
  return {
    ...scheme,
    elements: scheme.elements.map((e) => {
      const slot = Object.entries(map).find(([, id]) => id === e.id)?.[0];
      const sid = slot ? mimic[slot] : undefined;
      return sid && !e.sensor_id ? { ...e, sensor_id: sid } : e;
    }),
  };
}

/** Sxema tekshiruvi: viewBox ichida, id lar unikal, agregat elementlari `units` ga mos. */
export function validateScheme(s: Scheme): string[] {
  const errs: string[] = [];
  const ids = new Set<string>();
  const v = viewOf(s);
  for (const e of s.elements) {
    if (ids.has(e.id)) errs.push(`takror id: ${e.id}`);
    ids.add(e.id);
    if (e.x < 0 || e.y < 0 || e.x > v.w || e.y > v.h) errs.push(`${e.id}: viewBox dan tashqarida (${e.x}, ${e.y})`);
  }
  const units = s.elements.filter((e) => e.type === "unit");
  if (units.length !== s.units) errs.push(`agregat elementlari ${units.length}, units=${s.units}`);
  return errs;
}

/** Ikki agregat elementi ustma-ust tushmasligi (markazlar orasi ≥ kenglik yoki qatorlar farq qiladi). */
export function overlappingUnits(s: Scheme): number {
  const us = s.elements.filter((e) => e.type === "unit");
  let n = 0;
  for (let i = 0; i < us.length; i++)
    for (let j = i + 1; j < us.length; j++)
      if (Math.abs(us[i].x - us[j].x) < Math.max(us[i].w ?? 64, 50) && Math.abs(us[i].y - us[j].y) < 50) n++;
  return n;
}

export function moveElement(s: Scheme, id: string, x: number, y: number): Scheme {
  const v = viewOf(s);
  const cx = Math.max(0, Math.min(v.w, Math.round(x)));
  const cy = Math.max(0, Math.min(v.h, Math.round(y)));
  return { ...s, elements: s.elements.map((e) => (e.id === id ? { ...e, x: cx, y: cy } : e)) };
}

export function setUnits(s: Scheme, n: number): Scheme {
  const fresh = defaultScheme(n);
  const keep = new Map(s.elements.map((e) => [e.id, e]));
  return {
    ...fresh,
    elements: fresh.elements.map((e) => {
      const old = keep.get(e.id);
      return old ? { ...e, ...old, unit: e.unit ?? old.unit } : e;
    }),
  };
}

/** Sxemani JSON dan o'qish (yo'q/eski → standart n agregat, eski slotlardan bog'lab). */
export function loadScheme(raw: unknown, mimic: Record<string, number | null | undefined>, unitsGuess: number): Scheme {
  const s = raw as Partial<Scheme> | null | undefined;
  if (s && s.version === 1 && Array.isArray(s.elements) && typeof s.units === "number") return s as Scheme;
  return bindFromSlots(defaultScheme(unitsGuess), mimic);
}
