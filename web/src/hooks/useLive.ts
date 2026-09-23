import { useEffect, useRef, useState } from "react";
import type { LiveMessage, Sensor } from "../api/client";
import { openLiveConnection, type LiveState } from "./liveConnection";

export { NO_RETRY_CODES, OFFLINE_AFTER_MS, STALE_AFTER_MS, backoffMs, liveState, liveStats, parseLiveFrame, type LiveState } from "./liveConnection";

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

/** Loyiha jonli oqimi (WebSocket) — alohida ulanish, holat komponent ichida. Sahifalar umumiy
 * `store/live` (UX-11: bitta soket, har komponent o'z sensorlariga obuna) dan foydalanadi; bu hook testlar
 * va maxsus holatlar uchun qoldirilgan. Heartbeat, qayta ulanish — `liveConnection`. */
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
  useEffect(() => openLiveConnection({
    projectId,
    socket: factory.current ? (pid) => factory.current!(pid) : undefined,
    tickMs,
    onState: setState,
    onMessage: (m) => {
      if (m.type === "snapshot" || m.type === "reading") setSensors((prev) => applyLiveMessage(prev, m));
      cb.current?.(m);
    },
  }), [projectId, setSensors, tickMs]);
  return state;
}
