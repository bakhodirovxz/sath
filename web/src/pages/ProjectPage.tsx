import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, type Member, type Model, type Project, type Role, type User } from "../api/client";
import { useAuth } from "../store/auth";
import TopBar from "../ui/TopBar";
import Dialog from "../ui/Dialog";
import { label } from "../ui/format";

const ROLES: Role[] = ["viewer", "operator", "engineer", "approver"];

export default function ProjectPage() {
  const { projectId } = useParams();
  const pid = Number(projectId);
  const nav = useNavigate();
  const user = useAuth((s) => s.user);
  const [project, setProject] = useState<Project | null>(null);
  const [models, setModels] = useState<Model[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [allUsers, setAllUsers] = useState<User[]>([]);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", description: "" });
  const [newMember, setNewMember] = useState<{ user_id: string; role: Role }>({ user_id: "", role: "viewer" });

  const canEdit = project?.my_role === "engineer" || project?.my_role === "approver";
  const canManage = project?.my_role === "approver";

  const load = useCallback(async () => {
    try {
      const [p, m, mem] = await Promise.all([api.project(pid), api.models(pid), api.members(pid)]);
      setProject(p);
      setModels(m);
      setMembers(mem);
      if (user?.is_admin) setAllUsers(await api.users());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Xatolik");
    }
  }, [pid, user?.is_admin]);
  useEffect(() => {
    void load();
  }, [load]);

  async function createModel(e: React.FormEvent) {
    e.preventDefault();
    try {
      const m = await api.createModel(pid, form);
      setCreating(false);
      nav(`/models/${m.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Xatolik");
    }
  }

  async function addMember(e: React.FormEvent) {
    e.preventDefault();
    if (!newMember.user_id) return;
    try {
      await api.setMember(pid, Number(newMember.user_id), newMember.role);
      setNewMember({ user_id: "", role: "viewer" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Xatolik");
    }
  }

  if (!project) return <div className="page"><TopBar /><div className="page-body muted">{error || "Yuklanmoqda…"}</div></div>;

  const candidates = allUsers.filter((u) => u.is_active && !members.some((m) => m.user_id === u.id));

  return (
    <div className="page">
      <TopBar crumbs={[{ label: "Loyihalar", to: "/" }, { label: project.name }]}>
        <button className="btn sm" onClick={() => nav(`/projects/${pid}/dashboard`)} title="SCADA: jonli qiymatlar, alarmlar, hisobot">Dispetcher paneli</button>
        <button className="btn sm" onClick={() => nav(`/projects/${pid}/site`)} title="Yer, tuproq, seysmiklik, sathlar, inshoot belgilari — simulyatsiyalar uchun">Maydon pasporti</button>
        {canEdit && <TwinButton pid={pid} onDone={(id) => nav(`/models/${id}`)} onError={setError} />}
        {canEdit && <button className="btn sm primary" onClick={() => setCreating(true)}>Yangi model</button>}
      </TopBar>
      <div className="page-body page-narrow">
        <h1>{project.name}</h1>
        {project.location && <p className="muted" style={{ marginTop: -10 }}>{project.location}</p>}
        {project.description && <p>{project.description}</p>}
        {error && <p className="error">{error}</p>}

        <h2>Modellar</h2>
        {models.length === 0 ? (
          <p className="muted">{canEdit ? "Hali model yo'q. Yangi model yaratib, IFC fayl yuklang." : "Hali model yo'q."}</p>
        ) : (
          <table className="grid">
            <thead><tr><th>Nomi</th><th>Versiyalar</th><th>Tasdiqlangan</th><th>Xavfsizlik</th></tr></thead>
            <tbody>
              {models.map((m) => (
                <tr key={m.id} className="clickable" onClick={() => nav(`/models/${m.id}`)}>
                  <td><b>{m.name}</b>{m.description && <div className="muted small">{m.description}</div>}</td>
                  <td>{m.version_count}</td>
                  <td>{m.published_version_id ? <span className="badge published">bor</span> : <span className="dim">yo'q</span>}</td>
                  <td>{m.safety ? <span className="badge" title={`${m.safety.verdict}${m.safety.fails.length ? ": " + m.safety.fails.join("; ") : ""} · ${new Date(m.safety.at).toLocaleString("uz")}`} style={{ background: m.safety.counts.fail ? "var(--danger)" : m.safety.counts.warn ? "var(--warn, #b98626)" : "var(--ok)", color: "#fff" }}>{m.safety.score}/100</span> : <span className="dim small">tekshirilmagan</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <h2>A'zolar</h2>
        <table className="grid">
          <thead><tr><th>Foydalanuvchi</th><th>Rol</th>{canManage && <th />}</tr></thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.user_id}>
                <td>{m.full_name || m.username} <span className="dim small">{m.username}</span></td>
                <td>
                  {canManage ? (
                    <select className="select" style={{ width: "auto" }} value={m.role}
                      onChange={(e) => api.setMember(pid, m.user_id, e.target.value as Role).then(load)}>
                      {ROLES.map((r) => <option key={r} value={r}>{label(r)}</option>)}
                    </select>
                  ) : label(m.role)}
                </td>
                {canManage && <td><button className="btn sm" onClick={() => api.removeMember(pid, m.user_id).then(load)}>Chiqarish</button></td>}
              </tr>
            ))}
          </tbody>
        </table>
        {canManage && user?.is_admin && (
          <form className="row" style={{ marginTop: 10 }} onSubmit={addMember}>
            <select className="select" style={{ width: 260 }} value={newMember.user_id} onChange={(e) => setNewMember({ ...newMember, user_id: e.target.value })}>
              <option value="">Foydalanuvchi tanlang…</option>
              {candidates.map((u) => <option key={u.id} value={u.id}>{u.full_name || u.username} ({u.username})</option>)}
            </select>
            <select className="select" style={{ width: 160 }} value={newMember.role} onChange={(e) => setNewMember({ ...newMember, role: e.target.value as Role })}>
              {ROLES.map((r) => <option key={r} value={r}>{label(r)}</option>)}
            </select>
            <button className="btn" type="submit" disabled={!newMember.user_id}>Qo'shish</button>
          </form>
        )}
        {canManage && !user?.is_admin && <p className="dim small">A'zo qo'shishni administrator bajaradi; siz rollarni o'zgartira olasiz.</p>}
      </div>
      {creating && (
        <Dialog title="Yangi model" onClose={() => setCreating(false)}>
          <form onSubmit={createModel}>
            <label className="field"><span>Nomi (masalan: To'g'on, Mashina zali)</span><input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} autoFocus required /></label>
            <label className="field"><span>Tavsif</span><textarea className="textarea" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
            <div className="actions">
              <button type="button" className="btn" onClick={() => setCreating(false)}>Bekor qilish</button>
              <button type="submit" className="btn primary">Yaratish</button>
            </div>
          </form>
        </Dialog>
      )}
    </div>
  );
}


/** Tayyor raqamli egizak (haqiqiy GES presetlari: Chorvoq, Hoover…) — bir bosishda model + pasport + foto. */
function TwinButton({ pid, onDone, onError }: { pid: number; onDone: (modelId: number) => void; onError: (m: string) => void }) {
  const [presets, setPresets] = useState<{ id: string; title: string; description: string }[]>([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.twinPresets().then(setPresets).catch(() => undefined); }, []);
  if (!presets.length) return null;
  return (
    <select className="select sm" value="" disabled={busy} title="Tayyor GES raqamli egizagi: relyef, to'g'on, minora, tunnellar, mashina zali, agregatlar, suv tashlagich + maydon pasporti (ochiq manbalar) — simulyatsiyalar uchun tayyor" onChange={async (e) => {
      const id = e.target.value; if (!id) return;
      setBusy(true);
      try { const t = await api.createTwin(pid, id); onDone(t.model_id); } catch (err) { onError(err instanceof Error ? err.message : "Xatolik"); } finally { setBusy(false); }
    }}>
      <option value="">{busy ? "Yaratilmoqda…" : "Tayyor egizak…"}</option>
      {presets.map((p) => <option key={p.id} value={p.id} title={p.description}>{p.title}</option>)}
    </select>
  );
}
