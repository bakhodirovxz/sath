import Icon from "../../ui/Icon";
import { useLatest } from "../../hooks/useLatest";
import { dialogs } from "../../ui/dialogs";
import ControlBlock from "../operator/ControlBlock";
import { BOps, BPanel, BRow } from "../../ui/BlenderUI";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, canCommandRole, type AlarmState, type ReadingPoint, type Role, type Sensor, type SensorIn, type SensorKind } from "../../api/client";
import type { SelectedItem, Viewer } from "../../viewer/Viewer";
import LineChart from "../../ui/LineChart";
import Dialog from "../../ui/Dialog";
import { fmtDate, fmtShort, isAlarm } from "../../ui/format";
import { alarmLabel, sensorKindLabel } from "../../i18n/labels";
import { putSensors, useLiveMessages, useProjectLive, useSensorsByIds } from "../../store/live";
import { THEMES, alarmStyle, currentTheme } from "../../ui/tokens";
import { ApiError, type UnlinkedReport } from "../../api/client";
import { can } from "../../api/permissions";
import GatewayKeys from "../../ui/GatewayKeys";

interface Props {
  projectId: number;
  modelId: number;
  /** Ochiq versiya — bog'lanmagan sensorlar (SCADA-13) shu versiya bo'yicha */
  versionId?: number | null | undefined;
  role: Role | null;
  viewer: Viewer | null;
  selection: SelectedItem[];
}

const KINDS: { id: SensorKind; unit: string }[] = [
  { id: "level", unit: "m" },
  { id: "flow", unit: "m³/s" },
  { id: "power", unit: "MW" },
  { id: "pressure", unit: "bar" },
  { id: "temperature", unit: "°C" },
  { id: "vibration", unit: "mm/s" },
  { id: "status", unit: "" },
  { id: "position", unit: "%" },
  { id: "value", unit: "" },
];
/** 3D bo'yash uchun haqiqiy hex (viewer CSS o'zgaruvchini o'qimaydi) — tokenlardan, joriy tema bo'yicha (F1) */
function hexOf(token: string): string {
  return THEMES[currentTheme()][token] ?? THEMES.engineer[token];
}
function alarmHex(s: Sensor): string {
  const st = alarmStyle(s.alarm, s.priority);
  const m = /var\(--([\w-]+)\)/.exec(st.color);
  return hexOf(m ? m[1] : "ok");
}
const EMPTY: SensorIn = { key: "", name: "", kind: "value", unit: "", protocol: "http", address: {}, low_alarm: null, high_alarm: null, stale_after_s: 600, enabled: true };

