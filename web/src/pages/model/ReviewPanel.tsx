import { useEffect, useState } from "react";
import { api, type ChangeRequest, type Model, type Role, type SafetyCheck, type Version } from "../../api/client";
import { useAuth } from "../../store/auth";
import { fmtDate, label } from "../../ui/format";
import Dialog from "../../ui/Dialog";

interface Props {
  modelId: number;
  role: Role | null;
  versions: Version[];
  current: Version | null;
  crs: ChangeRequest[];
  onChanged: () => void;
  onOpenVersion: (versionId: number) => void;
}

/** Tasdiqlash oqimi: CR ochish → taqriz (izoh / o'zgartirish / ma'qullash) → tasdiqlash (merge). */
export default function ReviewPanel({ modelId, role, versions, current, crs, onChanged, onOpenVersion }: Props) {
  const me = useAuth((s) => s.user);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [comment, setComment] = useState<Record<number, string>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // Xavfsizlik tekshiruvi xulosasi (model bo'yicha oxirgi) — taqrizchi CR versiyasi tekshirilganini ko'radi
  const [safety, setSafety] = useState<Model["safety"] | null>(null);
  const [checking, setChecking] = useState(false);
  useEffect(() => { api.model(modelId).then((m) => setSafety(m.safety ?? null)).catch(() => undefined); }, [modelId, crs.length]);
  async function runSafety(versionId: number) {
    setChecking(true);
    try { const r: SafetyCheck = await api.safetyCheck(modelId, versionId); setSafety({ score: r.score, counts: r.counts, verdict: r.verdict, version_id: versionId, at: new Date().toISOString(), fails: r.rows.filter((x) => x.status === "fail").map((x) => x.title) }); }
    catch (err) { setError(err instanceof Error ? err.message : "Xatolik"); } finally { setChecking(false); }
  }

  const isEngineer = role === "engineer" || role === "approver";
  const isApprover = role === "approver";
  const canOpen = isEngineer && current && current.state === "wip";
  const wipVersions = versions.filter((v) => v.state === "wip");

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await fn();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Xatolik");
    } finally {
      setBusy(false);
    }
  }

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!current) return;
    await act(async () => {
      await api.createCR(modelId, { version_id: current.id, title, description });
      setCreating(false);
      setTitle("");
      setDescription("");
    });
  }

  return (
    <div>
      {error && <p className="error small">{error}</p>}
      {canOpen && (
        <div className="row" style={{ marginBottom: 8 }}>
          <button className="btn sm primary" onClick={() => setCreating(true)}>v{current.number} ni tasdiqqa yuborish</button>
        </div>
      )}
      {!canOpen && isEngineer && current && current.state !== "wip" && (
        <p className="dim small">v{current.number} holati: {label(current.state)} — faqat «Ishda» versiya tasdiqqa yuboriladi.</p>
      )}
      {crs.length === 0 && <p className="muted">Tasdiqlash so'rovlari yo'q.</p>}

      {crs.map((cr) => {
        const active = cr.status === "open" || cr.status === "changes_requested";
        const mine = cr.author_id === me?.id;
        return (
          <div key={cr.id} className="section-box">
            <div className="title row">
              <b>#{cr.id} {cr.title}</b>
              <span className={`badge ${cr.status}`}>{label(cr.status)}</span>
            </div>
            <div className="meta muted small">
              {cr.author_username} · {fmtDate(cr.created_at)} ·{" "}
              <a onClick={() => onOpenVersion(cr.version_id)}>v{cr.version_number} ni ochish</a>
            </div>
            {cr.description && <p className="small" style={{ margin: "6px 0" }}>{cr.description}</p>}
            {active && (
              <div className="row small" style={{ alignItems: "center", gap: 6, margin: "4px 0" }} title="Standart xavfsizlik ssenariylari (toshqinlar, zilzila, barqarorlik, filtratsiya…) shu versiya uchun">
                <span className="dim">Xavfsizlik:</span>
                {safety && safety.version_id === cr.version_id ? (
                  <>
                    <span className="badge" style={{ background: safety.counts.fail ? "var(--danger)" : safety.counts.warn ? "var(--warn, #b98626)" : "var(--ok)", color: "#fff" }}>{safety.score}/100</span>
                    <span className={safety.counts.fail ? "error" : "dim"}>{safety.counts.fail ? `${safety.counts.fail} ta mezon bajarilmadi: ${safety.fails.join("; ")}` : safety.counts.warn ? `${safety.counts.warn} ogohlantirish` : "barcha mezonlar bajarildi"}</span>
                  </>
                ) : (
                  <>
                    <span className="dim">bu versiya tekshirilmagan</span>
                    <button className="btn sm" disabled={checking} onClick={() => void runSafety(cr.version_id)}>{checking ? "…" : "Tekshirish"}</button>
                  </>
                )}
              </div>
            )}
            {cr.reviews.map((r) => (
              <div key={r.id} className="comment">
                <span className="who">{r.reviewer_username} · {fmtDate(r.created_at)} · </span>
                <span className={`badge ${r.decision === "approve" ? "approved" : r.decision === "request_changes" ? "changes_requested" : ""}`}>
                  {r.decision === "approve" ? "Ma'qulladi" : r.decision === "request_changes" ? "O'zgartirish so'radi" : "Izoh"}
                </span>
                {r.comment && <div>{r.comment}</div>}
              </div>
            ))}
            {active && (
              <div style={{ marginTop: 8 }}>
                <textarea className="textarea" style={{ minHeight: 44 }} placeholder="Izoh…" value={comment[cr.id] ?? ""} onChange={(e) => setComment({ ...comment, [cr.id]: e.target.value })} />
                <div className="row wrap" style={{ marginTop: 6 }}>
                  <button className="btn sm" disabled={busy || !(comment[cr.id] ?? "").trim()} onClick={() => act(() => api.reviewCR(cr.id, "comment", comment[cr.id]).then(() => setComment({ ...comment, [cr.id]: "" })))}>Izoh qoldirish</button>
                  {isApprover && !mine && (
                    <>
                      <button className="btn sm" disabled={busy} onClick={() => act(() => api.reviewCR(cr.id, "request_changes", comment[cr.id] ?? ""))}>O'zgartirish so'rash</button>
                      <button className="btn sm primary" disabled={busy} onClick={() => { const s = safety && safety.version_id === cr.version_id ? safety : null; if (s && s.counts.fail && !confirm(`Xavfsizlik tekshiruvida ${s.counts.fail} ta mezon bajarilmagan (${s.score}/100):\n${s.fails.join("\n")}\n\nBaribir ma'qullaysizmi?`)) return; if (!s && !confirm("Bu versiya xavfsizlik tekshiruvidan o'tkazilmagan. Baribir ma'qullaysizmi?")) return; void act(() => api.reviewCR(cr.id, "approve", comment[cr.id] ?? "")); }}>Ma'qullash</button>
                    </>
                  )}
                  {(isApprover || mine) && <button className="btn sm danger" disabled={busy} onClick={() => confirm("So'rovni yopasizmi?") && act(() => api.rejectCR(cr.id))}>Yopish</button>}
                </div>
                {cr.status === "changes_requested" && mine && wipVersions.length > 0 && (
                  <div className="row" style={{ marginTop: 6 }}>
                    <span className="small muted">Yangi versiyani bog'lash:</span>
                    <select className="select" style={{ width: "auto" }} defaultValue="" onChange={(e) => e.target.value && act(() => api.setCRVersion(cr.id, Number(e.target.value)))}>
                      <option value="">v…</option>
                      {wipVersions.map((v) => <option key={v.id} value={v.id}>v{v.number} {v.message}</option>)}
                    </select>
                  </div>
                )}
              </div>
            )}
            {cr.status === "approved" && isApprover && (
              <div className="row" style={{ marginTop: 8 }}>
                <button className="btn sm primary" disabled={busy} onClick={() => act(() => api.mergeCR(cr.id))}>Tasdiqlash (published)</button>
                <span className="dim small">Avvalgi tasdiqlangan versiya arxivga o'tadi</span>
              </div>
            )}
          </div>
        );
      })}

      {creating && current && (
        <Dialog title={`v${current.number} ni tasdiqqa yuborish`} onClose={() => setCreating(false)}>
          <form onSubmit={create}>
            <label className="field"><span>Sarlavha</span><input className="input" value={title} onChange={(e) => setTitle(e.target.value)} autoFocus required /></label>
            <label className="field"><span>Tavsif (nima o'zgardi, nimani tekshirish kerak)</span><textarea className="textarea" value={description} onChange={(e) => setDescription(e.target.value)} /></label>
            <div className="actions">
              <button type="button" className="btn" onClick={() => setCreating(false)}>Bekor qilish</button>
              <button type="submit" className="btn primary" disabled={busy}>Yuborish</button>
            </div>
          </form>
        </Dialog>
      )}
    </div>
  );
}
