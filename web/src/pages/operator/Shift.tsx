import { useCallback, useState } from "react";
import { usePolling } from "../../hooks/usePolling";
import { Link, useParams } from "react-router-dom";
import { api, type ShiftHandover, type ShiftSnapshot, type SoeEvent } from "../../api/client";
import Dialog from "../../ui/Dialog";
import { fmtDate, fmtValue } from "../../ui/format";
import { alarmStyle } from "../../ui/tokens";
import OperatorShell, { opsPath, useOps } from "./OperatorShell";
import { alarmModeLabel, commandStatusLabel } from "../../i18n/labels";
import { can } from "../../api/permissions";

/** Smena jurnali va navbat topshirish (F9): tuzilgan varaqa (faol alarmlar, ochiq ish buyruqlari, blokirovka
 * chetlab o'tishlari, shelved/OOS/o'chirilgan nuqtalar, kutilayotgan buyruqlar, aloqasiz sensorlar — avtomatik),
 * topshiruvchi va qabul qiluvchi imzosi (audit), smena hodisalari tasmasi (alarm, buyruq, izoh, SOE). */
export default function Shift() {
  const { projectId } = useParams();
  const pid = Number(projectId);
  return (
    <OperatorShell level={2} crumbs={[{ label: "L1 Umumiy", to: opsPath(pid) }, { label: "Smena" }]}>
      <Body />
    </OperatorShell>
  );
}

