import { useState } from "react";
import { Link } from "react-router-dom";
import { api, type AlarmEvent, type Sensor } from "../../api/client";
import Dialog from "../../ui/Dialog";
import { fmtDate, fmtValue } from "../../ui/format";
import { alarmStyle } from "../../ui/tokens";
import { opsPath } from "./OperatorShell";
import { fmtAge } from "./model";
import type { AlarmRow } from "./alarms";
import { alarmModeLabel, isaStateLabel, priorityLabel } from "../../i18n/labels";
import { areaTitle } from "./model";

/** Alarm jadvali (F5): ustuvorlik belgisi (shakl + kod), holat, qiymat, ISA-18.2 holati; amallar —
 * kvitlash (Dialog, prompt() emas), shelve/OOS; qator ochilganda ratsionalizatsiya (C3). */
export interface AlarmTableProps {
  rows: AlarmRow[];
  pid: number;
  canOperate: boolean;
  canEngineer: boolean;
  compact?: boolean;
  onChanged: (updated?: AlarmEvent) => void;
  onError?: (msg: string) => void;
}

type Dlg = { kind: "ack" | "shelve" | "oos"; row: AlarmRow } | null;

export default function AlarmTable({ rows, pid, canOperate, canEngineer, compact = false, onChanged, onError }: AlarmTableProps) {
  const [open, setOpen] = useState<number | null>(null);
  const [dlg, setDlg] = useState<Dlg>(null);
  const [text, setText] = useState("");
  const [hours, setHours] = useState(8);
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<AlarmEvent | Sensor | void>) => {
    setBusy(true);
    try {
      const r = await fn();
      onChanged(r && "sensor_id" in (r as AlarmEvent) ? (r as AlarmEvent) : undefined);
      setDlg(null); setText("");
    } catch (e) { onError?.(e instanceof Error ? e.message : "Xato"); } finally { setBusy(false); }
  };
  if (rows.length === 0) return <p className="muted">Alarm yo'q</p>;
  return (
    <>
      <table className={`grid ${compact ? "small" : ""} alarm-table`} data-testid="alarm-table">
        <thead><tr><th className="w-28" /><th>Vaqt</th><th>Sensor</th><th>Holat</th><th>Qiymat</th><th>ISA</th><th /></tr></thead>
        <tbody>
          {rows.map((e) => {
            const st = alarmStyle(e.state, e.priority ?? "medium");
            const s = e.sensor;
            const isOpen = open === e.id;
            return (
              <FragmentRow key={e.id}>
                <tr className={`${!e.ended_at && !e.suppressed ? "alarm-active" : undefined} cursor-pointer`} data-testid="alarm-row" data-priority={e.priority} data-state={e.state} onClick={() => setOpen(isOpen ? null : e.id)}>
                  <td><button type="button" className="row-toggle" aria-expanded={isOpen} aria-label={`${e.sensor_name}: tafsilotlar (ratsionalizatsiya)`} onClick={(ev) => { ev.stopPropagation(); setOpen(isOpen ? null : e.id); }}><span className="alarm-mark" style={{ color: st.color, fontSize: 14 }} title={priorityLabel(e.priority)}>{st.glyph || "·"}</span></button></td>
                  <td className="mono">{fmtDate(e.started_at)}{e.ended_at && <div className="dim">→ {fmtDate(e.ended_at)}</div>}</td>
                  <td><Link to={opsPath(pid, "sensor", e.sensor_id)} onClick={(ev) => ev.stopPropagation()}>{e.sensor_name}</Link><div className="dim">{e.sensor_key}{e.area ? ` · ${areaTitle(e.area)}` : ""}</div></td>
                  <td><span className="alarm-mark" style={{ color: st.color }}>{st.code || "—"}</span> {st.label}{e.suppressed && <span className="badge archived ml-4">{alarmModeLabel(e.suppressed)}</span>}</td>
                  <td className="mono">{e.value == null ? "—" : `${fmtValue(e.value)} ${e.unit}`}</td>
                  <td><span className={`badge ${e.alarm_state === "unack" ? "rejected" : e.alarm_state === "acked" ? "shared" : "archived"}`}>{isaStateLabel(e.alarm_state ?? (e.acked_at ? "acked" : "unack"))}</span></td>
                  <td className="row gap-4" onClick={(ev) => ev.stopPropagation()}>
                    {e.acked_at ? <span className="dim" title={e.comment}>kvitlangan</span> : canOperate ? <button className="btn sm" onClick={() => setDlg({ kind: "ack", row: e })}>Kvitlash</button> : null}
                    {canOperate && s && !e.ended_at && s.alarm_mode === "normal" && <button className="btn sm" onClick={() => setDlg({ kind: "shelve", row: e })}>Shelve</button>}
                    {canOperate && s && s.alarm_mode === "shelved" && <button className="btn sm" onClick={() => run(() => api.unshelveSensor(s.id))} disabled={busy}>Qaytarish</button>}
                    {canEngineer && s && !compact && s.alarm_mode === "normal" && <button className="btn sm" onClick={() => setDlg({ kind: "oos", row: e })}>OOS</button>}
                    {canEngineer && s && s.alarm_mode === "out_of_service" && <button className="btn sm" onClick={() => run(() => api.sensorInService(s.id))} disabled={busy}>Xizmatga</button>}
                  </td>
                </tr>
                {isOpen && (
                  <tr className="alarm-detail" data-testid="alarm-detail">
                    <td />
                    <td colSpan={6}>
                      <dl className="fp-dl">
                        <dt>Sabab</dt><dd>{e.cause || <span className="dim">ratsionalizatsiya qilinmagan</span>}</dd>
                        <dt>Harakatsizlik oqibati</dt><dd>{e.consequence || <span className="dim">—</span>}</dd>
                        <dt>Tuzatuvchi harakat</dt><dd>{e.corrective_action || <span className="dim">—</span>}</dd>
                        <dt>Javob vaqti</dt><dd>{e.response_time_s != null ? fmtAge(e.response_time_s) : <span className="dim">—</span>}</dd>
                        {s?.alarm_mode && s.alarm_mode !== "normal" && <><dt>Rejim</dt><dd>{alarmModeLabel(s.alarm_mode)}{s.alarm_mode_reason ? ` — ${s.alarm_mode_reason}` : ""}{s.alarm_mode_until ? ` (${fmtDate(s.alarm_mode_until)} gacha)` : ""}</dd></>}
                        {e.comment && <><dt>Kvitlash izohi</dt><dd>{e.comment}</dd></>}
                      </dl>
                    </td>
                  </tr>
                )}
              </FragmentRow>
            );
          })}
        </tbody>
      </table>
      {dlg && (
        <Dialog title={dlg.kind === "ack" ? `Kvitlash: ${dlg.row.sensor_name}` : dlg.kind === "shelve" ? `Shelving: ${dlg.row.sensor_name}` : `Xizmatdan chiqarish: ${dlg.row.sensor_name}`} onClose={() => setDlg(null)}>
          <p className="small dim">{alarmStyle(dlg.row.state, dlg.row.priority ?? "medium").label} · {dlg.row.value == null ? "—" : `${fmtValue(dlg.row.value)} ${dlg.row.unit}`} · {fmtDate(dlg.row.started_at)}</p>
          {dlg.row.corrective_action && <p className="small"><b>Tuzatuvchi harakat:</b> {dlg.row.corrective_action}</p>}
          <label className="field"><span>{dlg.kind === "ack" ? "Izoh (ixtiyoriy)" : "Sabab (majburiy)"}</span><input className="input" value={text} onChange={(e) => setText(e.target.value)} data-autofocus data-testid="dlg-text" /></label>
          {dlg.kind === "shelve" && <label className="field"><span>Muddat, soat</span><input className="input" type="number" min={0.5} step={0.5} value={hours} onChange={(e) => setHours(Number(e.target.value) || 8)} /></label>}
          <div className="actions">
            <button className="btn" onClick={() => setDlg(null)}>Bekor</button>
            <button className="btn primary" data-testid="dlg-ok" disabled={busy || (dlg.kind !== "ack" && text.trim().length < 3)} onClick={() => run(() => dlg.kind === "ack" ? api.ackAlarm(dlg.row.id, text.trim()) : dlg.kind === "shelve" ? api.shelveSensor(dlg.row.sensor_id, text.trim(), hours) : api.sensorOutOfService(dlg.row.sensor_id, text.trim()))}>
              {dlg.kind === "ack" ? "Kvitlash" : dlg.kind === "shelve" ? "Shelve" : "Xizmatdan chiqarish"}
            </button>
          </div>
        </Dialog>
      )}
    </>
  );
}

function FragmentRow({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
