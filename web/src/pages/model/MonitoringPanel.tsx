import Icon from "../../ui/Icon";
import { BOps, BPanel, BRow } from "../../ui/BlenderUI";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type AlarmState, type LiveMessage, type ReadingPoint, type Role, type Sensor, type SensorIn, type SensorKind } from "../../api/client";
import type { SelectedItem, Viewer } from "../../viewer/Viewer";
import LineChart from "../../ui/LineChart";
import Dialog from "../../ui/Dialog";
import { fmtDate } from "../../ui/format";

interface Props {
  projectId: number;
  modelId: number;
  role: Role | null;
  viewer: Viewer | null;
  selection: SelectedItem[];
}

const KINDS: { id: SensorKind; title: string; unit: string }[] = [
  { id: "level", title: "Suv sathi", unit: "m" },
  { id: "flow", title: "Sarf", unit: "m³/s" },
  { id: "power", title: "Quvvat", unit: "MW" },
  { id: "pressure", title: "Bosim", unit: "bar" },
  { id: "temperature", title: "Harorat", unit: "°C" },
  { id: "vibration", title: "Tebranish", unit: "mm/s" },
  { id: "status", title: "Holat (0/1)", unit: "" },
  { id: "position", title: "Ochilish (darvoza, zatvor)", unit: "%" },
  { id: "value", title: "Boshqa", unit: "" },
];
const ALARM_LABEL: Record<AlarmState, string> = { ok: "normal", low: "past", high: "yuqori", stale: "uzilgan" };
const ALARM_COLOR: Record<AlarmState, string> = { ok: "#3aa864", low: "#e0656a", high: "#e0656a", stale: "#6a6e76" };
const EMPTY: SensorIn = { key: "", name: "", kind: "value", unit: "", protocol: "http", address: {}, low_alarm: null, high_alarm: null, stale_after_s: 600, enabled: true };

