import { useEffect, useState } from "react";
import Icon from "../../ui/Icon";
import { api, type Issue, type IssueStatus, type Member, type Role, type Version, type Viewpoint } from "../../api/client";
import { useAuth } from "../../store/auth";
import { fmtDate, label } from "../../ui/format";
import Dialog from "../../ui/Dialog";
import { BBadge, BList, BOps, BPanel, BRow } from "../../ui/BlenderUI";

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

  return (
    <div>
      {error && <p className="error small">{error}</p>}
      <BPanel id="issues" title="Issue lar" count={list.length} right={
        <>
          <select className="select" style={{ width: "auto", padding: "1px 4px", fontSize: 11 }} value={filter} onChange={(e) => setFilter(e.target.value as "active" | "all")}>
            <option value="active">Faol</option>
            <option value="all">Hammasi</option>
          </select>
          <button className="btn sm primary" onClick={() => setCreating(true)} title="Joriy ko'rinish (kamera, tanlov, kesim) bilan"><Icon name="plus" size={12} /> Issue</button>
        </>
      }>
        <BList
          items={list} keyOf={(i) => i.id} activeKey={detail?.id ?? p.openIssueId} rows={6}
          onSelect={(i) => p.onOpenIssue(i.id)} onActivate={(i) => { if (detail?.id === i.id) void p.applyViewpoint(detail.viewpoint); }}
          empty={filter === "active" ? "Faol issue yo'q — elementni tanlab «Issue» bosing" : "Issue yo'q"}
          render={(i) => (
            <>
              <span className="dim mono">#{i.id}</span>
              <span className="grow">{i.title}</span>
              <span className="dim">{i.assignee_username ?? "—"}</span>
              {i.comment_count > 0 && <span className="dim">{i.comment_count}💬</span>}
              <BBadge kind={i.priority}>{label(i.priority)}</BBadge>
              <BBadge kind={i.status}>{label(i.status)}</BBadge>
            </>
          )}
        />
        <BOps>
          <button className="btn sm" title="BCF 2.1 — Revit/ArchiCAD/BIMcollab/Solibri uchun" onClick={async () => { try { const b = await api.bcfExport(p.modelId); const u = URL.createObjectURL(b); const a = document.createElement("a"); a.href = u; a.download = "issues.bcfzip"; a.click(); URL.revokeObjectURL(u); } catch (e) { setError(e instanceof Error ? e.message : "Xatolik"); } }}><Icon name="download" size={12} /> BCF eksport</button>
          {(p.role === "engineer" || p.role === "approver") && <label className="btn sm"><Icon name="upload" size={12} /> BCF import<input type="file" accept=".bcfzip,.bcf,.zip" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) api.bcfImport(p.modelId, f).then((r) => { alert(`BCF: ${r.created} yangi, ${r.updated} yangilandi`); p.onChanged(); }).catch((err) => setError(err.message)); e.target.value = ""; }} /></label>}
        </BOps>
      </BPanel>
      {detail && (
        <BPanel id="issue-detail" title={`#${detail.id} ${detail.title}`} right={<button className="btn sm" onClick={() => p.onOpenIssue(null)} title="Tafsilotni yopish"><Icon name="x" size={12} /></button>}>
          <BRow label="Holat">
            {canEditIssue(detail) ? (
              <select className="select" value={detail.status} onChange={(e) => update({ status: e.target.value as IssueStatus })}>
                {STATUSES.map((st) => <option key={st} value={st}>{label(st)}</option>)}
              </select>
            ) : <BBadge kind={detail.status}>{label(detail.status)}</BBadge>}
          </BRow>
          <BRow label="Muhimlik"><BBadge kind={detail.priority}>{label(detail.priority)}</BBadge></BRow>
          <BRow label="Ijrochi">
            {canEditIssue(detail) ? (
              <select className="select" value={detail.assignee_id ?? ""} onChange={(e) => update({ assignee_id: e.target.value ? Number(e.target.value) : null })}>
                <option value="">Ijrochi yo'q</option>
                {p.members.map((m) => <option key={m.user_id} value={m.user_id}>{m.full_name || m.username}</option>)}
              </select>
            ) : <span className="bval">{detail.assignee_username ?? "—"}</span>}
          </BRow>
          <BRow label="Muallif" value={`${detail.author_username} · ${fmtDate(detail.created_at)}`} />
          {detail.description && <BRow label="Tavsif" value={detail.description} title={detail.description} />}
          <BOps>
            <button className="btn sm primary" onClick={() => p.applyViewpoint(detail.viewpoint)}><Icon name="camera" size={12} /> Ko'rinishga o'tish</button>
          </BOps>
          <h3>Izohlar {detail.comments.length ? `(${detail.comments.length})` : ""}</h3>
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
        </BPanel>
      )}
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
