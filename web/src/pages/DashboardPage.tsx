import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import ErrorBoundary from "../ui/ErrorBoundary";
import { useOnline } from "../hooks/useOnline";
import Icon from "../ui/Icon";
import { ForecastPanel, HealthPanel, PartsPanel, WhatIfPanel, WorkOrdersPanel } from "./dashboard/HealthPanels";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, canCommandRole, type AlarmEvent, type Command, type Dashboard, type JournalEntry, type Project, type ReadingPoint, type Report, type Sensor, type Member } from "../api/client";
import { AssetsPanel, CommandsPanel, JournalPanel, SoePanel, TwinPanel } from "./dashboard/TwinPanels";
import TopBar from "../ui/TopBar";
import LineChart, { CHART_COLORS } from "../ui/LineChart";
import { fmtDate, fmtShort, fmtTime, fmtValue } from "../ui/format";
import { alarmLabel, periodLabel, sensorKindLabel } from "../i18n/labels";
import { DateField, DateTimeField } from "../ui/DateField";
import Mimic from "./operator/Mimic";
import MimicEditor from "./operator/MimicEditor";
import { loadScheme, type Scheme } from "./operator/scheme";
import AnnunciatorControl from "../ui/AnnunciatorControl";
import AlarmTable from "./operator/AlarmTable";
import { sortAlarms, toRows } from "./operator/alarms";
import { alignNearest } from "../ui/trendMath";
import { applyEvent, loadEvents, putSensors, useAlarmEvents, useLiveMessages, useProjectLive, useSensors } from "../store/live";
import { can } from "../api/permissions";

const RANGES: { label: string; hours: number }[] = [
  { label: "1 soat", hours: 1 },
  { label: "24 soat", hours: 24 },
  { label: "7 kun", hours: 168 },
  { label: "30 kun", hours: 720 },
];

type Section = "scheme" | "trend" | "twin" | "health" | "whatif" | "forecast" | "workorders" | "parts" | "assets" | "control" | "journal" | "soe";
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
  { id: "soe", title: "SOE" },
];

/** Dispetcher paneli (SCADA HMI): mimik sxema, KPI, jonli qiymatlar, trendlar, alarm jurnali, hisobot,
 * raqamli egizak, aktivlar, boshqaruv buyruqlari, smena jurnali, vaqt mashinasi.
 *
 * FE-04: sahifa qobig'i jonli qiymatlarga obuna emas — har bo'lim o'zi obuna (umumiy store, bitta soket):
 * bitta o'qish faqat sxema bo'limini qayta chizadi; trend va hisobot o'z holatiga ega. Ma'lumot bir marta
 * yuklanadi (vaqt mashinasidan jonliga qaytganda — qayta). */
