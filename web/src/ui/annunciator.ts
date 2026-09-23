/** Ovozli signal — annunciator (F6). Bitta doimiy AudioContext (Chrome hujjatga ~6 tadan ortiq kontekstga
 * ruxsat bermaydi — alarm toshqinida jim bo'lib qolmasin), `suspended` holatini aniqlash (kiosk: foydalanuvchi
 * harakati bo'lmagan), sog'liq ko'rsatkichi, ustuvorlik bo'yicha signal; kritik — ack gacha takrorlanadi;
 * vaqtincha o'chirish (silence) muddat bilan (audit — chaqiruvchi). */

export type AnnunciatorHealth = "ok" | "blocked" | "silenced" | "off" | "unsupported";
export type Priority = "low" | "medium" | "high" | "critical";

/** Test uchun minimal AudioContext interfeysi */
export interface AudioLike {
  state: "suspended" | "running" | "closed";
  currentTime: number;
  destination: unknown;
  resume(): Promise<void>;
  createOscillator(): { type: string; frequency: { value: number }; connect(n: unknown): void; start(t?: number): void; stop(t?: number): void };
  createGain(): { gain: { value: number; setValueAtTime?(v: number, t: number): void }; connect(n: unknown): void };
}

/** Ustuvorlik → signal: chastota (Hz), beep soni, takror davri (ms; 0 — takrorsiz). ISA-18.2 / UX-03: tovush
 * ustuvorlikka mos va KVITLANGUNCHA takrorlanadi (kritik 5 s, yuqori 10 s, o'rta 20 s); past — jim (faqat ekranda). */
export const PATTERNS: Record<Priority, { hz: number; beeps: number; repeatMs: number; ms: number }> = {
  critical: { hz: 880, beeps: 3, repeatMs: 5000, ms: 180 },
  high: { hz: 660, beeps: 2, repeatMs: 10_000, ms: 200 },
  medium: { hz: 520, beeps: 1, repeatMs: 20_000, ms: 200 },
  low: { hz: 0, beeps: 0, repeatMs: 0, ms: 0 },
};
const RANK: Record<Priority, number> = { critical: 4, high: 3, medium: 2, low: 1 };
/** Ketma-ket kelgan alarmlar (toshqin, sahifa yuklanishi) bitta signalga birlashadi */
const COALESCE_MS = 1500;

export interface AnnunciatorOptions {
  contextFactory?: () => AudioLike;
  setTimer?: (fn: () => void, ms: number) => number;
  clearTimer?: (id: number) => void;
  now?: () => number;
}

export class Annunciator {
  private ctx: AudioLike | null = null;
  private factory: () => AudioLike;
  private setTimer: (fn: () => void, ms: number) => number;
  private clearTimer: (id: number) => void;
  private now: () => number;
  /** Kvitlanmagan alarmlar (takrorlanadigan ustuvorlik) — bitta umumiy taymer eng yuqori ustuvorlik bo'yicha */
  private active = new Map<number, Priority>();
  private timer: number | null = null;
  private timerPrio: Priority | null = null;
  private lastBeep = -Infinity;
  private listeners = new Set<() => void>();
  muted = false;
  silencedUntil: number | null = null;
  /** Statistika (test/diagnostika): chalingan beeplar */
  played = 0;

  constructor(opts: AnnunciatorOptions = {}) {
    this.factory = opts.contextFactory ?? (() => new (window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)() as unknown as AudioLike);
    this.setTimer = opts.setTimer ?? ((fn, ms) => window.setTimeout(fn, ms));
    this.clearTimer = opts.clearTimer ?? ((id) => window.clearTimeout(id));
    this.now = opts.now ?? (() => Date.now());
  }

  /** Kontekstni bir marta yaratadi (kechiktirib — ilova ishga tushganda yoki birinchi foydalanuvchi harakatida). */
  init(): AudioLike | null {
    if (this.ctx && this.ctx.state !== "closed") return this.ctx;
    try {
      this.ctx = this.factory();
    } catch {
      this.ctx = null; // AudioContext yo'q (eski brauzer / test muhiti) — "unsupported"
    }
    this.emit();
    return this.ctx;
  }

