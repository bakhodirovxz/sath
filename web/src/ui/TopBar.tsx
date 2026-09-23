import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../store/auth";
import NotificationsBell from "./NotificationsBell";
import { useEffect, useState } from "react";
import { applyTheme, currentTheme, type ThemeName } from "./tokens";
import ProfileDialog from "./ProfileDialog";
import { t } from "../i18n";

/** Dispetcher ekrani kontrasti (UX-05): standart (ISA-101 kulrang) ↔ kunduzgi (yuqori kontrast); tanlov saqlanadi.
 * BIM (muhandis) sahifalarida ko'rsatilmaydi — u yerda Blender Dark doimiy. */
function ThemeToggle() {
  const [theme, setTheme] = useState<ThemeName>(() => currentTheme());
  useEffect(() => { setTheme(currentTheme()); }, []);
  if (theme === "engineer") return null;
  const next: ThemeName = theme === "operator" ? "operator-hc" : "operator";
  return (
    <button className="btn sm theme-toggle" title={t("theme.toggleTitle")} aria-pressed={theme === "operator-hc"} onClick={() => { applyTheme(next); setTheme(next); }}>
      {theme === "operator-hc" ? t("theme.operatorHc") : t("theme.operator")}
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