export default function DashboardPage() {
  const nav = useNavigate();
  const pid = Number(useParams().projectId);
  const [project, setProject] = useState<Project | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const [mimic, setMimic] = useState<Record<string, number | null>>({});
  const [scheme, setScheme] = useState<Scheme | null>(null);
  const [selEl, setSelEl] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [section, setSection] = useState<Section>("scheme");
  // Vaqt mashinasi: null — jonli; aks holda tanlangan vaqtdagi holat (sensorlar snapshot dan, store ga yozilmaydi)
  const [historyAt, setHistoryAt] = useState<string | null>(null);
  const [historySensors, setHistorySensors] = useState<Sensor[] | null>(null);

  const canEdit = project?.my_role === "engineer" || project?.my_role === "approver";
  const canOperate = can(project?.my_role, "scada.ack");
  const online = useOnline();
  const live = useProjectLive(pid);

  const load = useCallback(async () => {
    try {
      const p = await api.project(pid);
      setProject(p);
      const [dr] = await Promise.all([api.dashboard(pid).catch((e: Error) => e), loadEvents(pid)]);
      if (dr instanceof Error) {
        // Qisman ishlash (F12): dashboard konfiguratsiyasi yiqilsa ham jonli ma'lumot ko'rsatiladi
        setError(`Dispetcher konfiguratsiyasi yuklanmadi: ${dr.message} — jonli ma'lumot ko'rsatilmoqda`);
        const ss = await api.sensors(pid).catch(() => [] as Sensor[]);
        putSensors(pid, ss, { replace: true });
        setDash({ sensors: ss, units: [], mimic: {}, slots: [], tiles: [], scheme: null, pen_groups: [], active_alarms: 0, energy_24h_mwh: null, alarms_24h: { count: 0, by_state: {}, unacked: 0 }, alarm_flood: false, live_clients: 0 });
        setScheme(loadScheme(null, {}, Math.max(1, ss.filter((x) => /^AGG\d+\.P$/i.test(x.key)).length || 3)));
        return;
      }
      api.members(pid).then(setMembers).catch(() => setMembers([]));
      putSensors(pid, dr.sensors, { replace: true });
      setDash(dr);
      setMimic(dr.mimic);
      setScheme(loadScheme(dr.scheme, dr.mimic, Math.max(1, dr.units.length || 3)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Xatolik");
    }
  }, [pid]);
  useEffect(() => { void load(); }, [load]);

  // Vaqt mashinasi: snapshot — alohida ro'yxat; jonliga QAYTGANDA qayta yuklash (FE-04: birinchi renderda emas)
  const wasHistory = useRef(false);
  useEffect(() => {
    if (!historyAt) {
      setHistorySensors(null);
      if (wasHistory.current) { wasHistory.current = false; void load(); }
      return;
    }
    wasHistory.current = true;
    let dead = false;
    api.snapshot(pid, historyAt).then((snap) => {
      if (dead) return;
      const by = new Map(snap.sensors.map((x) => [x.sensor_id, x]));
      setHistorySensors((dash?.sensors ?? []).map((s) => { const u = by.get(s.id); return u ? { ...s, last_value: u.value, last_ts: u.ts, alarm: u.alarm } : s; }));
    }).catch((e) => setError(e.message));
    return () => { dead = true; };
  }, [historyAt, pid, load, dash]);

  // Yangi alarm — qisqa xabar (doimiy banner UX-03 da); ovoz store da (annunciator)
  useLiveMessages(pid, (m) => {
    if (m.type === "alarm" && m.event && !m.event.ended_at && !m.event.acked_at) {
      const e = m.event;
      setFlash(`${e.priority === "critical" ? "KRITIK · " : e.priority === "high" ? "MUHIM · " : ""}${e.sensor_name}: ${alarmLabel(e.state)}`);
    }
  });
  useEffect(() => {
    if (!flash) return;
    const t = window.setTimeout(() => setFlash(null), 6000);
    return () => window.clearTimeout(t);
  }, [flash]);

  async function saveMimic() {
    try {
      await api.saveDashboard(pid, { mimic, tiles: dash?.tiles ?? [], scheme });
      setEditing(false);
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "Xatolik"); }
  }

  if (!project || !dash) return <div className="page"><TopBar /><div className="page-body muted">{error || "Yuklanmoqda…"}</div></div>;

  return (
    <div className="page">
      <TopBar crumbs={[{ label: "Loyihalar", to: "/" }, { label: project.name, to: `/projects/${pid}` }, { label: "Dispetcher paneli" }]}>
        {historyAt ? <span className="badge high"><Icon name="history" size={12} /> TARIX REJIMI</span> : <span className={`badge live-${live.toLowerCase()} ${live === "LIVE" ? "published" : live === "STALE" ? "shared" : "rejected"}`} title="Jonli oqim: LIVE — xabar yaqinda; STALE — heartbeat kechikmoqda; OFFLINE — uzilgan"><Icon name={live === "OFFLINE" ? "wifi-off" : "wifi"} size={12} /> {live}</span>}
        <span className="row small" title="Vaqt mashinasi: tanlangan vaqtdagi holatni ko'rish (sxema, qiymatlar)">
          <DateTimeField className="history-at" aria-label="Vaqt mashinasi: sana va vaqt" value={historyAt ?? ""} onChange={(iso) => setHistoryAt(iso || null)} />
          {historyAt && <button className="btn sm primary" onClick={() => setHistoryAt(null)}>Jonli</button>}
        </span>
        <AnnunciatorControl projectId={pid} canOperate={canOperate} />
        {canEdit && !editing && <button className="btn sm" onClick={() => setEditing(true)}>Sxemani sozlash</button>}
        {editing && <><button className="btn sm primary" onClick={saveMimic}>Saqlash</button><button className="btn sm" onClick={() => { setEditing(false); setMimic(dash.mimic); setScheme(loadScheme(dash.scheme, dash.mimic, Math.max(1, dash.units.length || 3))); setSelEl(null); }}>Bekor</button></>}
      </TopBar>
      <div className="page-body dash">
        {!online && <div className="verdict warn" data-testid="offline-banner">OFFLAYN — tarmoq yo'q. Ko'rsatilayotgan qiymatlar oxirgi ma'lum holat, yangilanmaydi.</div>}
        {error && <p className="error">{error}</p>}
        {flash && <div className="dash-flash" role="alert"><Icon name="alert-triangle" /> ALARM — {flash}</div>}
        {historyAt && <div className="dash-history"><Icon name="history" size={14} /> Tarix rejimi: {fmtDate(historyAt)} holati ko'rsatilmoqda. <button type="button" className="link-btn" onClick={() => setHistoryAt(null)}>Jonli rejimga qaytish</button></div>}
        <UnackedTabs pid={pid} section={section} onSection={setSection} />

        {section === "scheme" && (
          <SchemeSection pid={pid} dash={dash} scheme={scheme} editing={editing} selEl={selEl} onSelect={setSelEl} onScheme={setScheme}
            historySensors={historySensors} canOperate={canOperate} canEdit={canEdit} onError={setError} onReload={load}
            onOpen={(sid) => nav(`/projects/${pid}/ops/sensor/${sid}`)} />
        )}
        {section === "trend" && (<>
          <TrendSection pid={pid} meta={dash.sensors} onError={setError} />
          <ReportSection pid={pid} onError={setError} />
        </>)}
        {section === "twin" && <ErrorBoundary name="Raqamli egizak"><TwinPanel projectId={pid} canRun={canEdit} canApprove={project?.my_role === "approver"} /></ErrorBoundary>}
        {section === "health" && <ErrorBoundary name="Sog'liq"><HealthPanel projectId={pid} sensors={dash.sensors} canEdit={canEdit} canOperate={canOperate} /></ErrorBoundary>}
        {section === "whatif" && <ErrorBoundary name="Optimal rejim"><WhatIfPanel projectId={pid} /></ErrorBoundary>}
        {section === "forecast" && <ErrorBoundary name="Toshqin prognozi"><ForecastPanel projectId={pid} /></ErrorBoundary>}
        {section === "workorders" && <ErrorBoundary name="Ish buyruqlari"><WorkOrdersPanel projectId={pid} members={members} canOperate={canOperate} canEdit={canEdit} canApprove={project?.my_role === "approver"} /></ErrorBoundary>}
        {section === "parts" && <ErrorBoundary name="Ehtiyot qismlar"><PartsPanel projectId={pid} canOperate={canOperate} canEdit={canEdit} /></ErrorBoundary>}
        {section === "assets" && <ErrorBoundary name="Aktivlar"><AssetsPanel projectId={pid} sensors={dash.sensors} canEdit={canEdit} canMaint={canOperate} /></ErrorBoundary>}
        {section === "control" && <ErrorBoundary name="Boshqaruv"><LiveCommands pid={pid} canCommand={canCommandRole(project?.my_role) && !historyAt} canOverride={can(project?.my_role, "scada.command.approve")} /></ErrorBoundary>}
        {section === "journal" && <ErrorBoundary name="Smena jurnali"><LiveJournal pid={pid} canWrite={canOperate} /></ErrorBoundary>}
        {section === "soe" && <ErrorBoundary name="SOE"><SoePanel projectId={pid} /></ErrorBoundary>}
        <p className="dim small">Sensorlarni qo'shish/bog'lash — model sahifasidagi <Link to={`/projects/${pid}`}>Monitoring</Link> panelida; SCADA ulanishi — <code>deploy/gateway</code>.</p>
      </div>
    </div>
  );
}

/** Bo'lim yorliqlari; kvitlanmaganlar soni — faqat alarm ro'yxati o'zgarganda qayta chiziladi. */
function UnackedTabs({ pid, section, onSection }: { pid: number; section: Section; onSection: (s: Section) => void }) {
  const events = useAlarmEvents(pid);
  const unacked = events.filter((e) => !e.acked_at).length;
  return (
    <div className="ws-tabs dash-tabs">
      {SECTIONS.map((sct) => <button key={sct.id} className={section === sct.id ? "active" : ""} onClick={() => onSection(sct.id)}>{sct.title}{sct.id === "scheme" && unacked > 0 && <span className="count">{unacked}</span>}</button>)}
    </div>
  );
}

interface SchemeProps {
  pid: number;
  dash: Dashboard;
  scheme: Scheme | null;
  editing: boolean;
  selEl: string | null;
  onSelect: (id: string | null) => void;
  onScheme: (s: Scheme) => void;
  historySensors: Sensor[] | null;
  canOperate: boolean;
  canEdit: boolean;
  onError: (m: string) => void;
  onReload: () => Promise<void>;
  onOpen: (sensorId: number) => void;
}

/** Sxema bo'limi: KPI, mimika, faol alarmlar — jonli sensorlarga obuna shu yerda (yoki tarix snapshot i). */
function SchemeSection({ pid, dash, scheme, editing, selEl, onSelect, onScheme, historySensors, canOperate, canEdit, onError, onReload, onOpen }: SchemeProps) {
  const liveSensors = useSensors(pid);
  const sensors = historySensors ?? liveSensors;
  const events = useAlarmEvents(pid);
  const [prioOnly, setPrioOnly] = useState(false); // toshqinda faqat yuqori/kritik (EEMUA-191)
  const activeAlarms = events.filter((e) => !e.ended_at).length;
  const unacked = events.filter((e) => !e.acked_at).length;
  const kpi = useMemo(() => {
    const power = sensors.filter((s) => s.kind === "power");
    return {
      power: power.reduce((a, s) => a + (!s.stale && s.last_value != null ? s.last_value : 0), 0),
      powerUnit: power[0]?.unit ?? "MW",
      stale: sensors.filter((s) => s.stale).length,
    };
  }, [sensors]);
  const rows = useMemo(() => sortAlarms(toRows(events.filter((e) => !prioOnly || e.priority === "high" || e.priority === "critical"), sensors)), [events, prioOnly, sensors]);
  return (<>
    <div className="tiles dash-kpi">
      <div className={`tile ${activeAlarms ? "tile-alarm" : ""}`}><div className="tile-t">Faol alarmlar</div><div className="tile-v">{activeAlarms} <span className="tile-u">{unacked ? `(${unacked} kvitlanmagan)` : ""}</span></div></div>
      <div className="tile"><div className="tile-t">Energiya, 24 soat</div><div className="tile-v">{dash.energy_24h_mwh == null ? "—" : fmtValue(dash.energy_24h_mwh)} <span className="tile-u">MWh</span></div></div>
      <div className="tile"><div className="tile-t">Umumiy quvvat</div><div className="tile-v">{fmtValue(kpi.power)} <span className="tile-u">{kpi.powerUnit}</span></div></div>
      <div className="tile"><div className="tile-t">Agregatlar</div><div className="tile-v">{dash.units.filter((u) => u.running).length}/{dash.units.length} <span className="tile-u">ishlayapti</span></div></div>
      <div className="tile"><div className="tile-t">Sensorlar</div><div className="tile-v">{sensors.length} <span className="tile-u">{kpi.stale} aloqasiz · {dash.live_clients} kuzatuvchi</span></div></div>
    </div>

    <div className="dash-main">
      <div className="dash-mimic">
        <ErrorBoundary name="Mimika">{scheme && <Mimic scheme={scheme} sensors={sensors} editing={editing} selected={selEl} onSelect={onSelect} onChange={onScheme} onOpen={onOpen} />}</ErrorBoundary>
        {editing && scheme && <MimicEditor scheme={scheme} sensors={sensors} selected={selEl} onSelect={onSelect} onChange={onScheme} />}
      </div>
      <div className="dash-alarms">
        {dash.alarm_flood && <div className="verdict warn mb-6">Alarm toshqini: 10 daqiqada 10 dan ko'p alarm (EEMUA-191). <button className={`btn sm ${prioOnly ? "active" : ""}`} onClick={() => setPrioOnly((v) => !v)}>{prioOnly ? "Hammasini ko'rsatish" : "Faqat yuqori/kritik"}</button></div>}
        <div className="row"><b>Faol alarmlar</b><span className="dim small">{unacked} kvitlanmagan</span><span className="grow" />
          <Link className="btn sm" to={`/projects/${pid}/ops/alarms`}>Alarm sahifasi (tarix, filtr, hammasini kvitlash) →</Link>
        </div>
        <ErrorBoundary name="Alarm jurnali"><AlarmTable rows={rows} pid={pid} canOperate={canOperate} canEngineer={canEdit} compact onChanged={(u?: AlarmEvent) => { if (u) applyEvent(pid, u); else void onReload(); }} onError={onError} /></ErrorBoundary>
      </div>
    </div>
  </>);
}

/** Trendlar: tanlangan sensorlar tarixi + jonli o'qishlar (umumiy oqimdan). Diagramma faqat qatorlar
 * o'zgarganda qayta hisoblanadi (FE-04: sensor qiymatlari emas); vaqt bo'yicha moslash — binar qidiruv. */
const TrendSection = memo(function TrendSection({ pid, meta, onError }: { pid: number; meta: Sensor[]; onError: (m: string) => void }) {
  const [trend, setTrend] = useState<number[]>(() => meta.filter((s) => s.kind === "power" || s.kind === "level").slice(0, 3).map((s) => s.id));
  const [hours, setHours] = useState(24);
  const [series, setSeries] = useState<Record<number, ReadingPoint[]>>({});
  useEffect(() => {
    let cancelled = false;
    Promise.all(trend.map((id) => api.readings(id, hours, 400).then((r) => [id, r.points] as const)))
      .then((rows) => { if (!cancelled) setSeries(Object.fromEntries(rows)); })
      .catch((e) => onError(e.message));
    return () => { cancelled = true; };
  }, [trend, hours, onError]);
  useLiveMessages(pid, (m) => {
    if (m.type === "reading" && m.sensor_id != null && m.ts && m.value != null && trend.includes(m.sensor_id) && hours <= 72) {
      const id = m.sensor_id, pt = { ts: m.ts, v: m.value, min: m.value, max: m.value };
      setSeries((prev) => ({ ...prev, [id]: [...(prev[id] ?? []), pt].slice(-2000) }));
    }
  });
  const byId = useMemo(() => new Map(meta.map((s) => [s.id, s])), [meta]);
  // Umumiy x — eng uzun qatorning vaqtlari; boshqalari eng yaqin nuqta bo'yicha (binar qidiruv)
  const chart = useMemo(() => {
    const ids = trend.filter((id) => series[id]?.length);
    if (!ids.length) return null;
    const base = ids.map((id) => series[id]).sort((a, b) => b.length - a.length)[0];
    const baseT = base.map((p) => Date.parse(p.ts));
    return {
      x: base.map((p) => (hours > 48 ? fmtShort(p.ts) : fmtTime(p.ts))),
      series: ids.map((id, i) => {
        const s = byId.get(id);
        const pts = series[id];
        return { name: `${s?.name ?? id} (${s?.unit ?? ""})`, values: alignNearest(baseT, pts.map((p) => Date.parse(p.ts)), pts.map((p) => p.v)), color: CHART_COLORS[i % CHART_COLORS.length] };
      }),
    };
  }, [trend, series, byId, hours]);
  return (
    <div className="dash-block">
      <div className="row wrap">
        <b>Trendlar</b>
        <span className="chips">
          {meta.map((s) => (
            <button key={s.id} className={`chip ${trend.includes(s.id) ? "on" : ""}`} aria-pressed={trend.includes(s.id)} onClick={() => setTrend((t) => (t.includes(s.id) ? t.filter((x) => x !== s.id) : [...t, s.id].slice(-5)))} title={s.key}>{s.name}</button>
          ))}
        </span>
        <span className="grow" />
        {RANGES.map((r) => <button key={r.hours} className={`btn sm ${hours === r.hours ? "active" : ""}`} onClick={() => setHours(r.hours)}>{r.label}</button>)}
        {trend.length === 1 && <button className="btn sm" onClick={() => api.downloadCsv(`/api/sensors/${trend[0]}/export.csv?hours=${hours}`, `${byId.get(trend[0])?.key ?? "sensor"}.csv`).catch((e) => onError(e.message))}>CSV</button>}
      </div>
      {chart ? <LineChart title="" unit="" x={chart.x} series={chart.series} height={220} /> : <p className="muted">Sensor tanlang</p>}
    </div>
  );
});

/** Hisobot: davr (kun/hafta/oy) va sana (kk.oo.yyyy) — o'z holati. */
const ReportSection = memo(function ReportSection({ pid, onError }: { pid: number; onError: (m: string) => void }) {
  const [period, setPeriod] = useState<Report["period"]>("day");
  const [date, setDate] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  useEffect(() => {
    api.report(pid, period, date || undefined).then(setReport).catch((e) => onError(e.message));
  }, [pid, period, date, onError]);
  return (
    <div className="dash-block">
      <div className="row wrap">
        <b>Hisobot</b>
        <select className="select w-120" value={period} onChange={(e) => setPeriod(e.target.value as Report["period"])} aria-label="Davr">
          {(["day", "week", "month"] as const).map((p) => <option key={p} value={p}>{periodLabel(p)}</option>)}
        </select>
        <DateField className="report-date" aria-label="Davr boshi" title="Davr boshi, kk.oo.yyyy (bo'sh — joriy)" value={date} onChange={setDate} />
        <span className="grow" />
        <button className="btn sm" onClick={() => api.downloadCsv(`/api/projects/${pid}/report?period=${period}${date ? `&date=${date}` : ""}&format=csv`, `hisobot-${period}.csv`).catch((e) => onError(e.message))}>CSV yuklab olish</button>
      </div>
      {report && (
        <>
          <p className="muted small">{fmtDate(report.start)} — {fmtDate(report.end)} · energiya <b>{fmtValue(report.energy_mwh)} MWh</b> · alarmlar {report.alarms.count} (yuqori {report.alarms.by_state.high ?? 0}, past {report.alarms.by_state.low ?? 0}, aloqa {report.alarms.by_state.stale ?? 0})</p>
          <table className="grid small">
            <thead><tr><th>Sensor</th><th>Tur</th><th>n</th><th>O'rtacha</th><th>Min</th><th>Max</th><th>Energiya, MWh</th></tr></thead>
            <tbody>
              {report.sensors.map((r) => (
                <tr key={r.sensor_id}><td>{r.name} <span className="dim">{r.key}</span></td><td>{sensorKindLabel(r.kind)}</td><td className="mono">{r.n}</td><td className="mono">{r.avg == null ? "—" : `${fmtValue(r.avg)} ${r.unit}`}</td><td className="mono">{r.min == null ? "—" : fmtValue(r.min)}</td><td className="mono">{r.max == null ? "—" : fmtValue(r.max)}</td><td className="mono">{r.energy_mwh == null ? "" : fmtValue(r.energy_mwh)}</td></tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
});

/** Boshqaruv bo'limi: yoziladigan nuqtalar jonli qiymati bilan (store), buyruq holati — jonli oqimdan. */
function LiveCommands({ pid, canCommand, canOverride }: { pid: number; canCommand: boolean; canOverride: boolean }) {
  const sensors = useSensors(pid);
  const [live, setLive] = useState<Command | null>(null);
  useLiveMessages(pid, (m) => { if (m.type === "command" && m.command) setLive(m.command); });
  return <CommandsPanel projectId={pid} sensors={sensors} canCommand={canCommand} live={live} canOverride={canOverride} />;
}

/** Smena jurnali — yangi yozuvlar jonli oqimdan. */
function LiveJournal({ pid, canWrite }: { pid: number; canWrite: boolean }) {
  const [live, setLive] = useState<JournalEntry | null>(null);
  useLiveMessages(pid, (m) => { if (m.type === "journal" && m.entry) setLive(m.entry); });
  return <JournalPanel projectId={pid} canWrite={canWrite} live={live} />;
}
