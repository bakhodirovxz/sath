import { useCallback, useEffect, useState } from "react";
import { api, type AuditRow, type RationalizationReport, type User } from "../api/client";
import { fmtDate } from "../ui/format";
import { useAuth } from "../store/auth";
import TopBar from "../ui/TopBar";
import Dialog from "../ui/Dialog";

export default function Admin() {
  const me = useAuth((s) => s.user);
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [resetFor, setResetFor] = useState<User | null>(null);
  const [form, setForm] = useState({ username: "", password: "", full_name: "", email: "", is_admin: false });
  const [newPassword, setNewPassword] = useState("");

  const load = () => api.users().then(setUsers).catch((e) => setError(e.message));
  useEffect(() => {
    void load();
  }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api.createUser(form);
      setCreating(false);
      setForm({ username: "", password: "", full_name: "", email: "", is_admin: false });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Xatolik");
    }
  }
  async function toggle(u: User, field: "is_active" | "is_admin") {
    try {
      await api.updateUser(u.id, { [field]: !u[field] });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Xatolik");
    }
  }
  async function resetPassword(e: React.FormEvent) {
    e.preventDefault();
    if (!resetFor) return;
    try {
      await api.updateUser(resetFor.id, { password: newPassword });
      setResetFor(null);
      setNewPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Xatolik");
    }
  }

  if (!me?.is_admin) return <div className="page"><TopBar /><div className="page-body">Faqat administrator uchun.</div></div>;

  return (
    <div className="page">
      <TopBar crumbs={[{ label: "Boshqaruv" }]}>
        <button className="btn sm primary" onClick={() => setCreating(true)}>Yangi foydalanuvchi</button>
      </TopBar>
      <div className="page-body page-narrow">
        <h1>Foydalanuvchilar</h1>
        {error && <p className="error">{error}</p>}
        <table className="grid">
          <thead><tr><th>Login</th><th>Ism</th><th>Email</th><th>Admin</th><th>Faol</th><th /></tr></thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td className="mono">{u.username}</td>
                <td>{u.full_name}</td>
                <td><input className="input" style={{ width: 180 }} defaultValue={u.email ?? ""} placeholder="—" onBlur={(e) => e.target.value !== (u.email ?? "") && api.updateUser(u.id, { email: e.target.value }).then(load).catch((err) => setError(err.message))} /></td>
                <td><input type="checkbox" checked={u.is_admin} disabled={u.id === me.id} onChange={() => toggle(u, "is_admin")} /></td>
                <td><input type="checkbox" checked={u.is_active} disabled={u.id === me.id} onChange={() => toggle(u, "is_active")} /></td>
                <td><button className="btn sm" onClick={() => setResetFor(u)}>Parolni almashtirish</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="dim small">Loyihaga a'zo qo'shish va rol berish — loyiha sahifasida.</p>
        <RationalizationSection />
        <AuditSection users={users} />
      </div>
      {creating && (
        <Dialog title="Yangi foydalanuvchi" onClose={() => setCreating(false)}>
          <form onSubmit={create}>
            <label className="field"><span>Login (lotin harflar, raqam, . _ -)</span><input className="input" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} autoFocus required pattern="[a-zA-Z0-9_.-]{3,64}" /></label>
            <label className="field"><span>Ism familiya</span><input className="input" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></label>
            <label className="field"><span>Email (bildirishnomalar uchun, ixtiyoriy)</span><input className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
            <label className="field"><span>Parol (kamida 4 belgi)</span><input className="input" type="text" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required minLength={4} /></label>
            <label className="row"><input type="checkbox" checked={form.is_admin} onChange={(e) => setForm({ ...form, is_admin: e.target.checked })} /> Administrator</label>
            <div className="actions">
              <button type="button" className="btn" onClick={() => setCreating(false)}>Bekor qilish</button>
              <button type="submit" className="btn primary">Yaratish</button>
            </div>
          </form>
        </Dialog>
      )}
      {resetFor && (
        <Dialog title={`Parol: ${resetFor.username}`} onClose={() => setResetFor(null)}>
          <form onSubmit={resetPassword}>
            <label className="field"><span>Yangi parol</span><input className="input" type="text" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} autoFocus required minLength={4} /></label>
            <div className="actions">
              <button type="button" className="btn" onClick={() => setResetFor(null)}>Bekor qilish</button>
              <button type="submit" className="btn primary">Saqlash</button>
            </div>
          </form>
        </Dialog>
      )}
    </div>
  );
}


