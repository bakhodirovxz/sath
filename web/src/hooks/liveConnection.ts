import { api, type LiveMessage } from "../api/client";

/** Jonli oqim ulanishi (React dan mustaqil): heartbeat holat mashinasi, eksponensial qayta ulanish + jitter,
 * avtorizatsiya rad etilsa to'xtash, buzuq kadrlarni tashlash (FE-02). `useLive` hook i va umumiy jonli store
 * (UX-11) shu yadrodan foydalanadi. */

export type LiveState = "LIVE" | "STALE" | "OFFLINE";

export const STALE_AFTER_MS = 15_000; // server ping 10 s — 1.5 davr xabar yo'q → STALE
export const OFFLINE_AFTER_MS = 30_000; // 3 davr → OFFLINE (yarim ochiq TCP da onclose kelmasa ham)
export const NO_RETRY_CODES = new Set([4401, 4403, 1008]); // avtorizatsiya rad — qayta urinmaslik

/** Holat mashinasi: oxirgi xabar yoshi va soket ochiqligi bo'yicha. */
export function liveState(lastMsgAt: number | null, now: number, socketOpen: boolean): LiveState {
  if (!socketOpen || lastMsgAt == null) return "OFFLINE";
  const age = now - lastMsgAt;
  if (age >= OFFLINE_AFTER_MS) return "OFFLINE";
  if (age >= STALE_AFTER_MS) return "STALE";
  return "LIVE";
}

/** Qayta ulanish kechikishi: eksponensial (1 s × 2^n), jitter ±30 %, chegara 60 s — server tiklanganda
 * barcha ekranlar bir vaqtda urmasin. */
export function backoffMs(attempt: number, rnd: () => number = Math.random): number {
  const base = Math.min(60_000, 1000 * Math.pow(2, Math.max(0, attempt)));
  const jitter = 0.7 + 0.6 * rnd();
  return Math.round(base * jitter);
}

/** Buzuq kadrlar hisoblagichi (FE-02): diagnostika (L4) va testlar uchun. */
export const liveStats = { badFrames: 0, lastBadAt: 0 };
const LIVE_TYPES = new Set(["snapshot", "reading", "alarm", "command", "journal", "ping"]);

/** Kadrni xavfsiz tahlil qilish: JSON emas yoki `type` noma'lum — null (hisoblanadi, jurnalga — 10 s da bir marta).
 * Bitta buzuq kadr butun oqimni (onmessage istisnosi) to'xtatib qo'ymaydi. */
export function parseLiveFrame(data: unknown): LiveMessage | null {
  let m: unknown;
  try {
    m = typeof data === "string" ? JSON.parse(data) : null;
  } catch {
    m = null;
  }
  if (m && typeof m === "object" && LIVE_TYPES.has((m as { type?: string }).type ?? "")) return m as LiveMessage;
  liveStats.badFrames++;
  const now = Date.now();
  if (now - liveStats.lastBadAt > 10_000) {
    liveStats.lastBadAt = now;
    console.warn(`[live] buzuq kadr tashlab yuborildi (jami ${liveStats.badFrames}):`, typeof data === "string" ? data.slice(0, 120) : typeof data);
  }
  return null;
}

export interface LiveConnectionOptions {
  projectId: number;
  /** Soket fabrikasi (test/injeksiya). Default: api.liveSocket — chipta olib, keyin soket */
  socket?: ((projectId: number) => WebSocket | Promise<WebSocket>) | undefined;
  /** Holat tekshiruv davri, ms */
  tickMs?: number | undefined;
  onMessage: (m: LiveMessage) => void;
  onState: (s: LiveState) => void;
}

/** Ulanishni boshlaydi; qaytaradi — to'xtatish funksiyasi. */
export function openLiveConnection(o: LiveConnectionOptions): () => void {
  let closed = false;
  let timer: number | undefined;
  let ws: WebSocket | null = null;
  let attempt = 0;
  let lastMsgAt: number | null = null;
  let open = false;
  let last: LiveState | null = null;
  const update = () => {
    const s = liveState(lastMsgAt, Date.now(), open);
    if (s !== last) { last = s; o.onState(s); }
  };
  const tick = window.setInterval(() => {
    update();
    // Yarim ochiq soket: xabar OFFLINE chegarasidan uzoq kelmasa — yopib, qayta ulanamiz
    if (open && lastMsgAt != null && Date.now() - lastMsgAt >= OFFLINE_AFTER_MS) ws?.close();
  }, o.tickMs ?? 1000);
  const attach = (sock: WebSocket) => {
    if (closed) { sock.close(); return; }
    ws = sock;
    ws.onopen = () => { open = true; lastMsgAt = Date.now(); attempt = 0; update(); };
    ws.onmessage = (ev) => {
      lastMsgAt = Date.now(); // buzuq kadr ham "aloqa bor" belgisi — lekin qo'llanmaydi
      const m = parseLiveFrame(ev.data);
      if (m?.type === "ping") { try { ws?.send("pong"); } catch { /* yopilmoqda */ } } // L4: bo'sh turish chegarasi uchun javob
      else if (m) o.onMessage(m);
      update();
    };
    ws.onclose = (ev) => {
      open = false;
      update();
      if (closed || NO_RETRY_CODES.has(ev.code)) return;
      timer = window.setTimeout(connect, backoffMs(attempt++));
    };
    ws.onerror = () => ws?.close();
  };
  const connect = () => {
    if (closed) return;
    let made: WebSocket | Promise<WebSocket>;
    try {
      made = (o.socket ?? api.liveSocket)(o.projectId);
    } catch {
      timer = window.setTimeout(connect, backoffMs(attempt++));
      return;
    }
    if (made instanceof Promise) {
      // Chipta olinmadi (tarmoq/401) — orqaga chekinib qayta urinamiz; sessiya tugagan bo'lsa request() o'zi chiqaradi
      made.then(attach, () => { if (!closed) timer = window.setTimeout(connect, backoffMs(attempt++)); });
    } else attach(made);
  };
  update();
  connect();
  return () => { closed = true; window.clearTimeout(timer); window.clearInterval(tick); ws?.close(); };
}
