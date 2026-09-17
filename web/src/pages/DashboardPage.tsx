import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Icon from "../ui/Icon";
import { ForecastPanel, HealthPanel, PartsPanel, WhatIfPanel, WorkOrdersPanel } from "./dashboard/HealthPanels";
import { Link, useParams } from "react-router-dom";
import { api, type AlarmEvent, type Command, type Dashboard, type JournalEntry, type LiveMessage, type Project, type ReadingPoint, type Report, type Sensor, type Member } from "../api/client";
import { AssetsPanel, CommandsPanel, JournalPanel, TwinPanel } from "./dashboard/TwinPanels";
import { useLive } from "../hooks/useLive";
import TopBar from "../ui/TopBar";
import Dialog from "../ui/Dialog";
import LineChart, { CHART_COLORS } from "../ui/LineChart";
import { ALARM_LABEL, fmtDate, fmtValue } from "../ui/format";
import Mimic from "./dashboard/Mimic";

const RANGES: { label: string; hours: number }[] = [
  { label: "1 soat", hours: 1 },
  { label: "24 soat", hours: 24 },
  { label: "7 kun", hours: 168 },
  { label: "30 kun", hours: 720 },
];

type Section = "scheme" | "trend" | "twin" | "health" | "whatif" | "forecast" | "workorders" | "parts" | "assets" | "control" | "journal";
const SECTIONS: { id: Section; title: string }[] = [
  { id: "scheme", title: "Sxema" },
  { id: "trend", title: "Trendlar / Hisobot" },
  { id: "twin", title: "Raqamli egizak" },
  { id: "health", title: "Sog'liq" },
  { id: "whatif", title: "Optimal rejim / Nima bo'lsa" },
  { id: "forecast", title: "Toshqin prognozi" },
  { id: "workorders", title: "Ish buyruqlari" },
  { id: "parts", title: "Ehtiyot qismlar" },
  { id: "assets", title: "Aktivlar" },
  { id: "control", title: "Boshqaruv" },
  { id: "journal", title: "Smena jurnali" },
];

/** Alarm ovozi (muhim/kritik) — WebAudio, fayl kerak emas. */
function beep(critical: boolean) {
  try {
    const ctx = new AudioContext();
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.type = "square"; o.frequency.value = critical ? 880 : 620;
    g.gain.value = 0.08;
    o.connect(g); g.connect(ctx.destination);
    o.start();
    o.stop(ctx.currentTime + (critical ? 0.6 : 0.25));
    o.onended = () => void ctx.close();
  } catch { /* ovoz bo'lmasa jim */ }
}

/** Dispetcher paneli (SCADA HMI): mimik sxema, KPI, jonli qiymatlar, trendlar, alarm jurnali, hisobot,
 * raqamli egizak, aktivlar, boshqaruv buyruqlari, smena jurnali, vaqt mashinasi. */
