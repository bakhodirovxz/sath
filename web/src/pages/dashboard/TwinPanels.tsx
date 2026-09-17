import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Icon from "../../ui/Icon";
import { api, type AssetState, type Command, type JournalEntry, type Sensor, type TwinState } from "../../api/client";
import { fmtDate, fmtValue } from "../../ui/format";
import Dialog from "../../ui/Dialog";

/* Dispetcher paneli bo'limlari: raqamli egizak, boshqaruv buyruqlari, smena jurnali, aktivlar. */

const CMD_LABEL: Record<Command["status"], string> = { pending: "kutmoqda", sent: "yuborildi", acked: "bajarildi", failed: "xato", cancelled: "bekor" };
const CMD_CLASS: Record<Command["status"], string> = { pending: "shared", sent: "open", acked: "published", failed: "rejected", cancelled: "archived" };

/** Raqamli egizak: jonli o'lchov ↔ model bo'yicha kutilgan quvvat, og'ish, FIK. */
export function TwinPanel({ projectId, canRun }: { projectId: number; canRun: boolean }) {
  const [t, setT] = useState<TwinState | null>(null);
  const [err, setErr] = useState("");
  const load = () => api.twin(projectId).then(setT).catch((e) => setErr(e.message));
  useEffect(() => { void load(); const id = window.setInterval(load, 15000); return () => window.clearInterval(id); }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!t) return <p className="muted">{err || "Yuklanmoqda…"}</p>;
  return (
    <div className="dash-block">
      <div className="row"><b>Raqamli egizak</b><span className="muted small">jonli o'lchov ↔ BIM model (Pset_GES, turbina FIK egri chizig'i)</span><span className="grow" />
        {canRun && <button className="btn sm" onClick={() => api.twinRun(projectId).then(setT).catch((e) => setErr(e.message))}>Hozir hisoblash</button>}
      </div>
      {t.status !== "ok" ? (
        <p className="muted">Egizak uchun ma'lumot yetarli emas: {t.reason}. {t.has_model === false ? "Modelda Pset_GES_Turbine bo'lgan versiya kerak." : "Sxemada yuqori/quyi byef sathi va agregat quvvati sensorlarini bog'lang."}</p>
      ) : (
        <>
          <p className="muted small">Brutto napor <b>{fmtValue(t.head_gross_m ?? 0)} m</b>{t.flow_total_m3s != null && <> · sarf <b>{fmtValue(t.flow_total_m3s)} m³/s</b></>} · o'lchangan <b>{fmtValue(t.measured_total_mw ?? 0)} MW</b> / kutilgan <b>{fmtValue(t.expected_total_mw ?? 0)} MW</b> (model v{t.version_id})</p>
          <table className="grid small">
            <thead><tr><th>Agregat</th><th>Holat</th><th>O'lchangan, MW</th><th>Kutilgan, MW</th><th>Og'ish</th><th>FIK (haqiqiy / model)</th><th>Sarf, m³/s</th><th>Netto napor, m</th></tr></thead>
            <tbody>
              {t.units.map((u) => {
                const dev = u.deviation_pct;
                const bad = dev != null && Math.abs(dev) > 10;
                return (
                  <tr key={u.sensor_id} className={bad ? "alarm-active" : undefined}>
                    <td>{u.name} <span className="dim">{u.model_unit}</span></td>
                    <td>{u.running ? <span className="badge published">ishlayapti</span> : <span className="badge archived">to'xtagan</span>}</td>
                    <td className="mono">{u.measured_mw == null ? "—" : fmtValue(u.measured_mw)}</td>
                    <td className="mono">{fmtValue(u.expected_mw)}</td>
                    <td className="mono">{dev == null ? "—" : <span className={bad ? "error" : ""}>{dev > 0 ? "+" : ""}{dev.toFixed(1)} %</span>}</td>
                    <td className="mono">{u.efficiency == null ? "—" : `${(u.efficiency * 100).toFixed(1)} %`} / {u.expected_efficiency == null ? "—" : `${(u.expected_efficiency * 100).toFixed(1)} %`}</td>
                    <td className="mono">{u.flow_m3s == null ? "—" : fmtValue(u.flow_m3s)}</td>
                    <td className="mono">{fmtValue(u.head_net_m)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="dim small">Og'ish ±10 % dan oshsa — «model bilan og'ish» alarmi (virtual sensor TWIN.*.DEV; chegaralar sensor sozlamasida). Sabablari: FIK pasayishi, sarf o'lchovi, quvur ifloslanishi, model parametrlari.</p>
        </>
      )}
      {t.safety && t.safety.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <div className="row"><b>Xavfsizlik ko'rsatkichlari</b><span className="muted small">maydon pasporti + jonli sath (gerb zaxirasi, suv tashlagich, to'g'on barqarorligi, inshoot balandligi)</span><span className="grow" /><Link to={`/projects/${projectId}/site`} className="small">Maydon pasporti</Link></div>
          <table className="grid small">
            <tbody>
              {t.safety.map((r) => (
                <tr key={r.name} className={r.ok ? undefined : "alarm-active"}>
                  <td style={{ width: 22 }}><Icon name={r.ok ? "check-circle" : "alert-triangle"} size={13} style={{ color: r.ok ? "var(--ok)" : "var(--danger)" }} /></td>
                  <td>{r.name}</td>
                  <td className="mono">{r.value} {r.unit}</td>
                  <td className="dim">{r.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {(!t.safety || t.safety.length === 0) && <p className="dim small" style={{ marginTop: 6 }}>Xavfsizlik ko'rsatkichlari uchun <Link to={`/projects/${projectId}/site`}>maydon pasportini</Link> to'ldiring (gerb, sathlar, to'g'on, inshoot belgilari).</p>}
    </div>
  );
}

/** Boshqaruv buyruqlari: writable sensorlarga setpoint, holat jonli. */
export function CommandsPanel({ projectId, sensors, canCommand, live }: { projectId: number; sensors: Sensor[]; canCommand: boolean; live: Command | null }) {
  const [cmds, setCmds] = useState<Command[]>([]);
  const [target, setTarget] = useState<Sensor | null>(null);
  const [value, setValue] = useState("");
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => { api.commands(projectId).then(setCmds).catch((e) => setErr(e.message)); }, [projectId]);
  useEffect(() => { if (live) setCmds((prev) => [live, ...prev.filter((c) => c.id !== live.id)]); }, [live]);
  const writable = sensors.filter((s) => s.writable);
  async function send() {
    if (!target) return;
    try {
      const c = await api.sendCommand(projectId, target.id, Number(value), note);
      setCmds((p) => [c, ...p.filter((x) => x.id !== c.id)]);
      setTarget(null); setValue(""); setNote(""); setErr("");
    } catch (e) { setErr(e instanceof Error ? e.message : "Xatolik"); }
  }
  return (
    <div className="dash-block">
      <div className="row wrap"><b>Boshqaruv (buyruqlar)</b><span className="muted small">setpoint / rele → gateway → SCADA; har buyruq auditda</span><span className="grow" />
        {canCommand && writable.map((s) => <button key={s.id} className="btn sm primary" onClick={() => { setTarget(s); setValue(s.last_value == null ? "" : String(s.last_value)); }}>{s.name} →</button>)}
        {canCommand && writable.length === 0 && <span className="dim small">Boshqaruv nuqtasi yo'q — sensor sozlamasida «Yozish mumkin»</span>}
      </div>
      {err && <p className="error small">{err}</p>}
      {cmds.length === 0 ? <p className="muted">Buyruqlar yo'q</p> : (
        <table className="grid small">
          <thead><tr><th>Vaqt</th><th>Nuqta</th><th>Qiymat</th><th>Kim</th><th>Holat</th><th>Natija</th><th /></tr></thead>
          <tbody>
            {cmds.slice(0, 30).map((c) => (
              <tr key={c.id}>
                <td className="mono">{fmtDate(c.created_at)}</td>
                <td>{c.sensor_name} <span className="dim">{c.sensor_key}</span></td>
                <td className="mono">{fmtValue(c.value)} {c.unit}</td>
                <td>{c.author_username}{c.note && <div className="dim">{c.note}</div>}</td>
                <td><span className={`badge ${CMD_CLASS[c.status]}`}>{CMD_LABEL[c.status]}</span></td>
                <td className="dim small">{c.result}</td>
                <td>{c.status === "pending" && canCommand && <button className="btn sm" onClick={() => api.cancelCommand(c.id).then((u) => setCmds((p) => p.map((x) => (x.id === u.id ? u : x))))}>Bekor</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {target && (
        <Dialog title={`Buyruq: ${target.name}`} onClose={() => setTarget(null)}>
          <p className="muted small">{target.key} · joriy qiymat {target.last_value == null ? "—" : `${fmtValue(target.last_value)} ${target.unit}`}. Buyruq gateway orqali SCADA ga yoziladi va audit jurnaliga tushadi.</p>
          <label className="field"><span>Yangi qiymat, {target.unit}</span><input className="input" type="number" step="any" value={value} onChange={(e) => setValue(e.target.value)} autoFocus /></label>
          <label className="field"><span>Izoh (sabab)</span><input className="input" value={note} onChange={(e) => setNote(e.target.value)} /></label>
          <div className="actions"><button className="btn" onClick={() => setTarget(null)}>Bekor</button><button className="btn primary" disabled={value === ""} onClick={() => confirm(`${target.name} → ${value} ${target.unit}. Yuborilsinmi?`) && send()}>Yuborish</button></div>
        </Dialog>
      )}
    </div>
  );
}

const JKIND: Record<JournalEntry["kind"], string> = { note: "yozuv", shift_start: "smena qabul", shift_end: "smena topshirish", event: "hodisa" };

/** Smena jurnali. */
export function JournalPanel({ projectId, canWrite, live }: { projectId: number; canWrite: boolean; live: JournalEntry | null }) {
  const [items, setItems] = useState<JournalEntry[]>([]);
  const [text, setText] = useState("");
  const [kind, setKind] = useState<JournalEntry["kind"]>("note");
  const [err, setErr] = useState("");
  useEffect(() => { api.journal(projectId).then(setItems).catch((e) => setErr(e.message)); }, [projectId]);
  useEffect(() => { if (live) setItems((p) => (p.some((x) => x.id === live.id) ? p : [live, ...p])); }, [live]);
  async function add(k: JournalEntry["kind"] = kind, t = text) {
    if (!t.trim()) return;
    try { const e = await api.addJournal(projectId, t.trim(), k); setItems((p) => (p.some((x) => x.id === e.id) ? p : [e, ...p])); setText(""); }
    catch (e) { setErr(e instanceof Error ? e.message : "Xatolik"); }
  }
  return (
    <div className="dash-block">
      <div className="row wrap"><b>Smena jurnali</b><span className="grow" />
        {canWrite && <><button className="btn sm" onClick={() => add("shift_start", "Smenani qabul qildim")}>Smena qabul</button><button className="btn sm" onClick={() => add("shift_end", "Smenani topshirdim")}>Smena topshirish</button></>}
      </div>
      {canWrite && (
        <form className="row" style={{ margin: "6px 0" }} onSubmit={(e) => { e.preventDefault(); void add(); }}>
          <select className="select" style={{ width: 130 }} value={kind} onChange={(e) => setKind(e.target.value as JournalEntry["kind"])}><option value="note">Yozuv</option><option value="event">Hodisa</option></select>
          <input className="input grow" placeholder="Jurnalga yozuv… (Enter)" value={text} onChange={(e) => setText(e.target.value)} />
          <button className="btn" type="submit" disabled={!text.trim()}>Yozish</button>
        </form>
      )}
      {err && <p className="error small">{err}</p>}
      {items.length === 0 ? <p className="muted">Yozuvlar yo'q</p> : (
        <div className="journal">
          {items.slice(0, 50).map((e) => (
            <div key={e.id} className={`journal-item ${e.kind}`}><span className="mono dim">{fmtDate(e.created_at)}</span> <span className="badge open">{JKIND[e.kind]}</span> <b>{e.author_username}</b>: {e.text}</div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Aktivlar (agregatlar): ish soatlari, ishga tushishlar, texnik xizmat. */
export function AssetsPanel({ projectId, sensors, canEdit, canMaint, onSelectGuid }: { projectId: number; sensors: Sensor[]; canEdit: boolean; canMaint: boolean; onSelectGuid?: (g: string) => void }) {
  const [items, setItems] = useState<AssetState[]>([]);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ name: "", power_sensor_id: "", maintenance_interval_hours: "8000", base_run_hours: "0" });
  const [err, setErr] = useState("");
  const load = () => api.assets(projectId).then(setItems).catch((e) => setErr(e.message));
  useEffect(() => { void load(); }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps
  const powerSensors = sensors.filter((s) => s.kind === "power" && s.protocol !== "twin");
  const cls = { ok: "published", due: "high", overdue: "rejected" };
  const lbl = { ok: "normal", due: "xizmat yaqin", overdue: "muddati o'tgan" };
  return (
    <div className="dash-block">
      <div className="row"><b>Aktivlar (agregatlar)</b><span className="muted small">ish soatlari, ishga tushishlar, texnik xizmat</span><span className="grow" />{canEdit && <button className="btn sm" onClick={() => setAdding(true)}>+ Aktiv</button>}</div>
      {err && <p className="error small">{err}</p>}
      {items.length === 0 ? <p className="muted">Aktivlar yo'q — quvvat sensori bilan agregat qo'shing.</p> : (
        <table className="grid small">
          <thead><tr><th>Aktiv</th><th>Holat</th><th>Ish soatlari</th><th>Ishga tushishlar</th><th>30 kun</th><th>Texnik xizmat</th><th /></tr></thead>
          <tbody>
            {items.map((a) => (
              <tr key={a.id}>
                <td>{a.element_guid && onSelectGuid ? <a onClick={() => onSelectGuid(a.element_guid!)}>{a.name}</a> : a.name}</td>
                <td>{a.running ? <span className="badge published">ishlayapti</span> : <span className="badge archived">to'xtagan</span>}</td>
                <td className="mono">{a.run_hours_total.toFixed(0)} s</td>
                <td className="mono">{a.starts_total}</td>
                <td className="mono">{a.run_hours_30d.toFixed(0)} s · {a.energy_30d_mwh.toFixed(0)} MWh · {a.availability_30d}%</td>
                <td>
                  <span className={`badge ${cls[a.status]}`}>{lbl[a.status]}</span>
                  {a.hours_to_maintenance != null && <div className="dim small">{a.hours_to_maintenance >= 0 ? `${a.hours_to_maintenance.toFixed(0)} soat qoldi` : `${(-a.hours_to_maintenance).toFixed(0)} soat kechikdi`}{a.last_maintenance_at && ` · oxirgi ${fmtDate(a.last_maintenance_at)}`}</div>}
                </td>
                <td>{canMaint && <button className="btn sm" onClick={() => { const n = prompt("Texnik xizmat izohi:", ""); if (n != null) api.assetMaintenance(a.id, n).then(load).catch((e) => setErr(e.message)); }}>Xizmat bajarildi</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {adding && (
        <Dialog title="Yangi aktiv" onClose={() => setAdding(false)}>
          <label className="field"><span>Nomi</span><input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} autoFocus /></label>
          <label className="field"><span>Quvvat sensori (ish soatlari shundan)</span>
            <select className="select" value={form.power_sensor_id} onChange={(e) => setForm({ ...form, power_sensor_id: e.target.value })}><option value="">—</option>{powerSensors.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
          </label>
          <div className="row">
            <label className="field grow"><span>Texnik xizmat oralig'i, soat</span><input className="input" type="number" value={form.maintenance_interval_hours} onChange={(e) => setForm({ ...form, maintenance_interval_hours: e.target.value })} /></label>
            <label className="field grow"><span>Tizimgacha ish soatlari</span><input className="input" type="number" value={form.base_run_hours} onChange={(e) => setForm({ ...form, base_run_hours: e.target.value })} /></label>
          </div>
          <div className="actions"><button className="btn" onClick={() => setAdding(false)}>Bekor</button><button className="btn primary" disabled={!form.name} onClick={() => api.createAsset(projectId, { name: form.name, power_sensor_id: form.power_sensor_id ? Number(form.power_sensor_id) : null, maintenance_interval_hours: form.maintenance_interval_hours ? Number(form.maintenance_interval_hours) : null, base_run_hours: Number(form.base_run_hours) || 0 }).then(() => { setAdding(false); void load(); }).catch((e) => setErr(e.message))}>Qo'shish</button></div>
        </Dialog>
      )}
    </div>
  );
}
