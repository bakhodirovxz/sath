import { useEffect, useState } from "react";
import Icon from "../ui/Icon";
import { useNavigate } from "react-router-dom";
import { api, type DesktopPackage, type Project } from "../api/client";
import { useAuth } from "../store/auth";
import TopBar from "../ui/TopBar";
import Dialog from "../ui/Dialog";
import { label } from "../ui/format";

export default function Projects() {
  const user = useAuth((s) => s.user);
  const nav = useNavigate();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", location: "" });
  const [error, setError] = useState("");
  const [desktop, setDesktop] = useState<DesktopPackage | null>(null);

  const load = () => api.projects().then(setProjects).catch((e) => setError(e.message));
  useEffect(() => {
    void load();
    api.desktopLatest().then(setDesktop).catch(() => setDesktop(null));
  }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    try {
      const p = await api.createProject(form);
      setCreating(false);
      nav(`/projects/${p.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Xatolik");
    }
  }

  return (
    <div className="page">
      <TopBar crumbs={[{ label: "Loyihalar" }]}>
        {desktop?.files.map((f) => (
          <button key={f.name} className="btn sm" onClick={() => api.desktopDownload(f.url).catch((e) => setError(e.message))}
            title={`${f.name} — ${(f.size / 1048576).toFixed(0)} MB. ${f.kind === "installer" ? "Sath desktop dasturini o'rnatish (Windows)" : "Portable zip — ochib Sath.bat ni ishga tushiring"}`}>
            Sath {desktop.version} {f.kind === "installer" ? "o'rnatish" : "zip"} <Icon name="download" size={13} />
          </button>
        ))}
        {user?.is_admin && <button className="btn sm primary" onClick={() => setCreating(true)}>Yangi loyiha</button>}
      </TopBar>
      <div className="page-body page-narrow">
        <h1>Loyihalar</h1>
        <p className="muted small">Har loyiha — bitta GES: 3D modellar (versiyalar, tasdiqlash), dispetcher paneli (SCADA, raqamli egizak), simulyatsiya. Chizish — Sath desktop (yuqoridagi yuklab olish).</p>
        {error && <p className="error">{error}</p>}
        {projects === null ? (
          <p className="muted">Yuklanmoqda…</p>
        ) : projects.length === 0 ? (
          <p className="muted">
            {user?.is_admin ? "Hali loyiha yo'q. Yuqoridagi tugma bilan birinchisini yarating." : "Sizga hali loyiha biriktirilmagan. Administratorga murojaat qiling."}
          </p>
        ) : (
          <div className="cards">
            {projects.map((p) => (
              <div key={p.id} className="card" onClick={() => nav(`/projects/${p.id}`)}>
                <div className="card-head">
                  <b>{p.name}</b>
                  {p.my_role ? <span className="badge open">{label(p.my_role)}</span> : <span className="badge archived">admin</span>}
                </div>
                <div className="muted small">{p.location || "—"}{p.description && ` · ${p.description}`}</div>
                <div className="card-stats"><span>{p.model_count} model</span></div>
                <div className="row card-actions" onClick={(e) => e.stopPropagation()}>
                  <button className="btn sm" onClick={() => nav(`/projects/${p.id}`)}>Modellar</button>
                  <button className="btn sm" onClick={() => nav(`/projects/${p.id}/dashboard`)}>Dispetcher paneli</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      {creating && (
        <Dialog title="Yangi loyiha" onClose={() => setCreating(false)}>
          <form onSubmit={create}>
            <label className="field"><span>Nomi (GES)</span><input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} autoFocus required /></label>
            <label className="field"><span>Joylashuv</span><input className="input" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} /></label>
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
