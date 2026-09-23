import { createContext, useCallback, useContext, useEffect, useState } from "react";
import ErrorBoundary from "../../ui/ErrorBoundary";
import { useOnline } from "../../hooks/useOnline";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type AlarmEvent, type Dashboard, type Project, type Sensor, type ShiftHandover } from "../../api/client";
import type { LiveState } from "../../hooks/liveConnection";
import { loadEvents, putSensors, useAlarmEvents, useLiveSelector, useLiveState, useProjectLive, useSensors } from "../../store/live";
import TopBar from "../../ui/TopBar";
import AnnunciatorControl from "../../ui/AnnunciatorControl";
import { summarize, type AlarmSummary } from "./model";
import { priorityLabel } from "../../i18n/labels";
import { can } from "../../api/permissions";
import { PriorityMark } from "../../ui/AlarmMark";
import ConnectionBanner, { LiveBadge } from "./ConnectionBanner";
import { t } from "../../i18n";

/** ISA-101 ekranlar ierarxiyasi (F2): L1 umumiy → L2 uchastka → L3 faceplate → L4 diagnostika.
 * Umumiy qobiq: jonli sensorlar (WebSocket), alarm jamlanmasi, navigatsiya (pastga/yuqoriga, tezkor tugmalar). */

/** Qobiq konteksti — kam o'zgaradigan qismlar (loyiha, konfiguratsiya). Jonli qismlar (sensorlar, alarmlar,
 * ulanish holati) umumiy store dan olinadi (UX-11): qobiq o'zi har o'qishda qayta chizilmaydi. */
interface OpsStatic {
  projectId: number;
  project: Project | null;
  dash: Dashboard | null;
  reload: () => Promise<void>;
  error: string;
}
export interface OpsContext extends OpsStatic {
  sensors: Sensor[];
  live: LiveState;
  summary: AlarmSummary;
  events: AlarmEvent[];
}

const Ctx = createContext<OpsStatic | null>(null);
/** Operator sahifasi konteksti + jonli ma'lumot (chaqirgan komponent sensorlar ro'yxatiga obuna bo'ladi). */
export const useOps = (): OpsContext => {
  const c = useContext(Ctx);
  if (!c) throw new Error("useOps OperatorShell ichida ishlatiladi");
  const sensors = useSensors(c.projectId);
  const events = useAlarmEvents(c.projectId);
  const live = useLiveState(c.projectId);
  const summary = useLiveSelector(c.projectId, summarize, sameSummary);
  return { ...c, sensors, events, live, summary };
};

