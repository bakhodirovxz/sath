/** Dizayn tokenlari — yagona manba (F1, UX-05). Qoidalar: docs/design/ui-direction.md.
 *
 * Uch tema: `engineer` (Blender Dark — BIM/model sahifalari), `operator` (ISA-101 / High Performance HMI:
 * neytral kulrang, rang faqat anomaliya uchun — dispetcher sahifalari) va `operator-hc` (kunduzgi, yuqori
 * kontrast — yorug' boshqaruv xonasi). Alarm holati × ustuvorlik → rang + SHAKL + raqam + kod: rang yagona kanal
 * emas (ISA-101, WCAG 1.4.1). Barcha juftliklar WCAG AA (matn 4.5:1, grafik 3:1) — `tokens.test.ts`.
 * CSS da xuddi shu qiymatlar `tokens.css` da (test sinxronlikni tekshiradi); komponentlarda hex yo'q.
 * Desktop (Blender) nusxasi: `python desktop/build/gen_tokens.py` → desktop/blender/sath/core/tokens.py va
 * template/Sath/theme_sath.xml (CI `--check` — bu yerdagi rang o'zgarsa desktop ham yangilanadi).
 */

import { alarmLabel, qualityLabel } from "../i18n/labels";

export type ThemeName = "engineer" | "operator" | "operator-hc";
export type OpsThemeName = Extract<ThemeName, "operator" | "operator-hc">;
export type AlarmStateName = "ok" | "low" | "high" | "stale" | "lowlow" | "highhigh" | "roc" | "deviation";
export type PriorityName = "low" | "medium" | "high" | "critical";
export type QualityName = "good" | "uncertain" | "bad" | "substituted" | "manual";

/** CSS o'zgaruvchilar (nomi `--` siz) — har tema uchun to'liq to'plam (faqat ranglar; o'lcham/oraliq —
 * tokens.css da, temadan mustaqil). */
