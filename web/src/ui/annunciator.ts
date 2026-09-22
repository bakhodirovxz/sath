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

/** Ustuvorlik → signal: chastota (Hz), beep soni, takror davri (ms; 0 — takrorsiz). ISA-18.2: tovush darajasi
 * ustuvorlikka mos, kritik — kvitlanguncha davom etadi. */
export const PATTERNS: Record<Priority, { hz: number; beeps: number; repeatMs: number; ms: number }> = {
  critical: { hz: 880, beeps: 3, repeatMs: 5000, ms: 180 },
  high: { hz: 660, beeps: 2, repeatMs: 0, ms: 200 },
  medium: { hz: 520, beeps: 1, repeatMs: 0, ms: 200 },
  low: { hz: 0, beeps: 0, repeatMs: 0, ms: 0 },
};

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
  private repeats = new Map<number, number>();
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

  /** Alarm keldi: signal; kritik — kvitlanguncha (ack) har 5 s takror. */
  alarm(eventId: number, priority: Priority): void {
    this.beep(priority);
    const p = PATTERNS[priority] ?? PATTERNS.medium;
    if (p.repeatMs > 0 && !this.repeats.has(eventId)) {
      const tick = () => {
        if (!this.repeats.has(eventId)) return;
        this.beep(priority);
        this.repeats.set(eventId, this.setTimer(tick, p.repeatMs));
      };
      this.repeats.set(eventId, this.setTimer(tick, p.repeatMs));
    }
  }

  /** Kvitlandi / yopildi — takror to'xtaydi. */
  ack(eventId: number): void {
    const t = this.repeats.get(eventId);
    if (t != null) this.clearTimer(t);
    this.repeats.delete(eventId);
  }

  stopAll(): void {
    for (const [id] of this.repeats) this.ack(id);
  }

  get repeating(): number { return this.repeats.size; }
}

/** Ilova bo'ylab bitta nusxa (kontekst bitta bo'lishi kerak). */
export const annunciator = new Annunciator();