/** Digital twin: SCADA o'lchovlari jonli (WebSocket), alarmlar, tarix, elementga bog'lash, 3D rang. */
export default function MonitoringPanel({ projectId, modelId, versionId, role, viewer, selection }: Props) {
  // UX-11: sensorlar umumiy jonli store da (bitta soket loyiha uchun); panel faqat o'z modeli sensorlariga obuna
  const [ids, setIds] = useState<number[]>([]);
  const sensors = useSensorsByIds(projectId, ids);
  const [selected, setSelected] = useState<number | null>(null);
  const [hours, setHours] = useState(24);
  const [history, setHistory] = useState<ReadingPoint[]>([]);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<SensorIn | null>(null);
  const [editId, setEditId] = useState<number | null>(null);
  const [showKeys, setShowKeys] = useState(false);
  const [manual, setManual] = useState("");
  const [cmdTarget, setCmdTarget] = useState<Sensor | null>(null); // boshqaruv buyrug'i (F8: ControlBlock dialogda)
  // 3D da element tanlansa — unga bog'langan sensor ochiladi (BIM → SCADA)
  useEffect(() => {
    const g = selection[0]?.guid;
    if (!g) return;
    const s = sensors.find((x) => x.element_guid === g);
    if (s) setSelected(s.id);
  }, [selection, sensors]);
  const [topic, setTopic] = useState("");
  const canEdit = role === "engineer" || role === "approver";

  const load = useCallback(() => api.sensors(projectId, modelId).then((ss) => { putSensors(projectId, ss); setIds(ss.map((s) => s.id)); }).catch((e) => setError(e.message)), [projectId, modelId]);
  useEffect(() => { void load(); }, [load]);

  // Jonli oqim — umumiy store (F4: heartbeat, LIVE/STALE/OFFLINE, eksponensial qayta ulanish; UX-11: bitta soket)
  const live = useProjectLive(projectId);
  useLiveMessages(projectId, (m) => {
    if (m.type === "reading" && m.sensor_id === selected && m.ts && m.value != null) {
      const pt = { ts: m.ts, v: m.value, min: m.value, max: m.value };
      setHistory((h) => [...h, pt].slice(-2000));
    }
  });

  // Tarix
  useEffect(() => {
    if (selected == null) return setHistory([]);
    api.readings(selected, hours).then((r) => setHistory(r.points)).catch((e) => setError(e.message));
  }, [selected, hours]);

  // --- Vaqt mashinasi (replay): tarixdan tanlangan vaqtdagi qiymatlar 3D ga (yorliqlar, ranglar, suv, darvozalar)
  const [replay, setReplay] = useState<{ on: boolean; hours: number; t: number; data: Record<number, ReadingPoint[]>; loading: boolean }>({ on: false, hours: 24, t: 1, data: {}, loading: false });
  const latestSensors = useLatest(sensors);
  const sensorIdsKey = sensors.map((s) => (s.enabled ? s.id : -s.id)).join(","); // ro'yxat o'zgarganda qayta yuklash, har jonli qiymatda emas
  useEffect(() => {
    if (!replay.on) return;
    let dead = false;
    setReplay((r) => ({ ...r, loading: true }));
    Promise.all(latestSensors.current.filter((s) => s.enabled).map((s) => api.readings(s.id, replay.hours, 600).then((r) => [s.id, r.points] as const).catch(() => [s.id, []] as const)))
      .then((rows) => { if (!dead) setReplay((r) => ({ ...r, data: Object.fromEntries(rows), loading: false })); });
    return () => { dead = true; };
  }, [replay.on, replay.hours, sensorIdsKey, latestSensors]);
  const replayTime = replay.on ? Date.now() - replay.hours * 3600e3 * (1 - replay.t) : null;
  /** Ko'rsatiladigan sensorlar: jonli yoki tarixdagi vaqt bo'yicha (oxirgi o'qish ≤ t; alarm chegaralar bo'yicha) */
  // useMemo (F11): har renderda yangi massiv bo'lmasin — 3D effektlar (rang, yorliq, suv) faqat o'zgarishda ishlaydi
  const view: Sensor[] = useMemo(() => replayTime == null ? sensors : sensors.map((s) => {
    const pts = replay.data[s.id] ?? [];
    let v: ReadingPoint | null = null;
    for (const pt of pts) { if (new Date(pt.ts).getTime() <= replayTime) v = pt; else break; }
    if (!v) return { ...s, last_value: null, last_ts: null, alarm: "ok" as AlarmState, stale: true };
    const alarm: AlarmState = s.hh_alarm != null && v.v > s.hh_alarm ? "highhigh" : s.high_alarm != null && v.v > s.high_alarm ? "high" : s.ll_alarm != null && v.v < s.ll_alarm ? "lowlow" : s.low_alarm != null && v.v < s.low_alarm ? "low" : "ok";
    return { ...s, last_value: v.v, last_ts: v.ts, alarm };
  }), [sensors, replayTime, replay.data]);

  // Raqamli egizak 3D da: yuqori byef sathi sensori (dispetcher sxemasi bog'lanishi) → suv tekisligi
  const [waterOn, setWaterOn] = useState(true);
  const [upstreamId, setUpstreamId] = useState<number | null>(null);
  useEffect(() => { api.dashboard(projectId).then((d) => setUpstreamId(d.mimic.upstream_level ?? null)).catch(() => setUpstreamId(null)); }, [projectId]);
  useEffect(() => {
    if (!viewer) return;
    const s = view.find((x) => x.id === upstreamId);
    viewer.setWaterLevel(waterOn && s && s.last_value != null && !s.stale ? s.last_value : null, { upstreamOnly: true });
  }, [viewer, view, upstreamId, waterOn]);
  useEffect(() => () => { viewer?.setWaterLevel(null); }, [viewer]);

  // 3D: sensor bog'langan elementlar alarm rangi; «sog'liq» rejimida aktivlar sog'liq indeksi rangi
  const [healthOn, setHealthOn] = useState(false);
  useEffect(() => {
    if (!viewer) return;
    const colors: Record<string, string> = {};
    for (const s of view) if (s.element_guid && s.enabled) colors[s.element_guid] = alarmHex(s);
    if (!healthOn) { void viewer.colorByGuids(colors); return; }
    api.health(projectId).then((h) => {
      for (const a of h.assets) if (a.element_guid) colors[a.element_guid] = hexOf(a.level === "yaxshi" ? "ok" : a.level === "qoniqarli" ? "warn" : "danger");
      void viewer.colorByGuids(colors);
    }).catch(() => void viewer.colorByGuids(colors));
  }, [view, viewer, healthOn, projectId]);
  // 3D: elementlar ustida jonli qiymatlar (sensor nomi + qiymat, alarm rangi)
  const [valuesOn, setValuesOn] = useState(true);
  useEffect(() => {
    if (!viewer) return;
    if (!valuesOn) { void viewer.setValueLabels(null); return; }
    const byGuid = new Map<string, { texts: string[]; color: string; alarm: boolean }>();
    for (const s of view) {
      if (!s.element_guid || !s.enabled) continue;
      const e = byGuid.get(s.element_guid) ?? { texts: [] as string[], color: alarmHex(s), alarm: false };
      e.texts.push(`${s.name}: ${s.last_value != null ? fmtVal(s.last_value) : "—"} ${s.unit}`.trim());
      if (s.alarm !== "ok") { e.color = alarmHex(s); e.alarm = e.alarm || isAlarm(s.alarm); }
      byGuid.set(s.element_guid, e);
    }
    void viewer.setValueLabels([...byGuid].map(([guid, e]) => ({ guid, text: e.texts.join(" · "), color: e.color, alarm: e.alarm })));
  }, [view, viewer, valuesOn]);
  // 3D animatsiya (HMI): darvoza ochilishi, agregat ishlashi, quvurdagi oqim — bog'langan sensorlar bo'yicha
  const [animOn, setAnimOn] = useState(true);
  useEffect(() => {
    if (!viewer) return;
    if (!animOn) { void viewer.setLiveBindings(null); return; }
    const items = view.filter((s) => s.element_guid && s.enabled && (s.kind === "position" || s.kind === "status" || s.kind === "power" || s.kind === "flow") && !s.stale)
      .map((s) => ({ guid: s.element_guid!, kind: s.kind, value: s.last_value }));
    void viewer.setLiveBindings(items);
  }, [view, viewer, animOn]);
  useEffect(() => () => { void viewer?.colorByGuids({}); void viewer?.setValueLabels(null); void viewer?.setLiveBindings(null); }, [viewer]);

  /** Yoziladigan nuqta chegaralari: chekli min ≤ max (SCADA-02) — aks holda saqlanmaydi (server ham 422). */
  const spError = editing?.writable ? setpointRangeError(editing.min_setpoint, editing.max_setpoint) : null;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!editing) return;
    try {
      const body = { ...editing, model_id: modelId, address: editing.protocol === "mqtt" ? { ...editing.address, topic } : editing.address };
      const put = (force: boolean) => (editId == null ? api.createSensor(projectId, body, force) : api.updateSensor(editId, body, force));
      try {
        await put(false);
      } catch (err) {
        // SCADA-13: GUID joriy versiyada yo'q — qurilishdan oldingi element bo'lishi mumkin: ongli tasdiq bilan saqlash
        if (!(err instanceof ApiError && err.status === 422 && /element_guid/.test(err.message))) throw err;
        if (!(await dialogs.confirm("Element joriy versiyada topilmadi", { text: `${err.message}\n\nHali modelda yo'q (qurilishi rejalashtirilgan) element bo'lsa — baribir saqlang; aks holda GUID ni tekshiring.`, ok: "Baribir saqlash" }))) return;
        await put(true);
      }
      setEditing(null);
      setEditId(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Xatolik");
    }
  }

  async function bindToSelection(s: Sensor) {
    const guid = selection[0]?.guid;
    if (!guid) return setError("Avval 3D da elementni tanlang");
    try { await api.updateSensor(s.id, { element_guid: guid }); await load(); } catch (err) { setError(err instanceof Error ? err.message : "Xatolik"); }
  }

  async function pushManual(s: Sensor) {
    const v = Number(manual);
    if (!Number.isFinite(v)) return;
    try { await api.pushReadings(projectId, [{ sensor_id: s.id, value: v }]); setManual(""); } catch (err) { setError(err instanceof Error ? err.message : "Xatolik"); }
  }

  const alarms = view.filter((s) => s.enabled && s.alarm !== "ok");

  return (
    <div className="mon">
      <BPanel id="mon-view" title="Jonli holat" right={<span className={`badge live-${live.toLowerCase()} ${live === "LIVE" ? "published" : live === "STALE" ? "shared" : "rejected"}`} title="Jonli oqim: LIVE — xabar yaqinda; STALE — heartbeat kechikmoqda; OFFLINE — uzilgan">{live}</span>}>
        <BRow label="Sensorlar" value={`${sensors.length} sensor · ${alarms.length} alarm`} />
        {upstreamId != null && <BRow label="Suv sathi 3D"><input type="checkbox" checked={waterOn} onChange={(e) => setWaterOn(e.target.checked)} title="Raqamli egizak: yuqori byef sathi sensoridan 3D da suv tekisligi" /></BRow>}
        <BRow label="Sog'liq rangi"><input type="checkbox" checked={healthOn} onChange={(e) => setHealthOn(e.target.checked)} title="Aktivlar sog'liq indeksi bo'yicha 3D da bo'yash (yashil / sariq / qizil)" /></BRow>
        <BRow label="Qiymatlar 3D da"><input type="checkbox" checked={valuesOn} onChange={(e) => setValuesOn(e.target.checked)} title="Elementlar ustida jonli qiymat yorliqlari (sensor nomi va qiymati, alarm rangi)" /></BRow>
        <BRow label="Animatsiya"><input type="checkbox" checked={animOn} onChange={(e) => setAnimOn(e.target.checked)} title="HMI animatsiya: darvoza ochilishi, agregat aylanishi, quvurdagi oqim" /></BRow>
        <BRow label="Vaqt mashinasi"><input type="checkbox" checked={replay.on} onChange={(e) => setReplay((r) => ({ ...r, on: e.target.checked, t: 1 }))} title="Tarixdagi istalgan vaqtdagi holatni 3D da ko'rish (hodisa tahlili)" /></BRow>
        <BOps>
          {canEdit && <button className="btn sm primary" onClick={() => { setEditing({ ...EMPTY, element_guid: selection[0]?.guid ?? null }); setEditId(null); setTopic(""); }}><Icon name="plus" size={12} /> Sensor</button>}
          {canEdit && <label className="btn sm" title="SCADA teglar ro'yxati (CSV: key;name;kind;unit;protocol;address;element;low;high) — element nomi bo'yicha 3D ga avtomatik bog'lanadi"><Icon name="upload" size={12} /> CSV import<input type="file" accept=".csv,text/csv" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (!f) return; f.text().then((t) => api.importSensors(projectId, t, modelId)).then(async (r) => { setError(`Import: ${r.created} yangi, ${r.updated} yangilandi, ${r.bound} ta 3D ga bog'landi${r.errors.length ? `; xatolar: ${r.errors.slice(0, 3).join(" | ")}` : ""}`); await load(); }).catch((err) => setError(err instanceof Error ? err.message : "Import xatosi")); }} /></label>}
          {can(role, "gateway.keys") && <button className="btn sm" onClick={() => setShowKeys(true)}><Icon name="lock" size={12} /> Ulanish kalitlari</button>}
        </BOps>
      </BPanel>
      {replay.on && (
        <div className="section-box small mb-8">
          <div className="row items-center gap-8 flex-wrap">
            <b>Vaqt mashinasi</b>
            <select className="select sm" value={replay.hours} onChange={(e) => setReplay((r) => ({ ...r, hours: Number(e.target.value) }))}>{[6, 24, 72, 168, 720].map((h) => <option key={h} value={h}>{h < 24 ? `${h} soat` : `${h / 24} kun`}</option>)}</select>
            <span className="mono small">{replayTime != null ? fmtDate(new Date(replayTime).toISOString()) : ""}</span>
            {replay.loading && <span className="dim small">yuklanmoqda…</span>}
          </div>
          <div className="row items-center gap-6">
            <button className="btn sm" title="1 qadam orqaga" onClick={() => setReplay((r) => ({ ...r, t: Math.max(0, r.t - 0.01) }))}>◀</button>
            <input type="range" className="grow" min={0} max={1000} value={Math.round(replay.t * 1000)} onChange={(e) => setReplay((r) => ({ ...r, t: Number(e.target.value) / 1000 }))} aria-label="Vaqt" />
            <button className="btn sm" title="1 qadam oldinga" onClick={() => setReplay((r) => ({ ...r, t: Math.min(1, r.t + 0.01) }))}>▶</button>
          </div>
          <div className="dim small">Slayder — tanlangan vaqtdagi o'qishlar 3D ga (yorliqlar, ranglar, suv sathi, darvozalar, agregatlar); jonli oqim vaqtincha ko'rsatilmaydi.</div>
        </div>
      )}
      {error && <p className="error small">{error} <button type="button" className="link-btn" onClick={() => setError("")}>yopish</button></p>}
      {showKeys && (
        <div className="section-box small">
          <b>Gateway kalitlari</b> — ikkita alohida kalit: <code>ingest</code> faqat o'lchov yuboradi (<code>X-Ingest-Key</code>), <code>command</code> buyruq kanali (<code>X-Command-Key</code>: claim/ack/readback). Kalitni faqat gateway hostida saqlang (<code>GES_GATEWAY_INGEST_KEY</code>, <code>GES_GATEWAY_COMMAND_KEY</code>).
          <GatewayKeys projectId={projectId} canManage={can(role, "gateway.keys")} />
          <div className="row"><button className="btn sm" onClick={() => setShowKeys(false)}>Yopish</button></div>
        </div>
      )}

      <UnlinkedSensors projectId={projectId} versionId={versionId ?? null} refresh={ids.length} canEdit={canEdit} selectionGuid={selection[0]?.guid ?? null}
        onBind={async (id, guid) => { try { await api.updateSensor(id, { element_guid: guid }); await load(); } catch (err) { setError(err instanceof Error ? err.message : "Xatolik"); } }} />
      {sensors.length === 0 && <p className="muted">Sensor yo'q. {canEdit ? "«Sensor qo'shish» — SCADA tegi nomi (kalit), turi, alarm chegaralari." : ""}</p>}
      {view.map((s) => (
        <div key={s.id} className={`list-item${selected === s.id ? " selected" : ""}`}>
          <button type="button" className="list-item-head" aria-expanded={selected === s.id} onClick={() => setSelected(selected === s.id ? null : s.id)}>
          <span className="title">
            <i className="dot" style={{ background: alarmStyle(s.alarm, s.priority).color }} title={alarmStyle(s.alarm, s.priority).label} />{alarmStyle(s.alarm, s.priority).code && <span className="alarm-mark" style={{ color: alarmStyle(s.alarm, s.priority).color }}>{alarmStyle(s.alarm, s.priority).glyph}{alarmStyle(s.alarm, s.priority).code}</span>}
            <b>{s.name}</b>
            <span className="grow" />
            <span className="mono">{s.last_value != null ? `${fmtVal(s.last_value)} ${s.unit}` : "—"}</span>
            <span className={`badge ${s.stale ? "archived" : s.alarm === "ok" ? "published" : "rejected"}`}>{alarmLabel(s.alarm)}</span>
          </span>
          <span className="meta">
            <span className="mono">{s.key}</span> · {sensorKindLabel(s.kind)}
            {s.last_ts && <> · {fmtDate(s.last_ts)}</>}
            {s.element_guid ? " · elementga bog'langan" : " · element bog'lanmagan"}
            {s.protocol === "mqtt" && <> · mqtt:{String(s.address.topic ?? "")}</>}
          </span>
          </button>
          {selected === s.id && (
            <div className="list-item-body">
              <div className="row wrap mb-6">
                {[1, 24, 168, 720].map((h) => <button key={h} className={`btn sm${hours === h ? " active" : ""}`} onClick={() => setHours(h)}>{h === 1 ? "1 soat" : h === 24 ? "1 kun" : h === 168 ? "1 hafta" : "1 oy"}</button>)}
                {s.element_guid && <button className="btn sm" onClick={() => viewer?.selectByGuids([s.element_guid!], true)}>3D da ko'rsatish</button>}
                {s.alarm !== "ok" && canEdit && <button className="btn sm" title="Alarm bo'yicha ish buyrug'i (CMMS): sensor, qiymat, element" onClick={() => api.createWorkOrder(projectId, { title: `${s.name}: ${alarmLabel(s.alarm)}${s.last_value != null ? ` (${fmtVal(s.last_value)} ${s.unit})` : ""}`, description: `Alarm ${alarmLabel(s.alarm)} — sensor ${s.key}${s.element_guid ? `, element GUID ${s.element_guid}` : ""}. 3D: /models/${modelId}?sel=${s.element_guid ?? ""}&tab=mon`, priority: s.alarm === "stale" ? "medium" : "high", source: "alarm" }).then((w) => setError(`Ish buyrug'i #${w.id} yaratildi (Dispetcher paneli → Ish buyruqlari)`)).catch((err) => setError(err instanceof Error ? err.message : "Xatolik"))}>Ish buyrug'i</button>}
                {canEdit && <button className="btn sm" onClick={() => bindToSelection(s)} title="Tanlangan elementga bog'lash">Tanlanganga bog'lash</button>}
                {canEdit && <button className="btn sm" onClick={() => { setEditing({ key: s.key, name: s.name, kind: s.kind, unit: s.unit, protocol: s.protocol, address: s.address, low_alarm: s.low_alarm, high_alarm: s.high_alarm, ll_alarm: s.ll_alarm ?? null, hh_alarm: s.hh_alarm ?? null, deadband: s.deadband ?? 0, on_delay_s: s.on_delay_s ?? 0, off_delay_s: s.off_delay_s ?? 0, roc_limit_per_min: s.roc_limit_per_min ?? null, stale_after_s: s.stale_after_s, enabled: s.enabled, element_guid: s.element_guid, priority: s.priority, writable: s.writable, min_setpoint: s.min_setpoint ?? null, max_setpoint: s.max_setpoint ?? null, max_rate_per_min: s.max_rate_per_min ?? null }); setEditId(s.id); setTopic(String(s.address.topic ?? "")); }}>Tahrirlash</button>}
                {role === "approver" && <button className="btn sm danger" onClick={() => void dialogs.confirm("Sensorni o'chirish", { text: `${s.name} (${s.key}) — tarix ham o'chadi.`, danger: true, ok: "O'chirish" }).then((ok) => { if (ok) void api.deleteSensor(s.id).then(load); })}>O'chirish</button>}
              </div>
              {history.length > 1 ? (
                <LineChart title={s.name} unit={s.unit} x={history.map((p) => fmtShort(p.ts))} series={[{ name: s.name, values: history.map((p) => p.v) }]}
                  refLines={[...(s.hh_alarm != null ? [{ value: s.hh_alarm, label: "HH" }] : []), ...(s.high_alarm != null ? [{ value: s.high_alarm, label: "yuqori" }] : []), ...(s.low_alarm != null ? [{ value: s.low_alarm, label: "past" }] : []), ...(s.ll_alarm != null ? [{ value: s.ll_alarm, label: "LL" }] : [])]} />
              ) : <p className="dim small">Bu davrda o'lchov yo'q.</p>}
              {s.writable && canCommandRole(role) && (
                <div className="row mt-6 items-center gap-6 flex-wrap" title="Supervisory control: buyruq gateway orqali SCADA ga yuboriladi (pending → sent → acked), audit jurnalida">
                  <b className="small">Boshqaruv</b>
                  <span className="dim small">joriy {s.last_value == null ? "—" : s.last_value} {s.unit}</span>
                  <button className="btn sm primary" onClick={() => setCmdTarget(s)}>Buyruq (select → execute)…</button>
                </div>
              )}
              {can(role, "scada.manual_entry") && (
                <div className="row mt-4 flex-wrap gap-4" title="SCADA-07: qo'lda kiritish — sifat 'manual', auditda">
                  <input className="input w-120" placeholder="Qiymat" value={manual} onChange={(e) => setManual(e.target.value)} onKeyDown={(e) => e.key === "Enter" && pushManual(s)} />
                  <button className="btn sm" onClick={() => pushManual(s)}>Qo'lda yuborish</button>
                  <label className="btn sm">CSV import<input type="file" accept=".csv,text/csv" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) api.importReadings(s.id, f).then((r) => { setError(""); setHours((h) => h); void dialogs.alert("CSV import", `${r.accepted} o'lchov yuklandi`); }).catch((err) => setError(err.message)); }} /></label>
                </div>
              )}
            </div>
          )}
        </div>
      ))}

      {editing && (
        <Dialog title={editId == null ? "Yangi sensor" : "Sensorni tahrirlash"} onClose={() => setEditing(null)}>
          <form onSubmit={save}>
            <div className="row">
              <label className="field grow"><span>Kalit (SCADA teg nomi)</span><input className="input mono" value={editing.key} onChange={(e) => setEditing({ ...editing, key: e.target.value })} required pattern="[A-Za-z0-9_.\-/:]+" disabled={editId != null} /></label>
              <label className="field grow"><span>Nomi</span><input className="input" value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} required /></label>
            </div>
            <div className="row">
              <label className="field grow"><span>Turi</span>
                <select className="select" value={editing.kind} onChange={(e) => { const k = KINDS.find((x) => x.id === e.target.value)!; setEditing({ ...editing, kind: k.id, unit: editing.unit || k.unit }); }}>
                  {KINDS.map((k) => <option key={k.id} value={k.id}>{sensorKindLabel(k.id)}</option>)}
                </select>
              </label>
              <label className="field w-90"><span>Birlik</span><input className="input" value={editing.unit} onChange={(e) => setEditing({ ...editing, unit: e.target.value })} /></label>
            </div>
            <div className="row">
              <label className="field grow"><span>Past alarm</span><input className="input" type="number" step="any" value={editing.low_alarm ?? ""} onChange={(e) => setEditing({ ...editing, low_alarm: e.target.value === "" ? null : Number(e.target.value) })} /></label>
              <label className="field grow"><span>Yuqori alarm</span><input className="input" type="number" step="any" value={editing.high_alarm ?? ""} onChange={(e) => setEditing({ ...editing, high_alarm: e.target.value === "" ? null : Number(e.target.value) })} /></label>
              <label className="field grow"><span>Uzilgan deb hisoblash, s</span><input className="input" type="number" value={editing.stale_after_s} onChange={(e) => setEditing({ ...editing, stale_after_s: Number(e.target.value) || 600 })} /></label>
            </div>
            <div className="row" title="ISA-18.2: LL/HH — ikkinchi bosqich; o'lik zona — chegarada tebranish chatter qilmasin; kechikishlar — qisqa sakrashlar alarm bermasin; ROC — o'zgarish tezligi (birlik/daqiqa)">
              <label className="field grow"><span>LL</span><input className="input" type="number" step="any" value={editing.ll_alarm ?? ""} onChange={(e) => setEditing({ ...editing, ll_alarm: e.target.value === "" ? null : Number(e.target.value) })} /></label>
              <label className="field grow"><span>HH</span><input className="input" type="number" step="any" value={editing.hh_alarm ?? ""} onChange={(e) => setEditing({ ...editing, hh_alarm: e.target.value === "" ? null : Number(e.target.value) })} /></label>
              <label className="field grow"><span>O'lik zona</span><input className="input" type="number" step="any" min={0} value={editing.deadband ?? 0} onChange={(e) => setEditing({ ...editing, deadband: Math.max(0, Number(e.target.value) || 0) })} /></label>
              <label className="field grow"><span>Kirish kechikishi, s</span><input className="input" type="number" min={0} value={editing.on_delay_s ?? 0} onChange={(e) => setEditing({ ...editing, on_delay_s: Math.max(0, Number(e.target.value) || 0) })} /></label>
              <label className="field grow"><span>Qaytish kechikishi, s</span><input className="input" type="number" min={0} value={editing.off_delay_s ?? 0} onChange={(e) => setEditing({ ...editing, off_delay_s: Math.max(0, Number(e.target.value) || 0) })} /></label>
              <label className="field grow"><span>ROC, birlik/daq</span><input className="input" type="number" step="any" min={0} value={editing.roc_limit_per_min ?? ""} onChange={(e) => setEditing({ ...editing, roc_limit_per_min: e.target.value === "" ? null : Math.abs(Number(e.target.value)) || null })} /></label>
            </div>
            <div className="row">
              <label className="field grow"><span>Alarm ustuvorligi</span>
                <select className="select" value={editing.priority ?? "medium"} onChange={(e) => setEditing({ ...editing, priority: e.target.value as SensorIn["priority"] })}>
                  <option value="low">Past</option><option value="medium">O'rta</option><option value="high">Muhim (ovoz)</option><option value="critical">Kritik (ovoz)</option>
                </select>
              </label>
              <label className="field grow" title="Dispetcher shu nuqtaga buyruq (setpoint) yubora oladi — gateway SCADA ga yozadi"><span>Boshqaruv nuqtasi</span>
                <select className="select" value={editing.writable ? "1" : "0"} onChange={(e) => setEditing({ ...editing, writable: e.target.value === "1" })}>
                  <option value="0">Faqat o'qish</option><option value="1">Yozish mumkin (setpoint)</option>
                </select>
              </label>
            </div>
            {editing.writable && (
              <div className="row" title="SCADA-02: boshqaruv chegaralari majburiy — server min ≤ max bo'lmasa rad etadi (422)">
                <label className="field grow"><span>Min topshiriq, {editing.unit || "birlik"}</span><input className="input" type="number" step="any" required value={editing.min_setpoint ?? ""} onChange={(e) => setEditing({ ...editing, min_setpoint: e.target.value === "" ? null : Number(e.target.value) })} data-testid="sp-min" /></label>
                <label className="field grow"><span>Maks topshiriq, {editing.unit || "birlik"}</span><input className="input" type="number" step="any" required value={editing.max_setpoint ?? ""} onChange={(e) => setEditing({ ...editing, max_setpoint: e.target.value === "" ? null : Number(e.target.value) })} data-testid="sp-max" /></label>
                <label className="field grow"><span>Tezlik ≤, /daq (ixtiyoriy)</span><input className="input" type="number" step="any" min={0} value={editing.max_rate_per_min ?? ""} onChange={(e) => setEditing({ ...editing, max_rate_per_min: e.target.value === "" ? null : Math.abs(Number(e.target.value)) || null })} /></label>
              </div>
            )}
            {spError && <p className="error small" role="alert" data-testid="sp-error">{spError}</p>}
            <div className="row">
              <label className="field grow"><span>Manba</span>
                <select className="select" value={editing.protocol} onChange={(e) => setEditing({ ...editing, protocol: e.target.value as SensorIn["protocol"] })}>
                  <option value="http">HTTP push (gateway/SCADA skripti)</option>
                  <option value="mqtt">MQTT topic</option>
                  <option value="csv">CSV import (qo'lda)</option>
                  <option value="opcua">OPC UA (gateway)</option>
                  <option value="modbus">Modbus TCP (gateway)</option>
                  <option value="twin">Raqamli egizak (avtomatik)</option>
                </select>
              </label>
              {editing.protocol === "mqtt" && <label className="field grow"><span>Topic</span><input className="input mono" value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="ges/agg1/power" /></label>}
            </div>
            <p className="dim small">Element: {editing.element_guid ?? (selection[0]?.guid ? `tanlangan — ${selection[0].name}` : "keyin «Tanlanganga bog'lash» bilan")}</p>
            {editId == null && selection[0]?.guid && <label className="row small"><input type="checkbox" defaultChecked onChange={(e) => setEditing({ ...editing, element_guid: e.target.checked ? selection[0].guid : null })} /> tanlangan elementga bog'lash</label>}
            <div className="actions">
              <button type="button" className="btn" onClick={() => setEditing(null)}>Bekor qilish</button>
              <button type="submit" className="btn primary" disabled={!!spError}>Saqlash</button>
            </div>
          </form>
        </Dialog>
      )}
      {cmdTarget && (
        <Dialog title={`Buyruq: ${cmdTarget.name}`} onClose={() => setCmdTarget(null)}>
          <ControlBlock projectId={projectId} sensor={cmdTarget} canCommand={canCommandRole(role)} canOverride={can(role, "scada.interlock.override")} onCommand={(c) => { setError(`Buyruq #${c.id}: ${c.status}`); setCmdTarget(null); }} />
        </Dialog>
      )}
    </div>
  );
}

/** SCADA-13: element GUID i ochiq versiyada yo'q sensorlar — qayta bog'lash (tanlangan elementga). */
function UnlinkedSensors({ projectId, versionId, refresh, canEdit, selectionGuid, onBind }: { projectId: number; versionId: number | null; refresh: number; canEdit: boolean; selectionGuid: string | null; onBind: (sensorId: number, guid: string) => Promise<void> }) {
  const [rep, setRep] = useState<UnlinkedReport | null>(null);
  useEffect(() => {
    let dead = false;
    api.unlinkedSensors(projectId, versionId).then((r) => { if (!dead) setRep(r); }).catch(() => { if (!dead) setRep(null); }); // eski server — endpoint yo'q
    return () => { dead = true; };
  }, [projectId, versionId, refresh]);
  if (!rep || rep.count === 0) return null;
  return (
    <div className="verdict warn attention" data-testid="unlinked-sensors">
      <Icon name="alert-triangle" size={16} />
      <div className="grow">
        <b>Bog'lanmagan sensorlar: {rep.count} ta</b> <span className="dim small">— element GUID i {rep.version_id ? "ochiq versiyada" : "joriy versiyada"} topilmadi</span>
        <ul className="warnings">
          {rep.sensors.slice(0, 20).map((s) => (
            <li key={s.id}><span className="mono">{s.key}</span> {s.name} <span className="dim mono small">{s.element_guid}</span>
              {canEdit && <button className="btn sm" disabled={!selectionGuid} title={selectionGuid ? "3D da tanlangan elementga bog'lash" : "Avval 3D da elementni tanlang"} onClick={() => selectionGuid && void onBind(s.id, selectionGuid)}>Tanlanganga bog'lash</button>}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function setpointRangeError(min: number | null | undefined, max: number | null | undefined): string | null {
  if (min == null || max == null || !Number.isFinite(min) || !Number.isFinite(max)) return "Yoziladigan nuqta uchun min va maks topshiriq chegaralari majburiy";
  if (min > max) return "Min topshiriq maksimaldan katta bo'lmasligi kerak";
  return null;
}

function fmtVal(v: number) {
  return Math.abs(v) >= 1000 ? v.toFixed(0) : Math.abs(v) >= 100 ? v.toFixed(1) : v.toFixed(2);
}