/** ISA-18.2 §10: alarm ta'rifi bor, lekin ratsionalizatsiya qilinmagan sensorlar (barcha loyihalar). */
function RationalizationSection() {
  const [rep, setRep] = useState<RationalizationReport | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { api.adminRationalization().then(setRep).catch((e) => setError(e.message)); }, []);
  return (
    <>
      <h1 style={{ marginTop: 28 }}>Alarm ratsionalizatsiyasi</h1>
      {error && <p className="error">{error}</p>}
      {rep && (
        <>
          <p className="muted small">Alarm ta'rifi bor sensorlar: {rep.total} · ratsionalizatsiya qilingan: {rep.rationalized} · qilinmagan: {rep.unrationalized.length} (ISA-18.2 §10: sabab, oqibat, tuzatuvchi harakat, javob vaqti, ustuvorlik asosi)</p>
          {rep.unrationalized.length > 0 && (
            <table className="grid small">
              <thead><tr><th>Loyiha</th><th>Sensor</th><th>Ustuvorlik</th><th>Yetishmayotgan</th></tr></thead>
              <tbody>
                {rep.unrationalized.map((r) => (
                  <tr key={r.id}>
                    <td>{r.project_id}</td>
                    <td>{r.name}<div className="dim mono">{r.key}</div></td>
                    <td><span className={`badge ${r.priority === "critical" ? "rejected" : r.priority === "high" ? "high" : "open"}`}>{r.priority}</span></td>
                    <td className="mono dim">{r.missing.join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </>
  );
}


const ACTIONS = ["", "auth.", "user.", "project.", "model.", "version.", "cr.", "issue.", "sensor.", "alarm.", "sim.", "desktop.", "dashboard."];

/** Audit jurnali: kim, nima, qachon — filtrlar bilan, sahifalab. */
function AuditSection({ users }: { users: User[] }) {
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [action, setAction] = useState("");
  const [userId, setUserId] = useState("");
  const [error, setError] = useState("");
  const load = useCallback((before?: number) =>
    api.audit({ action: action || undefined, user_id: userId ? Number(userId) : undefined, limit: 100, before_id: before })
      .then((r) => setRows((prev) => (before ? [...prev, ...r] : r)))
      .catch((e) => setError(e.message)), [action, userId]);
  useEffect(() => { void load(); }, [load]);
  return (
    <>
      <h1 style={{ marginTop: 28 }}>Audit jurnali</h1>
      <div className="row wrap">
        <select className="select" style={{ width: 160 }} value={action} onChange={(e) => setAction(e.target.value)}>
          {ACTIONS.map((a) => <option key={a} value={a}>{a || "barcha amallar"}</option>)}
        </select>
        <select className="select" style={{ width: 200 }} value={userId} onChange={(e) => setUserId(e.target.value)}>
          <option value="">barcha foydalanuvchilar</option>
          {users.map((u) => <option key={u.id} value={u.id}>{u.username}</option>)}
        </select>
        <span className="grow" />
        <button className="btn sm" onClick={() => api.downloadCsv(`/api/audit?limit=2000${action ? `&action=${action}` : ""}`, "audit.json").catch((e) => setError(e.message))}>JSON yuklab olish</button>
      </div>
      {error && <p className="error">{error}</p>}
      <table className="grid small">
        <thead><tr><th>Vaqt</th><th>Kim</th><th>Amal</th><th>Obyekt</th><th>Loyiha</th><th>Tafsilot</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td className="mono">{fmtDate(r.created_at)}</td>
              <td>{r.username ?? <span className="dim">tizim</span>}</td>
              <td className="mono">{r.action}</td>
              <td>{r.target_type}{r.target_id != null && ` #${r.target_id}`}</td>
              <td>{r.project_id ?? ""}</td>
              <td className="dim small mono">{Object.keys(r.detail).length ? JSON.stringify(r.detail) : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length >= 100 && <button className="btn sm" style={{ marginTop: 8 }} onClick={() => load(rows[rows.length - 1].id)}>Yana</button>}
    </>
  );
}
