import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import ErrorBoundary from "../../ui/ErrorBoundary";
import { useOnline } from "../../hooks/useOnline";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type AlarmEvent, type Command, type Dashboard, type LiveMessage, type Project, type Sensor, type ShiftHandover } from "../../api/client";
import { useLive, type LiveState } from "../../hooks/useLive";
import TopBar from "../../ui/TopBar";
import { alarmStyle, applyTheme, savedTheme } from "../../ui/tokens";
import { annunciator } from "../../ui/annunciator";
import AnnunciatorControl from "../../ui/AnnunciatorControl";
import { summarize, type AlarmSummary } from "./model";

/** ISA-101 ekranlar ierarxiyasi (F2): L1 umumiy → L2 uchastka → L3 faceplate → L4 diagnostika.
 * Umumiy qobiq: jonli sensorlar (WebSocket), alarm jamlanmasi, navigatsiya (pastga/yuqoriga, tezkor tugmalar). */

export interface OpsContext {
  projectId: number;
  project: Project | null;
  sensors: Sensor[];
  dash: Dashboard | null;
  live: LiveState;
  summary: AlarmSummary;
  events: AlarmEvent[];
  /** Oxirgi jonli buyruq yangilanishi (WS) — boshqaruv bloki holat kuzatuvi uchun */
  liveCommand: Command | null;
  reload: () => Promise<void>;
  error: string;
}

const Ctx = createContext<OpsContext | null>(null);
export const useOps = (): OpsContext => {
  const c = useContext(Ctx);
  if (!c) throw new Error("useOps OperatorShell ichida ishlatiladi");
  return c;
};

export function opsPath(pid: number, ...parts: (string | number)[]): string {
  return [`/projects/${pid}/ops`, ...parts].join("/");
}

export interface Crumb { label: string; to?: string }

