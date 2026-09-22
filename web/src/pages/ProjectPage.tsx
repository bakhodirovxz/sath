import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, type DocKind, type Member, type Model, type Project, type ProjectDocument, type Role, type User } from "../api/client";
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
        <button className="btn sm" onClick={() => nav(`/projects/${pid}/ops`)} title="ISA-101 operator ekranlari">Operator (L1)</button>
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
                  <td>{m.safety ? <span className="badge" title={`${m.safety.verdict}${m.safety.fails.length ? ": " + m.safety.fails.join("; ") : ""} · ${new Date(m.safety.at).toLocaleString("uz")}`} style={{ background: m.safety.counts.fail ? "var(--danger)" : m.safety.counts.warn ? "var(--warn, #b98626)" : "var(--ok)", color: "#fff" }}>{m.safety.score ?? "—"}/100</span> : <span className="dim small">tekshirilmagan</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <CrsSettings project={project} canManage={canManage} onSaved={load} onError={setError} />
        <NamingSettings project={project} canManage={canManage} onSaved={load} onError={setError} />
        <DocumentsSection projectId={pid} canEdit={project?.my_role === "engineer" || project?.my_role === "approver"} canDelete={canManage} onError={setError} />
        {canManage && (
          <p className="small">
            <label className="row" style={{ gap: 6 }}>
              <input type="checkbox" checked={!!project?.ids_required} onChange={(e) => api.updateProject(pid, { ids_required: e.target.checked }).then(load).catch((err) => setError(err.message))} data-testid="ids-required" />
              IDS majburiy — axborot talablari (docs/ids/sath-ges.ids) o'tmagan versiya tasdiqlanmaydi
            </label>
          </p>
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

/** G3: loyiha georeferensiyasi — EPSG (UTM 41N/42N, Pulkovo GK 11/12), lokal (0,0,0) ning global E/N/H, burilish. */
function CrsSettings({ project, canManage, onSaved, onError }: { project: Project | null; canManage: boolean; onSaved: () => void; onError: (m: string) => void }) {
  const [edit, setEdit] = useState(false);
  const [f, setF] = useState({ epsg_code: 32642, origin_e: 500000, origin_n: 4570000, origin_h: 0, crs_rotation_deg: 0 });
  const [ll, setLl] = useState({ lat: "41.62", lon: "69.98" });
  useEffect(() => { if (project?.crs) setF({ epsg_code: project.crs.epsg, origin_e: project.crs.origin_e, origin_n: project.crs.origin_n, origin_h: project.crs.origin_h, crs_rotation_deg: project.crs.rotation_deg }); }, [project]);
  if (!project) return null;
  const c = project.crs;
  return (
    <div className="panel" style={{ margin: "8px 0" }} data-testid="crs-settings">
      <div className="row">
        <b>Georeferensiya</b>
        <span className="grow" />
        {c ? <span className="small">EPSG:{c.epsg} <span className="dim">{c.name}</span> · E {c.origin_e.toFixed(2)} N {c.origin_n.toFixed(2)} H {c.origin_h.toFixed(1)}{c.rotation_deg ? ` · burilish ${c.rotation_deg}°` : ""}</span> : <span className="muted small">sozlanmagan — modellar faqat lokal koordinatada (DEM, GIS, geodeziya bilan solishtirish ishonchsiz)</span>}
        {canManage && <button className="btn sm" onClick={() => setEdit(!edit)}>{edit ? "Yopish" : "Sozlash"}</button>}
      </div>
      {edit && (
        <form className="row" style={{ flexWrap: "wrap", gap: 8, marginTop: 8 }} onSubmit={(e) => { e.preventDefault(); api.updateProject(project.id, f).then(() => { setEdit(false); onSaved(); }).catch((err) => onError(err.message)); }}>
          <label className="field"><span>EPSG</span>
            <select className="select" value={f.epsg_code} onChange={(e) => setF({ ...f, epsg_code: Number(e.target.value) })} data-testid="crs-epsg">
              <option value={32641}>32641 — WGS 84 / UTM 41N</option>
              <option value={32642}>32642 — WGS 84 / UTM 42N</option>
              <option value={28411}>28411 — Pulkovo 1942 / GK 11</option>
              <option value={28412}>28412 — Pulkovo 1942 / GK 12</option>
              {![32641, 32642, 28411, 28412].includes(f.epsg_code) && <option value={f.epsg_code}>{f.epsg_code}</option>}
            </select>
          </label>
          <label className="field"><span>Origin E, m</span><input className="input" type="number" step="0.01" value={f.origin_e} onChange={(e) => setF({ ...f, origin_e: Number(e.target.value) })} /></label>
          <label className="field"><span>Origin N, m</span><input className="input" type="number" step="0.01" value={f.origin_n} onChange={(e) => setF({ ...f, origin_n: Number(e.target.value) })} /></label>
          <label className="field"><span>Origin H, m</span><input className="input" type="number" step="0.1" value={f.origin_h} onChange={(e) => setF({ ...f, origin_h: Number(e.target.value) })} /></label>
          <label className="field"><span>X o'qi burilishi, ° (sharqdan)</span><input className="input" type="number" step="0.01" value={f.crs_rotation_deg} onChange={(e) => setF({ ...f, crs_rotation_deg: Number(e.target.value) })} /></label>
          <div className="row" style={{ gap: 6, alignItems: "flex-end" }}>
            <label className="field"><span>Lat</span><input className="input" style={{ width: 100 }} value={ll.lat} onChange={(e) => setLl({ ...ll, lat: e.target.value })} /></label>
            <label className="field"><span>Lon</span><input className="input" style={{ width: 100 }} value={ll.lon} onChange={(e) => setLl({ ...ll, lon: e.target.value })} /></label>
            <button type="button" className="btn sm" title="Lat/Lon dan zona va origin E/N ni taklif qilish" onClick={() => api.crsSuggest(project.id, Number(ll.lat), Number(ll.lon), f.epsg_code >= 28400 && f.epsg_code < 28500 ? "gk" : "utm").then((s) => setF({ ...f, epsg_code: s.epsg, origin_e: s.origin_e, origin_n: s.origin_n })).catch((err) => onError(err.message))}>Taklif</button>
          </div>
          <div className="actions" style={{ width: "100%" }}>
            {c && <button type="button" className="btn sm danger" onClick={() => api.updateProject(project.id, { epsg_code: 0 }).then(() => { setEdit(false); onSaved(); }).catch((err) => onError(err.message))}>O'chirish</button>}
            <button className="btn primary" type="submit" data-testid="crs-save">Saqlash</button>
          </div>
        </form>
      )}
    </div>
  );
}

/** G4 (ISO 19650): konteyner nomlash qoidasi — shablon maydonlari {project} {originator} {volume} {level} {type} {role} {number}. */
function NamingSettings({ project, canManage, onSaved, onError }: { project: Project | null; canManage: boolean; onSaved: () => void; onError: (m: string) => void }) {
  const [t, setT] = useState("");
  const [req, setReq] = useState(false);
  useEffect(() => { setT(project?.naming_template ?? ""); setReq(!!project?.naming_required); }, [project]);
  if (!project) return null;
  return (
    <div className="panel" style={{ margin: "8px 0" }} data-testid="naming-settings">
      <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
        <b>Konteyner nomlash (ISO 19650-2)</b>
        {canManage ? (
          <>
            <input className="input" style={{ minWidth: 320 }} placeholder="{project}-{originator}-{volume}-{level}-{type}-{role}-{number}" value={t} onChange={(e) => setT(e.target.value)} data-testid="naming-template" />
            <label className="row" style={{ gap: 4 }}><input type="checkbox" checked={req} onChange={(e) => setReq(e.target.checked)} /> majburiy (mos kelmasa yuklash rad)</label>
            <button className="btn sm" onClick={() => api.updateProject(project.id, { naming_template: t, naming_required: req }).then(onSaved).catch((e) => onError(e.message))}>Saqlash</button>
          </>
        ) : <span className="small mono">{project.naming_template || "—"}{project.naming_required ? " (majburiy)" : ""}</span>}
      </div>
      <p className="dim small" style={{ margin: "4px 0 0" }}>Maydonlar [A-Z0-9]+, ajratuvchi shablondagidek; masalan CHR-SATH-ZZ-XX-M3-C-0001.ifc. Yaroqlilik (S0–S7, A/B, CR, PR) va reviziya (P01/C01) kodlari versiyada — Model → Versiyalar.</p>
    </div>
  );
}

const DOC_KINDS: { id: DocKind; title: string }[] = [
  { id: "eir", title: "EIR — buyurtmachi axborot talablari" },
  { id: "bep", title: "BEP — BIM ijro rejasi" },
  { id: "tidp", title: "TIDP — vazifa axborot yetkazish rejasi" },
  { id: "midp", title: "MIDP — asosiy axborot yetkazish rejasi" },
  { id: "other", title: "Boshqa" },
];

/** G4: loyiha hujjatlari (EIR/BEP/TIDP/MIDP) — yuklash, ro'yxat, yuklab olish, o'chirish (tasdiqlovchi). */
function DocumentsSection({ projectId, canEdit, canDelete, onError }: { projectId: number; canEdit: boolean; canDelete: boolean; onError: (m: string) => void }) {
  const [docs, setDocs] = useState<ProjectDocument[]>([]);
  const [kind, setKind] = useState<DocKind>("eir");
  const [title, setTitle] = useState("");
  const load = useCallback(() => api.documents(projectId).then(setDocs).catch((e) => onError(e.message)), [projectId, onError]);
  useEffect(() => { void load(); }, [load]);
  return (
    <div className="panel" style={{ margin: "8px 0" }} data-testid="documents">
      <div className="row"><b>Hujjatlar (ISO 19650: EIR, BEP, TIDP/MIDP)</b><span className="grow" /><span className="dim small">{docs.length} ta</span></div>
      {docs.length > 0 && (
        <table className="grid small" style={{ marginTop: 6 }}>
          <thead><tr><th>Tur</th><th>Nomi</th><th>Fayl</th><th>Kim</th><th /></tr></thead>
          <tbody>
            {docs.map((d) => (
              <tr key={d.id}>
                <td className="mono">{d.kind.toUpperCase()}</td>
                <td>{d.title}</td>
                <td><button className="btn sm" onClick={() => api.downloadCsv(`/api/projects/${projectId}/documents/${d.id}/file`, d.file_name).catch((e) => onError(e.message))}>{d.file_name}</button> <span className="dim">{(d.file_size / 1024).toFixed(0)} KB</span></td>
                <td className="dim">{d.uploader_username} · {new Date(d.created_at).toLocaleDateString()}</td>
                <td>{canDelete && <button className="btn sm" onClick={() => api.deleteDocument(projectId, d.id).then(load).catch((e) => onError(e.message))}>O'chirish</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {canEdit && (
        <div className="row" style={{ gap: 6, marginTop: 6, flexWrap: "wrap" }}>
          <select className="select" value={kind} onChange={(e) => setKind(e.target.value as DocKind)} style={{ width: "auto" }}>
            {DOC_KINDS.map((k) => <option key={k.id} value={k.id}>{k.title}</option>)}
          </select>
          <input className="input" placeholder="Sarlavha (ixtiyoriy)" value={title} onChange={(e) => setTitle(e.target.value)} style={{ width: 220 }} />
          <label className="btn sm">
            Fayl tanlash (pdf, docx, xlsx…)
            <input type="file" style={{ display: "none" }} accept=".pdf,.docx,.xlsx,.doc,.xls,.txt,.md,.csv,.ids,.zip" data-testid="doc-file" onChange={(e) => { const f = e.target.files?.[0]; if (!f) return; api.uploadDocument(projectId, f, kind, title).then(() => { setTitle(""); void load(); }).catch((err) => onError(err.message)); e.target.value = ""; }} />
          </label>
        </div>
      )}
    </div>
  );
}
