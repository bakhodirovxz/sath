import { readFileSync } from "fs";
import { describe, expect, it } from "vitest";
import { DomListeners } from "./listeners";

/** F11: 20 marta "mount/unmount" (reestr yaratish + listenerlar + dispose) dan keyin window listenerlari soni o'smaydi. */
describe("DomListeners (Viewer xotira oqishi)", () => {
  it("dispose() barcha listener va taymerlarni olib tashlaydi; 20 sikldan keyin soni doimiy", () => {
    const counts = new Map<string, number>();
    const origAdd = window.addEventListener.bind(window);
    const origRemove = window.removeEventListener.bind(window);
    window.addEventListener = ((t: string, f: EventListenerOrEventListenerObject, o?: AddEventListenerOptions | boolean) => { counts.set(t, (counts.get(t) ?? 0) + 1); origAdd(t, f, o); }) as typeof window.addEventListener;
    window.removeEventListener = ((t: string, f: EventListenerOrEventListenerObject, o?: EventListenerOptions | boolean) => { counts.set(t, (counts.get(t) ?? 0) - 1); origRemove(t, f, o); }) as typeof window.removeEventListener;
    try {
      let fired = 0;
      for (let i = 0; i < 20; i++) {
        const d = new DomListeners();
        const el = document.createElement("div");
        d.on(window, "keydown", () => { fired++; });
        d.on(window, "pointermove", () => undefined);
        d.on(window, "pointerup", () => undefined);
        d.on(el, "click", () => undefined);
        d.timeout(() => { fired += 100; }, 10_000);
        expect(d.count).toBe(4);
        window.dispatchEvent(new KeyboardEvent("keydown"));
        d.dispose();
        expect(d.count).toBe(0);
        window.dispatchEvent(new KeyboardEvent("keydown")); // dispose dan keyin chaqirilmaydi
      }
      expect(fired).toBe(20);
      expect(counts.get("keydown")).toBe(0);
      expect(counts.get("pointermove")).toBe(0);
      expect(counts.get("pointerup")).toBe(0);
    } finally {
      window.addEventListener = origAdd;
      window.removeEventListener = origRemove;
    }
  });
  it("Viewer.ts DOM listenerlarni faqat reestr orqali qo'shadi (window/container/canvas ga to'g'ridan-to'g'ri emas)", () => {
    const src = readFileSync("src/viewer/Viewer.ts", "utf8");
    expect(src.match(/window\.addEventListener\(/g)).toBeNull();
    expect(src.match(/container\.addEventListener\(/g)).toBeNull();
    expect(src.match(/\bdom\.addEventListener\(/g)).toBeNull();
    expect(src).toContain("this.dom.dispose()");
    expect((src.match(/this\.dom\.on\(/g) ?? []).length).toBeGreaterThanOrEqual(10);
    // clearModel jonli obyektlarni dropLive orqali (geometry/material dispose) bo'shatadi
    expect(src).toContain("await this.dropLive(g, b)");
  });
});
