import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type AlarmEvent, type Dashboard, type LiveMessage, type Project, type Sensor } from "../../api/client";
import { useLive, type LiveState } from "../../hooks/useLive";
import TopBar from "../../ui/TopBar";
import { alarmStyle, applyTheme, savedTheme } from "../../ui/tokens";
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
  const [error, setError] = useState("");
  useEffect(() => { applyTheme(savedTheme("operator"), false); }, []);
  const reload = useCallback(async () => {
    try {
      const [p, d, ev] = await Promise.all([api.project(pid), api.dashboard(pid), api.alarmEvents(pid, true)]);
      setProject(p); setDash(d); setSensors(d.sensors); setEvents(ev); setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Yuklab bo'lmadi");
    }
  }, [pid]);
  useEffect(() => { void reload(); }, [reload]);
  const onMessage = useCallback((m: LiveMessage) => {
    if (m.type === "alarm" && m.event) {
      const e = m.event as AlarmEvent;
      setEvents((prev) => [e, ...prev.filter((x) => x.id !== e.id)].filter((x) => !(x.ended_at && x.acked_at)));
    }
  }, []);
  const live = useLive(pid, setSensors, onMessage);
  const summary = useMemo(() => summarize(sensors), [sensors]);
  const ctx: OpsContext = { projectId: pid, project, sensors, dash, live, summary, events, reload, error };
  const parent = crumbs.length > 1 ? crumbs[crumbs.length - 2] : null;
  return (
    <Ctx.Provider value={ctx}>
      <div className="page ops" data-level={level}>
        <TopBar crumbs={[{ label: "Loyihalar", to: "/" }, { label: project?.name ?? "…", to: `/projects/${pid}` }, ...crumbs]}>
          <span className={`live-dot ${live.toLowerCase()}`} title="Jonli oqim: LIVE — xabar yaqinda; STALE — heartbeat kechikmoqda; OFFLINE — uzilgan" data-testid="live-state">● {live}</span>
        </TopBar>
        <nav className="ops-nav" aria-label="ISA-101 navigatsiya">
          <span className="ops-level">L{level}</span>
          {parent?.to && <button className="btn sm" onClick={() => nav(parent.to!)} title="Ota ekranga qaytish">↑ {parent.label}</button>}
          <Link className={`btn sm ${level === 1 ? "active" : ""}`} to={opsPath(pid)}>L1 Umumiy</Link>
          <Link className="btn sm" to={opsPath(pid, "area", "hydro")}>Gidro</Link>
          <Link className="btn sm" to={opsPath(pid, "area", "powerhouse")}>Mashina zali</Link>
          <Link className="btn sm" to={opsPath(pid, "area", "electrical")}>Elektr</Link>
          <Link className={`btn sm ${level === 4 ? "active" : ""}`} to={opsPath(pid, "diag")}>L4 Diagnostika</Link>
          <span className="grow" />
          <AlarmStrip summary={summary} flood={!!dash?.alarm_flood} pid={pid} />
        </nav>
        {error && <p className="error" style={{ margin: "6px 16px" }}>{error}</p>}
        <div className="page-body ops-body">{children}</div>
      </div>
    </Ctx.Provider>
  );
}

/** Faol alarmlar jamlanmasi — ustuvorlik bo'yicha shakl + son (har ekranda ko'rinadi). */
export function AlarmStrip({ summary, flood, pid }: { summary: AlarmSummary; flood: boolean; pid: number }) {
  const items: ("critical" | "high" | "medium" | "low")[] = ["critical", "high", "medium", "low"];
  return (
    <Link to={`/projects/${pid}/dashboard`} className="alarm-strip" title="Alarm jurnali">
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
