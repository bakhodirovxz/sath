import { useCallback, useEffect, useState } from "react";
import { usePolling } from "../../hooks/usePolling";
import { Link } from "react-router-dom";
import Icon from "../../ui/Icon";
import { api, type AssetDocKind, type AssetDocument, type AssetState, type AssetTree, type AssetTreeNode, type Command, type JournalEntry, type Sensor, type SoeEvent, type TwinState, type Version } from "../../api/client";
import ControlBlock, { CMD_CLASS, CMD_LABEL } from "../operator/ControlBlock";
import { fmtDate, fmtValue } from "../../ui/format";
import Dialog from "../../ui/Dialog";
import { dialogs } from "../../ui/dialogs";
import { AssetHistoryDialog } from "./CmmsPanels";
import { CalibrationPanel } from "./CalibrationPanel";
import { EstimatorPanel } from "./EstimatorPanel";
import { VAL_CLS, VAL_TXT, ValidationPanel } from "./ValidationPanel";

/* Dispetcher paneli bo'limlari: raqamli egizak, boshqaruv buyruqlari, smena jurnali, aktivlar. */


/** Raqamli egizak: jonli o'lchov ↔ model bo'yicha kutilgan quvvat, og'ish, FIK. */
export function TwinPanel({ projectId, canRun, canApprove = false }: { projectId: number; canRun: boolean; canApprove?: boolean }) {
  const [t, setT] = useState<TwinState | null>(null);
  const [err, setErr] = useState("");
  const load = useCallback(() => api.twin(projectId).then(setT).catch((e) => setErr(e.message)), [projectId]);
  usePolling(load, 15000, String(projectId));
  if (!t) return <p className="muted">{err || "Yuklanmoqda…"}</p>;
  return (
    <>
    <div className="dash-block">
      <div className="row"><b>Raqamli egizak</b><span className="muted small">jonli o'lchov ↔ BIM model (Pset_GES, turbina FIK egri chizig'i)</span><span className="grow" />
        {t.validation && <span className={`badge ${VAL_CLS[t.validation.status]}`} title={t.validation.note || "Model validatsiyasi"} data-testid="twin-validation">{VAL_TXT[t.validation.status]}</span>}
        {canRun && <button className="btn sm" onClick={() => api.twinRun(projectId).then(setT).catch((e) => setErr(e.message))}>Hozir hisoblash</button>}
      </div>
      {t.status !== "ok" ? (
        <p className="muted">Egizak uchun ma'lumot yetarli emas: {t.reason}. {t.has_model === false ? "Modelda Pset_GES_Turbine bo'lgan versiya kerak." : "Sxemada yuqori/quyi byef sathi va agregat quvvati sensorlarini bog'lang."}</p>
      ) : (
        <>
          {t.model_note && <p className={`small ${t.calibration?.drifted ? "error" : "dim"}`} data-testid="twin-model-note">⚠ {t.model_note}</p>}
          {t.calibrated && !t.calibration?.drifted && <p className="small dim" data-testid="twin-calibrated">Model kalibrovkalangan{t.calibration?.applied_at ? ` (${new Date(t.calibration.applied_at).toLocaleDateString()})` : ""}{t.calibration?.rmse_mw != null ? ` · RMSE ${t.calibration.rmse_mw} MW` : ""}</p>}
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
      <EstimatorPanel projectId={projectId} canEdit={canRun} />
      <ValidationPanel projectId={projectId} canApprove={canApprove} />
      <CalibrationPanel projectId={projectId} canEdit={canRun} />
    </>
  );
}

/** Boshqaruv buyruqlari: writable sensorlarga setpoint, holat jonli. */
export function CommandsPanel({ projectId, sensors, canCommand, live, canOverride = false }: { projectId: number; sensors: Sensor[]; canCommand: boolean; live: Command | null; canOverride?: boolean }) {
  const [cmds, setCmds] = useState<Command[]>([]);
  const [target, setTarget] = useState<Sensor | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.commands(projectId).then(setCmds).catch((e) => setErr(e.message)); }, [projectId]);
  useEffect(() => { if (live) setCmds((prev) => [live, ...prev.filter((c) => c.id !== live.id)]); }, [live]);
  const writable = sensors.filter((s) => s.writable);
  function closeDialog() { setTarget(null); }
  function approve(id: number) {
    api.approveCommand(id).then((u) => setCmds((p) => p.map((x) => (x.id === u.id ? u : x)))).catch((e) => setErr(e instanceof Error ? e.message : "Xatolik"));
  }
  return (
    <div className="dash-block">
      <div className="row wrap"><b>Boshqaruv (buyruqlar)</b><span className="muted small">setpoint / rele → gateway → SCADA; har buyruq auditda</span><span className="grow" />
        {canCommand && writable.map((s) => <button key={s.id} className="btn sm primary" onClick={() => setTarget(s)}>{s.name} →</button>)}
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
                <td className="dim small">{c.result}{c.readback_value != null && <div>readback: <span className="mono">{fmtValue(c.readback_value)} {c.unit}</span></div>}{c.approved_by_username && <div>tasdiq: {c.approved_by_username}</div>}</td>
                <td>
                  {(c.status === "pending" || c.status === "pending_approval") && canCommand && <button className="btn sm" onClick={() => api.cancelCommand(c.id).then((u) => setCmds((p) => p.map((x) => (x.id === u.id ? u : x))))}>Bekor</button>}
                  {c.status === "pending_approval" && canCommand && <button className="btn sm primary" title="Ikki kishi qoidasi: muallif o'zini tasdiqlay olmaydi" onClick={() => approve(c.id)}>Tasdiqlash</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {target && (
        <Dialog title={`Buyruq: ${target.name}`} onClose={closeDialog}>
          <ControlBlock projectId={projectId} sensor={target} canCommand={canCommand} canOverride={canOverride} liveCommand={live} onCommand={(c) => { setCmds((p) => [c, ...p.filter((x) => x.id !== c.id)]); closeDialog(); }} />
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
  const [docsFor, setDocsFor] = useState<AssetState | null>(null);
  const [histFor, setHistFor] = useState<number | null>(null);
  const [view, setView] = useState<"list" | "tree">("list");
  const [tree, setTree] = useState<AssetTree | null>(null);
  const loadTree = useCallback(() => api.assetTree(projectId).then(setTree).catch((e) => setErr(e.message)), [projectId]);
  useEffect(() => { if (view === "tree") void loadTree(); }, [view, loadTree]);
  const [models, setModels] = useState<{ id: number; name: string; versions: Version[] }[]>([]);
  const [syncMsg, setSyncMsg] = useState("");
  // G6: IFC dan aktiv registri — loyiha modellari va oxirgi versiyalari
  useEffect(() => {
    if (!canEdit) return;
    api.models(projectId).then(async (ms) => setModels(await Promise.all(ms.map(async (m) => ({ id: m.id, name: m.name, versions: await api.versions(m.id) }))))).catch(() => setModels([]));
  }, [projectId, canEdit]);
  const [form, setForm] = useState({ name: "", power_sensor_id: "", maintenance_interval_hours: "8000", base_run_hours: "0" });
  const [err, setErr] = useState("");
  const load = useCallback(() => api.assets(projectId).then(setItems).catch((e) => setErr(e.message)), [projectId]);
  useEffect(() => { void load(); }, [load]);
  const powerSensors = sensors.filter((s) => s.kind === "power" && s.protocol !== "twin");
  const cls = { ok: "published", due: "high", overdue: "rejected" };
  const lbl = { ok: "normal", due: "xizmat yaqin", overdue: "muddati o'tgan" };
  return (
    <div className="dash-block">
      <div className="row"><b>Aktivlar (agregatlar)</b><span className="muted small">ish soatlari, ishga tushishlar, texnik xizmat</span><span className="grow" />
        {canEdit && models.some((m) => m.versions.length) && (
          <select className="select" style={{ width: "auto" }} value="" data-testid="assets-from-ifc" title="IFC dan aktiv registri (COBie): turbina, generator, transformator — pasport ma'lumotlari bilan" onChange={(e) => { const vid = Number(e.target.value); if (!vid) return; setSyncMsg(""); api.assetsFromIfc(projectId, vid).then((r) => { setSyncMsg(`IFC dan: ${r.created} yangi, ${r.updated} yangilandi (${r.components} komponent)`); void load(); }).catch((er) => setErr(er.message)); e.target.value = ""; }}>
            <option value="">IFC dan aktivlar…</option>
            {models.filter((m) => m.versions.length).map((m) => <option key={m.id} value={m.versions[0]?.id}>{m.name} v{m.versions[0]?.number}</option>)}
          </select>
        )}
        {canEdit && models.some((m) => m.versions.length) && <button className="btn sm" title="COBie ga o'xshash CSV varaqlari (Facility, Floor, Type, Component, Attribute) — topshirish uchun" onClick={() => { const v = models.find((m) => m.versions.length)?.versions[0]; if (v) api.downloadCsv(`/api/versions/${v.id}/assets/register?format=csv`, `cobie_v${v.number}.zip`).catch((er) => setErr(er.message)); }}>COBie CSV</button>}
        {canEdit && <button className="btn sm" onClick={() => setAdding(true)}>+ Aktiv</button>}</div>
      {syncMsg && <p className="small verdict ok" data-testid="assets-sync-msg">{syncMsg}</p>}
      {err && <p className="error small">{err}</p>}
      <div className="row" style={{ gap: 6, margin: "4px 0" }}>
        <button className={`btn sm ${view === "list" ? "active" : ""}`} onClick={() => setView("list")}>Ro'yxat</button>
        <button className={`btn sm ${view === "tree" ? "active" : ""}`} onClick={() => setView("tree")} data-testid="assets-tree-btn">Ierarxiya (KKS)</button>
        {canEdit && <label className="btn sm" title="CSV: kks_code, name, parent_kks, taxonomy_level, element_guid, sensor_key, function_location">KKS CSV import<input type="file" accept=".csv" style={{ display: "none" }} data-testid="kks-csv" onChange={(e) => { const f = e.target.files?.[0]; if (!f) return; api.importKks(projectId, f).then((r) => { setSyncMsg(`KKS: ${r.created} yangi, ${r.updated} yangilandi${r.errors.length ? `, ${r.errors.length} xato: ${r.errors[0]}` : ""}`); void load(); void loadTree(); }).catch((er) => setErr(er.message)); e.target.value = ""; }} /></label>}
      </div>
      {view === "tree" && tree && (
        <div data-testid="assets-tree">
          {tree.roots.length === 0 ? <p className="muted">Ierarxiya bo'sh — aktivga KKS kodi/ota bering yoki CSV import qiling.</p> : (
            <table className="grid small">
              <thead><tr><th>KKS / nomi</th><th>Daraja</th><th>Holat (agregat)</th><th>Sog'liq</th><th /></tr></thead>
              <tbody>{tree.roots.map((n) => <TreeRows key={n.id} n={n} depth={0} labels={tree.level_labels} canEdit={canEdit} onEdit={(a) => void (async () => { const kks = await dialogs.prompt("KKS / RDS-PP kodi", a.kks_code ?? "", { text: "masalan 1MKA10 AH001 MA01 (tizim → uskuna → komponent); bo'sh — o'chirish" }); if (kks == null) return; api.updateAsset(a.id, { kks_code: kks }).then(() => { void load(); void loadTree(); }).catch((e) => setErr(e.message)); })()} onSelectGuid={onSelectGuid} />)}</tbody>
            </table>
          )}
        </div>
      )}
      {view === "list" && (items.length === 0 ? <p className="muted">Aktivlar yo'q — quvvat sensori bilan agregat qo'shing.</p> : (
        <table className="grid small">
          <thead><tr><th>Aktiv</th><th>Holat</th><th>Ish soatlari</th><th>Ishga tushishlar</th><th>30 kun</th><th>Texnik xizmat</th><th /></tr></thead>
          <tbody>
            {items.map((a) => (
              <tr key={a.id}>
                <td>{a.element_guid && onSelectGuid ? <button type="button" className="link-btn" onClick={() => onSelectGuid(a.element_guid!)}>{a.name}</button> : a.name}{a.kks_code && <span className="mono dim small"> {a.kks_code}</span>}{a.config?.manufacturer && <div className="dim small">{a.config.manufacturer}{a.config.model ? ` ${a.config.model}` : ""}{a.config.serial ? ` · SN ${a.config.serial}` : ""}{a.config.classification ? ` · ${a.config.classification}` : ""}</div>}</td>
                <td>{a.running ? <span className="badge published">ishlayapti</span> : <span className="badge archived">to'xtagan</span>}</td>
                <td className="mono">{a.run_hours_total.toFixed(0)} s</td>
                <td className="mono">{a.starts_total}</td>
                <td className="mono">{a.run_hours_30d.toFixed(0)} s · {a.energy_30d_mwh.toFixed(0)} MWh · {a.availability_30d}%</td>
                <td>
                  <span className={`badge ${cls[a.status]}`}>{lbl[a.status]}</span>
                  {a.hours_to_maintenance != null && <div className="dim small">{a.hours_to_maintenance >= 0 ? `${a.hours_to_maintenance.toFixed(0)} soat qoldi` : `${(-a.hours_to_maintenance).toFixed(0)} soat kechikdi`}{a.last_maintenance_at && ` · oxirgi ${fmtDate(a.last_maintenance_at)}`}</div>}
                </td>
                <td><button className="btn sm" title="Xizmat tarixi va xarajat (ISO 14224 nosozlik kodlari)" data-testid={`asset-history-${a.id}`} onClick={() => setHistFor(a.id)}>Tarix</button> <button className="btn sm" title="Hujjatlar: qo'llanma, pasport, sinov protokoli, ishga tushirish akti" onClick={() => setDocsFor(a)}>Hujjatlar</button> {canMaint && <button className="btn sm" onClick={() => void dialogs.prompt("Texnik xizmat bajarildi", "", { text: `${a.name}: izoh (nima qilindi)`, ok: "Yozish" }).then((n) => { if (n != null) api.assetMaintenance(a.id, n).then(load).catch((e) => setErr(e.message)); })}>Xizmat bajarildi</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ))}
      {docsFor && <AssetDocsDialog asset={docsFor} canEdit={canMaint} canDelete={canEdit} onClose={() => setDocsFor(null)} />}
      {histFor != null && <AssetHistoryDialog assetId={histFor} onClose={() => setHistFor(null)} />}
      {adding && (
        <Dialog title="Yangi aktiv" onClose={() => setAdding(false)}>
          <label className="field"><span>Nomi</span><input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-autofocus /></label>
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


/** SOE — hodisalar ketma-ketligi (D3): ms aniqlikdagi diskret hodisalar + alarm jurnali bitta vaqt chizig'ida
 * (avariya tahlili: sabab → oqibat). F5 da to'liq ko'rinish. */
export function SoePanel({ projectId }: { projectId: number }) {
  const [rows, setRows] = useState<SoeEvent[]>([]);
  const [hours, setHours] = useState(24);
  const [onlySoe, setOnlySoe] = useState(false);
  const [filter, setFilter] = useState("");
  const [err, setErr] = useState("");
  const load = useCallback(() => (onlySoe ? api.soe(projectId, hours, filter || undefined) : api.timeline(projectId, hours)).then(setRows).catch((e) => setErr(e instanceof Error ? e.message : "Xato")), [projectId, hours, onlySoe, filter]);
  usePolling(load, 15000, `${projectId}:${hours}:${onlySoe}:${filter}`);
  const fmtMs = (ts: string) => { const d = new Date(ts); return `${d.toLocaleDateString()} ${d.toLocaleTimeString()}.${String(d.getMilliseconds()).padStart(3, "0")}`; };
  return (
    <div className="panel">
      <div className="row wrap" style={{ gap: 6 }}>
        <b>Hodisalar ketma-ketligi (SOE)</b>
        <select className="select" value={hours} onChange={(e) => setHours(Number(e.target.value))}>{[1, 6, 24, 168, 720].map((h) => <option key={h} value={h}>{h} soat</option>)}</select>
        <label className="row" style={{ gap: 4 }}><input type="checkbox" checked={onlySoe} onChange={(e) => setOnlySoe(e.target.checked)} /> faqat SOE</label>
        {onlySoe && <input className="input" style={{ width: 160 }} placeholder="nuqta, masalan AGG1.*" value={filter} onChange={(e) => setFilter(e.target.value)} />}
        <span className="grow" />
        <span className="muted small">{rows.length} ta · ms aniqlik · 15 s da yangilanadi</span>
      </div>
      {err && <p className="error">{err}</p>}
      <table className="grid small mono">
        <thead><tr><th>Vaqt (ms)</th><th>Manba</th><th>Nuqta</th><th>Holat</th><th>Sifat</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.type ?? "soe"}-${r.id}`} className={r.type === "alarm" ? "alarm-active" : undefined}>
              <td>{fmtMs(r.ts)}</td>
              <td>{r.source}</td>
              <td>{r.point}</td>
              <td>{r.state}{r.type === "alarm" && r.raw && (r.raw as { value?: number }).value != null ? ` (${(r.raw as { value: number }).value})` : ""}</td>
              <td className="dim">{r.quality}</td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={5} className="muted">Hodisa yo'q</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

const ASSET_DOC_KINDS: { id: AssetDocKind; title: string }[] = [
  { id: "manual", title: "Qo'llanma" },
  { id: "passport", title: "Pasport" },
  { id: "test", title: "Zavod sinov protokoli" },
  { id: "commissioning", title: "Ishga tushirish akti" },
  { id: "other", title: "Boshqa" },
];

/** G6: aktiv hujjatlari — yuklash (operator+), yuklab olish, o'chirish (muhandis). */
function AssetDocsDialog({ asset, canEdit, canDelete, onClose }: { asset: AssetState; canEdit: boolean; canDelete: boolean; onClose: () => void }) {
  const [docs, setDocs] = useState<AssetDocument[]>([]);
  const [kind, setKind] = useState<AssetDocKind>("passport");
  const [title, setTitle] = useState("");
  const [err, setErr] = useState("");
  const load = useCallback(() => api.assetDocuments(asset.id).then(setDocs).catch((e) => setErr(e.message)), [asset.id]);
  useEffect(() => { void load(); }, [load]);
  return (
    <Dialog title={`${asset.name} — hujjatlar`} onClose={onClose}>
      {asset.config && (asset.config.manufacturer || asset.config.serial) && <p className="small muted">{asset.config.manufacturer} {asset.config.model} {asset.config.serial ? `· SN ${asset.config.serial}` : ""} {asset.config.warranty_end ? `· kafolat ${asset.config.warranty_end}` : ""}</p>}
      {err && <p className="error small">{err}</p>}
      {docs.length === 0 ? <p className="muted">Hujjat yo'q</p> : (
        <table className="grid small">
          <thead><tr><th>Tur</th><th>Nomi</th><th>Fayl</th><th /></tr></thead>
          <tbody>
            {docs.map((d) => (
              <tr key={d.id}>
                <td>{ASSET_DOC_KINDS.find((k) => k.id === d.kind)?.title ?? d.kind}</td>
                <td>{d.title}</td>
                <td><button className="btn sm" onClick={() => api.downloadCsv(`/api/assets/${asset.id}/documents/${d.id}/file`, d.file_name).catch((e) => setErr(e.message))}>{d.file_name}</button></td>
                <td>{canDelete && <button className="btn sm" onClick={() => api.deleteAssetDocument(asset.id, d.id).then(load).catch((e) => setErr(e.message))}>O'chirish</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {canEdit && (
        <div className="row" style={{ gap: 6, marginTop: 8, flexWrap: "wrap" }}>
          <select className="select" style={{ width: "auto" }} value={kind} onChange={(e) => setKind(e.target.value as AssetDocKind)}>{ASSET_DOC_KINDS.map((k) => <option key={k.id} value={k.id}>{k.title}</option>)}</select>
          <input className="input" placeholder="Sarlavha" value={title} onChange={(e) => setTitle(e.target.value)} style={{ width: 200 }} />
          <label className="btn sm">Fayl tanlash<input type="file" style={{ display: "none" }} accept=".pdf,.docx,.xlsx,.doc,.xls,.txt,.md,.csv,.zip,.png,.jpg,.jpeg" data-testid="asset-doc-file" onChange={(e) => { const f = e.target.files?.[0]; if (!f) return; api.uploadAssetDocument(asset.id, f, kind, title).then(() => { setTitle(""); void load(); }).catch((er) => setErr(er.message)); e.target.value = ""; }} /></label>
        </div>
      )}
      <div className="actions"><button className="btn" onClick={onClose}>Yopish</button></div>
    </Dialog>
  );
}

/** H1: aktiv ierarxiyasi qatorlari (rekursiv) — KKS kodi, ISO 14224 darajasi, agregatsiya holati va sog'liq. */
function TreeRows({ n, depth, labels, canEdit, onEdit, onSelectGuid }: { n: AssetTreeNode; depth: number; labels: Record<string, string>; canEdit: boolean; onEdit: (a: AssetTreeNode) => void; onSelectGuid?: ((g: string) => void) | undefined }) {
  const cls: Record<string, string> = { ok: "published", due: "high", overdue: "rejected" };
  return (
    <>
      <tr>
        <td style={{ paddingLeft: 8 + depth * 18 }}>
          {n.kks_code && <span className="mono">{n.kks_code}</span>} {n.element_guid && onSelectGuid ? <button type="button" className="link-btn" onClick={() => onSelectGuid(n.element_guid!)}>{n.name}</button> : n.name}
          {n.kks?.system_name && <span className="dim small"> · {n.kks.system_name}</span>}
        </td>
        <td className="dim small">{n.taxonomy_level ? labels[n.taxonomy_level] ?? n.taxonomy_level : "—"}</td>
        <td><span className={`badge ${cls[n.agg_status] ?? "archived"}`}>{n.agg_status}</span>{n.running != null && <span className="dim small"> {n.running ? "ishlayapti" : "to'xtagan"}</span>}</td>
        <td className="mono">{n.agg_score != null ? `${n.agg_score}${n.score != null && n.score !== n.agg_score ? ` (o'zi ${n.score})` : ""}` : "—"}</td>
        <td>{canEdit && <button className="btn sm" onClick={() => onEdit(n)}>KKS</button>}</td>
      </tr>
      {n.children.map((c) => <TreeRows key={c.id} n={c} depth={depth + 1} labels={labels} canEdit={canEdit} onEdit={onEdit} onSelectGuid={onSelectGuid} />)}
    </>
  );
}
