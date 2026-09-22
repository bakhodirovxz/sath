import { useEffect, useRef, useState } from "react";
import { api, type LiveMessage, type Sensor } from "../api/client";

/** Jonli oqim holati (F4): LIVE — xabar yaqinda kelgan; STALE — heartbeat kechikmoqda; OFFLINE — uzilgan/jim.
 * Uchalasi vizual jihatdan farq qiladi (OperatorShell/MonitoringPanel). */
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

/** Xabarni sensor ro'yxatiga qo'llash (snapshot/reading): value, ts, alarm, stale, quality. */
export function applyLiveMessage(prev: Sensor[], m: LiveMessage): Sensor[] {
  if (m.type === "snapshot" && m.sensors) {
    const by = new Map(m.sensors.map((u) => [u.sensor_id, u]));
    return prev.map((s) => {
      const u = by.get(s.id);
      return u ? { ...s, last_value: u.value, last_ts: u.ts, alarm: u.alarm, stale: u.stale ?? s.stale, last_quality: u.quality ?? s.last_quality } : s;
    });
  }
  if (m.type === "reading" && m.sensor_id != null) {
    return prev.map((s) => (s.id === m.sensor_id ? { ...s, last_value: m.value ?? null, last_ts: m.ts ?? null, alarm: m.alarm ?? s.alarm, stale: m.stale ?? false, last_quality: m.quality ?? s.last_quality } : s));
  }
  return prev;
}

export interface LiveOptions {
  /** Test/injeksiya: soket fabrikasi (default api.liveSocket — chipta olib, keyin soket) */
  socket?: (projectId: number) => WebSocket | Promise<WebSocket>;
  /** Holat tekshiruv davri, ms */
  tickMs?: number;
}

/** Loyiha jonli oqimi (WebSocket): sensor holatlarini yangilab turadi, xabarlarni chaqiruvchiga beradi.
 * Heartbeat: server 10 s da ping yuboradi; xabar yoshi chegaradan oshsa LIVE → STALE → OFFLINE.
 * Qayta ulanish: eksponensial kechikish + jitter (≤ 60 s); 4401/4403 yopilishida takrorlanmaydi. */
export function useLive(
  projectId: number,
  setSensors: React.Dispatch<React.SetStateAction<Sensor[]>>,
  onMessage?: (m: LiveMessage) => void,
  opts: LiveOptions = {},
): LiveState {
  const [state, setState] = useState<LiveState>("OFFLINE");
  const cb = useRef(onMessage);
  cb.current = onMessage;
  const factory = useRef(opts.socket);
  factory.current = opts.socket;
  const tickMs = opts.tickMs ?? 1000;
  useEffect(() => {
    let closed = false;
    let timer: number | undefined;
    let ws: WebSocket | null = null;
    let attempt = 0;
    let lastMsgAt: number | null = null;
    let open = false;
    const update = () => setState(liveState(lastMsgAt, Date.now(), open));
    const tick = window.setInterval(() => {
      update();
      // Yarim ochiq soket: xabar OFFLINE chegarasidan uzoq kelmasa — yopib, qayta ulanamiz
      if (open && lastMsgAt != null && Date.now() - lastMsgAt >= OFFLINE_AFTER_MS) ws?.close();
    }, tickMs);
    const attach = (sock: WebSocket) => {
      if (closed) { sock.close(); return; }
      ws = sock;
      ws.onopen = () => { open = true; lastMsgAt = Date.now(); attempt = 0; update(); };
      ws.onmessage = (ev) => {
        lastMsgAt = Date.now();
        const m = JSON.parse(ev.data) as LiveMessage;
        if (m.type === "snapshot" || m.type === "reading") setSensors((prev) => applyLiveMessage(prev, m));
        if (m.type === "ping") { try { ws?.send("pong"); } catch { /* yopilmoqda */ } } // L4: bo'sh turish chegarasi uchun javob
        else cb.current?.(m);
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
        made = (factory.current ?? api.liveSocket)(projectId);
      } catch {
        timer = window.setTimeout(connect, backoffMs(attempt++));
        return;
      }
      if (made instanceof Promise) {
        // Chipta olinmadi (tarmoq/401) — orqaga chekinib qayta urinamiz; sessiya tugagan bo'lsa request() o'zi chiqaradi
        made.then(attach, () => { if (!closed) timer = window.setTimeout(connect, backoffMs(attempt++)); });
      } else attach(made);
    };
    connect();
    return () => { closed = true; window.clearTimeout(timer); window.clearInterval(tick); ws?.close(); };
  }, [projectId, setSensors, tickMs]);
  return state;
}
