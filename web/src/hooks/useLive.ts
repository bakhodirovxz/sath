import { useEffect, useRef, useState } from "react";
import { api, type LiveMessage, type Sensor } from "../api/client";

export type LiveState = "ulanmoqda" | "jonli" | "uzildi";

/** Loyiha jonli oqimi (WebSocket): sensor holatlarini yangilab turadi, alarm hodisalarini
 * chaqiruvchiga beradi; uzilsa 3 s dan keyin qayta ulanadi. */
export function useLive(
  projectId: number,
  setSensors: React.Dispatch<React.SetStateAction<Sensor[]>>,
  onMessage?: (m: LiveMessage) => void,
): LiveState {
  const [state, setState] = useState<LiveState>("ulanmoqda");
  const cb = useRef(onMessage);
  cb.current = onMessage;
  useEffect(() => {
    let closed = false;
    let timer: number | undefined;
    let ws: WebSocket | null = null;
    const connect = () => {
      ws = api.liveSocket(projectId);
      ws.onopen = () => setState("jonli");
      ws.onmessage = (ev) => {
        const m = JSON.parse(ev.data) as LiveMessage;
        if (m.type === "snapshot" && m.sensors) {
          setSensors((prev) => prev.map((s) => { const u = m.sensors!.find((x) => x.sensor_id === s.id); return u ? { ...s, last_value: u.value, last_ts: u.ts, alarm: u.alarm } : s; }));
        } else if (m.type === "reading" && m.sensor_id != null) {
          setSensors((prev) => prev.map((s) => (s.id === m.sensor_id ? { ...s, last_value: m.value ?? null, last_ts: m.ts ?? null, alarm: m.alarm ?? s.alarm } : s)));
        }
        cb.current?.(m);
      };
      ws.onclose = () => { setState("uzildi"); if (!closed) timer = window.setTimeout(connect, 3000); };
      ws.onerror = () => ws?.close();
    };
    connect();
    return () => { closed = true; window.clearTimeout(timer); ws?.close(); };
  }, [projectId, setSensors]);
  return state;
}
