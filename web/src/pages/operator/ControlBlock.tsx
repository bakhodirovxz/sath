import { useCallback, useEffect, useState } from "react";
import { usePolling } from "../../hooks/usePolling";
import { api, type Command, type Interlock, type SelectResult, type Sensor } from "../../api/client";
import { fmtDate, fmtValue } from "../../ui/format";
import { useLiveMessages } from "../../store/live";

/** Boshqaruv bloki (F8, faceplate ichida): joriy qiymat, ruxsat etilgan diapazon (B1), kiritish validatsiyasi,
 * sabab maydoni, blokirovkalar (B4) natijasi oldindan, select → execute (B2) qolgan vaqt bilan, ikkinchi kishi
 * tasdig'i kutish holati, buyruq holati kuzatuvi: pending → sent → acked → readback / mismatch. */

export interface SetpointCheck { ok: boolean; reason?: string }

/** Klient tomonidagi tekshiruv (server B1 ham rad etadi): chekli son, min/max, tezlik chegarasi (ogohlantirish). */
export function validateSetpoint(s: Pick<Sensor, "min_setpoint" | "max_setpoint" | "max_rate_per_min" | "last_value" | "unit">, raw: string): SetpointCheck & { warn?: string } {
  if (raw.trim() === "") return { ok: false, reason: "qiymat kiritilmagan" };
  const v = Number(raw);
  if (!Number.isFinite(v)) return { ok: false, reason: "chekli son emas" };
  if (s.min_setpoint != null && v < s.min_setpoint) return { ok: false, reason: `ruxsat etilgan minimum ${s.min_setpoint} ${s.unit}` };
  if (s.max_setpoint != null && v > s.max_setpoint) return { ok: false, reason: `ruxsat etilgan maksimum ${s.max_setpoint} ${s.unit}` };
  if (s.max_rate_per_min != null && s.last_value != null && Math.abs(v - s.last_value) > s.max_rate_per_min) {
    return { ok: true, warn: `o'zgarish ${fmtValue(Math.abs(v - s.last_value))} ${s.unit} > tezlik chegarasi ${s.max_rate_per_min}/daq — server pog'onali yoki rad etishi mumkin` };
  }
  return { ok: true };
}

export const CMD_LABEL: Record<string, string> = { pending: "navbatda", sent: "yuborildi", acked: "bajarildi", failed: "xato", cancelled: "bekor", expired: "muddati o'tdi", pending_approval: "tasdiq kutilmoqda", mismatch: "readback mos emas", unknown: "natija noma'lum" };
export const CMD_CLASS: Record<string, string> = { pending: "open", sent: "shared", acked: "published", failed: "rejected", cancelled: "archived", expired: "archived", pending_approval: "high", mismatch: "rejected", unknown: "high" };

