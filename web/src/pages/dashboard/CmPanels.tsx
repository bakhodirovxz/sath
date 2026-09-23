import { useCallback, useEffect, useState } from "react";
import { api, type AssetHealth, type CmState, type SpectrumRow } from "../../api/client";
import Dialog from "../../ui/Dialog";
import Icon from "../../ui/Icon";
import LineChart, { CHART_COLORS } from "../../ui/LineChart";
import { fmtDate } from "../../ui/format";

/* H3 — ISO 13374 (OSA-CBM) holat monitoringi: DA → DM → SD → HA → PA → AG bloklari, spektr
   yozuvlari (podshipnik nuqson chastotalari) va tashqi tizim natijalari. */

const STATE_CLS: Record<string, string> = { normal: "published", alert: "high", alarm: "rejected", unknown: "archived" };
const STATE_TXT: Record<string, string> = { normal: "normal", alert: "ogohlantirish", alarm: "alarm", unknown: "noma'lum" };
const BLOCK_NOTE: Record<string, string> = {
  DA: "ma'lumot yig'ish — kanallar va spektrlar",
  DM: "signal qayta ishlash — trend, z-score, spektr xususiyatlari",
  SD: "holat aniqlash — zona va chegaralar",
  HA: "sog'liq bahosi — indeks va tashxis",
  PA: "prognoz — qolgan resurs",
  AG: "tavsiya — muammo va chora",
};
const CHANNEL_TXT: Record<string, string> = {
  vibration: "tebranish",
  bearing_temp: "podshipnik harorati",
  shaft_vibration: "val nisbiy tebranishi",
  air_gap: "havo oralig'i",
  partial_discharge: "qisman razryad",
  oil_water: "moyda suv",
  bearing_defect: "podshipnik nuqsoni",
};

export function CmBadge({ state }: { state?: CmState | undefined }) {
  if (!state) return null;
  return <span className={`badge ${STATE_CLS[state]}`} title="ISO 13374 SD bloki holati">{STATE_TXT[state]}</span>;
}

