import { useCallback, useEffect, useState } from "react";
import { api, type ValidationState, type ValidationStatusKind } from "../../api/client";
import { dialogs } from "../../ui/dialogs";
import { fmtDate, fmtDay } from "../../ui/format";

/* I3 — model validatsiya yozuvlari: qaysi model, qaysi davr, qanday qabul mezoni, kim imzoladi va
   qachongacha amal qiladi. Validatsiyasiz natija muhandislik qarori uchun asos emas. */

export const VAL_CLS: Record<ValidationStatusKind, string> = {
  validated: "published",
  expired: "high",
  failed: "rejected",
  unvalidated: "archived",
};
export const VAL_TXT: Record<ValidationStatusKind, string> = {
  validated: "validatsiyalangan",
  expired: "muddati o'tgan",
  failed: "mos emas",
  unvalidated: "validatsiyalanmagan",
};

export function ValidationPanel({ projectId, canApprove }: { projectId: number; canApprove: boolean }) {
  const [st, setSt] = useState<ValidationState | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => api.validation(projectId).then(setSt).catch((e) => setErr(e.message)), [projectId]);
  useEffect(() => { void load(); }, [load]);
  const sign = () =>
    void dialogs.prompt("Validatsiya izohi", "", { text: "Qaysi ma'lumot va qanday tekshiruv asosida imzolanmoqda" }).then((note) => {
      if (note == null) return;
      setBusy(true);
      api.createValidation(projectId, { days: 30, note })
        .then(() => { setErr(""); void load(); })
        .catch((e) => setErr(e.message))
        .finally(() => setBusy(false));
    });
  const ev = st?.evaluation;
  const cur = st?.status;
  return (
    <div className="dash-block">
      <div className="row items-center">
        <b>Model validatsiyasi</b>
        <span className="muted small">qabul mezonlari, imzo va amal qilish muddati — egizak natijasiga tayanish uchun asos</span>
        {cur && <span className={`badge ${VAL_CLS[cur.status]}`} data-testid="val-status">{VAL_TXT[cur.status]}</span>}
        <span className="grow" />
        {canApprove && <button className="btn sm primary" disabled={busy} data-testid="val-sign" onClick={sign}>Imzolash</button>}
      </div>
      {err && <p className="error small">{err}</p>}
      {cur?.note && <p className={`small ${cur.status === "validated" ? "dim" : "error"}`}>{cur.note}</p>}
      {cur?.status === "validated" && (
        <p className="small dim">Imzoladi: <b>{cur.validated_by}</b> · {cur.validated_at ? fmtDate(cur.validated_at) : ""}
          {cur.valid_until && <> · amal qiladi: <b>{fmtDay(cur.valid_until)}</b></>}
          {cur.version_id != null && <> · model v{cur.version_id}</>}</p>
      )}
      {ev && (
        <table className="grid small" data-testid="val-criteria">
          <thead><tr><th>Mezon</th><th>Qiymat</th><th>Chegara</th><th>Holat</th></tr></thead>
          <tbody>
            {(ev.checks ?? []).map((c) => (
              <tr key={c.name} className={c.ok ? undefined : "alarm-active"}>
                <td>{c.label}</td>
                <td className="mono">{c.value}</td>
                <td className="mono dim">{c.limit}</td>
                <td><span className={`badge ${c.ok ? "published" : "rejected"}`}>{c.ok ? "mos" : "mos emas"}</span></td>
              </tr>
            ))}
            {(ev.checks ?? []).length === 0 && <tr><td colSpan={4} className="muted">{ev.reason || "baholash uchun ma'lumot yetarli emas"}</td></tr>}
          </tbody>
        </table>
      )}
      {st && st.records.length > 0 && (
        <table className="grid small" data-testid="val-records">
          <thead><tr><th>Sana</th><th>Imzo</th><th>Davr</th><th>RMSE / siljish</th><th>Verdikt</th><th>Amal qiladi</th><th>Izoh</th></tr></thead>
          <tbody>{st.records.map((r) => (
            <tr key={r.id}>
              <td className="dim">{fmtDate(r.created_at)}</td>
              <td>{r.validated_by ?? "—"}</td>
              <td className="dim">{Number(r.metrics.days ?? 0)} kun · {Number(r.metrics.n_points ?? 0)} nuqta</td>
              <td className="mono">{Number(r.metrics.rmse_pct ?? 0)} % / {Number(r.metrics.bias_pct ?? 0)} %</td>
              <td><span className={`badge ${r.verdict === "pass" ? "published" : "rejected"}`}>{r.verdict === "pass" ? "mos" : "mos emas"}</span></td>
              <td className="dim">{r.valid_until ? fmtDay(r.valid_until) : "—"}</td>
              <td className="dim">{r.note}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
    </div>
  );
}
