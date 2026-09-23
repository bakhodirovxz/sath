import { useCallback, useState } from "react";
import { usePolling } from "../../hooks/usePolling";
import { api, type EstimatorState } from "../../api/client";
import Icon from "../../ui/Icon";
import { fmtValue } from "../../ui/format";

/* I2 — holat baholash va ortiqcha o'lchovlar: ombor sathi uchun Kalman bahosi (sensor qotsa yoki
   yo'qolsa o'rnini bosadi) va bitta kattalikning bir nechta manbasini solishtirish. */

const ST_CLS: Record<string, string> = { ok: "published", alert: "high", alarm: "rejected" };

export function EstimatorPanel({ projectId, canEdit }: { projectId: number; canEdit: boolean }) {
  const [st, setSt] = useState<EstimatorState | null>(null);
  const [err, setErr] = useState("");
  const load = useCallback(() => api.estimator(projectId).then(setSt).catch((e) => setErr(e.message)), [projectId]);
  usePolling(load, 30000, String(projectId));
  const est = st?.estimate;
  const bal = est?.balance;
  return (
    <div className="dash-block">
      <div className="row items-center">
        <b>Holat baholash va ortiqchalik</b>
        <span className="muted small">suv balansi bo'yicha sath bahosi (Kalman) va bir kattalikning bir nechta manbasini solishtirish</span>
        {est?.frozen && <span className="badge rejected" data-testid="est-frozen">sensor qotgan</span>}
        {est?.source === "model" && !est?.frozen && <span className="badge high">baho (model)</span>}
        <span className="grow" />
        {canEdit && <button className="btn sm" data-testid="est-run" onClick={() => api.runEstimator(projectId).then(setSt).catch((e) => setErr(e.message))}>Hozir hisoblash</button>}
      </div>
      {err && <p className="error small">{err}</p>}
      {est?.status === "insufficient" && (
        <p className="muted small">Baho uchun ma'lumot yetarli emas{est.missing?.length ? `: ${est.missing.join(", ")}` : ""} — kiruvchi sarf sensori va maydon pasportidagi ombor egri chizig'i kerak.</p>
      )}
      {est?.status === "ok" && (
        <>
          <p className="small">
            Sath: o'lchov <b>{est.level_measured_m != null ? `${fmtValue(est.level_measured_m)} m` : "—"}</b> ·
            baho <b>{fmtValue(est.level_estimate_m ?? 0)} m</b> <span className="dim">±{est.sigma_m} m</span>
            {est.source === "model" && <span className="error"> · o'lchov ishlatilmadi (qotgan yoki aloqasiz) — model qadami</span>}
            {est.innovation_m != null && <span className="dim"> · farq {est.innovation_m > 0 ? "+" : ""}{est.innovation_m} m</span>}
          </p>
          {bal?.status === "ok" && (
            <p className="small dim">
              Balans: kiruvchi {fmtValue(bal.inflow_m3s ?? 0)} − chiqim {fmtValue(bal.outflow_m3s ?? 0)} = <b>{fmtValue(bal.net_m3s ?? 0)} m³/s</b>
              {" "}· ko'zgu {((bal.area_m2 ?? 0) / 1e6).toFixed(2)} km² · kutilgan o'zgarish <b>{(bal.dlevel_m_per_h ?? 0).toFixed(3)} m/soat</b>
            </p>
          )}
        </>
      )}
      {st && st.checks.length > 0 && (
        <table className="grid small" data-testid="est-checks">
          <thead><tr><th>Tekshiruv</th><th>Manbalar</th><th>Farq</th><th>Chidamlilik</th><th>Holat</th></tr></thead>
          <tbody>{st.checks.map((c) => (
            <tr key={c.name} className={c.status === "alarm" ? "alarm-active" : undefined}>
              <td>{c.label}{c.note && <div className="dim">{c.note}</div>}</td>
              <td className="small">{c.sources.map((s) => `${s.label}: ${s.value} ${c.unit}`).join(" · ")}</td>
              <td className="mono">{c.diff > 0 ? "+" : ""}{c.diff} {c.unit}</td>
              <td className="mono dim">±{c.tolerance}</td>
              <td><span className={`badge ${ST_CLS[c.status]}`}>{c.status === "ok" ? "mos" : c.status === "alert" ? "kelishmovchilik" : "katta farq"}</span></td>
            </tr>
          ))}</tbody>
        </table>
      )}
      {st && st.checks.length === 0 && est?.status === "ok" && (
        <p className="dim small"><Icon name="info" size={11} /> Ortiqcha manba yo'q — umumiy quvvat yoki sarf o'lchagichini bog'lasangiz solishtirish ishlaydi.</p>
      )}
    </div>
  );
}
