/** Dizayn tokenlari — yagona manba (F1).
 *
 * Ikki tema: `engineer` (Blender Dark uslubi, model/muhandislik sahifalari) va `operator`
 * (ISA-101: neytral kulrang asos, past to'yinganlik, rang faqat anomaliya uchun; dispetcher sahifalari
 * default). Alarm holati × ustuvorlik → rang + shakl + matn kodi: rang yagona kanal emas
 * (ISA-101 §6.2, rang ko'rishi buzilgan operatorlar). Barcha juftliklar WCAG AA (matn 4.5:1, grafik 3:1) —
 * `tokens.test.ts` tekshiradi. Sahifalar rang qiymatini shu yerdan oladi (test: hex literal yo'q).
 */

export type ThemeName = "engineer" | "operator";
export type AlarmStateName = "ok" | "low" | "high" | "stale" | "lowlow" | "highhigh" | "roc" | "deviation";
export type PriorityName = "low" | "medium" | "high" | "critical";
export type QualityName = "good" | "uncertain" | "bad" | "substituted" | "manual";

/** CSS o'zgaruvchilar (nomi `--` siz) — har tema uchun to'liq to'plam. */
export const THEMES: Record<ThemeName, Record<string, string>> = {
  engineer: {
    canvas: "#3d3d3d",
    panel: "#303030",
    chrome: "#282828",
    "chrome-2": "#3d3d3d",
    line: "#232323",
    "line-strong": "#191919",
    widget: "#545454",
    "widget-hover": "#656565",
    "widget-line": "#3d3d3d",
    field: "#1d1d1d",
    sel: "#334d80",
    text: "#e6e6e6",
    "text-muted": "#b3b3b3",
    "text-dim": "#aaaaaa",
    accent: "#4772b3",
    link: "#8fb0e6",
    "accent-2": "#39b7c9",
    brand: "#39b7c9",
    ok: "#6ad39c",
    warn: "#f0c060",
    danger: "#f7a8a8",
    wip: "#9a9a9a",
    // Alarm ustuvorligi (ISA-101 jadvali): kritik qizil, yuqori sariq-to'q, o'rta sariq, past ko'k-kulrang
    "alarm-critical": "#f7a8a8",
    "alarm-high": "#f5b86a",
    "alarm-medium": "#ecd75a",
    "alarm-low": "#9fc0ea",
    "alarm-stale": "#c4c4c4",
    "alarm-row": "#703d3d",
    "quality-bad": "#d8b0f5",
    "quality-uncertain": "#d2c290",
    "mimic-water": "#1d3f55",
    "mimic-concrete": "#5b616b",
    "mimic-outline": "#8b9098",
    "mimic-pipe": "#9aa0a8",
    "mimic-hall": "#2b2f36",
    "mimic-unit-on": "#1f3b2c",
    "mimic-unit-off": "#26282c",
    "mimic-unbound": "#9296a0",
    "mimic-idle": "#9aa0a8",
    // Trend qalamlari (F7): grafik foni (--field) ustida ≥ 3:1
    "pen-1": "#6fa8f5",
    "pen-2": "#f0b35a",
    "pen-3": "#6ad39c",
    "pen-4": "#d29cf0",
    "pen-5": "#f58c8c",
    "pen-6": "#7fd9e6",
  },
  operator: {
    // ISA-101: ochiq neytral kulrang fon, rang faqat holat uchun
    canvas: "#d9dbde",
    panel: "#e6e7e9",
    chrome: "#cfd2d6",
    "chrome-2": "#d9dbde",
    line: "#b8bcc2",
    "line-strong": "#9aa0a8",
    widget: "#c9ccd1",
    "widget-hover": "#b8bcc2",
    "widget-line": "#a8adb4",
    field: "#f4f5f6",
    sel: "#b9c9e6",
    text: "#1c1f24",
    "text-muted": "#4c525a",
    "text-dim": "#4a4f57",
    accent: "#27508f",
    link: "#27508f",
    "accent-2": "#1f7f8f",
    brand: "#1f7f8f",
    ok: "#1c5634",
    warn: "#6e4700",
    danger: "#9e1b14",
    wip: "#6a6e76",
    "alarm-critical": "#9e1b14",
    "alarm-high": "#823a00",
    "alarm-medium": "#5e4c00",
    "alarm-low": "#27508f",
    "alarm-stale": "#4a4f57",
    "alarm-row": "#e9b0aa",
    "quality-bad": "#5a3388",
    "quality-uncertain": "#54471c",
    "mimic-water": "#a9c4d8",
    "mimic-concrete": "#b0b5bd",
    "mimic-outline": "#5c626b",
    "mimic-pipe": "#8a9098",
    "mimic-hall": "#d3d6da",
    "mimic-unit-on": "#cfe7d8",
    "mimic-unit-off": "#dfe1e4",
    "mimic-unbound": "#5f646c",
    "mimic-idle": "#5f646c",
    "pen-1": "#1f5fb8",
    "pen-2": "#9a5a00",
    "pen-3": "#1c6b3f",
    "pen-4": "#6b3fa0",
    "pen-5": "#b3261e",
    "pen-6": "#0f6e7e",
  },
};

export const THEME_KEY = "sath.theme";

