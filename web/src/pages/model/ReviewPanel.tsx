import { useEffect, useState } from "react";
import { api, type ChangeRequest, type Model, type Role, type SafetyCheck, type Version } from "../../api/client";
import { useAuth } from "../../store/auth";
import { fmtDate, label } from "../../ui/format";
import Dialog from "../../ui/Dialog";
import Icon from "../../ui/Icon";
import { BBadge, BList, BOps, BPanel, BRow } from "../../ui/BlenderUI";

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
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const cr = crs.find((c) => c.id === selectedId) ?? crs.find((c) => c.status === "open" || c.status === "changes_requested") ?? crs[0] ?? null;
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

  const active = !!cr && (cr.status === "open" || cr.status === "changes_requested");
  const mine = !!cr && cr.author_id === me?.id;
  const crSafety = cr && safety && safety.version_id === cr.version_id ? safety : null;
  return (
    <div>
      {error && <p className="error small">{error}</p>}
      <BPanel id="crs" title="Tasdiqlash so'rovlari" count={crs.length} right={canOpen && (
        <button className="btn sm primary" onClick={() => setCreating(true)} title={`v${current.number} ni tasdiqqa yuborish`}><Icon name="send" size={12} /> v{current.number} ni tasdiqqa yuborish</button>
      )}>
        {!canOpen && isEngineer && current && current.state !== "wip" && (
          <p className="dim small" style={{ margin: "0 0 4px" }}>v{current.number} holati: {label(current.state)} — faqat «Ishda» versiya tasdiqqa yuboriladi.</p>
        )}
        <BList
          items={crs} keyOf={(c) => c.id} activeKey={cr?.id ?? null} rows={5} empty="Tasdiqlash so'rovlari yo'q"
          onSelect={(c) => setSelectedId(c.id)} onActivate={(c) => onOpenVersion(c.version_id)}
          render={(c) => (
            <>
              <span className="dim mono">#{c.id}</span>
              <span className="grow">{c.title}</span>
              <span className="dim">v{c.version_number}</span>
              <BBadge kind={c.status}>{label(c.status)}</BBadge>
            </>
          )}
        />
      </BPanel>
      {cr && (
        <BPanel id="cr-detail" title={`#${cr.id} ${cr.title}`}>
          <BRow label="Holat"><BBadge kind={cr.status}>{label(cr.status)}</BBadge></BRow>
          <BRow label="Muallif" value={`${cr.author_username} · ${fmtDate(cr.created_at)}`} />
          <BRow label="Versiya"><button className="btn sm" onClick={() => onOpenVersion(cr.version_id)}><Icon name="eye" size={12} /> v{cr.version_number} ni ochish</button></BRow>
          {cr.description && <BRow label="Tavsif" value={cr.description} title={cr.description} />}
          {active && (
            <BRow label="Xavfsizlik">
              {crSafety ? (
                <span className="row" style={{ gap: 6 }} title="Standart xavfsizlik ssenariylari shu versiya uchun">
                  <span className="badge" style={{ background: crSafety.counts.fail ? "var(--danger)" : crSafety.counts.warn ? "var(--warn)" : "var(--ok)", color: "#fff" }}>{crSafety.score}/100</span>
                  <span className={`small ${crSafety.counts.fail ? "error" : "dim"}`}>{crSafety.counts.fail ? `${crSafety.counts.fail} mezon bajarilmadi: ${crSafety.fails.join("; ")}` : crSafety.counts.warn ? `${crSafety.counts.warn} ogohlantirish` : "hammasi bajarildi"}</span>
                </span>
              ) : (
                <span className="row" style={{ gap: 6 }}>
                  <span className="dim small">tekshirilmagan</span>
                  <button className="btn sm" disabled={checking} onClick={() => void runSafety(cr.version_id)}>{checking ? "…" : "Tekshirish"}</button>
                </span>
              )}
            </BRow>
          )}
          {cr.reviews.length > 0 && (
            <div style={{ marginTop: 6 }}>
              {cr.reviews.map((r) => (
                <div key={r.id} className="comment">
                  <span className="who">{r.reviewer_username} · {fmtDate(r.created_at)} · </span>
                  <span className={`badge ${r.decision === "approve" ? "approved" : r.decision === "request_changes" ? "changes_requested" : ""}`}>
                    {r.decision === "approve" ? "Ma'qulladi" : r.decision === "request_changes" ? "O'zgartirish so'radi" : "Izoh"}
                  </span>
                  {r.comment && <div>{r.comment}</div>}
                </div>
              ))}
            </div>
          )}
          {active && (
            <div style={{ marginTop: 8 }}>
              <textarea className="textarea" style={{ minHeight: 44 }} placeholder="Izoh…" value={comment[cr.id] ?? ""} onChange={(e) => setComment({ ...comment, [cr.id]: e.target.value })} />
              <BOps>
                <button className="btn sm" disabled={busy || !(comment[cr.id] ?? "").trim()} onClick={() => act(() => api.reviewCR(cr.id, "comment", comment[cr.id]).then(() => setComment({ ...comment, [cr.id]: "" })))}>Izoh qoldirish</button>
                {isApprover && !mine && (
                  <>
                    <button className="btn sm" disabled={busy} onClick={() => act(() => api.reviewCR(cr.id, "request_changes", comment[cr.id] ?? ""))}>O'zgartirish so'rash</button>
                    <button className="btn sm primary" disabled={busy} onClick={() => { const s = crSafety; if (s && s.counts.fail && !confirm(`Xavfsizlik tekshiruvida ${s.counts.fail} ta mezon bajarilmagan (${s.score}/100):\n${s.fails.join("\n")}\n\nBaribir ma'qullaysizmi?`)) return; if (!s && !confirm("Bu versiya xavfsizlik tekshiruvidan o'tkazilmagan. Baribir ma'qullaysizmi?")) return; void act(() => api.reviewCR(cr.id, "approve", comment[cr.id] ?? "")); }}>Ma'qullash</button>
                  </>
                )}
                {(isApprover || mine) && <button className="btn sm danger" disabled={busy} onClick={() => confirm("So'rovni yopasizmi?") && act(() => api.rejectCR(cr.id))}>Yopish</button>}
              </BOps>
              {cr.status === "changes_requested" && mine && wipVersions.length > 0 && (
                <BRow label="Yangi versiya">
                  <select className="select" defaultValue="" onChange={(e) => e.target.value && act(() => api.setCRVersion(cr.id, Number(e.target.value)))}>
                    <option value="">bog'lash…</option>
                    {wipVersions.map((v) => <option key={v.id} value={v.id}>v{v.number} {v.message}</option>)}
                  </select>
                </BRow>
              )}
            </div>
          )}
          {cr.status === "approved" && isApprover && (
            <BOps>
              <button className="btn sm primary" disabled={busy} onClick={() => act(() => api.mergeCR(cr.id))}><Icon name="check" size={12} /> Tasdiqlash (published)</button>
              <span className="dim small">Avvalgi tasdiqlangan versiya arxivga o'tadi</span>
            </BOps>
          )}
        </BPanel>
      )}

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
