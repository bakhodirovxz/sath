import { useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./store/auth";
import Login from "./pages/Login";
import Projects from "./pages/Projects";
import ProjectPage from "./pages/ProjectPage";
import ModelPage from "./pages/ModelPage";
import Admin from "./pages/Admin";
import DashboardPage from "./pages/DashboardPage";
import SitePage from "./pages/SitePage";

function RequireAuth({ children }: { children: JSX.Element }) {
  const { user, ready } = useAuth();
  const loc = useLocation();
  if (!ready) return <div className="page-body muted">Yuklanmoqda…</div>;
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  return children;
}

export default function App() {
  const init = useAuth((s) => s.init);
  useEffect(() => {
    void init();
  }, [init]);
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<RequireAuth><Projects /></RequireAuth>} />
      <Route path="/projects/:projectId" element={<RequireAuth><ProjectPage /></RequireAuth>} />
      <Route path="/projects/:projectId/dashboard" element={<RequireAuth><DashboardPage /></RequireAuth>} />
      <Route path="/projects/:projectId/site" element={<RequireAuth><SitePage /></RequireAuth>} />
      <Route path="/models/:modelId" element={<RequireAuth><ModelPage /></RequireAuth>} />
      <Route path="/admin" element={<RequireAuth><Admin /></RequireAuth>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
