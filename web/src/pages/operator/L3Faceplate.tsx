import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type ReadingPoint, type Sensor, type WorkOrder } from "../../api/client";
import Dialog from "../../ui/Dialog";
import Trend from "../../ui/Trend";
import { fmtDate, fmtValue } from "../../ui/format";
import { alarmStyle, qualityStyle } from "../../ui/tokens";
import OperatorShell, { opsPath, useOps } from "./OperatorShell";
import ValueCard from "./ValueCard";
import ControlBlock from "./ControlBlock";
import { AREAS, ageSeconds, areaOf, fmtAge, sortByAlarm, unitOf } from "./model";

/** Level 3 — faceplate: bitta sensor (yoki agregat) uchun joriy qiymat, chegaralar (LL/L/H/HH), sifat, yosh,
 * trend (6 soat), alarm rejimi (shelve/OOS — C2), ratsionalizatsiya (C3), bog'liq ish buyruqlari, boshqaruv
 * (yozish mumkin bo'lsa — B2 select→execute, F8 da to'liq). */
export default function L3Faceplate() {
  const { projectId, sensorId, unit } = useParams();
  const pid = Number(projectId);
  return (
    <OperatorShell level={3} crumbs={[{ label: "L1 Umumiy", to: opsPath(pid) }, { label: "L2", to: opsPath(pid, "area", "powerhouse") }, { label: unit ? `Agregat ${unit}` : "Faceplate" }]}>
      {unit ? <UnitBody unit={Number(unit)} /> : <SensorBody sensorId={Number(sensorId)} />}
    </OperatorShell>
  );
}