  /** Foydalanuvchi harakatida chaqiriladi: bloklangan (suspended) kontekstni davom ettiradi. */
  async unlock(): Promise<AnnunciatorHealth> {
    const c = this.init();
    if (c && c.state === "suspended") {
      try { await c.resume(); } catch { /* hali ham bloklangan */ }
    }
    this.emit();
    return this.health();
  }

  health(): AnnunciatorHealth {
    if (this.muted) return "off";
    if (this.silencedUntil != null && this.silencedUntil > this.now()) return "silenced";
    if (!this.ctx) return this.init() ? this.health() : "unsupported";
    return this.ctx.state === "running" ? "ok" : "blocked";
  }

  onChange(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }
  private emit() { for (const l of this.listeners) l(); }

  setMuted(m: boolean) { this.muted = m; if (m) this.stopAll(); this.emit(); }

  /** Vaqtincha o'chirish (silence) — muddat bilan; auditga yozishni chaqiruvchi bajaradi. */
  silence(minutes: number) {
    this.silencedUntil = minutes > 0 ? this.now() + minutes * 60_000 : null;
    if (minutes > 0) this.stopAll();
    this.emit();
  }

  private canPlay(): boolean {
    return this.health() === "ok";
  }

  /** Bir marta signal (ustuvorlik bo'yicha). Qaytaradi: chalindimi. */
  beep(priority: Priority): boolean {
    const p = PATTERNS[priority] ?? PATTERNS.medium;
    if (!p.beeps || !this.canPlay() || !this.ctx) return false;
    const ctx = this.ctx;
    try {
      for (let i = 0; i < p.beeps; i++) {
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.type = "square";
        o.frequency.value = p.hz;
        g.gain.value = 0.08;
        o.connect(g);
        g.connect(ctx.destination);
        const t0 = ctx.currentTime + i * (p.ms / 1000 + 0.08);
        o.start(t0);
        o.stop(t0 + p.ms / 1000);
      }
      this.played += 1;
      return true;
    } catch {
      return false; // bitta xato butun annunciatorni to'xtatmasin; sog'liq health() da ko'rinadi
    }
  }

  /** Alarm keldi: signal (toshqinda birlashtiriladi); kvitlanguncha eng yuqori ustuvorlik davri bilan takror.
   * 45 ta kvitlanmagan alarm — 45 ta taymer emas, bitta (ovoz tartibsiz bo'lmaydi). */
  alarm(eventId: number, priority: Priority): void {
    const isNew = !this.active.has(eventId);
    const p = PATTERNS[priority] ? priority : "medium";
    if (PATTERNS[p].repeatMs > 0) this.active.set(eventId, p);
    if (isNew && this.now() - this.lastBeep >= COALESCE_MS && this.beep(p)) this.lastBeep = this.now();
    // yuqoriroq ustuvorlik keldi — tezroq davrga o'tish
    if (this.timer != null && this.timerPrio && RANK[p] > RANK[this.timerPrio] && PATTERNS[p].repeatMs > 0) this.cancelTimer();
    this.schedule();
  }

  private top(): Priority | null {
    let best: Priority | null = null;
    for (const p of this.active.values()) if (!best || RANK[p] > RANK[best]) best = p;
    return best;
  }

  private schedule() {
    if (this.timer != null) return;
    const p = this.top();
    if (!p) return;
    this.timerPrio = p;
    this.timer = this.setTimer(() => {
      this.timer = null;
      const q = this.top();
      if (!q) return;
      if (this.beep(q)) this.lastBeep = this.now();
      this.schedule();
    }, PATTERNS[p].repeatMs);
  }

  private cancelTimer() {
    if (this.timer != null) this.clearTimer(this.timer);
    this.timer = null;
    this.timerPrio = null;
  }

  /** Kvitlandi / yopildi — shu alarm takrordan chiqadi; boshqa kvitlanmaganlar bo'lsa davom etadi. */
  ack(eventId: number): void {
    this.active.delete(eventId);
    if (!this.active.size) this.cancelTimer();
    else if (this.timerPrio && !([...this.active.values()].includes(this.timerPrio))) { this.cancelTimer(); this.schedule(); }
  }

  stopAll(): void {
    this.active.clear();
    this.cancelTimer();
  }

  get repeating(): number { return this.active.size; }
}

/** Ilova bo'ylab bitta nusxa (kontekst bitta bo'lishi kerak). */
export const annunciator = new Annunciator();