export const THEMES: Record<ThemeName, Record<string, string>> = {
  engineer: {
    // Sirtlar (Blender: panel ichidagi bo'limlar, sarlavhalar), qoplamalar, viewport
    "canvas-2": "#2b2b2b",
    "surface-1": "#383838",
    "surface-2": "#424242",
    "surface-hover": "#4a4a4a",
    "on-sel": "#ffffff",
    overlay: "rgba(48, 48, 48, 0.75)",
    "overlay-strong": "rgba(32, 33, 36, 0.94)",
    "vp-ink": "#111111",
    "vp-shadow": "#000000",
    // BIM versiya farqi (qo'shilgan / o'zgargan / o'chirilgan) — faqat diff ko'rinishida
    "diff-add": "#2ecc71",
    "diff-change": "#f1c40f",
    "diff-del": "#e74c3c",
    // Blender 4.x "Blender Dark" neytrallari
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
    "menu-bg": "#1f1f1f",
    sel: "#334d80",
    "sel-strong": "#4d6fa8",
    text: "#e6e6e6",
    "text-muted": "#b3b3b3",
    "text-dim": "#aaaaaa",
    accent: "#4772b3",
    "accent-hover": "#5680c4",
    "on-accent": "#ffffff",
    link: "#8fb0e6",
    "accent-2": "#39b7c9",
    brand: "#39b7c9",
    focus: "#8fb0e6",
    ok: "#6ad39c",
    warn: "#f0c060",
    danger: "#f7a8a8",
    "danger-strong": "#c0392b",
    "on-danger": "#ffffff",
    wip: "#9a9a9a",
    // Neytral "e'tibor" (muddati o'tgan ish buyrug'i, kam qism) — alarm EMAS (UX-02)
    attention: "#c9b27a",
    "attention-bg": "#3a3527",
    // Alarm ustuvorligi: shakl to'ldirish + siyoh (shakl ichidagi raqam) + kontur
    "alarm-critical": "#ff6262",
    "alarm-high": "#f29a38",
    "alarm-medium": "#f2c94c",
    "alarm-low": "#5b8ff0",
    "alarm-critical-ink": "#000000",
    "alarm-high-ink": "#000000",
    "alarm-medium-ink": "#000000",
    "alarm-low-ink": "#000000",
    "alarm-outline": "#111111",
    "alarm-stale": "#c4c4c4",
    "alarm-row": "#5a3434",
    "quality-bad": "#d8b0f5",
    "quality-uncertain": "#d2c290",
    // Mimika (muhandis temasida ham ISA qoidalari: rang faqat holat)
    "mimic-liquid": "#46505a",
    "mimic-concrete": "#5b616b",
    "mimic-outline": "#8b9098",
    "mimic-on": "#9aa0a8",
    "mimic-on-ink": "#1d1d1d",
    "mimic-off": "#3d3d3d",
    "mimic-hall": "#353535",
    "mimic-unbound": "#9296a0",
    // Trend qalamlari (F7): grafik foni (--field) ustida ≥ 3:1
    "pen-1": "#6fa8f5",
    "pen-2": "#f0b35a",
    "pen-3": "#6ad39c",
    "pen-4": "#d29cf0",
    "pen-5": "#f58c8c",
    "pen-6": "#7fd9e6",
  },
  operator: {
    "canvas-2": "#d6d8db",
    "surface-1": "#d6d8db",
    "surface-2": "#cdd0d4",
    "surface-hover": "#c2c6cb",
    "on-sel": "#16181b",
    overlay: "rgba(228, 229, 231, 0.8)",
    "overlay-strong": "rgba(244, 245, 246, 0.96)",
    "vp-ink": "#111111",
    "vp-shadow": "#ffffff",
    "diff-add": "#1c6b3f",
    "diff-change": "#8a6d00",
    "diff-del": "#b3261e",
    // ISA-101 / HP-HMI: neytral kulrang; rang FAQAT anomaliya uchun
    canvas: "#dcdddf",
    panel: "#e4e5e7",
    chrome: "#cdd0d4",
    "chrome-2": "#d6d8db",
    line: "#b8bcc2",
    "line-strong": "#8e949c",
    widget: "#d0d3d7",
    "widget-hover": "#c2c6cb",
    "widget-line": "#8e949c",
    field: "#f4f5f6",
    "menu-bg": "#f4f5f6",
    sel: "#c9ccd1",
    "sel-strong": "#b5b9bf",
    text: "#16181b",
    "text-muted": "#3f444b",
    "text-dim": "#4a4f57",
    // navigatsiya/tanlov — to'q kulrang (ko'k P4 alarmga band)
    accent: "#2f343b",
    "accent-hover": "#454a52",
    "on-accent": "#ffffff",
    link: "#1f3f73",
    "accent-2": "#3f444b",
    brand: "#1f5f6b",
    focus: "#000000",
    // "ok/normal" — rangsiz (ISA-101: normal holat uchun yashil yo'q)
    ok: "#3f444b",
    warn: "#6e4700",
    danger: "#9e1b14",
    "danger-strong": "#b3261e",
    "on-danger": "#ffffff",
    wip: "#4a4f57",
    attention: "#3f444b",
    "attention-bg": "#d6d8db",
    "alarm-critical": "#d6211a",
    "alarm-high": "#ec8a1c",
    "alarm-medium": "#f2c200",
    "alarm-low": "#2e6fd8",
    "alarm-critical-ink": "#ffffff",
    "alarm-high-ink": "#000000",
    "alarm-medium-ink": "#000000",
    "alarm-low-ink": "#ffffff",
    "alarm-outline": "#1b1d20",
    "alarm-stale": "#4a4f57",
    "alarm-row": "#f3d3d0",
    "quality-bad": "#3f444b",
    "quality-uncertain": "#3f444b",
    "mimic-liquid": "#c4c8cd",
    "mimic-concrete": "#b8bcc2",
    "mimic-outline": "#5c626b",
    "mimic-on": "#5c626b",
    "mimic-on-ink": "#ffffff",
    "mimic-off": "#e4e5e7",
    "mimic-hall": "#d6d8db",
    "mimic-unbound": "#5f646c",
    "pen-1": "#1f5fb8",
    "pen-2": "#9a5a00",
    "pen-3": "#1c6b3f",
    "pen-4": "#6b3fa0",
    "pen-5": "#b3261e",
    "pen-6": "#0f6e7e",
  },
  "operator-hc": {
    "canvas-2": "#ededed",
    "surface-1": "#ededed",
    "surface-2": "#e0e0e0",
    "surface-hover": "#d4d4d4",
    "on-sel": "#000000",
    overlay: "rgba(255, 255, 255, 0.85)",
    "overlay-strong": "rgba(255, 255, 255, 0.97)",
    "vp-ink": "#000000",
    "vp-shadow": "#ffffff",
    "diff-add": "#1c6b3f",
    "diff-change": "#7a5f00",
    "diff-del": "#8a130e",
    // Kunduzgi / yuqori kontrast: oqroq fon, qora matn, qalinroq konturlar
    canvas: "#f2f2f2",
    panel: "#ffffff",
    chrome: "#e6e6e6",
    "chrome-2": "#ededed",
    line: "#8a8a8a",
    "line-strong": "#333333",
    widget: "#e6e6e6",
    "widget-hover": "#d4d4d4",
    "widget-line": "#333333",
    field: "#ffffff",
    "menu-bg": "#ffffff",
    sel: "#d4d4d4",
    "sel-strong": "#bdbdbd",
    text: "#000000",
    "text-muted": "#26292d",
    "text-dim": "#333333",
    accent: "#111111",
    "accent-hover": "#333333",
    "on-accent": "#ffffff",
    link: "#0b2e66",
    "accent-2": "#26292d",
    brand: "#0b4a55",
    focus: "#000000",
    ok: "#26292d",
    warn: "#5a3a00",
    danger: "#8a130e",
    "danger-strong": "#b3261e",
    "on-danger": "#ffffff",
    wip: "#333333",
    attention: "#26292d",
    "attention-bg": "#e6e6e6",
    "alarm-critical": "#d6211a",
    "alarm-high": "#ec8a1c",
    "alarm-medium": "#f2c200",
    "alarm-low": "#2e6fd8",
    "alarm-critical-ink": "#ffffff",
    "alarm-high-ink": "#000000",
    "alarm-medium-ink": "#000000",
    "alarm-low-ink": "#ffffff",
    "alarm-outline": "#000000",
    "alarm-stale": "#333333",
    "alarm-row": "#f6cfcb",
    "quality-bad": "#26292d",
    "quality-uncertain": "#26292d",
    "mimic-liquid": "#d4d4d4",
    "mimic-concrete": "#c4c4c4",
    "mimic-outline": "#333333",
    "mimic-on": "#333333",
    "mimic-on-ink": "#ffffff",
    "mimic-off": "#ffffff",
    "mimic-hall": "#ededed",
    "mimic-unbound": "#333333",
    "pen-1": "#1f5fb8",
    "pen-2": "#8a5000",
    "pen-3": "#1c6b3f",
    "pen-4": "#6b3fa0",
    "pen-5": "#b3261e",
    "pen-6": "#0f6e7e",
  },
};