function UnitBody({ unit }: { unit: number }) {
  const { projectId: pid, sensors } = useOps();
  const mine = useMemo(() => sortByAlarm(sensors.filter((s) => s.enabled && unitOf(s) === unit)), [sensors, unit]);
  const [wos, setWos] = useState<WorkOrder[]>([]);
  useEffect(() => { api.workOrders(pid).then((w) => setWos(w.filter((x) => x.status !== "done" && x.asset_name && new RegExp(`\\b${unit}\\b`).test(x.asset_name)))).catch(() => setWos([])); }, [pid, unit]);
  const p = mine.find((s) => s.kind === "power");
  return (
    <div className="l3">
      <div className="row" style={{ marginBottom: 8 }}><h2 style={{ margin: 0 }}>Agregat {unit}</h2><span className="grow" />{p && <span className="tile-v">{p.last_value == null ? "—" : fmtValue(p.last_value)} <span className="tile-u">{p.unit}</span></span>}</div>
      <section className="panel"><div className="row"><b>Sensorlar</b></div><div className="vgrid">{mine.map((s) => <ValueCard key={s.id} s={s} pid={pid} />)}</div>{mine.length === 0 && <p className="muted">Sensor yo'q</p>}</section>
      <section className="panel">
        <div className="row"><b>Ochiq ish buyruqlari</b><span className="grow" /><Link className="btn sm" to={`/projects/${pid}/dashboard`}>Ish buyruqlari →</Link></div>
        {wos.length === 0 ? <p className="muted">Yo'q</p> : <ul className="small">{wos.map((w) => <li key={w.id}>#{w.id} {w.title} <span className="dim">({w.status}, {w.priority})</span></li>)}</ul>}
      </section>
    </div>
  );
}

function SensorBody({ sensorId }: { sensorId: number }) {
  const { projectId: pid, sensors, reload, project, liveCommand } = useOps();
  const s = sensors.find((x) => x.id === sensorId);
  const [pts, setPts] = useState<ReadingPoint[]>([]);
  const [hours, setHours] = useState(6);
  const [dlg, setDlg] = useState<null | "shelve" | "oos">(null);
  const [reason, setReason] = useState("");
  const [shelveH, setShelveH] = useState(8);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const canOperate = project?.my_role === "operator" || project?.my_role === "engineer" || project?.my_role === "approver";
  const canEngineer = project?.my_role === "engineer" || project?.my_role === "approver";
  const loadTrend = useCallback(() => api.readings(sensorId, hours, 400).then((r) => setPts(r.points)).catch(() => setPts([])), [sensorId, hours]);
  useEffect(() => { void loadTrend(); const t = setInterval(loadTrend, 30_000); return () => clearInterval(t); }, [loadTrend]);
  if (!s) return <p className="muted">Sensor topilmadi (id {sensorId})</p>;
  const st = alarmStyle(s.alarm, s.priority);
  const q = qualityStyle(s.last_quality);
  const age = ageSeconds(s.last_ts);
  const area = AREAS.find((a) => a.id === areaOf(s))!;
  const limits: { label: string; v: number | null | undefined }[] = [
    { label: "HH", v: s.hh_alarm }, { label: "H", v: s.high_alarm }, { label: "L", v: s.low_alarm }, { label: "LL", v: s.ll_alarm },
  ];
  const refLines = limits.filter((l) => l.v != null).map((l) => ({ value: l.v as number, label: l.label }));
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true); setErr("");
    try { await fn(); await reload(); setDlg(null); setReason(""); } catch (e) { setErr(e instanceof Error ? e.message : "Xato"); } finally { setBusy(false); }
  };
  return (
    <div className="l3" data-testid="faceplate">
      <div className="row wrap" style={{ marginBottom: 8, gap: 10 }}>
        <h2 style={{ margin: 0 }}>{s.name}</h2>
        <span className="mono dim">{s.key}</span>
        <Link className="btn sm" to={opsPath(pid, "area", area.id)}>L2 {area.short}</Link>
        {unitOf(s) != null && <Link className="btn sm" to={opsPath(pid, "unit", unitOf(s)!)}>Agregat {unitOf(s)}</Link>}
        <Link className="btn sm" to={opsPath(pid, "diag", s.id)}>L4 Diagnostika</Link>
      </div>
      <div className="l3-grid">
        <section className={`panel fp-value ${st.rank ? "alarm" : ""}`} style={st.rank ? { borderColor: st.color } : undefined}>
          <div className="fp-big">{s.last_value == null ? "—" : fmtValue(s.last_value)} <span className="tile-u">{s.unit}</span></div>
          <div className="row wrap" style={{ gap: 8 }}>
            {st.code ? <span className="alarm-mark" style={{ color: st.color, fontSize: 14 }}>{st.glyph}{st.code} {st.label} · {s.priority}</span> : <span className="badge published">normal</span>}
            <span className="alarm-mark" style={{ color: q.color }} title="sifat">{q.code || "✓"} {q.label}</span>
            <span className={`dim ${age != null && age > s.stale_after_s ? "error" : ""}`}>yosh {fmtAge(age)} {s.last_ts ? `(${fmtDate(s.last_ts)})` : ""}</span>
          </div>
          <table className="grid small" style={{ marginTop: 8 }}>
            <tbody>
              {limits.map((l) => <tr key={l.label}><td>{l.label}</td><td className="mono">{l.v == null ? "—" : `${l.v} ${s.unit}`}</td></tr>)}
              <tr><td>O'lik zona / kechikish</td><td className="mono">{s.deadband ?? 0} · {s.on_delay_s ?? 0}s / {s.off_delay_s ?? 0}s</td></tr>
              {s.roc_limit_per_min != null && <tr><td>ROC chegarasi</td><td className="mono">{s.roc_limit_per_min} /daq</td></tr>}
              <tr><td>Alarm rejimi</td><td>{s.alarm_mode ?? "normal"}{s.alarm_mode_reason ? ` — ${s.alarm_mode_reason}` : ""}{s.alarm_mode_until ? ` (${fmtDate(s.alarm_mode_until)} gacha)` : ""}{s.suppressed ? " · shart bo'yicha bostirilgan" : ""}</td></tr>
            </tbody>
          </table>
          <div className="row wrap" style={{ marginTop: 8, gap: 6 }}>
            {canOperate && s.alarm_mode !== "shelved" && s.alarm_mode !== "out_of_service" && <button className="btn sm" onClick={() => setDlg("shelve")}>Shelve</button>}
            {canOperate && s.alarm_mode === "shelved" && <button className="btn sm" onClick={() => run(() => api.unshelveSensor(s.id))} disabled={busy}>Shelve dan qaytarish</button>}
            {canEngineer && s.alarm_mode !== "out_of_service" && <button className="btn sm" onClick={() => setDlg("oos")}>Xizmatdan chiqarish</button>}
            {canEngineer && s.alarm_mode === "out_of_service" && <button className="btn sm" onClick={() => run(() => api.sensorInService(s.id))} disabled={busy}>Xizmatga qaytarish</button>}
          </div>
          {err && <p className="error">{err}</p>}
        </section>
        {s.writable && <ControlBlock projectId={pid} sensor={s} canCommand={!!canOperate} canOverride={project?.my_role === "approver"} liveCommand={liveCommand} onCommand={() => void reload()} />}
        <section className="panel">
          <div className="row"><b>Trend</b><span className="grow" />{[1, 6, 24, 168].map((h) => <button key={h} className={`btn sm ${hours === h ? "active" : ""}`} onClick={() => setHours(h)}>{h < 24 ? `${h} s` : `${h / 24} k`}</button>)}</div>
          {pts.length ? <Trend series={[{ id: s.id, name: s.name, unit: s.unit, points: pts.map((p) => ({ t: Date.parse(p.ts), v: p.v, min: p.min, max: p.max })) }]} height={200} refLines={refLines} /> : <p className="muted">Ma'lumot yo'q</p>}
        </section>
        <section className="panel">
          <div className="row"><b>Ratsionalizatsiya (ISA-18.2)</b><span className="grow" />{s.rationalized_at ? <span className="badge published">tasdiqlangan</span> : <span className="badge shared">tasdiqlanmagan</span>}</div>
          <dl className="fp-dl">
            <dt>Sabab</dt><dd>{s.cause || <span className="dim">—</span>}</dd>
            <dt>Harakatsizlik oqibati</dt><dd>{s.consequence || <span className="dim">—</span>}</dd>
            <dt>Tuzatuvchi harakat</dt><dd>{s.corrective_action || <span className="dim">—</span>}</dd>
            <dt>Javob vaqti</dt><dd>{s.response_time_s != null ? fmtAge(s.response_time_s) : <span className="dim">—</span>}</dd>
            <dt>Ustuvorlik asosi</dt><dd>{s.priority_basis || <span className="dim">—</span>}</dd>
          </dl>
        </section>
      </div>
      {dlg && (
        <Dialog title={dlg === "shelve" ? `Shelving: ${s.name}` : `Xizmatdan chiqarish: ${s.name}`} onClose={() => setDlg(null)}>
          <label className="field"><span>Sabab (majburiy)</span><input className="input" value={reason} onChange={(e) => setReason(e.target.value)} autoFocus /></label>
          {dlg === "shelve" && <label className="field"><span>Muddat, soat</span><input className="input" type="number" min={0.5} step={0.5} value={shelveH} onChange={(e) => setShelveH(Number(e.target.value) || 8)} /></label>}
          {err && <p className="error">{err}</p>}
          <div className="actions">
            <button className="btn" onClick={() => setDlg(null)}>Bekor</button>
            <button className="btn primary" disabled={busy || reason.trim().length < 3} onClick={() => run(() => (dlg === "shelve" ? api.shelveSensor(s.id, reason.trim(), shelveH) : api.sensorOutOfService(s.id, reason.trim())))}>{dlg === "shelve" ? "Shelve" : "Xizmatdan chiqarish"}</button>
          </div>
        </Dialog>
      )}
    </div>
  );
}
