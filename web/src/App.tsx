import { Suspense, lazy, useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./store/auth";
import Login from "./pages/Login";
import { DialogHost } from "./ui/dialogs";
import ProfileDialog from "./ui/ProfileDialog";

// Sahifa darajasida kod bo'linishi (F10): login ekrani Three.js/ThatOpen/web-ifc ni yuklamaydi
const Projects = lazy(() => import("./pages/Projects"));
const ProjectPage = lazy(() => import("./pages/ProjectPage"));
const ModelPage = lazy(() => import("./pages/ModelPage"));
const Admin = lazy(() => import("./pages/Admin"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const SitePage = lazy(() => import("./pages/SitePage"));
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
  if (!ready) return <div className="page-body muted">Yuklanmoqda…</div>;
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  // L2: admin bergan/boshlang'ich parol — almashtirilguncha faqat profil
  if (user.must_change_password) return <><div className="page-body muted">Parolni almashtiring…</div><ProfileDialog onClose={() => undefined} /></>;
  return children;
}

export default function App() {
  const init = useAuth((s) => s.init);
  useEffect(() => {
    void init();
  }, [init]);
  return (
    <>
    <DialogHost />
    <Suspense fallback={<div className="page-body muted">Yuklanmoqda…</div>}>
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<RequireAuth><Projects /></RequireAuth>} />
      <Route path="/projects/:projectId" element={<RequireAuth><ProjectPage /></RequireAuth>} />
      <Route path="/projects/:projectId/dashboard" element={<RequireAuth><DashboardPage /></RequireAuth>} />
      <Route path="/projects/:projectId/site" element={<RequireAuth><SitePage /></RequireAuth>} />
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
      <Route path="/admin" element={<RequireAuth><Admin /></RequireAuth>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </Suspense>
    </>
  );
}
