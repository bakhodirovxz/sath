import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../store/auth";
import NotificationsBell from "./NotificationsBell";

export interface Crumb {
  label: string;
  to?: string;
}

export default function TopBar({ crumbs = [], children }: { crumbs?: Crumb[]; children?: React.ReactNode }) {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  return (
    <div className="topbar ws-top">
      <Link to="/" className="brand">Sath</Link>
      <div className="crumbs">
        {crumbs.map((c, i) => (
          <span key={i} className="row" style={{ gap: 6 }}>
            {i > 0 && <span className="sep">›</span>}
            {c.to ? <Link to={c.to}>{c.label}</Link> : <span>{c.label}</span>}
          </span>
        ))}
      </div>
      <div className="spacer" />
      {children}
      <NotificationsBell />
      {user?.is_admin && <Link to="/admin" className="small">Boshqaruv</Link>}
      <span className="muted small">{user?.full_name || user?.username}</span>
      <button className="btn sm" onClick={() => { logout(); nav("/login"); }}>Chiqish</button>
    </div>
  );
}