export default function ControlBlock({ projectId, sensor, canCommand, canOverride = false, liveCommand, onCommand }: { projectId: number; sensor: Sensor; canCommand: boolean; canOverride?: boolean; liveCommand?: Command | null; onCommand?: (c: Command) => void }) {
  const [value, setValue] = useState(sensor.last_value == null ? "" : String(sensor.last_value));
  const [note, setNote] = useState("");
  const [sel, setSel] = useState<SelectResult | null>(null);
  const [left, setLeft] = useState(0);
  const [err, setErr] = useState("");
  const [ovReason, setOvReason] = useState("");
  const [interlocks, setInterlocks] = useState<Interlock[]>([]);
  const [last, setLast] = useState<Command | null>(null);
  const check = validateSetpoint(sensor, value);
  const loadInterlocks = useCallback(() => api.interlocks(projectId).then((all) => setInterlocks(all.filter((i) => i.sensor_id === sensor.id && i.enabled))).catch(() => setInterlocks([])), [projectId, sensor.id]);
  usePolling(loadInterlocks, 15_000, `${projectId}:${sensor.id}`);
  useEffect(() => { api.commands(projectId).then((cs) => setLast(cs.find((c) => c.sensor_id === sensor.id) ?? null)).catch(() => undefined); }, [projectId, sensor.id]);
  useEffect(() => { if (liveCommand && liveCommand.sensor_id === sensor.id) setLast(liveCommand); }, [liveCommand, sensor.id]);
  // Buyruq holati (pending → sent → acked) — umumiy jonli oqimdan (UX-11), alohida soket yo'q
  useLiveMessages(projectId, (m) => { if (m.type === "command" && m.command && m.command.sensor_id === sensor.id) setLast(m.command); });
  useEffect(() => {
    if (!sel) return;
    const tick = () => { const s = Math.max(0, Math.round((new Date(sel.expires_at).getTime() - Date.now()) / 1000)); setLeft(s); if (s <= 0) setSel(null); };
    tick();
    const id = window.setInterval(tick, 500);
    return () => window.clearInterval(id);
  }, [sel]);
  const blocked = interlocks.filter((i) => i.current_ok === false);
  const select = async (override?: { reason: string }) => {
    setErr("");
    try { setSel(await api.selectCommand(projectId, sensor.id, Number(value), note, override)); } catch (e) { setErr(e instanceof Error ? e.message : "Xato"); }
  };
  const execute = async () => {
    if (!sel) return;
    try {
      const c = await api.executeCommand(projectId, sel.select_token, note);
      setLast(c); onCommand?.(c); setSel(null); setNote(""); setErr("");
    } catch (e) { setErr(e instanceof Error ? e.message : "Xato"); setSel(null); }
  };
  const cancel = async () => { if (last) try { const u = await api.cancelCommand(last.id); setLast(u); } catch (e) { setErr(e instanceof Error ? e.message : "Xato"); } };
  if (!sensor.writable) return null;
  return (
    <section className="panel control-block" data-testid="control-block">
      <div className="row"><b>Boshqaruv</b><span className="dim small">select → execute · audit</span></div>
      <table className="grid small" style={{ margin: "6px 0" }}><tbody>
        <tr><td>Joriy qiymat</td><td className="mono">{sensor.last_value == null ? "—" : fmtValue(sensor.last_value)} {sensor.unit}</td></tr>
        <tr><td>Ruxsat etilgan diapazon</td><td className="mono">{sensor.min_setpoint ?? "−∞"} … {sensor.max_setpoint ?? "+∞"} {sensor.unit}{sensor.max_rate_per_min != null ? ` · ≤ ${sensor.max_rate_per_min}/daq` : ""}</td></tr>
        {sensor.requires_dual_approval && <tr><td>Tasdiq</td><td>ikki kishi qoidasi (muallif o'zini tasdiqlay olmaydi)</td></tr>}
      </tbody></table>
      {interlocks.length > 0 && (
        <ul className="small" style={{ margin: "4px 0", paddingLeft: 16 }} data-testid="interlocks">
          {interlocks.map((i) => <li key={i.id} style={{ color: i.current_ok === false ? "var(--danger)" : i.current_ok ? "var(--ok)" : "var(--text-muted)" }}>{i.current_ok === false ? "✗" : i.current_ok ? "✓" : "?"} {i.name}: <span className="mono">{i.condition}</span>{i.current_ok === false && i.current_message ? ` — ${i.current_message}` : ""}</li>)}
        </ul>
      )}
      {canCommand ? (
        <>
          <div className="row" style={{ gap: 6 }}>
            <label className="field grow"><span>Yangi qiymat, {sensor.unit}</span><input className="input" type="number" step="any" min={sensor.min_setpoint ?? undefined} max={sensor.max_setpoint ?? undefined} value={value} onChange={(e) => { setValue(e.target.value); setSel(null); }} disabled={!!sel} data-testid="ctl-value" /></label>
            <label className="field grow"><span>Sabab</span><input className="input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="dispetcher ko'rsatmasi, rejim…" data-testid="ctl-note" /></label>
          </div>
          {!check.ok && value !== "" && <p className="error small" data-testid="ctl-invalid">Rad: {check.reason} (server ham rad etadi)</p>}
          {check.ok && check.warn && <p className="small" style={{ color: "var(--warn)" }}>{check.warn}</p>}
          {blocked.length > 0 && !sel && <p className="error small">Blokirovka: {blocked.map((b) => b.name).join(", ")} — buyruq rad etiladi{canOverride ? " (smena boshlig'i sabab bilan chetlab o'ta oladi)" : ""}</p>}
          {sel && <p className="small" style={{ color: "var(--warn)" }} data-testid="ctl-selected">Tanlandi: {fmtValue(sel.value)} {sensor.unit}. Bajarish uchun <b>{left} s</b> qoldi{sel.requires_approval ? " · ikkinchi operator tasdig'i talab qilinadi" : ""}{sel.override ? " · blokirovka chetlab o'tildi" : ""}</p>}
          {sel?.interlocks && sel.interlocks.length > 0 && <ul className="small" style={{ margin: "4px 0", paddingLeft: 16 }}>{sel.interlocks.map((il) => <li key={il.interlock_id} style={{ color: il.ok ? "var(--ok)" : "var(--danger)" }}>{il.ok ? "✓" : "✗"} {il.name}{il.message ? ` — ${il.message}` : ""}</li>)}</ul>}
          {err && <p className="error small">{err}</p>}
          {err && /[Bb]lokirovka/.test(err) && canOverride && !sel && <div className="row" style={{ gap: 6 }}><input className="input" placeholder="Chetlab o'tish sababi (majburiy)" value={ovReason} onChange={(e) => setOvReason(e.target.value)} /><button className="btn sm danger" disabled={ovReason.trim().length < 3} onClick={() => void select({ reason: ovReason.trim() })}>Chetlab o'tish</button></div>}
          <div className="row" style={{ gap: 6 }}>
            {!sel
              ? <button className="btn" disabled={!check.ok || note.trim().length < 2} title={note.trim().length < 2 ? "Sabab majburiy" : undefined} onClick={() => void select()} data-testid="ctl-select">1. Tanlash</button>
              : <><button className="btn primary" onClick={() => void execute()} data-testid="ctl-execute">2. Bajarish ({left} s)</button><button className="btn" onClick={() => setSel(null)}>Bekor</button></>}
          </div>
        </>
      ) : <p className="muted small">Boshqaruv — faqat dispetcher va smena boshlig'i (loyihalash rollari buyruq bermaydi)</p>}
      {last?.status === "unknown" && (
        <div className="verdict bad" role="alert" data-testid="ctl-unknown">
          <b>Buyruq #{last.id} natijasi noma'lum</b> — gateway tasdiq bermadi (nazorat taymeri). Jihoz holatini joyida yoki qayta o'qish bilan tekshiring; tekshirmasdan buyruqni takrorlamang.
        </div>
      )}
      {last && (
        <div className="small" style={{ marginTop: 6 }} data-testid="ctl-status">
          <b>Oxirgi buyruq:</b> {fmtValue(last.value)} {last.unit} · <span className={`badge ${CMD_CLASS[last.status] ?? ""}`}>{CMD_LABEL[last.status] ?? last.status}</span> · {last.author_username} · {fmtDate(last.created_at)}
          <div className="dim">
            {(["pending", "sent", "acked"] as const).map((st, i) => <span key={st} style={{ marginRight: 6 }}>{i ? "→ " : ""}<span className={["pending", "sent", "acked"].indexOf(last.status) >= i || last.status === "mismatch" ? "" : "dim"}>{CMD_LABEL[st]}</span></span>)}
            → {last.readback_value != null ? `readback ${fmtValue(last.readback_value)} ${last.unit}${last.status === "mismatch" ? " ✗" : " ✓"}` : "readback kutilmoqda"}
            {last.result && <div>{last.result}</div>}
            {last.status === "pending_approval" && <div style={{ color: "var(--warn)" }}>Ikkinchi operator tasdig'i kutilmoqda — dispetcherlarga bildirishnoma yuborildi</div>}
          </div>
          {(last.status === "pending" || last.status === "pending_approval") && canCommand && <button className="btn sm" onClick={() => void cancel()}>Bekor qilish</button>}
        </div>
      )}
    </section>
  );
}