function sameSummary(a: AlarmSummary, b: AlarmSummary): boolean {
  return a.total === b.total && a.stale === b.stale && a.worst === b.worst && (["critical", "high", "medium", "low"] as const).every((p) => a.byPriority[p] === b.byPriority[p]);
}

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
  const [openHandover, setOpenHandover] = useState<ShiftHandover | null>(null);
  const [error, setError] = useState("");
  const reload = useCallback(async () => {
    try {
      const [p, d, hs] = await Promise.all([api.project(pid), api.dashboard(pid), api.shiftHandovers(pid).catch(() => [] as ShiftHandover[]), loadEvents(pid)]);
      putSensors(pid, d.sensors, { replace: true });
      setProject(p); setDash(d); setError("");
      setOpenHandover(hs.find((h) => h.status === "handed") ?? null); // F9: qabul qilinmagan topshirish — ogohlantirish
    } catch (e) {
      setError(e instanceof Error ? e.message : "Yuklab bo'lmadi");
    }
  }, [pid]);
  useEffect(() => { void reload(); }, [reload]);
  // Jonli oqim — umumiy store (bitta soket); annunciator ham store da (yangi kvitlanmagan alarm)
  useProjectLive(pid);
  const online = useOnline();
  const summary = useLiveSelector(pid, summarize, sameSummary);
  const ctx: OpsStatic = { projectId: pid, project, dash, reload, error };
  const parent = crumbs.length > 1 ? crumbs[crumbs.length - 2] : null;
  return (
    <Ctx.Provider value={ctx}>
      <div className="page ops" data-level={level}>
        <TopBar alarms={{ pid, role: project?.my_role }} crumbs={[{ label: t("nav.projects"), to: "/" }, { label: project?.name ?? "…", to: `/projects/${pid}` }, ...crumbs]}>
          <LiveBadge pid={pid} />
          <AnnunciatorControl projectId={pid} canOperate={can(project?.my_role, "scada.ack")} />
        </TopBar>
        <nav className="ops-nav" aria-label={t("ops.nav")}>
          <span className="ops-level">L{level}</span>
          {parent?.to && <button className="btn sm" onClick={() => nav(parent.to!)} title={t("ops.up")}>↑ {parent.label}</button>}
          <Link className={`btn sm ${level === 1 ? "active" : ""}`} to={opsPath(pid)}>{t("ops.overview")}</Link>
          <Link className="btn sm" to={opsPath(pid, "area", "hydro")}>{t("ops.hydro")}</Link>
          <Link className="btn sm" to={opsPath(pid, "area", "powerhouse")}>{t("ops.powerhouse")}</Link>
          <Link className="btn sm" to={opsPath(pid, "area", "electrical")}>{t("ops.electrical")}</Link>
          <Link className="btn sm" to={opsPath(pid, "alarms")} data-testid="nav-alarms">{t("ops.alarms")}{summary.total ? ` (${summary.total})` : ""}</Link>
          <Link className="btn sm" to={opsPath(pid, "trends")} data-testid="nav-trends">{t("ops.trends")}</Link>
          <Link className="btn sm" to={opsPath(pid, "shift")} data-testid="nav-shift">{t("ops.shift")}</Link>
          <Link className={`btn sm ${level === 4 ? "active" : ""}`} to={opsPath(pid, "diag")}>{t("ops.diag")}</Link>
          <span className="grow" />
          <AlarmStrip summary={summary} flood={!!dash?.alarm_flood} pid={pid} />
        </nav>
        <ConnectionBanner pid={pid} />
        {error && <p className="error my-6 mx-16">{error}</p>}
        {openHandover && <div className="verdict warn my-6 mx-16" data-testid="handover-banner">Smena topshirish #{openHandover.id} ({openHandover.handed_by_username}) qabul qilinmagan — <Link to={opsPath(pid, "shift")}>qabul qiluvchi imzolasin</Link></div>}
        {!online && <div className="verdict warn my-6 mx-16" data-testid="offline-banner">{t("live.browserOffline")}</div>}
        <div className="page-body ops-body"><ErrorBoundary name={`L${level} ekran`}>{children}</ErrorBoundary></div>
      </div>
    </Ctx.Provider>
  );
}

/** Faol alarmlar jamlanmasi — ustuvorlik bo'yicha shakl + son (har ekranda ko'rinadi). */
export function AlarmStrip({ summary, flood, pid }: { summary: AlarmSummary; flood: boolean; pid: number }) {
  const items: ("critical" | "high" | "medium" | "low")[] = ["critical", "high", "medium", "low"];
  return (
    <Link to={opsPath(pid, "alarms")} className="alarm-strip" title={t("ops.alarmStripTitle")}>
      {flood && <span className="badge rejected">{t("ops.flood")}</span>}
      {items.map((p) => {
        const n = summary.byPriority[p];
        return (
          <span key={p} className={`row gap-2 ${n ? "" : "zero"}`} title={`${priorityLabel(p)}: ${n}`}>
            <PriorityMark priority={p} muted={!n} title={`${priorityLabel(p)}: ${n}`} /><b className="mono">{n}</b>
          </span>
        );
      })}
      {summary.stale > 0 && <span className="alarm-mark c-stale" title="aloqa yo'q">?{summary.stale}</span>}
    </Link>
  );
}
