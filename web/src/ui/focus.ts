import { useEffect, useRef } from "react";

/** Fokus yordamchilari (UX-10): dialog fokus-tuzog'i, boshlang'ich fokus, `autoFocus` o'rniga. */

const FOCUSABLE = [
  "a[href]", "area[href]", "button:not([disabled])", "input:not([disabled]):not([type=hidden])", "select:not([disabled])",
  "textarea:not([disabled])", "iframe", "[tabindex]:not([tabindex='-1'])", "[contenteditable=true]",
].join(",");

/** Konteyner ichidagi klaviatura bilan yetib boriladigan elementlar (hujjat tartibida, ko'rinadiganlari). */
export function focusables(root: HTMLElement): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => !el.hasAttribute("inert") && el.getAttribute("aria-hidden") !== "true" && (el.offsetParent !== null || el === document.activeElement || isTestEnv()));
}

// jsdom da layout yo'q (offsetParent doim null) — testlarda ko'rinish filtri o'tkazib yuboriladi
function isTestEnv(): boolean {
  return typeof navigator !== "undefined" && /jsdom/i.test(navigator.userAgent);
}

/** Boshlang'ich fokus nuqtasi: `[data-autofocus]` → birinchi forma maydoni → birinchi tugma → konteynerning o'zi. */
export function initialFocusTarget(root: HTMLElement): HTMLElement {
  const marked = root.querySelector<HTMLElement>("[data-autofocus]");
  if (marked) return marked;
  const all = focusables(root);
  return all.find((el) => /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)) ?? all[0] ?? root;
}

/** Tab / Shift+Tab ni konteyner ichida aylantiradi. true — hodisa qayta ishlandi. */
export function trapTab(root: HTMLElement, e: KeyboardEvent): boolean {
  if (e.key !== "Tab") return false;
  const all = focusables(root);
  if (!all.length) { e.preventDefault(); root.focus(); return true; }
  const first = all[0], last = all[all.length - 1];
  const active = document.activeElement as HTMLElement | null;
  const inside = !!active && root.contains(active);
  if (e.shiftKey && (active === first || !inside)) { e.preventDefault(); last.focus(); return true; }
  if (!e.shiftKey && (active === last || !inside)) { e.preventDefault(); first.focus(); return true; }
  return false;
}

/** Element paydo bo'lganda fokus (autoFocus o'rniga — ekran o'quvchi va mobil klaviatura uchun boshqariladigan). */
export function useFocusOnMount<T extends HTMLElement>(enabled = true) {
  const ref = useRef<T>(null);
  useEffect(() => { if (enabled) ref.current?.focus(); }, [enabled]);
  return ref;
}

/** Callback-ref: element DOM ga qo'shilganda fokus (shartli ko'rsatiladigan maydonlar uchun). */
export function focusOnMount(el: HTMLElement | null): void {
  el?.focus();
}