export default function OperatorShell({ level, crumbs, children }: { level: 1 | 2 | 3 | 4; crumbs: Crumb[]; children: React.ReactNode }) {
  const { projectId } = useParams();
  const pid = Number(projectId);
  const nav = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [sensors, setSensors] = useState<Sensor[]>([]);
  const [events, setEvents] = useState<AlarmEvent[]>([]);
  const [liveCommand, setLiveCommand] = useState<Command | null>(null);
  const [openHandover, setOpenHandover] = useState<ShiftHandover | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { applyTheme(savedTheme("operator"), false); }, []);
  const reload = useCallback(async () => {
    try {
      const [p, d, ev, hs] = await Promise.all([api.project(pid), api.dashboard(pid), api.alarmEvents(pid, true), api.shiftHandovers(pid).catch(() => [] as ShiftHandover[])]);
      setProject(p); setDash(d); setSensors(d.sensors); setEvents(ev); setError("");
      setOpenHandover(hs.find((h) => h.status === "handed") ?? null); // F9: qabul qilinmagan topshirish — ogohlantirish
    } catch (e) {
      setError(e instanceof Error ? e.message : "Yuklab bo'lmadi");
    }
  }, [pid]);
  useEffect(() => { void reload(); }, [reload]);
  const onMessage = useCallback((m: LiveMessage) => {
    if (m.type === "alarm" && m.event) {
      const e = m.event as AlarmEvent;
      setEvents((prev) => [e, ...prev.filter((x) => x.id !== e.id)].filter((x) => !(x.ended_at && x.acked_at)));
      // Annunciator (F6): yangi kvitlanmagan alarm — signal (kritik ack gacha takror); kvitlash/yopilish — to'xtaydi
      if (e.acked_at || e.ended_at) annunciator.ack(e.id);
      else if (!prevIds.current.has(e.id)) annunciator.alarm(e.id, (e.priority ?? "medium") as "low" | "medium" | "high" | "critical");
      prevIds.current.add(e.id);
    }
    if (m.type === "command" && m.command) setLiveCommand(m.command);
  }, []);
  const prevIds = useRef(new Set<number>());
  const live = useLive(pid, setSensors, onMessage);
  const online = useOnline();
  const summary = useMemo(() => summarize(sensors), [sensors]);
  const ctx: OpsContext = { projectId: pid, project, sensors, dash, live, summary, events, liveCommand, reload, error };
  const parent = crumbs.length > 1 ? crumbs[crumbs.length - 2] : null;
  return (
    <Ctx.Provider value={ctx}>
      <div className="page ops" data-level={level}>
        <TopBar crumbs={[{ label: "Loyihalar", to: "/" }, { label: project?.name ?? "…", to: `/projects/${pid}` }, ...crumbs]}>
          <span className={`live-dot ${live.toLowerCase()}`} title="Jonli oqim: LIVE — xabar yaqinda; STALE — heartbeat kechikmoqda; OFFLINE — uzilgan" data-testid="live-state">● {live}</span>
          <AnnunciatorControl projectId={pid} canOperate={["operator", "engineer", "approver"].includes(project?.my_role ?? "")} />
        </TopBar>
        <nav className="ops-nav" aria-label="ISA-101 navigatsiya">
          <span className="ops-level">L{level}</span>
          {parent?.to && <button className="btn sm" onClick={() => nav(parent.to!)} title="Ota ekranga qaytish">↑ {parent.label}</button>}
          <Link className={`btn sm ${level === 1 ? "active" : ""}`} to={opsPath(pid)}>L1 Umumiy</Link>
          <Link className="btn sm" to={opsPath(pid, "area", "hydro")}>Gidro</Link>
          <Link className="btn sm" to={opsPath(pid, "area", "powerhouse")}>Mashina zali</Link>
          <Link className="btn sm" to={opsPath(pid, "area", "electrical")}>Elektr</Link>
          <Link className="btn sm" to={opsPath(pid, "alarms")} data-testid="nav-alarms">Alarmlar{summary.total ? ` (${summary.total})` : ""}</Link>
          <Link className="btn sm" to={opsPath(pid, "trends")} data-testid="nav-trends">Trendlar</Link>
          <Link className="btn sm" to={opsPath(pid, "shift")} data-testid="nav-shift">Smena</Link>
          <Link className={`btn sm ${level === 4 ? "active" : ""}`} to={opsPath(pid, "diag")}>L4 Diagnostika</Link>
          <span className="grow" />
          <AlarmStrip summary={summary} flood={!!dash?.alarm_flood} pid={pid} />
        </nav>
        {error && <p className="error" style={{ margin: "6px 16px" }}>{error}</p>}
        {openHandover && <div className="verdict warn" style={{ margin: "6px 16px" }} data-testid="handover-banner">Smena topshirish #{openHandover.id} ({openHandover.handed_by_username}) qabul qilinmagan — <Link to={opsPath(pid, "shift")}>qabul qiluvchi imzolasin</Link></div>}
        {!online && <div className="verdict warn" style={{ margin: "6px 16px" }} data-testid="offline-banner">OFFLAYN — tarmoq yo'q. Qiymatlar oxirgi ma'lum holat.</div>}
        <div className="page-body ops-body"><ErrorBoundary name={`L${level} ekran`}>{children}</ErrorBoundary></div>
      </div>
    </Ctx.Provider>
  );
}

/** Faol alarmlar jamlanmasi — ustuvorlik bo'yicha shakl + son (har ekranda ko'rinadi). */
export function AlarmStrip({ summary, flood, pid }: { summary: AlarmSummary; flood: boolean; pid: number }) {
  const items: ("critical" | "high" | "medium" | "low")[] = ["critical", "high", "medium", "low"];
  return (
    <Link to={opsPath(pid, "alarms")} className="alarm-strip" title="Alarm sahifasi">
      {flood && <span className="badge rejected">TOSHQIN</span>}
      {items.map((p) => {
        const st = alarmStyle("high", p);
        const n = summary.byPriority[p];
        return (
          <span key={p} className="alarm-mark" style={{ color: n ? st.color : "var(--text-dim)" }} title={`${p}: ${n}`}>
            {st.glyph}{n}
          </span>
        );
      })}
      {summary.stale > 0 && <span className="alarm-mark" style={{ color: "var(--alarm-stale)" }} title="aloqa yo'q">?{summary.stale}</span>}
    </Link>
  );
}
