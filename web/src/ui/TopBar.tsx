import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../store/auth";
import NotificationsBell from "./NotificationsBell";
import { useEffect, useState } from "react";
import { applyTheme, currentTheme, type ThemeName } from "./tokens";
import ProfileDialog from "./ProfileDialog";

/** Tema almashtirgich (F1): engineer (Blender) ↔ operator (ISA-101); tanlov saqlanadi. */
function ThemeToggle() {
  const [theme, setTheme] = useState<ThemeName>(() => currentTheme());
  useEffect(() => { setTheme(currentTheme()); }, []);
  const next: ThemeName = theme === "operator" ? "engineer" : "operator";
  return (
    <button className="btn sm theme-toggle" title={`Tema: ${theme === "operator" ? "operator (ISA-101)" : "muhandis (Blender)"} — almashtirish`} onClick={() => { applyTheme(next); setTheme(next); }}>
      {theme === "operator" ? "ISA-101" : "Blender"}
    </button>
  );
}

export interface Crumb {
  label: string;
  to?: string;
}

export default function TopBar({ crumbs = [], children }: { crumbs?: Crumb[]; children?: React.ReactNode }) {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [profile, setProfile] = useState(false);
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
      <ThemeToggle />
      <NotificationsBell />
      {user?.is_admin && <Link to="/admin" className="small">Boshqaruv</Link>}
      <button className={`btn sm ${user?.mfa_required ? "warn" : ""}`} title={user?.mfa_required ? "MFA yoqilishi shart" : "Profil: parol, MFA"} onClick={() => setProfile(true)} data-testid="profile-btn">{user?.full_name || user?.username}{user?.mfa_required ? " ⚠" : ""}</button>
      <button className="btn sm" onClick={() => { logout(); nav("/login"); }}>Chiqish</button>
      {profile && <ProfileDialog onClose={() => setProfile(false)} />}
    </div>
  );
}
