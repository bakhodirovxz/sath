import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../store/auth";
import NotificationsBell from "./NotificationsBell";
import { useEffect, useState } from "react";
import { applyTheme, currentTheme, type ThemeName } from "./tokens";
import ProfileDialog from "./ProfileDialog";
import { t } from "../i18n";
import type { Role } from "../api/client";
import AlarmBanner from "../pages/operator/AlarmBanner";

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

/** `alarms` — loyiha sahifasi: ostida doimiy alarm banneri (UX-03; kvitlanmagan alarm bo'lmasa — yo'q). */
export default function TopBar({ crumbs = [], children, alarms }: { crumbs?: Crumb[]; children?: React.ReactNode; alarms?: { pid: number; role?: Role | null | undefined } | undefined }) {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [profile, setProfile] = useState(false);
  return (
    <>
    <div className="topbar ws-top">
      <Link to="/" className="brand">Sath</Link>
      <div className="crumbs">
        {crumbs.map((c, i) => (
          <span key={i} className="row gap-6">
            {i > 0 && <span className="sep">›</span>}
            {c.to ? <Link to={c.to}>{c.label}</Link> : <span>{c.label}</span>}
          </span>
        ))}
      </div>
      <div className="spacer" />
      {children}
      <ThemeToggle />
      <NotificationsBell />
      {user?.is_admin && <Link to="/admin" className="small" title={t("nav.adminTitle")}>{t("nav.admin")}</Link>}
      <button className={`btn sm ${user?.mfa_required ? "warn" : ""}`} title={user?.mfa_required ? t("nav.mfaRequired") : t("nav.profile")} onClick={() => setProfile(true)} data-testid="profile-btn">{user?.full_name || user?.username}{user?.mfa_required ? " ⚠" : ""}</button>
      <button className="btn sm" onClick={() => { logout(); nav("/login"); }}>{t("nav.logout")}</button>
      {profile && <ProfileDialog onClose={() => setProfile(false)} />}
    </div>
    {alarms && alarms.pid > 0 && <AlarmBanner pid={alarms.pid} role={alarms.role} />}
    </>
  );
}
