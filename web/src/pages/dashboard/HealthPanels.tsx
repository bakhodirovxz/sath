import { useEffect, useState } from "react";
import { api, type AssetHealth, type DispatchResult, type FloodForecast, type HealthReport, type Member, type PartMovement, type Sensor, type SparePart, type TwinState, type WorkOrder, type WorkOrderKpi } from "../../api/client";
import LineChart, { CHART_COLORS } from "../../ui/LineChart";
import Icon from "../../ui/Icon";
import Dialog from "../../ui/Dialog";
import { fmtDate, fmtValue } from "../../ui/format";

/* Holat monitoringi (sog'liq indeksi, ISO 20816-5 zonalari, RUL, kavitatsiya) va «nima bo'lsa» sinovi + optimal rejim. */

const LEVEL_CLS: Record<string, string> = { yaxshi: "published", qoniqarli: "shared", yomon: "high", kritik: "rejected" };
const ZONE_CLS: Record<string, string> = { A: "published", B: "published", C: "high", D: "rejected" };

export function HealthPanel({ projectId, sensors, canEdit, canOperate }: { projectId: number; sensors: Sensor[]; canEdit: boolean; canOperate?: boolean }) {
  const [rep, setRep] = useState<HealthReport | null>(null);
  const [err, setErr] = useState("");
  const [cfgFor, setCfgFor] = useState<AssetHealth | null>(null);
  const load = () => api.health(projectId).then(setRep).catch((e) => setErr(e.message));
  useEffect(() => { void load(); const id = window.setInterval(load, 30000); return () => window.clearInterval(id); }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!rep) return <p className="muted">{err || "Yuklanmoqda…"}</p>;
  return (
    <div className="dash-block">
      <div className="row" style={{ alignItems: "center" }}>
        <b>Holat monitoringi</b>
        <span className="muted small">sog'liq indeksi · tebranish (ISO 20816-5) · podshipnik harorati · FIK trendi · anomaliya · kavitatsiya (Toma σ)</span>
        <span className="grow" />
        {rep.plant_score != null && <span className={`badge ${LEVEL_CLS[lvl(rep.plant_score)]}`}>Stansiya: {rep.plant_score} / 100</span>}
        {canEdit && <button className="btn sm" onClick={() => api.healthRun(projectId).then(setRep).catch((e) => setErr(e.message))}>Hozir hisoblash</button>}
      </div>
      {err && <p className="error small">{err}</p>}
      {rep.assets.length === 0 && <p className="muted">Aktivlar yo'q — «Aktivlar» bo'limida agregat qo'shing va sensorlarni bog'lang.</p>}
      <div className="health-cards">
        {rep.assets.map((a) => (
          <div key={a.asset_id} className={`health-card ${a.level}`}>
            <div className="row" style={{ alignItems: "center" }}>
              <b>{a.name}</b>
              <span className={`badge ${LEVEL_CLS[a.level]}`}>{a.level}</span>
              <span className="grow" />
              <span className="health-score">{a.score}</span>
              {(canOperate || canEdit) && a.problems.length > 0 && <button className="btn sm" title="Ish buyrug'i yaratish (muammolardan)" onClick={() => api.createWorkOrder(projectId, { title: `${a.name}: ${a.problems[0].slice(0, 120)}`, description: a.problems.join("; ") + (a.tips.length ? " | Tavsiya: " + a.tips.join("; ") : ""), asset_id: a.asset_id, priority: a.level === "kritik" ? "critical" : a.level === "yomon" ? "high" : "medium", source: "health" }).then(() => setErr("Ish buyrug'i yaratildi (Ish buyruqlari bo'limi)")).catch((e) => setErr(e.message))}><Icon name="wrench" size={12} /></button>}
              {canEdit && <button className="btn sm" title="Sensorlar va parametrlar" onClick={() => setCfgFor(a)}><Icon name="settings" size={12} /></button>}
            </div>
            <div className="health-bar"><i style={{ width: `${a.score}%` }} /></div>
            <div className="health-grid small">
              <div><span className="dim">Tebranish</span>{a.vibration ? (a.vibration.value == null ? <span className="dim">aloqa yo'q</span> : <><b>{fmtValue(a.vibration.value)} {a.vibration.unit}</b> <span className={`badge ${ZONE_CLS[a.vibration.zone ?? "A"]}`}>{a.vibration.zone} zona</span>{a.vibration.days_to_d != null && <div className="dim">D zonagacha ≈ {a.vibration.days_to_d} kun</div>}{a.vibration.anomaly && <div className="error">anomaliya z={a.vibration.z}</div>}</>) : <span className="dim">sensor bog'lanmagan</span>}</div>
              <div><span className="dim">Podshipnik harorati</span>{a.bearing_temp ? (a.bearing_temp.value == null ? <span className="dim">aloqa yo'q</span> : <><b>{fmtValue(a.bearing_temp.value)} °C</b> <span className="dim">/ {a.bearing_temp.warn}–{a.bearing_temp.alarm}</span>{a.bearing_temp.days_to_alarm != null && <div className="dim">alarmgacha ≈ {a.bearing_temp.days_to_alarm} kun</div>}{a.bearing_temp.anomaly && <div className="error">anomaliya</div>}</>) : <span className="dim">sensor bog'lanmagan</span>}</div>
              <div><span className="dim">FIK (egizak)</span>{a.efficiency ? <><b>{a.efficiency.measured != null ? `${(a.efficiency.measured * 100).toFixed(1)} %` : "—"}</b> <span className="dim">/ model {a.efficiency.expected != null ? `${(a.efficiency.expected * 100).toFixed(1)} %` : "—"}</span>{a.efficiency.deviation_pct != null && <div className={a.efficiency.deviation_pct < -5 ? "error" : "dim"}>og'ish {a.efficiency.deviation_pct > 0 ? "+" : ""}{a.efficiency.deviation_pct} %</div>}{a.efficiency.trend_pct_per_month != null && <div className="dim">trend {a.efficiency.trend_pct_per_month} %/oy</div>}</> : <span className="dim">egizak ma'lumoti yo'q</span>}</div>
              {a.electrical && <div><span className="dim">Transformator (IEC 60076-7)</span><b>K {a.electrical.load_factor}</b> <span className="dim">· moy {a.electrical.top_oil_c} °C · issiq nuqta {a.electrical.hot_spot_c} °C</span><div className={a.electrical.aging_rate > 1 ? "error" : "dim"}>qarish {a.electrical.aging_rate}×</div></div>}
              <div><span className="dim">Kavitatsiya (Toma)</span>{a.cavitation ? <><b>σ {a.cavitation.sigma_plant}</b> <span className="dim">/ σ_kr {a.cavitation.sigma_critical}</span><div className={a.cavitation.margin < 0 ? "error" : "dim"}>zaxira {a.cavitation.margin > 0 ? "+" : ""}{a.cavitation.margin} · n_s {a.cavitation.ns}</div></> : <span className="dim">rpm/runner belgisi kiritilmagan</span>}</div>
            </div>
            {a.problems.length > 0 && <ul className="health-problems small">{a.problems.map((p, i) => <li key={i}><Icon name="alert-triangle" size={11} /> {p}</li>)}</ul>}
            {a.tips.length > 0 && <div className="dim small"><Icon name="wrench" size={11} /> {a.tips.join(" · ")}</div>}
          </div>
        ))}
      </div>
      {cfgFor && <AssetConfigDialog asset={cfgFor} sensors={sensors} onClose={() => setCfgFor(null)} onSaved={() => { setCfgFor(null); void load(); }} />}
    </div>
  );
}

function lvl(score: number) { return score >= 80 ? "yaxshi" : score >= 60 ? "qoniqarli" : score >= 40 ? "yomon" : "kritik"; }

function AssetConfigDialog({ asset, sensors, onClose, onSaved }: { asset: AssetHealth; sensors: Sensor[]; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({
    vibration_sensor_id: String(asset.vibration?.sensor_id ?? ""),
    bearing_temp_sensor_id: String(asset.bearing_temp?.sensor_id ?? ""),
    machine_group: String(asset.machine_group ?? 4),
    temp_warn: String(asset.bearing_temp?.warn ?? 70),
    temp_alarm: String(asset.bearing_temp?.alarm ?? 80),
    rated_speed_rpm: "",
    runner_elev_m: "",
    turbine_type: "Francis",
    rated_mva: "",
    cos_phi: "0.9",
    ambient_c: "30",
    cooling: "ONAF",
  });
  const [err, setErr] = useState("");
  const vib = sensors.filter((s) => s.kind === "vibration");
  const tmp = sensors.filter((s) => s.kind === "temperature");
  const save = () => {
    const cfg: Record<string, unknown> = {
      vibration_sensor_id: f.vibration_sensor_id ? Number(f.vibration_sensor_id) : null,
      bearing_temp_sensor_id: f.bearing_temp_sensor_id ? Number(f.bearing_temp_sensor_id) : null,
      machine_group: Number(f.machine_group),
      temp_warn: Number(f.temp_warn),
      temp_alarm: Number(f.temp_alarm),
      turbine_type: f.turbine_type,
    };
    if (f.rated_speed_rpm) cfg.rated_speed_rpm = Number(f.rated_speed_rpm);
    if (f.runner_elev_m) cfg.runner_elev_m = Number(f.runner_elev_m);
    if (f.rated_mva) { cfg.rated_mva = Number(f.rated_mva); cfg.cos_phi = Number(f.cos_phi); cfg.ambient_c = Number(f.ambient_c); cfg.cooling = f.cooling; }
    api.updateAsset(asset.asset_id, { config: cfg }).then(onSaved).catch((e) => setErr(e.message));
  };
  return (
    <Dialog title={`${asset.name} — holat monitoringi sozlamalari`} onClose={onClose}>
      {err && <p className="error small">{err}</p>}
      <label className="field"><span>Tebranish sensori (mm/s r.m.s.)</span><select className="select" value={f.vibration_sensor_id} onChange={(e) => setF({ ...f, vibration_sensor_id: e.target.value })}><option value="">—</option>{vib.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
      <label className="field"><span>Mashina guruhi (ISO 20816-5)</span><select className="select" value={f.machine_group} onChange={(e) => setF({ ...f, machine_group: e.target.value })}>
        <option value="1">1 — gorizontal, &gt;300 ayl/min (1.6 / 2.5 / 4.0)</option><option value="2">2 — gorizontal kapsulali, &lt;300 (2.5 / 4.0 / 6.4)</option><option value="3">3 — vertikal, podshipniklar poydevorda (1.6 / 2.5 / 4.0)</option><option value="4">4 — vertikal, yuqori podshipnik statorda (2.5 / 4.0 / 6.4)</option></select></label>
      <label className="field"><span>Podshipnik harorati sensori</span><select className="select" value={f.bearing_temp_sensor_id} onChange={(e) => setF({ ...f, bearing_temp_sensor_id: e.target.value })}><option value="">—</option>{tmp.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
      <div className="row">
        <label className="field grow"><span>Ogohlantirish, °C</span><input className="input" type="number" value={f.temp_warn} onChange={(e) => setF({ ...f, temp_warn: e.target.value })} /></label>
        <label className="field grow"><span>Alarm, °C</span><input className="input" type="number" value={f.temp_alarm} onChange={(e) => setF({ ...f, temp_alarm: e.target.value })} /></label>
      </div>
      <div className="row">
        <label className="field grow"><span>Aylanish tezligi, ayl/min (kavitatsiya)</span><input className="input" type="number" value={f.rated_speed_rpm} onChange={(e) => setF({ ...f, rated_speed_rpm: e.target.value })} placeholder="masalan 150" /></label>
        <label className="field grow"><span>Runner belgisi, m (mutlaq)</span><input className="input" type="number" step="any" value={f.runner_elev_m} onChange={(e) => setF({ ...f, runner_elev_m: e.target.value })} placeholder="masalan 838" /></label>
        <label className="field grow"><span>Turbina turi</span><select className="select" value={f.turbine_type} onChange={(e) => setF({ ...f, turbine_type: e.target.value })}>{["Francis", "Kaplan", "Pelton", "Bulb"].map((t) => <option key={t}>{t}</option>)}</select></label>
      </div>
      <div className="row">
        <label className="field grow"><span>Transformator S_nom, MVA (0 — yo'q)</span><input className="input" type="number" value={f.rated_mva} onChange={(e) => setF({ ...f, rated_mva: e.target.value })} placeholder="masalan 63" /></label>
        <label className="field grow"><span>cos φ</span><input className="input" type="number" step="0.01" value={f.cos_phi} onChange={(e) => setF({ ...f, cos_phi: e.target.value })} /></label>
        <label className="field grow"><span>Havo harorati, °C</span><input className="input" type="number" value={f.ambient_c} onChange={(e) => setF({ ...f, ambient_c: e.target.value })} /></label>
        <label className="field grow"><span>Sovutish</span><select className="select" value={f.cooling} onChange={(e) => setF({ ...f, cooling: e.target.value })}>{["ONAN", "ONAF", "OF", "OD"].map((c) => <option key={c}>{c}</option>)}</select></label>
      </div>
      <div className="actions"><button className="btn" onClick={onClose}>Bekor</button><button className="btn primary" onClick={save}>Saqlash</button></div>
    </Dialog>
  );
}

/** «Nima bo'lsa»: sath/sarf/quvvatni o'zgartirib egizakni sinash (jonli ma'lumotga tegilmaydi) + optimal rejim. */
export function WhatIfPanel({ projectId }: { projectId: number }) {
  const [live, setLive] = useState<TwinState | null>(null);
  const [f, setF] = useState<Record<string, string>>({ upstream_level: "", downstream_level: "", penstock_flow: "", inflow: "", target_mw: "" });
  const [res, setRes] = useState<(TwinState & { dispatch?: DispatchResult }) | null>(null);
  const [disp, setDisp] = useState<DispatchResult | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.twin(projectId).then(setLive).catch(() => undefined);
    api.twinDispatch(projectId).then(setDisp).catch(() => undefined);
  }, [projectId]);
  const run = async () => {
    setBusy(true); setErr("");
    try {
      const body: Record<string, number> = {};
      for (const [k, v] of Object.entries(f)) if (v !== "" && Number.isFinite(Number(v))) body[k] = Number(v);
      setRes(await api.twinWhatIf(projectId, body));
    } catch (e) { setErr(e instanceof Error ? e.message : "Xatolik"); } finally { setBusy(false); }
  };
  const num = (k: string, label: string, hint?: string) => (
    <label className="field" style={{ width: 170 }}><span>{label}</span><input className="input" type="number" step="any" placeholder={hint} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></label>
  );
  const dispatchTable = (d: DispatchResult | null | undefined) => d && d.status === "ok" ? (
    <table className="grid small" style={{ marginTop: 4 }}>
      <thead><tr><th>Agregat</th><th>MW</th><th>yuk</th><th>sarf, m³/s</th><th>FIK</th></tr></thead>
      <tbody>{d.units.map((u) => <tr key={u.name} className={u.power_mw > 0 ? undefined : "dim"}><td>{u.name}</td><td className="mono">{u.power_mw}</td><td className="mono">{u.load_pct} %</td><td className="mono">{u.flow_m3s}</td><td className="mono">{u.efficiency != null ? `${(u.efficiency * 100).toFixed(1)} %` : "—"}</td></tr>)}</tbody>
      <tfoot><tr><td>Jami</td><td className="mono">{d.target_mw}</td><td /><td className="mono">{d.total_flow_m3s}</td><td className="dim">{d.saving_pct != null ? `joriyga nisbatan ${d.saving_pct > 0 ? "−" : "+"}${Math.abs(d.saving_pct)} % suv` : ""}</td></tr></tfoot>
    </table>
  ) : <p className="muted small">{d?.reason ?? (d?.status === "idle" ? "Agregatlar ishlamayapti" : "Optimal rejim uchun egizak ma'lumoti yetarli emas (model Pset_GES_Turbine + sath sensorlari)")}</p>;
  return (
    <div className="dash-block">
      <div className="row"><b>Bugungi optimal rejim</b><span className="muted small">jonli napor va joriy umumiy quvvat uchun agregatlar yuk taqsimoti (minimal suv sarfi)</span><span className="grow" /><button className="btn sm" onClick={() => api.twinDispatch(projectId).then(setDisp).catch((e) => setErr(e.message))}>Yangilash</button></div>
      {dispatchTable(disp)}
      <div className="row" style={{ marginTop: 14 }}><b>«Nima bo'lsa» sinovi</b><span className="muted small">sath / sarf / quvvatni o'zgartiring — egizak, xavfsizlik ko'rsatkichlari va optimal taqsimot qayta hisoblanadi; jonli ma'lumotga tegilmaydi (mashq, rejalashtirish)</span></div>
      {live && <p className="dim small">Jonli: brutto napor {live.head_gross_m != null ? fmtValue(live.head_gross_m) : "—"} m · sarf {live.flow_total_m3s != null ? fmtValue(live.flow_total_m3s) : "—"} m³/s · quvvat {live.measured_total_mw != null ? fmtValue(live.measured_total_mw) : "—"} MW</p>}
      <div className="row wrap">
        {num("upstream_level", "Yuqori byef sathi, m", "jonli")}
        {num("downstream_level", "Quyi byef sathi, m", "jonli")}
        {num("penstock_flow", "Quvur sarfi, m³/s", "jonli")}
        {num("inflow", "Kiruvchi sarf, m³/s", "jonli")}
        {num("target_mw", "Kerakli quvvat, MW", "joriy")}
        <button className="btn primary" style={{ alignSelf: "flex-end", marginBottom: 10 }} disabled={busy} onClick={run}>{busy ? "…" : "Sinash"}</button>
      </div>
      {err && <p className="error small">{err}</p>}
      {res && (
        <div className="section-box">
          <div className="row"><b>Natija (sinov)</b><span className="dim small">napor {res.head_gross_m != null ? fmtValue(res.head_gross_m) : "—"} m · kutilgan {res.expected_total_mw != null ? fmtValue(res.expected_total_mw) : "—"} MW</span></div>
          {res.status !== "ok" && <p className="muted small">{res.reason}</p>}
          {res.units.length > 0 && (
            <table className="grid small"><thead><tr><th>Agregat</th><th>Kutilgan, MW</th><th>Sarf</th><th>Netto napor</th></tr></thead>
              <tbody>{res.units.map((u) => <tr key={u.sensor_id}><td>{u.name}</td><td className="mono">{fmtValue(u.expected_mw)}</td><td className="mono">{u.flow_m3s ?? "—"}</td><td className="mono">{fmtValue(u.head_net_m)}</td></tr>)}</tbody></table>
          )}
          {res.safety && res.safety.length > 0 && (
            <table className="grid small" style={{ marginTop: 6 }}><tbody>{res.safety.map((r) => <tr key={r.name} className={r.ok ? undefined : "alarm-active"}><td style={{ width: 22 }}><Icon name={r.ok ? "check-circle" : "alert-triangle"} size={13} style={{ color: r.ok ? "var(--ok)" : "var(--danger)" }} /></td><td>{r.name}</td><td className="mono">{r.value} {r.unit}</td><td className="dim">{r.note}</td></tr>)}</tbody></table>
          )}
          <div style={{ marginTop: 6 }}><b className="small">Optimal taqsimot (sinov sharoitida)</b>{dispatchTable(res.dispatch)}</div>
        </div>
      )}
    </div>
  );
}


const WO_STATUS: Record<string, [string, string]> = { open: ["ochiq", "open"], in_progress: ["bajarilmoqda", "shared"], done: ["bajarildi", "published"], cancelled: ["bekor", "archived"] };
const PRIO_CLS: Record<string, string> = { critical: "rejected", high: "high", medium: "open", low: "archived" };

/** Ish buyruqlari (CMMS): ro'yxat, KPI, yaratish, holat, yopish. */
export function WorkOrdersPanel({ projectId, members, canOperate, canEdit }: { projectId: number; members: Member[]; canOperate: boolean; canEdit: boolean }) {
  const [items, setItems] = useState<WorkOrder[]>([]);
  const [kpi, setKpi] = useState<WorkOrderKpi | null>(null);
  const [filter, setFilter] = useState<string>("active");
  const [adding, setAdding] = useState(false);
  const [closing, setClosing] = useState<WorkOrder | null>(null);
  const [err, setErr] = useState("");
  const [form, setForm] = useState({ title: "", description: "", priority: "medium", assignee_id: "", due_at: "" });
  const [closeForm, setCloseForm] = useState({ resolution: "", downtime_hours: "0", cost: "0" });
  const load = () => Promise.all([api.workOrders(projectId), api.workOrderKpi(projectId)]).then(([w, k]) => { setItems(w); setKpi(k); }).catch((e) => setErr(e.message));
  useEffect(() => { void load(); }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps
  const shown = items.filter((w) => filter === "all" ? true : filter === "active" ? (w.status === "open" || w.status === "in_progress") : w.status === filter);
  const setStatus = (w: WorkOrder, status: WorkOrder["status"]) => api.updateWorkOrder(w.id, { status }).then(load).catch((e) => setErr(e.message));
  return (
    <div className="dash-block">
      <div className="row" style={{ alignItems: "center" }}>
        <b>Ish buyruqlari</b><span className="muted small">texnik xizmat / ta'mirlash vazifalari — qo'lda, sog'liq indeksidan (avto), alarmdan</span><span className="grow" />
        <select className="select" value={filter} onChange={(e) => setFilter(e.target.value)}><option value="active">Faol</option><option value="open">Ochiq</option><option value="in_progress">Bajarilmoqda</option><option value="done">Bajarilgan</option><option value="all">Hammasi</option></select>
        {canOperate && <button className="btn sm primary" onClick={() => setAdding(true)}>+ Buyruq</button>}
      </div>
      {err && <p className="error small">{err}</p>}
      {kpi && (
        <div className="tiles" style={{ gridTemplateColumns: "repeat(6, 1fr)" }}>
          <div className="tile"><div className="tile-v">{kpi.open + kpi.in_progress}</div><div className="tile-t">faol {kpi.overdue > 0 && <span className="error">· {kpi.overdue} muddati o'tgan</span>}</div></div>
          <div className="tile"><div className="tile-v">{kpi.by_priority.critical + kpi.by_priority.high}</div><div className="tile-t">kritik/muhim</div></div>
          <div className="tile"><div className="tile-v">{kpi.done_90d}</div><div className="tile-t">bajarildi (90 kun)</div></div>
          <div className="tile"><div className="tile-v">{kpi.mttr_hours ?? "—"} <span className="tile-u">soat</span></div><div className="tile-t">MTTR (o'rtacha ta'mirlash)</div></div>
          <div className="tile"><div className="tile-v">{kpi.mtbf_hours ?? "—"} <span className="tile-u">soat</span></div><div className="tile-t">MTBF (nosozliklar orasi)</div></div>
          <div className="tile"><div className="tile-v">{kpi.downtime_90d_hours} <span className="tile-u">soat</span></div><div className="tile-t">to'xtab turish (90 kun) · xarajat {kpi.cost_90d}</div></div>
        </div>
      )}
      {shown.length === 0 ? <p className="muted">Buyruqlar yo'q.</p> : (
        <table className="grid small">
          <thead><tr><th>#</th><th>Buyruq</th><th>Aktiv</th><th>Ustuvorlik</th><th>Holat</th><th>Ijrochi</th><th>Muddat</th><th /></tr></thead>
          <tbody>{shown.map((w) => (
            <tr key={w.id} className={w.overdue ? "alarm-active" : undefined}>
              <td className="dim">{w.id}</td>
              <td><b>{w.title}</b>{w.description && <div className="dim" style={{ maxWidth: 420, whiteSpace: "pre-wrap" }}>{w.description}</div>}{w.resolution && <div className="ok-text">✓ {w.resolution}{w.downtime_hours ? ` · ${w.downtime_hours} soat to'xtash` : ""}</div>}<div className="dim">{w.source === "health" ? "sog'liq indeksi" : w.source === "alarm" ? "alarm" : w.source === "maintenance" ? "texnik xizmat" : w.author_username} · {fmtDate(w.created_at)}</div></td>
              <td>{w.asset_name ?? "—"}</td>
              <td><span className={`badge ${PRIO_CLS[w.priority]}`}>{w.priority}</span></td>
              <td><span className={`badge ${WO_STATUS[w.status][1]}`}>{WO_STATUS[w.status][0]}</span></td>
              <td>{canEdit ? <select className="select" value={w.assignee_id ?? ""} onChange={(e) => api.updateWorkOrder(w.id, { assignee_id: e.target.value ? Number(e.target.value) : null }).then(load).catch((er) => setErr(er.message))}><option value="">—</option>{members.map((m) => <option key={m.user_id} value={m.user_id}>{m.username}</option>)}</select> : (w.assignee_username ?? "—")}</td>
              <td className="dim">{w.due_at ? fmtDate(w.due_at) : "—"}</td>
              <td className="row" style={{ gap: 4 }}>
                {canOperate && w.status === "open" && <button className="btn sm" onClick={() => setStatus(w, "in_progress")}>Boshlash</button>}
                {canOperate && (w.status === "open" || w.status === "in_progress") && <button className="btn sm primary" onClick={() => { setClosing(w); setCloseForm({ resolution: "", downtime_hours: "0", cost: "0" }); }}>Yopish</button>}
                {canOperate && (w.status === "open" || w.status === "in_progress") && <button className="btn sm" title="Bekor qilish" onClick={() => setStatus(w, "cancelled")}><Icon name="x" size={12} /></button>}
                {canOperate && w.status !== "open" && w.status !== "in_progress" && <button className="btn sm" title="Qayta ochish" onClick={() => setStatus(w, "open")}><Icon name="refresh" size={12} /></button>}
                {canEdit && <button className="btn sm" title="O'chirish" onClick={() => { if (confirm("O'chirilsinmi?")) api.deleteWorkOrder(w.id).then(load).catch((er) => setErr(er.message)); }}><Icon name="trash" size={12} /></button>}
              </td>
            </tr>
          ))}</tbody>
        </table>
      )}
      {adding && (
        <Dialog title="Yangi ish buyrug'i" onClose={() => setAdding(false)}>
          <label className="field"><span>Sarlavha</span><input className="input" value={form.title} autoFocus onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
          <label className="field"><span>Tavsif</span><textarea className="textarea" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
          <div className="row">
            <label className="field grow"><span>Ustuvorlik</span><select className="select" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>{["low", "medium", "high", "critical"].map((p) => <option key={p}>{p}</option>)}</select></label>
            {canEdit && <label className="field grow"><span>Ijrochi</span><select className="select" value={form.assignee_id} onChange={(e) => setForm({ ...form, assignee_id: e.target.value })}><option value="">—</option>{members.map((m) => <option key={m.user_id} value={m.user_id}>{m.username}</option>)}</select></label>}
            <label className="field grow"><span>Muddat</span><input className="input" type="datetime-local" value={form.due_at} onChange={(e) => setForm({ ...form, due_at: e.target.value })} /></label>
          </div>
          <div className="actions"><button className="btn" onClick={() => setAdding(false)}>Bekor</button><button className="btn primary" disabled={!form.title} onClick={() => api.createWorkOrder(projectId, { title: form.title, description: form.description, priority: form.priority, assignee_id: form.assignee_id ? Number(form.assignee_id) : null, due_at: form.due_at ? new Date(form.due_at).toISOString() : null }).then(() => { setAdding(false); void load(); }).catch((e) => setErr(e.message))}>Yaratish</button></div>
        </Dialog>
      )}
      {closing && (
        <Dialog title={`Yopish: ${closing.title}`} onClose={() => setClosing(null)}>
          <label className="field"><span>Natija / bajarilgan ish</span><textarea className="textarea" value={closeForm.resolution} autoFocus onChange={(e) => setCloseForm({ ...closeForm, resolution: e.target.value })} /></label>
          <div className="row">
            <label className="field grow"><span>To'xtab turish, soat</span><input className="input" type="number" step="any" value={closeForm.downtime_hours} onChange={(e) => setCloseForm({ ...closeForm, downtime_hours: e.target.value })} /></label>
            <label className="field grow"><span>Xarajat</span><input className="input" type="number" step="any" value={closeForm.cost} onChange={(e) => setCloseForm({ ...closeForm, cost: e.target.value })} /></label>
          </div>
          <div className="actions"><button className="btn" onClick={() => setClosing(null)}>Bekor</button><button className="btn primary" onClick={() => api.updateWorkOrder(closing.id, { status: "done", resolution: closeForm.resolution, downtime_hours: Number(closeForm.downtime_hours) || 0, cost: Number(closeForm.cost) || 0 }).then(() => { setClosing(null); void load(); }).catch((e) => setErr(e.message))}>Bajarildi</button></div>
        </Dialog>
      )}
    </div>
  );
}

/** Toshqin prognozi: kutilayotgan yog'in + jonli sath + pasport → sath, gerbdan oshish, tavsiya. */
export function ForecastPanel({ projectId }: { projectId: number }) {
  const [f, setF] = useState({ rain_mm: "80", rain_hours: "24", amc: "II", snowmelt: false, air_temp: "8", glof: false, gate_opening: "1" });
  const [res, setRes] = useState<FloodForecast | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true); setErr("");
    try {
      setRes(await api.floodForecast(projectId, { rain_mm: Number(f.rain_mm), rain_hours: Number(f.rain_hours), amc: f.amc, snowmelt: f.snowmelt, air_temp: Number(f.air_temp), glof: f.glof, gate_opening: Number(f.gate_opening) }));
    } catch (e) { setErr(e instanceof Error ? e.message : "Xatolik"); } finally { setBusy(false); }
  };
  const s = res?.summary;
  return (
    <div className="dash-block">
      <div className="row"><b>Toshqin prognozi</b><span className="muted small">ob-havo prognozidagi yog'in + jonli sath/sarf + maydon pasporti (havza CN, ombor, suv tashlagich) → sath 3–5 kun, gerbdan oshish vaqti, oldindan sath tushirish tavsiyasi (SCS-CN → Puls)</span></div>
      <div className="row wrap" style={{ marginTop: 6 }}>
        <label className="field" style={{ width: 130 }}><span>Yog'in, mm</span><input className="input" type="number" value={f.rain_mm} onChange={(e) => setF({ ...f, rain_mm: e.target.value })} /></label>
        <label className="field" style={{ width: 110 }}><span>Davomiylik, soat</span><input className="input" type="number" value={f.rain_hours} onChange={(e) => setF({ ...f, rain_hours: e.target.value })} /></label>
        <label className="field" style={{ width: 170 }}><span>Oldingi namlik</span><select className="select" value={f.amc} onChange={(e) => setF({ ...f, amc: e.target.value })}><option value="I">I — quruq</option><option value="II">II — o'rtacha</option><option value="III">III — nam (yomg'ir yoqqan)</option></select></label>
        <label className="field" style={{ width: 130 }}><span>Darvozalar (0–1)</span><input className="input" type="number" step="0.1" min="0" max="1" value={f.gate_opening} onChange={(e) => setF({ ...f, gate_opening: e.target.value })} /></label>
        <label className="row small field-check"><input type="checkbox" checked={f.snowmelt} onChange={(e) => setF({ ...f, snowmelt: e.target.checked })} /> qor erishi</label>
        {f.snowmelt && <label className="field" style={{ width: 100 }}><span>Harorat, °C</span><input className="input" type="number" value={f.air_temp} onChange={(e) => setF({ ...f, air_temp: e.target.value })} /></label>}
        <label className="row small field-check" title="Muzlik ko'li toshqini (pasportdagi hajm)"><input type="checkbox" checked={f.glof} onChange={(e) => setF({ ...f, glof: e.target.checked })} /> GLOF</label>
        <button className="btn primary" style={{ alignSelf: "flex-end", marginBottom: 10 }} disabled={busy} onClick={run}>{busy ? "…" : "Prognoz"}</button>
      </div>
      {err && <p className="error small">{err}</p>}
      {res && s && (
        <div className="section-box">
          {!res.site_filled && <p className="error small">Maydon pasporti to'ldirilmagan — standart havza/ombor qiymatlari ishlatildi.</p>}
          <p className="dim small">Jonli: {Object.entries(res.live).map(([k, v]) => `${k} ${v}`).join(" · ") || "sensor yo'q (pasport sathlari)"}</p>
          <div className="tiles">
            <div className="tile"><div className="tile-v">{String(s.peak_inflow_m3s)} <span className="tile-u">m³/s</span></div><div className="tile-t">maks. kiruvchi sarf ({String(s.time_to_peak_h)} soatda)</div></div>
            <div className="tile"><div className="tile-v">{String(s.max_level_m)} <span className="tile-u">m</span></div><div className="tile-t">maksimal sath ({String(s.t_max_level_h)} soat)</div></div>
            <div className={`tile${s.overtopped ? " bad" : ""}`}><div className="tile-v">{String(s.freeboard_m)} <span className="tile-u">m</span></div><div className="tile-t">qolgan zaxira (gerbgacha)</div></div>
          </div>
          {res.recommendation && <div className={`verdict ${res.recommendation.action === "pre_release" ? "bad" : "ok"}`}><Icon name={res.recommendation.action === "pre_release" ? "alert-triangle" : "info"} size={16} /> <span>{res.recommendation.text}</span></div>}
          {!res.recommendation && <div className="verdict ok"><Icon name="check-circle" size={16} /> <span>{String(s.verdict)}</span></div>}
          <LineChart title="Ombor sathi prognozi" unit="m" x={res.series.t} series={[{ name: "Sath", values: res.series.level, color: CHART_COLORS[0] }]} />
          <LineChart title="Kiruvchi / chiqim" unit="m³/s" x={res.series.t} series={[{ name: "Kiruvchi", values: res.series.inflow, color: CHART_COLORS[1] }, { name: "Chiqim", values: res.series.outflow, color: CHART_COLORS[2] }]} />
        </div>
      )}
    </div>
  );
}


/** Ehtiyot qismlar ombori: ro'yxat (kam zaxira belgisi), kirim/sarf (ish buyrug'iga bog'lab), tarix. */
export function PartsPanel({ projectId, canOperate, canEdit }: { projectId: number; canOperate: boolean; canEdit: boolean }) {
  const [items, setItems] = useState<SparePart[]>([]);
  const [orders, setOrders] = useState<WorkOrder[]>([]);
  const [err, setErr] = useState("");
  const [adding, setAdding] = useState(false);
  const [moving, setMoving] = useState<{ part: SparePart; dir: 1 | -1 } | null>(null);
  const [hist, setHist] = useState<{ part: SparePart; rows: PartMovement[] } | null>(null);
  const [form, setForm] = useState({ name: "", code: "", unit: "dona", qty: "0", min_qty: "1", location: "", unit_cost: "0" });
  const [mv, setMv] = useState({ qty: "1", work_order_id: "", note: "" });
  const load = () => Promise.all([api.parts(projectId), api.workOrders(projectId)]).then(([p, w]) => { setItems(p); setOrders(w.filter((o) => o.status === "open" || o.status === "in_progress")); }).catch((e) => setErr(e.message));
  useEffect(() => { void load(); }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps
  const low = items.filter((p) => p.low).length;
  return (
    <div className="dash-block">
      <div className="row" style={{ alignItems: "center" }}>
        <b>Ehtiyot qismlar</b><span className="muted small">ombor qoldig'i, minimal zaxira, sarf ish buyrug'iga bog'lanadi (xarajat avtomatik)</span>
        {low > 0 && <span className="badge rejected">{low} ta kam</span>}
        <span className="grow" />
        {canEdit && <button className="btn sm primary" onClick={() => setAdding(true)}>+ Qism</button>}
      </div>
      {err && <p className="error small">{err}</p>}
      {items.length === 0 ? <p className="muted">Qismlar yo'q.</p> : (
        <table className="grid small">
          <thead><tr><th>Nomi</th><th>Kod</th><th>Qoldiq</th><th>Min</th><th>Joy</th><th>Narx</th><th>Aktiv</th><th /></tr></thead>
          <tbody>{items.map((p) => (
            <tr key={p.id} className={p.low ? "alarm-active" : undefined}>
              <td><b>{p.name}</b>{p.notes && <div className="dim">{p.notes}</div>}</td>
              <td className="mono dim">{p.code}</td>
              <td className="mono">{p.qty} {p.unit}{p.low && <Icon name="alert-triangle" size={12} style={{ color: "var(--danger)", marginLeft: 4 }} />}</td>
              <td className="mono dim">{p.min_qty}</td>
              <td className="dim">{p.location}</td>
              <td className="mono dim">{p.unit_cost}</td>
              <td className="dim">{p.asset_name ?? "—"}</td>
              <td className="row" style={{ gap: 4 }}>
                {canOperate && <button className="btn sm" title="Sarf (−)" onClick={() => { setMoving({ part: p, dir: -1 }); setMv({ qty: "1", work_order_id: "", note: "" }); }}><Icon name="minus" size={12} /></button>}
                {canEdit && <button className="btn sm" title="Kirim (+)" onClick={() => { setMoving({ part: p, dir: 1 }); setMv({ qty: "1", work_order_id: "", note: "" }); }}><Icon name="plus" size={12} /></button>}
                <button className="btn sm" title="Harakatlar tarixi" onClick={() => api.partMovements(p.id).then((rows) => setHist({ part: p, rows })).catch((e) => setErr(e.message))}><Icon name="history" size={12} /></button>
                {canEdit && <button className="btn sm" title="O'chirish" onClick={() => { if (confirm("O'chirilsinmi?")) api.deletePart(p.id).then(load).catch((e) => setErr(e.message)); }}><Icon name="trash" size={12} /></button>}
              </td>
            </tr>
          ))}</tbody>
        </table>
      )}
      {adding && (
        <Dialog title="Yangi ehtiyot qism" onClose={() => setAdding(false)}>
          <div className="row"><label className="field grow"><span>Nomi</span><input className="input" value={form.name} autoFocus onChange={(e) => setForm({ ...form, name: e.target.value })} /></label><label className="field"><span>Kod</span><input className="input" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} /></label></div>
          <div className="row">
            <label className="field grow"><span>Boshlang'ich qoldiq</span><input className="input" type="number" step="any" value={form.qty} onChange={(e) => setForm({ ...form, qty: e.target.value })} /></label>
            <label className="field grow"><span>Birlik</span><input className="input" value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })} /></label>
            <label className="field grow"><span>Minimal zaxira</span><input className="input" type="number" step="any" value={form.min_qty} onChange={(e) => setForm({ ...form, min_qty: e.target.value })} /></label>
            <label className="field grow"><span>Birlik narxi</span><input className="input" type="number" step="any" value={form.unit_cost} onChange={(e) => setForm({ ...form, unit_cost: e.target.value })} /></label>
          </div>
          <label className="field"><span>Joylashuv (ombor, javon)</span><input className="input" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} /></label>
          <div className="actions"><button className="btn" onClick={() => setAdding(false)}>Bekor</button><button className="btn primary" disabled={!form.name} onClick={() => api.createPart(projectId, { name: form.name, code: form.code, unit: form.unit, qty: Number(form.qty) || 0, min_qty: Number(form.min_qty) || 0, location: form.location, unit_cost: Number(form.unit_cost) || 0 }).then(() => { setAdding(false); void load(); }).catch((e) => setErr(e.message))}>Qo'shish</button></div>
        </Dialog>
      )}
      {moving && (
        <Dialog title={`${moving.dir > 0 ? "Kirim" : "Sarf"}: ${moving.part.name} (qoldiq ${moving.part.qty} ${moving.part.unit})`} onClose={() => setMoving(null)}>
          <div className="row">
            <label className="field grow"><span>Miqdor, {moving.part.unit}</span><input className="input" type="number" step="any" min="0" value={mv.qty} autoFocus onChange={(e) => setMv({ ...mv, qty: e.target.value })} /></label>
            {moving.dir < 0 && <label className="field grow"><span>Ish buyrug'i (xarajat unga yoziladi)</span><select className="select" value={mv.work_order_id} onChange={(e) => setMv({ ...mv, work_order_id: e.target.value })}><option value="">—</option>{orders.map((o) => <option key={o.id} value={o.id}>#{o.id} {o.title}</option>)}</select></label>}
          </div>
          <label className="field"><span>Izoh</span><input className="input" value={mv.note} onChange={(e) => setMv({ ...mv, note: e.target.value })} /></label>
          <div className="actions"><button className="btn" onClick={() => setMoving(null)}>Bekor</button><button className="btn primary" onClick={() => api.movePart(moving.part.id, { qty: moving.dir * Math.abs(Number(mv.qty) || 0), work_order_id: mv.work_order_id ? Number(mv.work_order_id) : null, note: mv.note }).then(() => { setMoving(null); void load(); }).catch((e) => setErr(e.message))}>{moving.dir > 0 ? "Kirim" : "Sarf"}</button></div>
        </Dialog>
      )}
      {hist && (
        <Dialog title={`Tarix: ${hist.part.name}`} onClose={() => setHist(null)}>
          <table className="grid small"><thead><tr><th>Vaqt</th><th>Miqdor</th><th>Buyruq</th><th>Kim</th><th>Izoh</th></tr></thead>
            <tbody>{hist.rows.map((r) => <tr key={r.id}><td className="dim">{fmtDate(r.created_at)}</td><td className={`mono ${r.qty < 0 ? "bad-text" : "ok-text"}`}>{r.qty > 0 ? "+" : ""}{r.qty}</td><td className="dim">{r.work_order_id ? `#${r.work_order_id}` : "—"}</td><td>{r.author_username}</td><td className="dim">{r.note}</td></tr>)}</tbody></table>
          <div className="actions"><button className="btn" onClick={() => setHist(null)}>Yopish</button></div>
        </Dialog>
      )}
    </div>
  );
}