export const THEME_KEY = "sath.opsTheme";

/** Temani hujjatga qo'llaydi (`data-theme` — qiymatlar tokens.css da). `persist` — faqat operator varianti
 * (standart ↔ kunduzgi) saqlanadi; muhandis temasi BIM sahifalariga bog'langan. */
export function applyTheme(name: ThemeName, persist = true): void {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-theme", name);
  if (persist && name !== "engineer") {
    try { localStorage.setItem(THEME_KEY, name); } catch { /* xotira yopiq (kiosk) — sessiya ichida ishlaydi */ }
  }
}

/** Dispetcher sahifalari temasi: saqlangan operator varianti (standart yoki kunduzgi), default — standart. */
export function opsTheme(): OpsThemeName {
  try {
    const v = localStorage.getItem(THEME_KEY);
    if (v === "operator" || v === "operator-hc") return v;
  } catch { /* yo'q */ }
  return "operator";
}

/** @deprecated — kontekst bo'yicha: BIM → `engineer`, dispetcher → `opsTheme()`. */
export function savedTheme(fallback: ThemeName): ThemeName {
  return fallback === "engineer" ? "engineer" : opsTheme();
}

export function currentTheme(): ThemeName {
  if (typeof document === "undefined") return "engineer";
  const t = document.documentElement.getAttribute("data-theme");
  return t === "operator" || t === "operator-hc" ? t : "engineer";
}

