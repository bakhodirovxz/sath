import { useCallback, useEffect, useState } from "react";
import { api, type CalibrationRun, type CalibrationState } from "../../api/client";
import Icon from "../../ui/Icon";
import { dialogs } from "../../ui/dialogs";
import { fmtDate } from "../../ui/format";

/* I1 — model kalibrovkasi: tarixiy ma'lumotdan parametrlarni moslashtirish, qoldiq (drift) kuzatuvi
   va kalibrovka tarixi. Kalibrovkalanmagan model «og'ish %» ni ishonchsiz qiladi — panel shuni aytadi. */

const RES_CLS: Record<string, string> = { ok: "published", drifted: "rejected", uncalibrated: "high", insufficient: "archived" };
const RES_TXT: Record<string, string> = {
  ok: "model amalda",
  drifted: "model siljigan",
  uncalibrated: "kalibrovkalanmagan",
  insufficient: "ma'lumot yetarli emas",
};

function paramsText(p: { penstock_roughness_mm?: number; eff?: Record<string, number> }): string {
  const parts: string[] = [];
  if (p.penstock_roughness_mm != null) parts.push(`g'adir-budurlik ${p.penstock_roughness_mm} mm`);
  for (const [k, v] of Object.entries(p.eff ?? {})) parts.push(`FIK${k} ${(v * 100).toFixed(1)} %`);
  return parts.join(" · ") || "—";
}

export function CalibrationPanel({ projectId, canEdit }: { projectId: number; canEdit: boolean }) {
  const [st, setSt] = useState<CalibrationState | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [days, setDays] = useState("30");
  const load = useCallback(() => api.calibration(projectId).then(setSt).catch((e) => setErr(e.message)), [projectId]);
  useEffect(() => { void load(); }, [load]);
  const run = (apply: boolean) => {
    setBusy(true);
    api.runCalibration(projectId, { days: Number(days) || 30, apply })
      .then((r: CalibrationRun) => { setErr(r.status === "ok" ? "" : r.note); void load(); })
      .catch((e) => setErr(e.message))
      .finally(() => setBusy(false));
  };
  const res = st?.residuals;
  return (
    <div className="dash-block">
      <div className="row items-center">
        <b>Model kalibrovkasi</b>
        <span className="muted small">tarixiy o'lchovdan parametrlarni moslashtirish (eng kichik kvadratlar) — kalibrovkasiz «og'ish %» model xatosini ham o'z ichiga oladi</span>
        {res && <span className={`badge ${RES_CLS[res.status]}`} data-testid="calib-status">{RES_TXT[res.status]}</span>}
        <span className="grow" />
        {canEdit && <label className="field"><span>Oyna, kun</span><input className="input w-70" type="number" min="1" value={days} data-testid="calib-days" onChange={(e) => setDays(e.target.value)} /></label>}
        {canEdit && <button className="btn sm" disabled={busy} data-testid="calib-run" onClick={() => run(false)}>Hisoblash</button>}
        {canEdit && <button className="btn sm primary" disabled={busy} data-testid="calib-apply" onClick={() => run(true)}>Hisoblash va qo'llash</button>}
      </div>
      {err && <p className="error small">{err}</p>}
      {res && (
        <p className="small">
          {res.status === "insufficient"
            ? `Kalibrovka uchun ma'lumot yetarli emas${res.n_points != null ? ` (${res.n_points} nuqta)` : ""}${res.reason ? ` — ${res.reason}` : ""}.`
            : <>Oxirgi {res.days} kun: qoldiq RMSE <b>{res.rmse_mw} MW</b>, siljish <b>{res.bias_mw} MW</b>
                {res.calibration_rmse_mw != null && <span className="dim"> (kalibrovkadagi RMSE {res.calibration_rmse_mw} MW)</span>}
                {res.advice && <span className={res.status === "drifted" ? "error" : "dim"}> · {res.advice}</span>}</>}
        </p>
      )}
      {st && st.runs.length > 0 && (
        <table className="grid small" data-testid="calib-runs">
          <thead><tr><th>Vaqt</th><th>Oyna</th><th>Nuqta</th><th>Parametrlar (oldin → keyin)</th><th>RMSE</th><th>Holat</th><th /></tr></thead>
          <tbody>{st.runs.map((r) => (
            <tr key={r.id} className={r.applied ? "alarm-active" : undefined}>
              <td className="dim">{fmtDate(r.created_at)}{r.author && <div className="dim">{r.author}</div>}</td>
              <td className="dim">{r.targets.map((t) => (t === "penstock_roughness_mm" ? "quvur" : "FIK")).join(", ")}</td>
              <td className="mono">{r.n_points}</td>
              <td className="small">
                {r.status === "ok" ? <>{paramsText(r.params_before)} → <b>{paramsText(r.params_after)}</b></> : <span className="dim">{r.note}</span>}
                {Object.entries(r.diagnostics ?? {}).filter(([, d]) => !d.identifiable).map(([k, d]) => (
                  <div key={k} className="dim">⚠ {k === "penstock_roughness_mm" ? "quvur g'adir-budurligi" : "FIK"}: {d.note}</div>
                ))}
              </td>
              <td className="mono">{r.rmse_before != null ? `${r.rmse_before} → ${r.rmse_after}` : "—"}{r.improvement_pct != null && <div className="dim">{r.improvement_pct > 0 ? "+" : ""}{r.improvement_pct} %</div>}</td>
              <td>{r.applied ? <span className="badge published">qo'llangan</span> : <span className="badge archived">{r.status === "ok" ? "saqlangan" : r.status}</span>}</td>
              <td>{canEdit && r.status === "ok" && !r.applied && <button className="btn sm" title="Shu kalibrovkani qo'llash" onClick={() => api.applyCalibration(r.id).then(() => load()).catch((e) => setErr(e.message))}><Icon name="check" size={12} /></button>}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
      {canEdit && res?.calibrated && (
        <div className="row"><button className="btn sm" data-testid="calib-revert" onClick={() => void dialogs.confirm("Kalibrovka bekor qilinsinmi?", { text: "Model IFC pasporti qiymatlariga qaytadi", ok: "Bekor qilish", danger: true }).then((ok) => { if (ok) api.revertCalibration(projectId).then(() => load()).catch((e) => setErr(e.message)); })}>Kalibrovkani bekor qilish</button></div>
      )}
    </div>
  );
}