/** Aktiv bo'yicha ISO 13374 zanjiri: bloklar, kanallar holati, spektrlar va tashqi tizim natijalari. */
export function CmDialog({ projectId, asset, onClose }: { projectId: number; asset: AssetHealth; onClose: () => void }) {
  const [cm, setCm] = useState<AssetHealth | null>(null);
  const [spectra, setSpectra] = useState<SpectrumRow[]>([]);
  const [shown, setShown] = useState<SpectrumRow | null>(null);
  const [err, setErr] = useState("");
  const load = useCallback(() => Promise.all([api.assetCm(asset.asset_id), api.spectra(projectId, asset.asset_id)])
    .then(([c, s]) => { setCm(c); setSpectra(s); })
    .catch((e) => setErr(e.message)), [asset.asset_id, projectId]);
  useEffect(() => { void load(); }, [load]);
  const openSpectrum = (id: number) => api.spectrum(id).then(setShown).catch((e) => setErr(e.message));
  const states = Object.entries(cm?.states ?? {});
  const days = Object.entries(cm?.prognosis?.days ?? {}).filter(([, v]) => v != null);
  return (
    <Dialog title={`Holat monitoringi: ${asset.name}${asset.kks_code ? ` (${asset.kks_code})` : ""}`} onClose={onClose}>
      {err && <p className="error small">{err}</p>}
      {!cm ? <p className="muted">Yuklanmoqda…</p> : (
        <>
          <div className="row items-center gap-8">
            <span className="health-score">{cm.score}</span>
            <CmBadge state={cm.state} />
            <span className="dim small">ichki {cm.internal_score}{cm.external_score != null ? ` · tashqi ${cm.external_score}` : ""}</span>
            <span className="grow" />
            {cm.prognosis?.rul_days != null && <span className="badge high" title={`asos: ${cm.prognosis.rul_basis}`}>RUL ≈ {cm.prognosis.rul_days} kun</span>}
          </div>

          <h4>ISO 13374 bloklari</h4>
          <table className="grid small" data-testid="cm-blocks">
            <thead><tr><th>Blok</th><th>Vazifa</th><th>Natija</th></tr></thead>
            <tbody>
              {cm.blocks && Object.entries(cm.blocks).map(([k, v]) => (
                <tr key={k}>
                  <td><b>{k}</b></td>
                  <td className="dim">{BLOCK_NOTE[k]}</td>
                  <td className="small">{k === "DA" ? `${v.channels.length} kanal · ${v.spectra} spektr`
                    : k === "DM" ? `${v.features.length} xususiyat`
                    : k === "SD" ? <><CmBadge state={v.state} /> <span className="dim">{v.items.map((i: string) => CHANNEL_TXT[i] ?? i).join(", ") || "—"}</span></>
                    : k === "HA" ? `indeks ${v.score} (ichki ${v.internal}${v.external != null ? `, tashqi ${v.external}` : ""})`
                    : k === "PA" ? (v.rul_days != null ? `${v.rul_days} kun` : "prognoz yo'q")
                    : `${v.problems} muammo · ${v.tips} tavsiya`}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h4>Holat belgilari (SD)</h4>
          {states.length === 0 ? <p className="muted">Kanal bog'lanmagan — «Sensorlar va parametrlar» dan tebranish/harorat sensorini tanlang.</p> : (
            <table className="grid small" data-testid="cm-states">
              <thead><tr><th>Kanal</th><th>Holat</th><th>Sabab</th></tr></thead>
              <tbody>{states.map(([k, v]) => (
                <tr key={k} className={v.state === "alarm" ? "row-attention" : undefined}>
                  <td>{k.startsWith("external:") ? <>{k.slice(9)} <span className="dim small">tashqi</span></> : CHANNEL_TXT[k] ?? k}</td>
                  <td><CmBadge state={v.state} /></td>
                  <td className="small">{v.reason}{v.anomaly && <span className="error"> · anomaliya</span>}</td>
                </tr>
              ))}</tbody>
            </table>
          )}

          {days.length > 0 && (
            <>
              <h4>Prognoz (PA)</h4>
              <p className="small">{days.map(([k, v]) => `${CHANNEL_TXT[k.split("_")[0] ?? k] ?? k}: ≈ ${v} kun`).join(" · ")}
                {cm.prognosis?.efficiency_pct_per_year != null && ` · FIK ${cm.prognosis.efficiency_pct_per_year} %/yil`}</p>
            </>
          )}

          <h4>Spektrlar (DA/DM)</h4>
          {spectra.length === 0 ? <p className="muted">Spektr yozuvi yo'q — CM gateway'i <code>POST /api/projects/{projectId}/cm/spectra</code> orqali yuboradi.</p> : (
            <table className="grid small" data-testid="cm-spectra">
              <thead><tr><th>Vaqt</th><th>Tur</th><th>Diapazon</th><th>Chiziq</th><th>Manba</th><th /></tr></thead>
              <tbody>{spectra.map((sp) => (
                <tr key={sp.id}>
                  <td className="dim">{fmtDate(sp.ts)}</td>
                  <td>{sp.kind}{sp.rpm ? <span className="dim"> · {sp.rpm} ayl/min</span> : null}</td>
                  <td className="mono dim">{sp.f_min}–{sp.f_max} Gs</td>
                  <td className="mono dim">{sp.n_lines}</td>
                  <td className="dim">{sp.source || "—"}</td>
                  <td><button className="btn sm" data-testid={`spectrum-${sp.id}`} onClick={() => void openSpectrum(sp.id)}><Icon name="bar-chart" size={12} /></button></td>
                </tr>
              ))}</tbody>
            </table>
          )}

          {cm.external && cm.external.length > 0 && (
            <>
              <h4>Tashqi tizimlar</h4>
              <table className="grid small" data-testid="cm-external">
                <thead><tr><th>Manba</th><th>Blok</th><th>Holat</th><th>Indeks</th><th>RUL</th><th>Tashxis</th><th>Vaqt</th></tr></thead>
                <tbody>{cm.external.map((e) => (
                  <tr key={e.id}>
                    <td>{e.source}</td><td className="dim">{e.block}</td><td><CmBadge state={e.state} /></td>
                    <td className="mono">{e.health_score ?? "—"}</td><td className="mono">{e.rul_days != null ? `${e.rul_days} kun` : "—"}</td>
                    <td className="small">{e.diagnosis}{e.confidence != null && <span className="dim"> ({Math.round(e.confidence * 100)} %)</span>}</td>
                    <td className="dim">{fmtDate(e.ts)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </>
          )}
        </>
      )}
      {shown && <SpectrumDialog sp={shown} onClose={() => setShown(null)} />}
      <div className="actions"><button className="btn" onClick={onClose}>Yopish</button></div>
    </Dialog>
  );
}

/** Bitta spektr: chastota–amplituda grafigi, cho'qqilar va podshipnik nuqson chastotalari (ISO 13373-3). */
function SpectrumDialog({ sp, onClose }: { sp: SpectrumRow; onClose: () => void }) {
  const values = sp.values ?? [];
  const freqs = sp.freqs ?? values.map((_, i) => sp.f_min + ((sp.f_max - sp.f_min) * i) / Math.max(values.length - 1, 1));
  const f = sp.features;
  return (
    <Dialog title={`Spektr #${sp.id} — ${sp.kind}`} onClose={onClose}>
      <LineChart title={`${sp.kind} (${sp.unit})`} unit={sp.unit} x={freqs.map((v) => v.toFixed(1))} series={[{ name: "Amplituda", values, color: CHART_COLORS[0] }]} />
      {f && (
        <>
          <p className="small">Umumiy daraja: <b>{f.overall} {sp.unit}</b>{f.rpm ? ` · val ${(f.rpm / 60).toFixed(2)} Gs` : ""}
            {Object.keys(f.harmonics).length > 0 && ` · garmonikalar: ${Object.entries(f.harmonics).map(([k, v]) => `${k} ${v}`).join(", ")}`}</p>
          <p className="small dim">Cho'qqilar: {f.peaks.map((p) => `${p.f} Gs / ${p.a}`).join(" · ") || "—"}</p>
          {f.bearing_frequencies && (
            <table className="grid small" data-testid="bearing-freqs">
              <thead><tr><th>Nuqson</th><th>Chastota</th><th>Amplituda</th><th>Ulush</th></tr></thead>
              <tbody>{["BPFO", "BPFI", "BSF", "FTF"].map((name) => {
                const m = f.bearing_matches.find((x) => x.name === name);
                return (
                  <tr key={name} className={m && m.share > 0.15 ? "row-attention" : undefined}>
                    <td>{name}</td>
                    <td className="mono">{f.bearing_frequencies?.[name]} Gs</td>
                    <td className="mono">{m ? m.amplitude : "—"}</td>
                    <td className="mono">{m ? `${Math.round(m.share * 100)} %` : "—"}</td>
                  </tr>
                );
              })}</tbody>
            </table>
          )}
          {!f.bearing_frequencies && <p className="small dim">Podshipnik geometriyasi (n, d, D) kiritilmagan — nuqson chastotalari hisoblanmaydi.</p>}
        </>
      )}
      <div className="actions"><button className="btn" onClick={onClose}>Yopish</button></div>
    </Dialog>
  );
}