/** Alarm holati × ustuvorlik → ko'rsatish tokeni. Shakl va kod rangdan mustaqil kanal. */
export interface AlarmStyle {
  /** CSS rang ifodasi (`var(--…)`) */
  color: string;
  /** Qator/fon uchun */
  bg: string;
  /** Shakl ichidagi raqam/kod rangi (to'ldirishga nisbatan ≥ 4.5:1) */
  ink: string;
  /** ISA-101 / HP-HMI: kritik — romb ◆, yuqori — uchburchak ▲, o'rta — kvadrat ■, past — doira ●; ok — yo'q */
  shape: "diamond" | "square" | "triangle" | "circle" | "none";
  /** Ustuvorlik nomi (CSS sinf: `prio-<nom>`); ok/stale — null */
  priority: PriorityName | null;
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
const PRIO_RANK: Record<PriorityName, 1 | 2 | 3 | 4> = { critical: 1, high: 2, medium: 3, low: 4 };
const PRIO_SHAPE: Record<PriorityName, AlarmStyle["shape"]> = { critical: "diamond", high: "triangle", medium: "square", low: "circle" };
export const PRIO_GLYPH: Record<PriorityName, string> = { critical: "◆", high: "▲", medium: "■", low: "●" };

export function isActiveAlarm(state: string | null | undefined): boolean {
  return !!state && state !== "ok" && state !== "stale";
}

export function alarmStyle(state: AlarmStateName | string, priority: PriorityName | string = "medium"): AlarmStyle {
  const st = (state in STATE_CODE ? state : "ok") as AlarmStateName;
  const pr = (priority in PRIO_RANK ? priority : "medium") as PriorityName;
  if (st === "ok") return { color: "var(--text-muted)", ink: "var(--text)", bg: "transparent", shape: "none", priority: null, code: "", rank: 0, label: alarmLabel("ok"), glyph: "" };
  if (st === "stale") return { color: "var(--alarm-stale)", ink: "var(--text)", bg: "transparent", shape: "none", priority: null, code: "?", rank: 0, label: alarmLabel("stale"), glyph: "?" };
  return {
    color: `var(--alarm-${pr})`,
    ink: `var(--alarm-${pr}-ink)`,
    bg: "var(--alarm-row)",
    shape: PRIO_SHAPE[pr],
    priority: pr,
    code: STATE_CODE[st],
    rank: PRIO_RANK[pr],
    label: alarmLabel(st),
    glyph: PRIO_GLYPH[pr],
  };
}

/** Sifat belgisi: rangdan tashqari `?`/`~`/`m` kodi — bad qiymat hech qachon "normal" ko'rinmaydi. */
export function qualityStyle(q: QualityName | string | undefined): { code: string; color: string; label: string } {
  switch (q) {
    case "bad": return { code: "✕", color: "var(--quality-bad)", label: qualityLabel("bad") };
    case "uncertain": return { code: "~", color: "var(--quality-uncertain)", label: qualityLabel("uncertain") };
    case "substituted": return { code: "s", color: "var(--quality-uncertain)", label: qualityLabel("substituted") };
    case "manual": return { code: "m", color: "var(--quality-uncertain)", label: qualityLabel("manual") };
    default: return { code: "", color: "var(--text)", label: qualityLabel("good") };
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