export default function DashboardPage() {
  const pid = Number(useParams().projectId);
  const [project, setProject] = useState<Project | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [sensors, setSensors] = useState<Sensor[]>([]);
  const [events, setEvents] = useState<AlarmEvent[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const [mimic, setMimic] = useState<Record<string, number | null>>({});
  const [slotDlg, setSlotDlg] = useState<string | null>(null);
  const [trend, setTrend] = useState<number[]>([]);
  const [hours, setHours] = useState(24);
  const [series, setSeries] = useState<Record<number, ReadingPoint[]>>({});
  const [period, setPeriod] = useState<Report["period"]>("day");
  const [date, setDate] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [section, setSection] = useState<Section>("scheme");
  const [muted, setMuted] = useState(false);
  const [liveCmd, setLiveCmd] = useState<Command | null>(null);
  const [liveJournal, setLiveJournal] = useState<JournalEntry | null>(null);
  // Vaqt mashinasi: null — jonli; aks holda tanlangan vaqtdagi holat (sensorlar snapshot dan)
  const [historyAt, setHistoryAt] = useState<string | null>(null);
  const historyRef = useRef<string | null>(null);
  historyRef.current = historyAt;

  const canEdit = project?.my_role === "engineer" || project?.my_role === "approver";
  const canOperate = canEdit || project?.my_role === "operator";

  const load = useCallback(async () => {
    try {
      const [p, d, ev] = await Promise.all([api.project(pid), api.dashboard(pid), api.alarmEvents(pid, true)]);
      setProject(p);
      api.members(pid).then(setMembers).catch(() => setMembers([]));
      setDash(d);
      setSensors(d.sensors);
      setMimic(d.mimic);
      setEvents(ev);
      setTrend((t) => (t.length ? t : d.sensors.filter((s) => s.kind === "power" || s.kind === "level").slice(0, 3).map((s) => s.id)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Xatolik");
    }
  }, [pid]);
  useEffect(() => { void load(); }, [load]);

  const onLive = useCallback((m: LiveMessage) => {
    if (m.type === "alarm" && m.event) {
      const e = m.event;
      setEvents((prev) => {
        const rest = prev.filter((x) => x.id !== e.id);
        const s = sensors.find((x) => x.id === e.sensor_id);
        const merged: AlarmEvent = { ...(prev.find((x) => x.id === e.id) ?? { sensor_key: s?.key ?? "", unit: s?.unit ?? "", acked_at: null, comment: "" }), ...e };
        // yopilgan va kvitlangan — faol ro'yxatdan chiqadi
        if (merged.ended_at && merged.acked_at) return rest;
        return [merged, ...rest];
      });
      if (!e.ended_at) {
        setFlash(`${e.priority === "critical" ? "KRITIK · " : e.priority === "high" ? "MUHIM · " : ""}${e.sensor_name}: ${ALARM_LABEL[e.state]}`);
        if (!muted && (e.priority === "critical" || e.priority === "high")) beep(e.priority === "critical");
      }
    } else if (m.type === "command" && m.command) {
      setLiveCmd(m.command);
    } else if (m.type === "journal" && m.entry) {
      setLiveJournal(m.entry);
    } else if (m.type === "reading" && m.sensor_id != null && m.ts && m.value != null && trend.includes(m.sensor_id) && hours <= 72) {
      setSeries((prev) => ({ ...prev, [m.sensor_id!]: [...(prev[m.sensor_id!] ?? []), { ts: m.ts!, v: m.value!, min: m.value!, max: m.value! }].slice(-2000) }));
    }
  }, [sensors, trend, hours, muted]);
  // Tarix rejimida jonli yangilanishlar sensorlarga qo'llanmaydi (snapshot ustun)
  const setSensorsLive = useCallback<React.Dispatch<React.SetStateAction<Sensor[]>>>((u) => { if (!historyRef.current) setSensors(u); }, []);
  const live = useLive(pid, setSensorsLive, onLive);

  // Vaqt mashinasi: snapshot ni sensorlarga qo'yish; jonliga qaytganda qayta yuklash
  useEffect(() => {
    if (!historyAt) { void load(); return; }
    api.snapshot(pid, historyAt).then((snap) => {
      setSensors((prev) => prev.map((s) => { const u = snap.sensors.find((x) => x.sensor_id === s.id); return u ? { ...s, last_value: u.value, last_ts: u.ts, alarm: u.alarm } : s; }));
    }).catch((e) => setError(e.message));
  }, [historyAt, pid]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!flash) return;
    const t = window.setTimeout(() => setFlash(null), 6000);
    return () => window.clearTimeout(t);
  }, [flash]);

  // Trend ma'lumotlari
  useEffect(() => {
    let cancelled = false;
    Promise.all(trend.map((id) => api.readings(id, hours, 400).then((r) => [id, r.points] as const)))
      .then((rows) => { if (!cancelled) setSeries(Object.fromEntries(rows)); })
      .catch((e) => setError(e.message));
    return () => { cancelled = true; };
  }, [trend, hours]);

  // Hisobot
  useEffect(() => {
    api.report(pid, period, date || undefined).then(setReport).catch((e) => setError(e.message));
  }, [pid, period, date]);

  const labels = useMemo(() => Object.fromEntries((dash?.slots ?? []).map((s) => [s.slot, s.label])), [dash]);
  const activeAlarms = events.filter((e) => !e.ended_at).length;
  const unacked = events.filter((e) => !e.acked_at).length;
  const kinds = useMemo(() => {
    const g: Record<string, Sensor[]> = {};
    for (const s of sensors) (g[s.kind] ??= []).push(s);
    return g;
  }, [sensors]);

  async function saveMimic() {
    try {
      await api.saveDashboard(pid, { mimic, tiles: dash?.tiles ?? [] });
      setEditing(false);
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "Xatolik"); }
  }
  async function ack(e: AlarmEvent) {
    const comment = prompt(`${e.sensor_name} — ${ALARM_LABEL[e.state]}. Izoh (ixtiyoriy):`, "") ?? "";
    try {
      const u = await api.ackAlarm(e.id, comment);
      setEvents((prev) => prev.map((x) => (x.id === u.id ? u : x)).filter((x) => !(x.ended_at && x.acked_at)));
    } catch (err) { setError(err instanceof Error ? err.message : "Xatolik"); }
  }

  // Trend grafigi: umumiy x — birinchi qatorning vaqtlari (eng uzun)
  const chart = useMemo(() => {
    const ids = trend.filter((id) => series[id]?.length);
    if (!ids.length) return null;
    const base = ids.map((id) => series[id]).sort((a, b) => b.length - a.length)[0];
    const x = base.map((p) => p.ts);
    return {
      x: x.map((t) => new Date(t).toLocaleTimeString("uz-UZ", hours > 48 ? { day: "2-digit", month: "2-digit", hour: "2-digit" } : { hour: "2-digit", minute: "2-digit" })),
      series: ids.map((id, i) => {
        const s = sensors.find((q) => q.id === id);
        const pts = series[id];
        // vaqt bo'yicha eng yaqin nuqta
        const vals = x.map((t) => { const tt = new Date(t).getTime(); let best = pts[0]; for (const p of pts) if (Math.abs(new Date(p.ts).getTime() - tt) < Math.abs(new Date(best.ts).getTime() - tt)) best = p; return best.v; });
        return { name: `${s?.name ?? id} (${s?.unit ?? ""})`, values: vals, color: CHART_COLORS[i % CHART_COLORS.length] };
      }),
    };
  }, [trend, series, sensors, hours]);

  if (!project || !dash) return <div className="page"><TopBar /><div className="page-body muted">{error || "Yuklanmoqda…"}</div></div>;

  return (
    <div className="page">
      <TopBar crumbs={[{ label: "Loyihalar", to: "/" }, { label: project.name, to: `/projects/${pid}` }, { label: "Dispetcher paneli" }]}>
        {historyAt ? <span className="badge high"><Icon name="history" size={12} /> TARIX REJIMI</span> : <span className={`badge ${live === "jonli" ? "published" : "rejected"}`}><Icon name={live === "jonli" ? "wifi" : "wifi-off"} size={12} /> {live}</span>}
        <label className="row small" title="Vaqt mashinasi: tanlangan vaqtdagi holatni ko'rish (sxema, qiymatlar)">
          <input className="input" style={{ width: 190, padding: "2px 6px" }} type="datetime-local" value={historyAt ? toLocalInput(historyAt) : ""} onChange={(e) => setHistoryAt(e.target.value ? new Date(e.target.value).toISOString() : null)} />
          {historyAt && <button className="btn sm primary" onClick={() => setHistoryAt(null)}>Jonli</button>}
        </label>
        <button className={`btn sm ${muted ? "" : "active"}`} title="Alarm ovozi (muhim/kritik)" onClick={() => setMuted(!muted)}><Icon name={muted ? "volume-x" : "volume"} /></button>
        {canEdit && !editing && <button className="btn sm" onClick={() => setEditing(true)}>Sxemani sozlash</button>}
        {editing && <><button className="btn sm primary" onClick={saveMimic}>Saqlash</button><button className="btn sm" onClick={() => { setEditing(false); setMimic(dash.mimic); }}>Bekor</button></>}
      </TopBar>
      <div className="page-body dash">
        {error && <p className="error">{error}</p>}
        {flash && <div className="dash-flash" role="alert"><Icon name="alert-triangle" /> ALARM — {flash}</div>}
        {historyAt && <div className="dash-history"><Icon name="history" size={14} /> Tarix rejimi: {fmtDate(historyAt)} holati ko'rsatilmoqda. <a onClick={() => setHistoryAt(null)}>Jonli rejimga qaytish</a></div>}
        <div className="ws-tabs dash-tabs">
          {SECTIONS.map((sct) => <button key={sct.id} className={section === sct.id ? "active" : ""} onClick={() => setSection(sct.id)}>{sct.title}{sct.id === "scheme" && unacked > 0 && <span className="count">{unacked}</span>}</button>)}
        </div>

        {section === "scheme" && (<>
        <div className="tiles dash-kpi">
          <div className={`tile ${activeAlarms ? "tile-alarm" : ""}`}><div className="tile-t">Faol alarmlar</div><div className="tile-v">{activeAlarms} <span className="tile-u">{unacked ? `(${unacked} kvitlanmagan)` : ""}</span></div></div>
          <div className="tile"><div className="tile-t">Energiya, 24 soat</div><div className="tile-v">{dash.energy_24h_mwh == null ? "—" : fmtValue(dash.energy_24h_mwh)} <span className="tile-u">MWh</span></div></div>
          <div className="tile"><div className="tile-t">Umumiy quvvat</div><div className="tile-v">{fmtValue((kinds.power ?? []).reduce((a, s) => a + (s.alarm !== "stale" && s.last_value != null ? s.last_value : 0), 0))} <span className="tile-u">{kinds.power?.[0]?.unit ?? "MW"}</span></div></div>
          <div className="tile"><div className="tile-t">Agregatlar</div><div className="tile-v">{dash.units.filter((u) => u.running).length}/{dash.units.length} <span className="tile-u">ishlayapti</span></div></div>
          <div className="tile"><div className="tile-t">Sensorlar</div><div className="tile-v">{sensors.length} <span className="tile-u">{sensors.filter((s) => s.alarm === "stale").length} aloqasiz · {dash.live_clients} kuzatuvchi</span></div></div>
        </div>

        <div className="dash-main">
          <div className="dash-mimic">
            <Mimic sensors={sensors} mimic={Object.fromEntries(Object.entries(mimic).filter(([, v]) => v) as [string, number][])} labels={labels} editing={editing} onSlotClick={editing ? setSlotDlg : undefined} />
            {editing && <p className="muted small">Slotni bosib sensor tanlang. Bo'sh slotlar ko'rinmaydi.</p>}
          </div>
          <div className="dash-alarms">
            <div className="row"><b>Alarm jurnali</b><span className="grow" />
              <button className={`btn sm ${showHistory ? "active" : ""}`} onClick={async () => { const h = !showHistory; setShowHistory(h); setEvents(await api.alarmEvents(pid, !h)); }}>{showHistory ? "Faollar" : "Tarix (7 kun)"}</button>
              {canOperate && unacked > 0 && <button className="btn sm" onClick={() => api.ackAll(pid).then(load)}>Hammasini kvitlash</button>}
            </div>
            {events.length === 0 ? <p className="muted">Alarm yo'q</p> : (
              <table className="grid small">
                <thead><tr><th>Vaqt</th><th>Sensor</th><th>Holat</th><th>Qiymat</th><th /></tr></thead>
                <tbody>
                  {events.map((e) => (
                    <tr key={e.id} className={!e.ended_at ? "alarm-active" : undefined}>
                      <td className="mono">{fmtDate(e.started_at)}{e.ended_at && <div className="dim">→ {fmtDate(e.ended_at)}</div>}</td>
                      <td>{e.sensor_name}<div className="dim">{e.sensor_key}</div></td>
                      <td><span className={`badge ${e.state === "stale" ? "archived" : e.state}`}>{ALARM_LABEL[e.state]}</span>{(e.priority === "critical" || e.priority === "high") && <span className={`badge ${e.priority === "critical" ? "rejected" : "high"}`} style={{ marginLeft: 4 }}>{e.priority === "critical" ? "kritik" : "muhim"}</span>}{!e.ended_at && <div className="dim">davom etmoqda</div>}</td>
                      <td className="mono">{e.value == null ? "—" : `${fmtValue(e.value)} ${e.unit}`}</td>
                      <td className="row" style={{ gap: 4 }}>{e.acked_at ? <span className="dim" title={e.comment}>kvitlangan</span> : canOperate ? <button className="btn sm" onClick={() => ack(e)}>Kvitlash</button> : <span className="badge rejected">yangi</span>}
                        {(() => { const s = sensors.find((x) => x.id === e.sensor_id); return s?.element_guid && s.model_id ? <Link className="btn sm" to={`/models/${s.model_id}?sel=${encodeURIComponent(s.element_guid)}&tab=mon`} title="3D modelda elementni ko'rsatish (monitoring paneli bilan)">3D</Link> : null; })()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        </>)}

        {section === "trend" && (<>
        <div className="dash-block">
          <div className="row wrap">
            <b>Trendlar</b>
            <span className="chips">
              {sensors.map((s) => (
                <button key={s.id} className={`chip ${trend.includes(s.id) ? "on" : ""}`} onClick={() => setTrend((t) => (t.includes(s.id) ? t.filter((x) => x !== s.id) : [...t, s.id].slice(-5)))} title={s.key}>{s.name}</button>
              ))}
            </span>
            <span className="grow" />
            {RANGES.map((r) => <button key={r.hours} className={`btn sm ${hours === r.hours ? "active" : ""}`} onClick={() => setHours(r.hours)}>{r.label}</button>)}
            {trend.length === 1 && <button className="btn sm" onClick={() => api.downloadCsv(`/api/sensors/${trend[0]}/export.csv?hours=${hours}`, `${sensors.find((s) => s.id === trend[0])?.key ?? "sensor"}.csv`).catch((e) => setError(e.message))}>CSV</button>}
          </div>
          {chart ? <LineChart title="" unit="" x={chart.x} series={chart.series} height={220} /> : <p className="muted">Sensor tanlang</p>}
        </div>

        <div className="dash-block">
          <div className="row wrap">
            <b>Hisobot</b>
            <select className="select" style={{ width: 120 }} value={period} onChange={(e) => setPeriod(e.target.value as Report["period"])}>
              <option value="day">Kun</option><option value="week">Hafta</option><option value="month">Oy</option>
            </select>
            <input className="input" style={{ width: 150 }} type="date" value={date} onChange={(e) => setDate(e.target.value)} title="Davr boshi (bo'sh — joriy)" />
            <span className="grow" />
            <button className="btn sm" onClick={() => api.downloadCsv(`/api/projects/${pid}/report?period=${period}${date ? `&date=${date}` : ""}&format=csv`, `hisobot-${period}.csv`).catch((e) => setError(e.message))}>CSV yuklab olish</button>
          </div>
          {report && (
            <>
              <p className="muted small">{fmtDate(report.start)} — {fmtDate(report.end)} · energiya <b>{fmtValue(report.energy_mwh)} MWh</b> · alarmlar {report.alarms.count} (yuqori {report.alarms.by_state.high ?? 0}, past {report.alarms.by_state.low ?? 0}, aloqa {report.alarms.by_state.stale ?? 0})</p>
              <table className="grid small">
                <thead><tr><th>Sensor</th><th>Tur</th><th>n</th><th>O'rtacha</th><th>Min</th><th>Max</th><th>Energiya, MWh</th></tr></thead>
                <tbody>
                  {report.sensors.map((r) => (
                    <tr key={r.sensor_id}><td>{r.name} <span className="dim">{r.key}</span></td><td>{r.kind}</td><td className="mono">{r.n}</td><td className="mono">{r.avg == null ? "—" : `${fmtValue(r.avg)} ${r.unit}`}</td><td className="mono">{r.min == null ? "—" : fmtValue(r.min)}</td><td className="mono">{r.max == null ? "—" : fmtValue(r.max)}</td><td className="mono">{r.energy_mwh == null ? "" : fmtValue(r.energy_mwh)}</td></tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
        </>)}
        {section === "twin" && <TwinPanel projectId={pid} canRun={canEdit} />}
        {section === "health" && <HealthPanel projectId={pid} sensors={sensors} canEdit={canEdit} canOperate={canOperate} />}
        {section === "whatif" && <WhatIfPanel projectId={pid} />}
        {section === "forecast" && <ForecastPanel projectId={pid} />}
        {section === "workorders" && <WorkOrdersPanel projectId={pid} members={members} canOperate={canOperate} canEdit={canEdit} />}
        {section === "parts" && <PartsPanel projectId={pid} canOperate={canOperate} canEdit={canEdit} />}
        {section === "assets" && <AssetsPanel projectId={pid} sensors={sensors} canEdit={canEdit} canMaint={canOperate} />}
        {section === "control" && <CommandsPanel projectId={pid} sensors={sensors} canCommand={canOperate && !historyAt} live={liveCmd} />}
        {section === "journal" && <JournalPanel projectId={pid} canWrite={canOperate} live={liveJournal} />}
        <p className="dim small">Sensorlarni qo'shish/bog'lash — model sahifasidagi <Link to={`/projects/${pid}`}>Monitoring</Link> panelida; SCADA ulanishi — <code>deploy/gateway</code>.</p>
      </div>

      {slotDlg && (
        <Dialog title={labels[slotDlg] ?? slotDlg} onClose={() => setSlotDlg(null)}>
          <p className="muted small">Slotga bog'lanadigan sensor:</p>
          <div className="list">
            <button className="list-item" onClick={() => { setMimic({ ...mimic, [slotDlg]: null }); setSlotDlg(null); }}>— bo'sh —</button>
            {sensors.map((s) => (
              <button key={s.id} className={`list-item ${mimic[slotDlg] === s.id ? "active" : ""}`} onClick={() => { setMimic({ ...mimic, [slotDlg]: s.id }); setSlotDlg(null); }}>
                {s.name} <span className="dim">{s.key} · {s.kind} {s.unit}</span>
              </button>
            ))}
          </div>
        </Dialog>
      )}
    </div>
  );
}

/** ISO (UTC) → <input type=datetime-local> qiymati (mahalliy vaqt) */
function toLocalInput(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