/** Digital twin: SCADA o'lchovlari jonli (WebSocket), alarmlar, tarix, elementga bog'lash, 3D rang. */
export default function MonitoringPanel({ projectId, modelId, role, viewer, selection }: Props) {
  const [sensors, setSensors] = useState<Sensor[]>([]);
  const [live, setLive] = useState<"ulanmoqda" | "jonli" | "uzildi">("ulanmoqda");
  const [selected, setSelected] = useState<number | null>(null);
  const [hours, setHours] = useState(24);
  const [history, setHistory] = useState<ReadingPoint[]>([]);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<SensorIn | null>(null);
  const [editId, setEditId] = useState<number | null>(null);
  const [ingest, setIngest] = useState<{ ingest_key: string; url: string } | null>(null);
  const [manual, setManual] = useState("");
  const [cmdVal, setCmdVal] = useState("0"); // boshqaruv buyrug'i qiymati
  // 3D da element tanlansa — unga bog'langan sensor ochiladi (BIM → SCADA)
  useEffect(() => {
    const g = selection[0]?.guid;
    if (!g) return;
    const s = sensors.find((x) => x.element_guid === g);
    if (s) { setSelected(s.id); setCmdVal(String(s.last_value ?? 0)); }
  }, [selection, sensors]);
  const [topic, setTopic] = useState("");
  const wsRef = useRef<WebSocket | null>(null);
  const canEdit = role === "engineer" || role === "approver";

  const load = useCallback(() => api.sensors(projectId, modelId).then(setSensors).catch((e) => setError(e.message)), [projectId, modelId]);
  useEffect(() => { void load(); }, [load]);

  // Jonli oqim — uzilsa 3 s dan keyin qayta ulanadi
  useEffect(() => {
    let closed = false;
    let timer: number | undefined;
    const connect = () => {
      const ws = api.liveSocket(projectId);
      wsRef.current = ws;
      ws.onopen = () => setLive("jonli");
      ws.onmessage = (ev) => {
        const m = JSON.parse(ev.data) as LiveMessage;
        if (m.type === "snapshot" && m.sensors) {
          setSensors((prev) => prev.map((s) => { const u = m.sensors!.find((x) => x.sensor_id === s.id); return u ? { ...s, last_value: u.value, last_ts: u.ts, alarm: u.alarm } : s; }));
        } else if (m.type === "reading" && m.sensor_id != null) {
          setSensors((prev) => prev.map((s) => (s.id === m.sensor_id ? { ...s, last_value: m.value ?? null, last_ts: m.ts ?? null, alarm: m.alarm ?? s.alarm } : s)));
          if (m.sensor_id === selected && m.ts && m.value != null) setHistory((h) => [...h, { ts: m.ts!, v: m.value!, min: m.value!, max: m.value! }].slice(-2000));
        }
      };
      ws.onclose = () => { setLive("uzildi"); if (!closed) timer = window.setTimeout(connect, 3000); };
      ws.onerror = () => ws.close();
    };
    connect();
    return () => { closed = true; window.clearTimeout(timer); wsRef.current?.close(); };
  }, [projectId, selected]);

  // Tarix
  useEffect(() => {
    if (selected == null) return setHistory([]);
    api.readings(selected, hours).then((r) => setHistory(r.points)).catch((e) => setError(e.message));
  }, [selected, hours]);

  // --- Vaqt mashinasi (replay): tarixdan tanlangan vaqtdagi qiymatlar 3D ga (yorliqlar, ranglar, suv, darvozalar)
  const [replay, setReplay] = useState<{ on: boolean; hours: number; t: number; data: Record<number, ReadingPoint[]>; loading: boolean }>({ on: false, hours: 24, t: 1, data: {}, loading: false });
  useEffect(() => {
    if (!replay.on) return;
    let dead = false;
    setReplay((r) => ({ ...r, loading: true }));
    Promise.all(sensors.filter((s) => s.enabled).map((s) => api.readings(s.id, replay.hours, 600).then((r) => [s.id, r.points] as const).catch(() => [s.id, []] as const)))
      .then((rows) => { if (!dead) setReplay((r) => ({ ...r, data: Object.fromEntries(rows), loading: false })); });
    return () => { dead = true; };
  }, [replay.on, replay.hours, sensors.length]); // eslint-disable-line react-hooks/exhaustive-deps
  const replayTime = replay.on ? Date.now() - replay.hours * 3600e3 * (1 - replay.t) : null;
  /** Ko'rsatiladigan sensorlar: jonli yoki tarixdagi vaqt bo'yicha (oxirgi o'qish ≤ t; alarm chegaralar bo'yicha) */
  const view: Sensor[] = replayTime == null ? sensors : sensors.map((s) => {
    const pts = replay.data[s.id] ?? [];
    let v: ReadingPoint | null = null;
    for (const pt of pts) { if (new Date(pt.ts).getTime() <= replayTime) v = pt; else break; }
    if (!v) return { ...s, last_value: null, last_ts: null, alarm: "stale" as AlarmState };
    const alarm: AlarmState = s.high_alarm != null && v.v > s.high_alarm ? "high" : s.low_alarm != null && v.v < s.low_alarm ? "low" : "ok";
    return { ...s, last_value: v.v, last_ts: v.ts, alarm };
  });

  // Raqamli egizak 3D da: yuqori byef sathi sensori (dispetcher sxemasi bog'lanishi) → suv tekisligi
  const [waterOn, setWaterOn] = useState(true);
  const [upstreamId, setUpstreamId] = useState<number | null>(null);
  useEffect(() => { api.dashboard(projectId).then((d) => setUpstreamId(d.mimic.upstream_level ?? null)).catch(() => setUpstreamId(null)); }, [projectId]);
  useEffect(() => {
    if (!viewer) return;
    const s = view.find((x) => x.id === upstreamId);
    viewer.setWaterLevel(waterOn && s && s.last_value != null && s.alarm !== "stale" ? s.last_value : null, { upstreamOnly: true });
  }, [viewer, view, upstreamId, waterOn]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => { viewer?.setWaterLevel(null); }, [viewer]);

  // 3D: sensor bog'langan elementlar alarm rangi; «sog'liq» rejimida aktivlar sog'liq indeksi rangi
  const [healthOn, setHealthOn] = useState(false);
  useEffect(() => {
    if (!viewer) return;
    const colors: Record<string, string> = {};
    for (const s of view) if (s.element_guid && s.enabled) colors[s.element_guid] = ALARM_COLOR[s.alarm];
    if (!healthOn) { void viewer.colorByGuids(colors); return; }
    api.health(projectId).then((h) => {
      for (const a of h.assets) if (a.element_guid) colors[a.element_guid] = a.level === "yaxshi" ? "#3aa864" : a.level === "qoniqarli" ? "#b98626" : "#d95c5c";
      void viewer.colorByGuids(colors);
    }).catch(() => void viewer.colorByGuids(colors));
  }, [view, viewer, healthOn, projectId]); // eslint-disable-line react-hooks/exhaustive-deps
  // 3D: elementlar ustida jonli qiymatlar (sensor nomi + qiymat, alarm rangi)
  const [valuesOn, setValuesOn] = useState(true);
  useEffect(() => {
    if (!viewer) return;
    if (!valuesOn) { void viewer.setValueLabels(null); return; }
    const byGuid = new Map<string, { texts: string[]; color: string }>();
    for (const s of view) {
      if (!s.element_guid || !s.enabled) continue;
      const e = byGuid.get(s.element_guid) ?? { texts: [], color: ALARM_COLOR[s.alarm] };
      e.texts.push(`${s.name}: ${s.last_value != null ? fmtVal(s.last_value) : "—"} ${s.unit}`.trim());
      if (s.alarm !== "ok") e.color = ALARM_COLOR[s.alarm];
      byGuid.set(s.element_guid, e);
    }
    void viewer.setValueLabels([...byGuid].map(([guid, e]) => ({ guid, text: e.texts.join(" · "), color: e.color, alarm: e.color === ALARM_COLOR.high })));
  }, [view, viewer, valuesOn]); // eslint-disable-line react-hooks/exhaustive-deps
  // 3D animatsiya (HMI): darvoza ochilishi, agregat ishlashi, quvurdagi oqim — bog'langan sensorlar bo'yicha
  const [animOn, setAnimOn] = useState(true);
  useEffect(() => {
    if (!viewer) return;
    if (!animOn) { void viewer.setLiveBindings(null); return; }
    const items = view.filter((s) => s.element_guid && s.enabled && (s.kind === "position" || s.kind === "status" || s.kind === "power" || s.kind === "flow") && s.alarm !== "stale")
      .map((s) => ({ guid: s.element_guid!, kind: s.kind, value: s.last_value }));
    void viewer.setLiveBindings(items);
  }, [view, viewer, animOn]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => { void viewer?.colorByGuids({}); void viewer?.setValueLabels(null); void viewer?.setLiveBindings(null); }, [viewer]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!editing) return;
    try {
      const body = { ...editing, model_id: modelId, address: editing.protocol === "mqtt" ? { ...editing.address, topic } : editing.address };
      if (editId == null) await api.createSensor(projectId, body);
      else await api.updateSensor(editId, body);
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
      <BPanel id="mon-view" title="Jonli holat" right={<span className={`badge ${live === "jonli" ? "published" : live === "uzildi" ? "rejected" : ""}`}>{live}</span>}>
        <BRow label="Sensorlar" value={`${sensors.length} sensor · ${alarms.length} alarm`} />
        {upstreamId != null && <BRow label="Suv sathi 3D"><input type="checkbox" checked={waterOn} onChange={(e) => setWaterOn(e.target.checked)} title="Raqamli egizak: yuqori byef sathi sensoridan 3D da suv tekisligi" /></BRow>}
        <BRow label="Sog'liq rangi"><input type="checkbox" checked={healthOn} onChange={(e) => setHealthOn(e.target.checked)} title="Aktivlar sog'liq indeksi bo'yicha 3D da bo'yash (yashil / sariq / qizil)" /></BRow>
        <BRow label="Qiymatlar 3D da"><input type="checkbox" checked={valuesOn} onChange={(e) => setValuesOn(e.target.checked)} title="Elementlar ustida jonli qiymat yorliqlari (sensor nomi va qiymati, alarm rangi)" /></BRow>
        <BRow label="Animatsiya"><input type="checkbox" checked={animOn} onChange={(e) => setAnimOn(e.target.checked)} title="HMI animatsiya: darvoza ochilishi, agregat aylanishi, quvurdagi oqim" /></BRow>
        <BRow label="Vaqt mashinasi"><input type="checkbox" checked={replay.on} onChange={(e) => setReplay((r) => ({ ...r, on: e.target.checked, t: 1 }))} title="Tarixdagi istalgan vaqtdagi holatni 3D da ko'rish (hodisa tahlili)" /></BRow>
        <BOps>
          {canEdit && <button className="btn sm primary" onClick={() => { setEditing({ ...EMPTY, element_guid: selection[0]?.guid ?? null }); setEditId(null); setTopic(""); }}><Icon name="plus" size={12} /> Sensor</button>}
          {canEdit && <label className="btn sm" title="SCADA teglar ro'yxati (CSV: key;name;kind;unit;protocol;address;element;low;high) — element nomi bo'yicha 3D ga avtomatik bog'lanadi"><Icon name="upload" size={12} /> CSV import<input type="file" accept=".csv,text/csv" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (!f) return; f.text().then((t) => api.importSensors(projectId, t, modelId)).then(async (r) => { setError(`Import: ${r.created} yangi, ${r.updated} yangilandi, ${r.bound} ta 3D ga bog'landi${r.errors.length ? `; xatolar: ${r.errors.slice(0, 3).join(" | ")}` : ""}`); await load(); }).catch((err) => setError(err instanceof Error ? err.message : "Import xatosi")); }} /></label>}
          {role === "approver" && <button className="btn sm" onClick={() => api.ingestKey(projectId).then(setIngest).catch((e) => setError(e.message))}><Icon name="lock" size={12} /> Ulanish kaliti</button>}
        </BOps>
      </BPanel>
      {replay.on && (
        <div className="section-box small" style={{ marginBottom: 8 }}>
          <div className="row" style={{ alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <b>Vaqt mashinasi</b>
            <select className="select sm" value={replay.hours} onChange={(e) => setReplay((r) => ({ ...r, hours: Number(e.target.value) }))}>{[6, 24, 72, 168, 720].map((h) => <option key={h} value={h}>{h < 24 ? `${h} soat` : `${h / 24} kun`}</option>)}</select>
            <span className="mono small">{replayTime != null ? fmtDate(new Date(replayTime).toISOString()) : ""}</span>
            {replay.loading && <span className="dim small">yuklanmoqda…</span>}
          </div>
          <div className="row" style={{ alignItems: "center", gap: 6 }}>
            <button className="btn sm" title="1 qadam orqaga" onClick={() => setReplay((r) => ({ ...r, t: Math.max(0, r.t - 0.01) }))}>◀</button>
            <input type="range" className="grow" min={0} max={1000} value={Math.round(replay.t * 1000)} onChange={(e) => setReplay((r) => ({ ...r, t: Number(e.target.value) / 1000 }))} aria-label="Vaqt" />
            <button className="btn sm" title="1 qadam oldinga" onClick={() => setReplay((r) => ({ ...r, t: Math.min(1, r.t + 0.01) }))}>▶</button>
          </div>
          <div className="dim small">Slayder — tanlangan vaqtdagi o'qishlar 3D ga (yorliqlar, ranglar, suv sathi, darvozalar, agregatlar); jonli oqim vaqtincha ko'rsatilmaydi.</div>
        </div>
      )}
      {error && <p className="error small">{error} <a onClick={() => setError("")}>yopish</a></p>}
      {ingest && (
        <div className="section-box small">
          <b>SCADA/gateway ulanishi</b> — HTTP POST, sarlavha <code>X-Ingest-Key</code>:
          <pre className="mono" style={{ whiteSpace: "pre-wrap", margin: "4px 0" }}>{`curl -X POST ${location.origin}${ingest.url} \\
  -H "X-Ingest-Key: ${ingest.ingest_key}" -H "Content-Type: application/json" \\
  -d '[{"key":"AGG1.P","value":24.3},{"key":"RES.LEVEL","value":903.2}]'`}</pre>
          <div className="row"><button className="btn sm danger" onClick={() => api.rotateIngestKey(projectId).then((r) => setIngest({ ...ingest, ingest_key: r.ingest_key }))}>Kalitni almashtirish</button><button className="btn sm" onClick={() => setIngest(null)}>Yopish</button></div>
        </div>
      )}

      {sensors.length === 0 && <p className="muted">Sensor yo'q. {canEdit ? "«Sensor qo'shish» — SCADA tegi nomi (kalit), turi, alarm chegaralari." : ""}</p>}
      {view.map((s) => (
        <div key={s.id} className={`list-item${selected === s.id ? " selected" : ""}`} onClick={() => setSelected(selected === s.id ? null : s.id)}>
          <div className="title">
            <i className="dot" style={{ background: ALARM_COLOR[s.alarm] }} />
            <b>{s.name}</b>
            <span className="grow" />
            <span className="mono">{s.last_value != null ? `${fmtVal(s.last_value)} ${s.unit}` : "—"}</span>
            <span className={`badge ${s.alarm === "ok" ? "published" : s.alarm === "stale" ? "archived" : "rejected"}`}>{ALARM_LABEL[s.alarm]}</span>
          </div>
          <div className="meta">
            <span className="mono">{s.key}</span> · {KINDS.find((k) => k.id === s.kind)?.title}
            {s.last_ts && <> · {fmtDate(s.last_ts)}</>}
            {s.element_guid ? " · elementga bog'langan" : " · element bog'lanmagan"}
            {s.protocol === "mqtt" && <> · mqtt:{String(s.address.topic ?? "")}</>}
          </div>
          {selected === s.id && (
            <div onClick={(e) => e.stopPropagation()} style={{ marginTop: 6 }}>
              <div className="row wrap" style={{ marginBottom: 6 }}>
                {[1, 24, 168, 720].map((h) => <button key={h} className={`btn sm${hours === h ? " active" : ""}`} onClick={() => setHours(h)}>{h === 1 ? "1 soat" : h === 24 ? "1 kun" : h === 168 ? "1 hafta" : "1 oy"}</button>)}
                {s.element_guid && <button className="btn sm" onClick={() => viewer?.selectByGuids([s.element_guid!], true)}>3D da ko'rsatish</button>}
                {s.alarm !== "ok" && canEdit && <button className="btn sm" title="Alarm bo'yicha ish buyrug'i (CMMS): sensor, qiymat, element" onClick={() => api.createWorkOrder(projectId, { title: `${s.name}: ${ALARM_LABEL[s.alarm]}${s.last_value != null ? ` (${fmtVal(s.last_value)} ${s.unit})` : ""}`, description: `Alarm ${ALARM_LABEL[s.alarm]} — sensor ${s.key}${s.element_guid ? `, element GUID ${s.element_guid}` : ""}. 3D: /models/${modelId}?sel=${s.element_guid ?? ""}&tab=mon`, priority: s.alarm === "stale" ? "medium" : "high", source: "alarm" }).then((w) => setError(`Ish buyrug'i #${w.id} yaratildi (Dispetcher paneli → Ish buyruqlari)`)).catch((err) => setError(err instanceof Error ? err.message : "Xatolik"))}>Ish buyrug'i</button>}
                {canEdit && <button className="btn sm" onClick={() => bindToSelection(s)} title="Tanlangan elementga bog'lash">Tanlanganga bog'lash</button>}
                {canEdit && <button className="btn sm" onClick={() => { setEditing({ key: s.key, name: s.name, kind: s.kind, unit: s.unit, protocol: s.protocol, address: s.address, low_alarm: s.low_alarm, high_alarm: s.high_alarm, stale_after_s: s.stale_after_s, enabled: s.enabled, element_guid: s.element_guid, priority: s.priority, writable: s.writable }); setEditId(s.id); setTopic(String(s.address.topic ?? "")); }}>Tahrirlash</button>}
                {role === "approver" && <button className="btn sm danger" onClick={() => confirm(`${s.name} sensorini o'chirasizmi? Tarix ham o'chadi.`) && api.deleteSensor(s.id).then(load)}>O'chirish</button>}
              </div>
              {history.length > 1 ? (
                <LineChart title={s.name} unit={s.unit} x={history.map((p) => p.ts.slice(0, 16).replace("T", " "))} series={[{ name: s.name, values: history.map((p) => p.v) }]}
                  refLines={[...(s.high_alarm != null ? [{ value: s.high_alarm, label: "yuqori" }] : []), ...(s.low_alarm != null ? [{ value: s.low_alarm, label: "past" }] : [])]} />
              ) : <p className="dim small">Bu davrda o'lchov yo'q.</p>}
              {s.writable && (role === "operator" || role === "engineer" || role === "approver") && (
                <div className="row" style={{ marginTop: 6, alignItems: "center", gap: 6, flexWrap: "wrap" }} title="Supervisory control: buyruq gateway orqali SCADA ga yuboriladi (pending → sent → acked), audit jurnalida">
                  <b className="small">Boshqaruv</b>
                  {s.kind === "position" ? (
                    <input type="range" min={0} max={100} step={1} className="grow" value={Number(cmdVal) || 0} onChange={(e) => setCmdVal(e.target.value)} aria-label="Ochilish" />
                  ) : s.kind === "status" ? (
                    <select className="select sm" value={cmdVal} onChange={(e) => setCmdVal(e.target.value)}><option value="1">Ishga tushirish (1)</option><option value="0">To'xtatish (0)</option></select>
                  ) : (
                    <input className="input" style={{ width: 110 }} placeholder="Qiymat" value={cmdVal} onChange={(e) => setCmdVal(e.target.value)} />
                  )}
                  <span className="mono small">{s.kind === "position" ? `${Number(cmdVal) || 0} %` : ""}</span>
                  <button className="btn sm primary" onClick={() => { const v = Number(cmdVal); if (!Number.isFinite(v)) return; if (!confirm(`Buyruqni tasdiqlang (select-before-operate):\n${s.name} → ${v} ${s.unit}\n\nBuyruq gateway orqali SCADA ga yuboriladi va audit jurnaliga yoziladi.`)) return; api.sendCommand(projectId, s.id, v, `3D dan: ${s.name}`).then((c) => setError(`Buyruq #${c.id} yuborildi (${s.name} → ${v}${s.unit})`)).catch((err) => setError(err instanceof Error ? err.message : "Buyruq yuborilmadi")); }}>Buyruq yuborish</button>
                </div>
              )}
              {canEdit && (
                <div className="row" style={{ marginTop: 4, flexWrap: "wrap", gap: 4 }}>
                  <input className="input" style={{ width: 120 }} placeholder="Qiymat" value={manual} onChange={(e) => setManual(e.target.value)} onKeyDown={(e) => e.key === "Enter" && pushManual(s)} />
                  <button className="btn sm" onClick={() => pushManual(s)}>Qo'lda yuborish</button>
                  <label className="btn sm">CSV import<input type="file" accept=".csv,text/csv" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) api.importReadings(s.id, f).then((r) => { setError(""); setHours((h) => h); alert(`${r.accepted} o'lchov yuklandi`); }).catch((err) => setError(err.message)); }} /></label>
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
                  {KINDS.map((k) => <option key={k.id} value={k.id}>{k.title}</option>)}
                </select>
              </label>
              <label className="field" style={{ width: 90 }}><span>Birlik</span><input className="input" value={editing.unit} onChange={(e) => setEditing({ ...editing, unit: e.target.value })} /></label>
            </div>
            <div className="row">
              <label className="field grow"><span>Past alarm</span><input className="input" type="number" step="any" value={editing.low_alarm ?? ""} onChange={(e) => setEditing({ ...editing, low_alarm: e.target.value === "" ? null : Number(e.target.value) })} /></label>
              <label className="field grow"><span>Yuqori alarm</span><input className="input" type="number" step="any" value={editing.high_alarm ?? ""} onChange={(e) => setEditing({ ...editing, high_alarm: e.target.value === "" ? null : Number(e.target.value) })} /></label>
              <label className="field grow"><span>Uzilgan deb hisoblash, s</span><input className="input" type="number" value={editing.stale_after_s} onChange={(e) => setEditing({ ...editing, stale_after_s: Number(e.target.value) || 600 })} /></label>
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
              <button type="submit" className="btn primary">Saqlash</button>
            </div>
          </form>
        </Dialog>
      )}
    </div>
  );
}

function fmtVal(v: number) {
  return Math.abs(v) >= 1000 ? v.toFixed(0) : Math.abs(v) >= 100 ? v.toFixed(1) : v.toFixed(2);
}
