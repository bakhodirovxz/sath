import { Suspense, lazy, useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./store/auth";
import Login from "./pages/Login";
import { DialogHost } from "./ui/dialogs";
import NoticeHost from "./ui/NoticeHost";
import ProfileDialog from "./ui/ProfileDialog";
import { t, useLocale } from "./i18n";
import { applyTheme, opsTheme, type ThemeName } from "./ui/tokens";

// Sahifa darajasida kod bo'linishi (F10): login ekrani Three.js/ThatOpen/web-ifc ni yuklamaydi
const Projects = lazy(() => import("./pages/Projects"));
const ProjectPage = lazy(() => import("./pages/ProjectPage"));
const ModelPage = lazy(() => import("./pages/ModelPage"));
const Admin = lazy(() => import("./pages/Admin"));
const MyTasksPage = lazy(() => import("./pages/MyTasksPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const SitePage = lazy(() => import("./pages/SitePage"));
const FederationPage = lazy(() => import("./pages/FederationPage"));
const MonitoringRedirect = lazy(() => import("./pages/MonitoringRedirect"));
const L1Overview = lazy(() => import("./pages/operator/L1Overview"));
const L2Area = lazy(() => import("./pages/operator/L2Area"));
const L3Faceplate = lazy(() => import("./pages/operator/L3Faceplate"));
const L4Diagnostics = lazy(() => import("./pages/operator/L4Diagnostics"));
const AlarmsPage = lazy(() => import("./pages/operator/AlarmsPage"));
const Trends = lazy(() => import("./pages/operator/Trends"));
const Shift = lazy(() => import("./pages/operator/Shift"));

function RequireAuth({ children }: { children: JSX.Element }) {
  const { user, ready } = useAuth();
  const loc = useLocation();
  if (!ready) return <div className="page-body muted">{t("common.loading")}</div>;
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  // L2: admin bergan/boshlang'ich parol — almashtirilguncha faqat profil
  if (user.must_change_password) return <><div className="page-body muted">Parolni almashtiring…</div><ProfileDialog onClose={() => undefined} /></>;
  return children;
}

/** Tema marshrutga bog'langan (UX-05): dispetcher ekranlari (`/ops`, `/dashboard`) — ISA-101 operator varianti
 * (standart yoki kunduzgi, foydalanuvchi tanlovi), qolgan hammasi (BIM) — Blender Dark. */
export function themeForPath(path: string): ThemeName {
  return /^\/projects\/\d+\/(ops|dashboard)(\/|$)/.test(path) ? opsTheme() : "engineer";
}
function RouteTheme() {
  const { pathname } = useLocation();
  useEffect(() => { applyTheme(themeForPath(pathname), false); }, [pathname]);
  return null;
}

export default function App() {
  const init = useAuth((s) => s.init);
  const locale = useLocale(); // til almashganda sahifalar yangi matn bilan qayta chiziladi (UX-09)
  useEffect(() => {
    void init();
  }, [init]);
  return (
    <>
    <RouteTheme />
    <DialogHost />
    <NoticeHost />
    <Suspense fallback={<div className="page-body muted">{t("common.loading")}</div>}>
    <Routes key={locale}>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<RequireAuth><Projects /></RequireAuth>} />
      <Route path="/projects/:projectId" element={<RequireAuth><ProjectPage /></RequireAuth>} />
      <Route path="/projects/:projectId/dashboard" element={<RequireAuth><DashboardPage /></RequireAuth>} />
      <Route path="/projects/:projectId/site" element={<RequireAuth><SitePage /></RequireAuth>} />
      {/* SCADA-13 bildirishnomasi: bog'lanmagan sensorlar → versiya modelida Monitoring */}
      <Route path="/projects/:projectId/monitoring" element={<RequireAuth><MonitoringRedirect /></RequireAuth>} />
      {/* ISA-101 operator ekranlari (F2): L1 umumiy → L2 uchastka → L3 faceplate → L4 diagnostika */}
      <Route path="/projects/:projectId/ops" element={<RequireAuth><L1Overview /></RequireAuth>} />
      <Route path="/projects/:projectId/ops/area/:area" element={<RequireAuth><L2Area /></RequireAuth>} />
      <Route path="/projects/:projectId/ops/sensor/:sensorId" element={<RequireAuth><L3Faceplate /></RequireAuth>} />
      <Route path="/projects/:projectId/ops/unit/:unit" element={<RequireAuth><L3Faceplate /></RequireAuth>} />
      <Route path="/projects/:projectId/ops/alarms" element={<RequireAuth><AlarmsPage /></RequireAuth>} />
      <Route path="/projects/:projectId/ops/trends" element={<RequireAuth><Trends /></RequireAuth>} />
      <Route path="/projects/:projectId/ops/shift" element={<RequireAuth><Shift /></RequireAuth>} />
      <Route path="/projects/:projectId/ops/diag" element={<RequireAuth><L4Diagnostics /></RequireAuth>} />
      <Route path="/projects/:projectId/ops/diag/:sensorId" element={<RequireAuth><L4Diagnostics /></RequireAuth>} />
      <Route path="/models/:modelId" element={<RequireAuth><ModelPage /></RequireAuth>} />
      <Route path="/federations/:fedId" element={<RequireAuth><FederationPage /></RequireAuth>} />
      <Route path="/admin" element={<RequireAuth><Admin /></RequireAuth>} />
      <Route path="/tasks" element={<RequireAuth><MyTasksPage /></RequireAuth>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </Suspense>
    </>
  );
}
