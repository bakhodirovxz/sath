import { useState } from "react";
import { api, type AlarmEvent, type Sensor } from "../../api/client";
import Dialog from "../../ui/Dialog";
import { fmtDate, fmtValue } from "../../ui/format";
import { alarmStyle } from "../../ui/tokens";

export type AlarmAction = "ack" | "shelve" | "oos";

/** Alarm ustida amal (kvitlash / shelving / xizmatdan chiqarish) — sahifa ichidagi dialog (prompt() emas):
 * alarm jadvali va har sahifadagi alarm banneri (UX-03) shuni ishlatadi. Kvitlash izohi ixtiyoriy, boshqalari —
 * sabab majburiy (≥ 3 belgi, audit). */
export default function AlarmActionDialog({ kind, event, onDone, onClose, onError }: {
  kind: AlarmAction;
  event: Pick<AlarmEvent, "id" | "sensor_id" | "sensor_name" | "state" | "priority" | "value" | "unit" | "started_at"> & { corrective_action?: string | null };
  onDone: (updated?: AlarmEvent) => void;
  onClose: () => void;
  onError?: (msg: string) => void;
}) {
  const [text, setText] = useState("");
  const [hours, setHours] = useState(8);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const run = async () => {
    setBusy(true); setErr("");
    try {
      const r: AlarmEvent | Sensor = kind === "ack" ? await api.ackAlarm(event.id, text.trim()) : kind === "shelve" ? await api.shelveSensor(event.sensor_id, text.trim(), hours) : await api.sensorOutOfService(event.sensor_id, text.trim());
      onDone("sensor_id" in r ? r : undefined);
    } catch (e) {
      const m = e instanceof Error ? e.message : "Xato";
      setErr(m);
      onError?.(m);
    } finally { setBusy(false); }
  };
  const title = kind === "ack" ? `Kvitlash: ${event.sensor_name}` : kind === "shelve" ? `Shelving: ${event.sensor_name}` : `Xizmatdan chiqarish: ${event.sensor_name}`;
  return (
    <Dialog title={title} onClose={onClose}>
      <p className="small dim">{alarmStyle(event.state, event.priority ?? "medium").label} · {event.value == null ? "—" : `${fmtValue(event.value)} ${event.unit}`} · {fmtDate(event.started_at)}</p>
      {event.corrective_action && <p className="small"><b>Tuzatuvchi harakat:</b> {event.corrective_action}</p>}
      <label className="field"><span>{kind === "ack" ? "Izoh (ixtiyoriy)" : "Sabab (majburiy)"}</span><input className="input" value={text} onChange={(e) => setText(e.target.value)} data-autofocus data-testid="dlg-text" /></label>
      {kind === "shelve" && <label className="field"><span>Muddat, soat</span><input className="input" type="number" min={0.5} step={0.5} value={hours} onChange={(e) => setHours(Number(e.target.value) || 8)} /></label>}
      {err && <p className="error small" role="alert">{err}</p>}
      <div className="actions">
        <button className="btn" onClick={onClose}>Bekor</button>
        <button className="btn primary" data-testid="dlg-ok" disabled={busy || (kind !== "ack" && text.trim().length < 3)} onClick={() => void run()}>
          {kind === "ack" ? "Kvitlash" : kind === "shelve" ? "Shelve" : "Xizmatdan chiqarish"}
        </button>
      </div>
    </Dialog>
  );
}