function Body() {
  const { projectId: pid, project } = useOps();
  const [snap, setSnap] = useState<ShiftSnapshot | null>(null);
  const [handovers, setHandovers] = useState<ShiftHandover[]>([]);
  const [feed, setFeed] = useState<SoeEvent[]>([]);
  const [notes, setNotes] = useState("");
  const [ack, setAck] = useState(false);
  const [dlg, setDlg] = useState<null | "hand" | "receive">(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const canOperate = can(project?.my_role, "scada.ack"); // smena topshirish/qabul (server: operator+)
  const load = useCallback(async () => {
    try {
      const [s, h, f] = await Promise.all([api.shiftSnapshot(pid), api.shiftHandovers(pid), api.shiftFeed(pid, 12)]);
      setSnap(s); setHandovers(h); setFeed(f); setErr("");
    } catch (e) { setErr(e instanceof Error ? e.message : "Xato"); }
  }, [pid]);
  usePolling(load, 30_000, String(pid));
  const open = handovers.find((h) => h.status === "handed") ?? null;
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true); setErr("");
    try { await fn(); setDlg(null); setNotes(""); setAck(false); await load(); } catch (e) { setErr(e instanceof Error ? e.message : "Xato"); } finally { setBusy(false); }
  };
  return (
    <div className="shift-page">
      {open && <div className="verdict warn" data-testid="handover-open">Smena topshirish #{open.id} ({open.handed_by_username}, {fmtDate(open.handed_at!)}) hali <b>qabul qilinmagan</b> — qabul qiluvchi imzolashi kerak.</div>}
      <div className="l3-grid">
        <section className="panel" data-testid="shift-snapshot">
          <div className="row"><b>Topshirish varaqasi</b><span className="dim small">{snap ? `smena boshi ${fmtDate(snap.since)}` : ""}</span></div>
          {snap ? (
            <>
              {snap.warnings.length > 0 ? <ul className="small error pl-16" data-testid="shift-warnings">{snap.warnings.map((w) => <li key={w}>{w}</li>)}</ul> : <p className="small c-ok">Yakunlanmagan ishlar yo'q</p>}
              <Section title={`Faol alarmlar (${snap.alarms.length}, ${snap.unacked} kvitlanmagan)`}>
                {snap.alarms.map((a) => { const st = alarmStyle(a.state, a.priority); return <li key={a.event_id}><span className="alarm-mark" style={{ color: st.color }}>{st.glyph}{st.code}</span> <Link to={opsPath(pid, "sensor", a.sensor_id)}>{a.name}</Link> {a.value != null ? `${fmtValue(a.value)}` : ""} · {fmtDate(a.started_at)} {a.acked ? <span className="dim">kvitlangan</span> : <span className="badge rejected">UNACK</span>}</li>; })}
              </Section>
              <Section title={`Ochiq ish buyruqlari (${snap.work_orders.length})`}>
                {snap.work_orders.map((w) => <li key={w.id}>#{w.id} {w.title} <span className="dim">({w.status}, {w.priority})</span>{w.overdue && <span className="badge rejected ml-4">muddati o'tgan</span>}</li>)}
              </Section>
              <Section title={`Blokirovka chetlab o'tishlari (${snap.interlock_overrides.length})`}>
                {snap.interlock_overrides.map((o, i) => <li key={i}>{fmtDate(o.at)} · {detailText(o.detail)}</li>)}
              </Section>
              <Section title={`Shelved / OOS / o'chirilgan nuqtalar (${snap.alarm_modes.length})`}>
                {snap.alarm_modes.map((m) => <li key={`${m.sensor_id}-${m.mode}`}><Link to={opsPath(pid, "sensor", m.sensor_id)}>{m.name}</Link> — {alarmModeLabel(m.mode)}{m.reason ? ` (${m.reason})` : ""}{m.until ? ` ${fmtDate(m.until)} gacha` : ""}</li>)}
              </Section>
              <Section title={`Kutilayotgan buyruqlar (${snap.pending_commands.length})`}>
                {snap.pending_commands.map((c) => <li key={c.id}>#{c.id} {c.sensor_key} → {fmtValue(c.value)} <span className="badge open">{commandStatusLabel(c.status)}</span> {fmtDate(c.created_at)}</li>)}
              </Section>
              <Section title={`Aloqasiz sensorlar (${snap.stale_sensors.length})`}>
                {snap.stale_sensors.map((s) => <li key={s.sensor_id}><Link to={opsPath(pid, "sensor", s.sensor_id)}>{s.name}</Link> <span className="dim mono">{s.key}</span></li>)}
              </Section>
              {canOperate && !open && <button className="btn primary mt-8" onClick={() => setDlg("hand")} data-testid="handover-btn">Smenani topshirish (imzo)</button>}
              {canOperate && open && <button className="btn primary mt-8" onClick={() => setDlg("receive")} data-testid="receive-btn">Smenani qabul qilish (imzo)</button>}
            </>
          ) : <p className="muted">Yuklanmoqda…</p>}
          {err && <p className="error">{err}</p>}
        </section>
        <section className="panel">
          <div className="row"><b>Topshirishlar tarixi</b></div>
          {handovers.length === 0 ? <p className="muted">Yo'q</p> : (
            <table className="grid small"><thead><tr><th>#</th><th>Topshirdi</th><th>Qabul qildi</th><th>Ogohlantirish</th><th>Izoh</th></tr></thead><tbody>
              {handovers.map((h) => <tr key={h.id}><td>{h.id}</td><td>{h.handed_by_username}<div className="dim mono">{fmtDate(h.handed_at!)}</div></td><td>{h.received_by_username ?? <span className="badge shared">kutilmoqda</span>}{h.received_at && <div className="dim mono">{fmtDate(h.received_at)}</div>}</td><td className="small">{h.warnings.length ? h.warnings.join("; ") : <span className="dim">—</span>}</td><td className="small">{h.notes}{h.receive_notes && <div className="dim">qabul: {h.receive_notes}</div>}</td></tr>)}
            </tbody></table>
          )}
        </section>
        <section className="panel">
          <div className="row"><b>Smena hodisalari (12 soat)</b><span className="dim small">alarm · buyruq · izoh · SOE</span></div>
          <table className="grid small mono"><tbody>
            {feed.slice(0, 200).map((r) => <tr key={`${r.type}-${r.id}`} className={r.type === "alarm" ? "alarm-active" : undefined}><td>{fmtDate(r.ts)}</td><td><span className="badge open">{r.type}</span></td><td>{r.point}</td><td>{r.state}</td></tr>)}
            {feed.length === 0 && <tr><td colSpan={4} className="muted">Hodisa yo'q</td></tr>}
          </tbody></table>
        </section>
      </div>
      {dlg && snap && (
        <Dialog title={dlg === "hand" ? "Smenani topshirish" : `Smenani qabul qilish (#${open?.id})`} onClose={() => setDlg(null)}>
          {dlg === "hand" && snap.warnings.length > 0 && (
            <div className="verdict warn"><b>Yakunlanmagan ishlar:</b><ul className="my-4 mx-0 pl-16">{snap.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
              <label className="row gap-6"><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} data-testid="ack-warn" /> Ko'rib chiqdim, qabul qiluvchiga yetkazaman</label>
            </div>
          )}
          {dlg === "receive" && open && <p className="small">Topshiruvchi: <b>{open.handed_by_username}</b>, {fmtDate(open.handed_at!)}. Izoh: {open.notes || "—"}{open.warnings.length ? <><br />Ogohlantirishlar: {open.warnings.join("; ")}</> : null}</p>}
          <label className="field"><span>Izoh</span><textarea className="textarea" value={notes} onChange={(e) => setNotes(e.target.value)} data-autofocus data-testid="handover-notes" /></label>
          {err && <p className="error">{err}</p>}
          <div className="actions">
            <button className="btn" onClick={() => setDlg(null)}>Bekor</button>
            <button className="btn primary" data-testid="handover-ok" disabled={busy || (dlg === "hand" && snap.warnings.length > 0 && !ack)} onClick={() => run(() => (dlg === "hand" ? api.shiftHandover(pid, notes, ack) : api.shiftReceive(open!.id, notes)))}>{dlg === "hand" ? "Imzolab topshirish" : "Imzolab qabul qilish"}</button>
          </div>
        </Dialog>
      )}
    </div>
  );
}

/** Audit tafsiloti (blokirovka chetlab o'tish) — xom JSON o'rniga «kalit: qiymat» ro'yxati. */
function detailText(d: Record<string, unknown>): string {
  return Object.entries(d).filter(([, v]) => v != null && v !== "").map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`).join(" · ") || "—";
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const arr = Array.isArray(children) ? children : [children];
  return (
    <details open={arr.filter(Boolean).length > 0} className="mt-6">
      <summary className="small"><b>{title}</b></summary>
      <ul className="small pl-16 my-4 mx-0">{arr.filter(Boolean).length ? children : <li className="dim">yo'q</li>}</ul>
    </details>
  );
}
