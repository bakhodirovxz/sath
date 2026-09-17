import { useEffect, useState } from "react";
import Icon from "../../ui/Icon";
import { api, type Issue, type IssueStatus, type Member, type Role, type Version, type Viewpoint } from "../../api/client";
import { useAuth } from "../../store/auth";
import { fmtDate, label } from "../../ui/format";
import Dialog from "../../ui/Dialog";

interface Props {
  modelId: number;
  role: Role | null;
  members: Member[];
  current: Version | null;
  issues: Issue[];
  openIssueId: number | null;
  createRequested: number; // ISSUE buyrug'i uchun trigger (o'sib boradi)
  getViewpoint: () => Promise<Viewpoint>;
  applyViewpoint: (vp: Viewpoint) => Promise<void>;
  onChanged: () => void;
  onOpenIssue: (id: number | null) => void;
}

const STATUSES: IssueStatus[] = ["open", "in_progress", "resolved", "closed"];

/** BCF uslubidagi muammolar: 3D ko'rinish (kamera + tanlangan elementlar + kesim) bilan saqlanadi. */
export default function IssuesPanel(p: Props) {
  const me = useAuth((s) => s.user);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<{ title: string; description: string; assignee_id: string; priority: Issue["priority"] }>({ title: "", description: "", assignee_id: "", priority: "normal" });
  const [detail, setDetail] = useState<Issue | null>(null);
  const [comment, setComment] = useState("");
  const [withView, setWithView] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<"active" | "all">("active");

  useEffect(() => {
    if (p.createRequested > 0) setCreating(true);
  }, [p.createRequested]);

  useEffect(() => {
    if (p.openIssueId == null) return setDetail(null);
    api.issue(p.openIssueId).then(setDetail).catch((e) => setError(e.message));
  }, [p.openIssueId, p.issues]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const vp = await p.getViewpoint();
      const issue = await api.createIssue(p.modelId, {
        title: form.title,
        description: form.description,
        version_id: p.current?.id ?? null,
        assignee_id: form.assignee_id ? Number(form.assignee_id) : null,
        priority: form.priority,
        viewpoint: vp,
      });
      setCreating(false);
      setForm({ title: "", description: "", assignee_id: "", priority: "normal" });
      p.onChanged();
      p.onOpenIssue(issue.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Xatolik");
    }
  }

  async function update(body: Parameters<typeof api.updateIssue>[1]) {
    if (!detail) return;
    try {
      setDetail(await api.updateIssue(detail.id, body));
      p.onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Xatolik");
    }
  }

  async function addComment(e: React.FormEvent) {
    e.preventDefault();
    if (!detail || !comment.trim()) return;
    try {
      setDetail(await api.commentIssue(detail.id, comment, withView ? await p.getViewpoint() : null));
      setComment("");
      p.onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Xatolik");
    }
  }

  const canEditIssue = (i: Issue) => p.role === "approver" || i.author_id === me?.id || i.assignee_id === me?.id;
  const list = p.issues.filter((i) => filter === "all" || (i.status !== "closed" && i.status !== "resolved"));

  if (detail) {
    return (
      <div>
        <div className="row" style={{ marginBottom: 8 }}>
          <button className="btn sm" onClick={() => p.onOpenIssue(null)}><Icon name="arrow-left" size={13} /> Ro'yxat</button>
          <button className="btn sm" onClick={() => p.applyViewpoint(detail.viewpoint)}>Ko'rinishga o'tish</button>
        </div>
        {error && <p className="error small">{error}</p>}
        <div className="title row"><b>#{detail.id} {detail.title}</b><span className={`badge ${detail.status}`}>{label(detail.status)}</span><span className={`badge ${detail.priority}`}>{label(detail.priority)}</span></div>
        <div className="meta muted small">{detail.author_username} · {fmtDate(detail.created_at)} · ijrochi: {detail.assignee_username ?? "—"}</div>
        {detail.description && <p className="small">{detail.description}</p>}
        {canEditIssue(detail) && (
          <div className="row wrap" style={{ margin: "8px 0" }}>
            <select className="select" style={{ width: "auto" }} value={detail.status} onChange={(e) => update({ status: e.target.value as IssueStatus })}>
              {STATUSES.map((s) => <option key={s} value={s}>{label(s)}</option>)}
            </select>
            <select className="select" style={{ width: "auto" }} value={detail.assignee_id ?? ""} onChange={(e) => update({ assignee_id: e.target.value ? Number(e.target.value) : null })}>
              <option value="">Ijrochi yo'q</option>
              {p.members.map((m) => <option key={m.user_id} value={m.user_id}>{m.full_name || m.username}</option>)}
            </select>
          </div>
        )}
        <h3>Izohlar</h3>
        {detail.comments.length === 0 && <p className="dim small">Izoh yo'q.</p>}
        {detail.comments.map((c) => (
          <div key={c.id} className="comment">
            <span className="who">{c.author_username} · {fmtDate(c.created_at)}</span>
            {c.viewpoint && <> · <a onClick={() => p.applyViewpoint(c.viewpoint!)}>ko'rinish</a></>}
            <div>{c.body}</div>
          </div>
        ))}
        <form onSubmit={addComment} style={{ marginTop: 8 }}>
          <textarea className="textarea" style={{ minHeight: 44 }} value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Izoh…" />
          <div className="row" style={{ marginTop: 6 }}>
            <label className="row small"><input type="checkbox" checked={withView} onChange={(e) => setWithView(e.target.checked)} /> joriy ko'rinish bilan</label>
            <span className="grow" />
            <button className="btn sm primary" type="submit" disabled={!comment.trim()}>Yuborish</button>
          </div>
        </form>
      </div>
    );
  }

  return (
    <div>
      <div className="row wrap" style={{ marginBottom: 8 }}>
        <button className="btn sm primary" onClick={() => setCreating(true)}>Issue ochish</button>
        <button className="btn sm" title="BCF 2.1 — Revit/ArchiCAD/BIMcollab/Solibri uchun" onClick={async () => { try { const b = await api.bcfExport(p.modelId); const u = URL.createObjectURL(b); const a = document.createElement("a"); a.href = u; a.download = "issues.bcfzip"; a.click(); URL.revokeObjectURL(u); } catch (e) { setError(e instanceof Error ? e.message : "Xatolik"); } }}>BCF eksport</button>
        {(p.role === "engineer" || p.role === "approver") && <label className="btn sm">BCF import<input type="file" accept=".bcfzip,.bcf,.zip" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) api.bcfImport(p.modelId, f).then((r) => { alert(`BCF: ${r.created} yangi, ${r.updated} yangilandi`); p.onChanged(); }).catch((err) => setError(err.message)); e.target.value = ""; }} /></label>}
        <span className="grow" />
        <select className="select" style={{ width: "auto" }} value={filter} onChange={(e) => setFilter(e.target.value as "active" | "all")}>
          <option value="active">Faol</option>
          <option value="all">Hammasi</option>
        </select>
      </div>
      {error && <p className="error small">{error}</p>}
      {list.length === 0 && <p className="muted">{filter === "active" ? "Faol issue yo'q." : "Issue yo'q."} Elementni tanlab, «Issue ochish» — joriy ko'rinish saqlanadi.</p>}
      {list.map((i) => (
        <div key={i.id} className="list-item" onClick={() => p.onOpenIssue(i.id)}>
          <div className="title"><b>#{i.id}</b><span className="grow">{i.title}</span><span className={`badge ${i.status}`}>{label(i.status)}</span></div>
          <div className="meta">{i.author_username} → {i.assignee_username ?? "—"} · {label(i.priority)} · {i.comment_count} izoh · {fmtDate(i.updated_at)}</div>
        </div>
      ))}
      {creating && (
        <Dialog title="Yangi issue" onClose={() => setCreating(false)}>
          <form onSubmit={create}>
            <label className="field"><span>Sarlavha</span><input className="input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} autoFocus required /></label>
            <label className="field"><span>Tavsif</span><textarea className="textarea" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
            <div className="row">
              <label className="field grow"><span>Ijrochi</span>
                <select className="select" value={form.assignee_id} onChange={(e) => setForm({ ...form, assignee_id: e.target.value })}>
                  <option value="">—</option>
                  {p.members.map((m) => <option key={m.user_id} value={m.user_id}>{m.full_name || m.username}</option>)}
                </select>
              </label>
              <label className="field"><span>Muhimlik</span>
                <select className="select" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value as Issue["priority"] })}>
                  {(["low", "normal", "high", "critical"] as const).map((s) => <option key={s} value={s}>{label(s)}</option>)}
                </select>
              </label>
            </div>
            <p className="dim small">Joriy kamera, tanlangan elementlar va kesimlar issue bilan saqlanadi.</p>
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
