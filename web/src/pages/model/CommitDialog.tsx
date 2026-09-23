import { useState } from "react";
import Dialog from "../../ui/Dialog";
import { defaultCommitMessage, type CommitSummary } from "./commitSummary";

/** Qoralamalarni IFC ga qo'shish (commit): o'zgarishlar soni, ogohlantirishlar, izoh (UX-12). */
export default function CommitDialog({ summary, baseLabel, busy, onCommit, onClose }: {
  summary: CommitSummary;
  baseLabel: string;
  busy: boolean;
  onCommit: (message: string) => void;
  onClose: () => void;
}) {
  const [msg, setMsg] = useState(() => defaultCommitMessage(summary));
  const total = summary.added + summary.changed + summary.deleted;
  return (
    <Dialog title="Yangi versiya (commit)" onClose={onClose}>
      <div data-testid="commit-dialog">
        <table className="grid small commit-counts">
          <tbody>
            <tr><td>Qo'shilgan elementlar</td><td className="mono" data-testid="commit-added">{summary.added}</td></tr>
            <tr><td>O'zgargan elementlar</td><td className="mono" data-testid="commit-changed">{summary.changed}</td></tr>
            <tr><td>O'chirilgan elementlar</td><td className="mono" data-testid="commit-deleted">{summary.deleted}</td></tr>
          </tbody>
        </table>
        <p className="dim small">Asos: {baseLabel}</p>
        {summary.warnings.length > 0 && (
          <div className="verdict attention small" data-testid="commit-warnings"><ul className="warnings">{summary.warnings.map((w) => <li key={w}>{w}</li>)}</ul></div>
        )}
        <label className="field"><span>Nima o'zgardi (izoh)</span>
          <textarea className="textarea" value={msg} onChange={(e) => setMsg(e.target.value)} data-autofocus data-testid="commit-message" />
        </label>
        <div className="actions">
          <button type="button" className="btn" onClick={onClose}>Bekor qilish</button>
          <button type="button" className="btn primary" disabled={busy || total === 0 || !msg.trim()} onClick={() => onCommit(msg.trim())} data-testid="commit-ok">{busy ? "Saqlanmoqda…" : "Versiya yaratish"}</button>
        </div>
      </div>
    </Dialog>
  );
}