/** Temani hujjatga qo'llaydi (CSS o'zgaruvchilar + `data-theme`) va saqlaydi. */
export function applyTheme(name: ThemeName, persist = true): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.setAttribute("data-theme", name);
  for (const [k, v] of Object.entries(THEMES[name])) root.style.setProperty(`--${k}`, v);
  if (persist) {
    try { localStorage.setItem(THEME_KEY, name); } catch { /* xotira yopiq (kiosk) — sessiya ichida ishlaydi */ }
  }
}

/** Saqlangan tema yoki `fallback` (dispetcher sahifalari `operator`, boshqalar `engineer`). */
export function savedTheme(fallback: ThemeName): ThemeName {
  try {
    const v = localStorage.getItem(THEME_KEY);
    if (v === "engineer" || v === "operator") return v;
  } catch { /* yo'q */ }
  return fallback;
}

export function currentTheme(): ThemeName {
  if (typeof document === "undefined") return "engineer";
  return document.documentElement.getAttribute("data-theme") === "operator" ? "operator" : "engineer";
}

/** Alarm holati × ustuvorlik → ko'rsatish tokeni. Shakl va kod rangdan mustaqil kanal. */
export interface AlarmStyle {
  /** CSS rang ifodasi (`var(--…)`) */
  color: string;
  /** Qator/fon uchun */
  bg: string;
  /** ISA-101: kritik — romb, yuqori — kvadrat, o'rta — uchburchak, past — doira; ok — yo'q */
  shape: "diamond" | "square" | "triangle" | "circle" | "none";
  /** Qisqa matn kodi: HH, H, L, LL, ROC, DEV, ?, — */
  code: string;
  /** Ustuvorlik raqami (1 = kritik … 4 = past), ok/stale — 0 */
  rank: 0 | 1 | 2 | 3 | 4;
  label: string;
  /** Shakl ichidagi belgi (Unicode) — rangsiz ham o'qiladi */
  glyph: string;
}

export const STATE_CODE: Record<AlarmStateName, string> = {
  ok: "", low: "L", high: "H", stale: "?", lowlow: "LL", highhigh: "HH", roc: "ROC", deviation: "DEV",
};
export const STATE_LABEL: Record<AlarmStateName, string> = {
  ok: "normal", low: "past", high: "yuqori", stale: "aloqa yo'q", lowlow: "juda past (LL)",
  highhigh: "juda yuqori (HH)", roc: "tez o'zgarish", deviation: "model bilan og'ish",
};
const PRIO_RANK: Record<PriorityName, 1 | 2 | 3 | 4> = { critical: 1, high: 2, medium: 3, low: 4 };
const PRIO_SHAPE: Record<PriorityName, AlarmStyle["shape"]> = { critical: "diamond", high: "square", medium: "triangle", low: "circle" };
const PRIO_GLYPH: Record<PriorityName, string> = { critical: "◆", high: "■", medium: "▲", low: "●" };

export function isActiveAlarm(state: string | null | undefined): boolean {
  return !!state && state !== "ok" && state !== "stale";
}

export function alarmStyle(state: AlarmStateName | string, priority: PriorityName | string = "medium"): AlarmStyle {
  const st = (state in STATE_CODE ? state : "ok") as AlarmStateName;
  const pr = (priority in PRIO_RANK ? priority : "medium") as PriorityName;
  if (st === "ok") return { color: "var(--ok)", bg: "transparent", shape: "none", code: "", rank: 0, label: STATE_LABEL.ok, glyph: "" };
  if (st === "stale") return { color: "var(--alarm-stale)", bg: "transparent", shape: "none", code: "?", rank: 0, label: STATE_LABEL.stale, glyph: "?" };
  return {
    color: `var(--alarm-${pr})`,
    bg: "var(--alarm-row)",
    shape: PRIO_SHAPE[pr],
    code: STATE_CODE[st],
    rank: PRIO_RANK[pr],
    label: STATE_LABEL[st],
    glyph: PRIO_GLYPH[pr],
  };
}

/** Sifat belgisi: rangdan tashqari `?`/`~`/`m` kodi — bad qiymat hech qachon "normal" ko'rinmaydi. */
export function qualityStyle(q: QualityName | string | undefined): { code: string; color: string; label: string } {
  switch (q) {
    case "bad": return { code: "✕", color: "var(--quality-bad)", label: "yaroqsiz" };
    case "uncertain": return { code: "~", color: "var(--quality-uncertain)", label: "noaniq" };
    case "substituted": return { code: "s", color: "var(--quality-uncertain)", label: "almashtirilgan" };
    case "manual": return { code: "m", color: "var(--quality-uncertain)", label: "qo'lda" };
    default: return { code: "", color: "var(--text)", label: "yaxshi" };
  }
}

/** Ustuvorlik bo'yicha saralash kaliti: kritik birinchi, keyin holat og'irligi, keyin vaqt (chaqiruvchi). */
export function alarmRank(state: string, priority: string): number {
  const s = alarmStyle(state, priority);
  const sev: Record<string, number> = { highhigh: 0, lowlow: 0, high: 1, low: 1, roc: 2, deviation: 2, stale: 3, ok: 4 };
  return (s.rank || 5) * 10 + (sev[state] ?? 4);
}

// --- WCAG kontrast (test va tekshiruvlar uchun) ------------------------------------------------

export function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const n = parseInt(full, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function luminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex).map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG 2.x kontrast nisbati (1 … 21). */
export function contrast(a: string, b: string): number {
  const la = luminance(a);
  const lb = luminance(b);
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}
