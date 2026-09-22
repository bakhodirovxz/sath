/** DOM listener reestri (F11): `on()` orqali qo'shilgan har bir listener `dispose()` da olib tashlanadi —
 * anonim funksiyalar `window` ga bog'lanib `this` ni ushlab turmaydi (Viewer/sahna/GPU buferlari oqmaydi). */
export class DomListeners {
  private items: { target: EventTarget; type: string; fn: EventListenerOrEventListenerObject; opts?: AddEventListenerOptions | boolean | undefined }[] = [];
  private timers = new Set<number>();

  on<K extends keyof WindowEventMap>(target: Window, type: K, fn: (ev: WindowEventMap[K]) => void, opts?: AddEventListenerOptions | boolean): void;
  on<K extends keyof HTMLElementEventMap>(target: HTMLElement, type: K, fn: (ev: HTMLElementEventMap[K]) => void, opts?: AddEventListenerOptions | boolean): void;
  on(target: EventTarget, type: string, fn: EventListenerOrEventListenerObject, opts?: AddEventListenerOptions | boolean): void;
  on(target: EventTarget, type: string, fn: EventListenerOrEventListenerObject | ((ev: never) => void), opts?: AddEventListenerOptions | boolean): void {
    const f = fn as EventListenerOrEventListenerObject;
    target.addEventListener(type, f, opts);
    this.items.push({ target, type, fn: f, opts });
  }

  /** Tozalanadigan taymer (dispose da bekor qilinadi). */
  timeout(fn: () => void, ms: number): number {
    const id = window.setTimeout(() => { this.timers.delete(id); fn(); }, ms);
    this.timers.add(id);
    return id;
  }

  clearTimeout(id: number): void {
    window.clearTimeout(id);
    this.timers.delete(id);
  }

  get count(): number { return this.items.length; }

  dispose(): void {
    for (const { target, type, fn, opts } of this.items) target.removeEventListener(type, fn, opts);
    this.items = [];
    for (const t of this.timers) window.clearTimeout(t);
    this.timers.clear();
  }
}
