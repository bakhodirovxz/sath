import { useSyncExternalStore } from "react";
import { ru } from "./ru";
import { latnToCyrl } from "./translit";
import { uzLatn, type MessageKey } from "./uz-Latn";

/** Yengil i18n qatlami (UX-09): tiplangan lug'at + `t()`. Tillar: uz-Latn (asosiy, to'liq), uz-Cyrl (uz-Latn dan
 * transliteratsiya — to'liq), ru (qisman, yetishmagani uz-Latn ga qaytadi). Tanlov localStorage da. */
export type Locale = "uz-Latn" | "uz-Cyrl" | "ru";
export type { MessageKey } from "./uz-Latn";

export const LOCALES: { id: Locale; title: string }[] = [
  { id: "uz-Latn", title: "O'zbekcha (lotin)" },
  { id: "uz-Cyrl", title: "Ўзбекча (кирилл)" },
  { id: "ru", title: "Русский (qisman)" },
];

const LOCALE_KEY = "sath.locale";
let cyrl: Record<string, string> | null = null;
function cyrlDict(): Record<string, string> {
  if (!cyrl) cyrl = Object.fromEntries(Object.entries(uzLatn).map(([k, v]) => [k, latnToCyrl(v)]));
  return cyrl;
}

function initial(): Locale {
  try {
    const v = localStorage.getItem(LOCALE_KEY);
    if (v === "uz-Latn" || v === "uz-Cyrl" || v === "ru") return v;
  } catch { /* yopiq xotira */ }
  return "uz-Latn";
}

let locale: Locale = initial();
const subs = new Set<() => void>();

export function getLocale(): Locale {
  return locale;
}
export function setLocale(l: Locale): void {
  if (l === locale) return;
  locale = l;
  try { localStorage.setItem(LOCALE_KEY, l); } catch { /* */ }
  if (typeof document !== "undefined") document.documentElement.lang = l === "ru" ? "ru" : l === "uz-Cyrl" ? "uz-Cyrl" : "uz";
  subs.forEach((f) => f());
}
/** Til o'zgarganda qayta chizish. */
export function useLocale(): Locale {
  return useSyncExternalStore((f) => { subs.add(f); return () => subs.delete(f); }, getLocale, getLocale);
}

export function hasKey(key: string): key is MessageKey {
  return Object.prototype.hasOwnProperty.call(uzLatn, key);
}

/** Tarjima: `{nom}` parametrlari almashtiriladi. Joriy tilda yo'q bo'lsa — uz-Latn. */
export function t(key: MessageKey, params?: Record<string, string | number>): string {
  const raw = locale === "uz-Cyrl" ? cyrlDict()[key] : locale === "ru" ? (ru[key] ?? uzLatn[key]) : uzLatn[key];
  const s = raw ?? key;
  return params ? s.replace(/\{(\w+)\}/g, (m, p: string) => (p in params ? String(params[p]) : m)) : s;
}

/** Enum qiymati yorlig'i: `enum.<group>.<value>`; noma'lum qiymat — o'zgarishsiz (xom inglizcha emas, lekin yo'qolmasin). */
export function tEnum(group: string, value: string | null | undefined): string {
  if (value == null || value === "") return "—";
  const key = `enum.${group}.${value}`;
  return hasKey(key) ? t(key) : value;
}

/** Test/diagnostika: lug'at kalitlari. */
export const MESSAGE_KEYS = Object.keys(uzLatn) as MessageKey[];
export const DICTS = { "uz-Latn": uzLatn as Record<string, string>, ru: ru as Record<string, string>, "uz-Cyrl": () => cyrlDict() };
