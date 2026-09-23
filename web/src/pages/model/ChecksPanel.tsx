import { useCallback, useEffect, useMemo, useState } from "react";
import Icon from "../../ui/Icon";
import { api, ApiError, type Clash, type ClashReport, type IdsResult, type Qto, type Version } from "../../api/client";
import type { Viewer } from "../../viewer/Viewer";
import { fmtValue, ifcLabel } from "../../ui/format";
import { PAL } from "../../viewer/palette";

interface Props {
  current: Version | null;
  viewer: Viewer | null;
  /** Tanlangan elementlar (clash) bo'yicha issue ochish — ISSUE buyrug'i kabi */
  onCreateIssue: () => void;
}

const KIND_LABEL: Record<Clash["kind"], string> = { hard: "to'qnashuv", possible: "ehtimoliy", touch: "tegib turibdi" };
const KIND_CLASS: Record<Clash["kind"], string> = { hard: "rejected", possible: "high", touch: "archived" };

/** BIM tekshiruvlar: hajm-miqdor hisobi (QTO) va to'qnashuvlar (clash detection). */
export default function ChecksPanel({ current, viewer, onCreateIssue }: Props) {
  const [mode, setMode] = useState<"qto" | "clash" | "ids">("clash");
  const [qto, setQto] = useState<Qto | null>(null);
  const [clash, setClash] = useState<ClashReport | null>(null);
  const [ids, setIds] = useState<IdsResult | null>(null);
  const [idsPending, setIdsPending] = useState(false);
  const [kind, setKind] = useState<Clash["kind"] | "">("hard");
  const [busy, setBusy] = useState(false);
  /** OPS-03: server og'ir hisobni navbatga qo'ygan (202) — kutish vaqti, ms (xato emas) */
  const [queued, setQueued] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [picked, setPicked] = useState<number | null>(null);
  const [qFilter, setQFilter] = useState("");

  const currentId = current?.id;
  useEffect(() => { setQto(null); setClash(null); setIds(null); setIdsPending(false); setPicked(null); }, [currentId]);

  const run = useCallback(async () => {
    if (!currentId) return;
    setBusy(true); setError(""); setQueued(null);
    const onProgress = (p: { waitingMs: number }) => setQueued(p.waitingMs);
    try {
      if (mode === "qto") setQto(await api.qto(currentId, onProgress));
      else if (mode === "ids") {
        try { setIds(await api.ids(currentId)); setIdsPending(false); }
        catch (e) { if (e instanceof ApiError && e.status === 404) setIdsPending(true); else throw e; } // navbatda — hali yo'q
      }
      else setClash(await api.clashes(currentId, undefined, onProgress));
    } catch (e) { setError(e instanceof Error ? e.message : "Xatolik"); }
    finally { setBusy(false); setQueued(null); }
  }, [currentId, mode]);
  useEffect(() => {
    if (currentId && ((mode === "qto" && !qto) || (mode === "clash" && !clash) || (mode === "ids" && !ids && !idsPending))) void run();
  }, [mode, currentId, qto, clash, ids, idsPending, run]);
  const runIds = useCallback(async () => {
    if (!currentId) return;
    setBusy(true); setError("");
    try { setIds(await api.runIds(currentId)); setIdsPending(false); } catch (e) { setError(e instanceof Error ? e.message : "Xatolik"); } finally { setBusy(false); }
  }, [currentId]);

  async function show(c: Clash, i: number) {
    setPicked(i);
    if (!viewer) return;
    await viewer.colorByGuids({});
    await viewer.colorByGuids({ [c.a.guid]: PAL.fail, [c.b.guid]: PAL.warn });
    await viewer.selectByGuids([c.a.guid, c.b.guid], true);
  }
  useEffect(() => () => { void viewer?.colorByGuids({}); }, [viewer]);

  const rows = useMemo(() => (clash?.clashes ?? []).filter((c) => !kind || c.kind === kind), [clash, kind]);
  const qRows = useMemo(() => (qto?.elements ?? []).filter((e) => !qFilter || `${e.name} ${e.type} ${e.storey}`.toLowerCase().includes(qFilter.toLowerCase())), [qto, qFilter]);

  if (!current) return <p className="muted">Versiya tanlang</p>;
  return (
    <div className="checks">
      <div className="row">
        <button className={`btn sm ${mode === "clash" ? "active" : ""}`} onClick={() => setMode("clash")}>To'qnashuvlar</button>
        <button className={`btn sm ${mode === "qto" ? "active" : ""}`} onClick={() => setMode("qto")}>Hajm-miqdor</button>
        <button className={`btn sm ${mode === "ids" ? "active" : ""}`} onClick={() => setMode("ids")} data-testid="checks-ids">IDS</button>
        <span className="grow" />
        {busy && <span className="muted small" role="status" data-testid="checks-progress">{queued != null ? `server hisoblamoqda (navbatda, ${Math.round(queued / 1000)} s)…` : "hisoblanmoqda…"}</span>}
      </div>
      {error && <p className="error">{error}</p>}

      {mode === "clash" && clash && (
        <>
          <div className="tiles cols-3">
            <button className={`tile ${kind === "hard" ? "tile-alarm" : ""}`} onClick={() => setKind("hard")}><div className="tile-t">To'qnashuv</div><div className="tile-v">{clash.hard}</div></button>
            <button className={`tile ${kind === "possible" ? "tile-alarm" : ""}`} onClick={() => setKind("possible")}><div className="tile-t">Ehtimoliy</div><div className="tile-v">{clash.possible}</div></button>
            <button className={`tile ${kind === "touch" ? "tile-alarm" : ""}`} onClick={() => setKind("touch")}><div className="tile-t">Tegib turadi</div><div className="tile-v">{clash.touch}</div></button>
          </div>
          <p className="dim small">{clash.element_count} element, {clash.pairs_checked} juftlik tekshirildi{clash.exact ? "" : " (katta model — faqat bbox)"}. <button className="btn sm" onClick={() => setKind("")}>hammasi</button></p>
          {rows.length === 0 ? <p className="muted">Bu turda yo'q</p> : (
            <div className="list">
              {rows.map((c, i) => (
                <div key={i} className={`list-item ${picked === i ? "selected" : ""}`}>
                  <button type="button" className="list-item-head" aria-expanded={picked === i} onClick={() => show(c, i)}>
                    <span className="title"><span className={`badge ${KIND_CLASS[c.kind]}`}>{KIND_LABEL[c.kind]}</span><span className="grow" /><span className="dim small">{c.kind === "touch" ? "" : `${fmtValue(c.overlap_volume_m3)} m³`}</span></span>
                    <span className="li-line"><Icon name="square" size={11} className="clash-a" /> {c.a.name || c.a.guid} <span className="dim">{ifcLabel(c.a.type)}</span></span>
                    <span className="li-line"><Icon name="square" size={11} className="clash-b" /> {c.b.name || c.b.guid} <span className="dim">{ifcLabel(c.b.type)}</span></span>
                  </button>
                  {picked === i && c.kind !== "touch" && (
                    <div className="row mt-4">
                      <span className="dim small mono">{c.point.map((v) => v.toFixed(2)).join(", ")} m · kesishuv {c.overlap_m.map((v) => v.toFixed(2)).join("×")} m</span>
                      <span className="grow" />
                      <button className="btn sm" onClick={() => onCreateIssue()}>Muammo ochish</button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {mode === "ids" && (
        <div className="ids" data-testid="ids-panel">
          <p className="muted small">
            Axborot talablari (IDS, buildingSMART) — <code>docs/ids/sath-ges.ids</code>: nomlash, georeferensiya, Pset_GES_* pasportlari. Har yuklashda avtomatik.
            <button className="btn sm ml-8" onClick={() => void runIds()} disabled={busy}>Qayta tekshirish</button>
          </p>
          {idsPending && !ids && <p className="muted">Tekshiruv navbatda… (bir necha soniya) yoki «Qayta tekshirish»</p>}
          {ids && (
            <>
              <p>
                <span className={`badge ${ids.status === "pass" ? "approved" : ids.status === "fail" ? "rejected" : "high"}`} data-testid="ids-status">{ids.status === "pass" ? "O'TDI" : ids.status === "fail" ? "O'TMADI" : "XATO"}</span>
                {" "}{ids.total_specifications_pass ?? 0}/{ids.total_specifications ?? 0} talab · {ids.total_checks_pass ?? 0}/{ids.total_checks ?? 0} tekshiruv · {new Date(ids.checked_at).toLocaleString()}
                {ids.error && <span className="error"> {ids.error}</span>}
              </p>
              <div className="list">
                {(ids.specifications ?? []).map((sp) => (
                  <div key={sp.identifier ?? sp.name} className="list-item">
                    <div className="title">
                      <span className={`badge ${sp.status ? "approved" : "rejected"}`}>{sp.status ? "ok" : "yo'q"}</span>
                      <span className="mono dim small">{sp.identifier}</span> <span>{sp.name}</span>
                      <span className="grow" />
                      <span className="dim small">{sp.passed}/{sp.applicable}{sp.failed ? ` · ${sp.failed} yiqildi` : ""}</span>
                    </div>
                    {sp.description && <div className="dim small">{sp.description}</div>}
                    {sp.requirements.filter((r) => !r.status).map((r, i) => (
                      <div key={i} className="mt-4">
                        <div className="small">{r.description}</div>
                        {r.failed.slice(0, 50).map((f, j) => (
                          <button type="button" key={j} className="row-btn small" disabled={!f.guid} onClick={() => f.guid && viewer?.selectByGuids([f.guid], true)} title={f.reason ?? ""}>
                            <Icon name="square" size={11} className="clash-a" /> {f.name || f.guid} <span className="dim">{f.class ? ifcLabel(f.class) : ""} — {f.reason}</span>
                          </button>
                        ))}
                        {r.failed_total > 50 && <div className="dim small">…yana {r.failed_total - 50} ta</div>}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {mode === "qto" && qto && (
        <>
          <p className="muted small">{qto.element_count} element · jami hajm <b>{fmtValue(qto.total_volume_m3)} m³</b> · IfcOpenShell geometriyasidan (IFC BaseQuantities bo'lsa jadvalda)</p>
          <table className="grid small">
            <thead><tr><th>Tur</th><th>Soni</th><th>Hajm, m³</th><th>Sirt, m²</th></tr></thead>
            <tbody>
              {Object.entries(qto.by_type).map(([t, b]) => (
                <tr key={t}><td>{ifcLabel(t)} <span className="dim">{t}</span></td><td className="mono">{b.count}</td><td className="mono">{fmtValue(b.volume_m3)}</td><td className="mono">{fmtValue(b.area_m2)}</td></tr>
              ))}
            </tbody>
          </table>
          <div className="row mt-8 mr-0 mb-4 ml-0">
            <input className="input" placeholder="Element/tur/qavat bo'yicha filtr" value={qFilter} onChange={(e) => setQFilter(e.target.value)} />
            <button className="btn sm" onClick={() => api.downloadCsv(`/api/versions/${current.id}/qto?format=csv`, `qto_v${current.number}.csv`).catch((e) => setError(e.message))}>CSV</button>
          </div>
          <table className="grid small">
            <thead><tr><th>Element</th><th>Hajm m³</th><th>L×W×H m</th></tr></thead>
            <tbody>
              {qRows.slice(0, 300).map((e) => (
                <tr key={e.guid} className="clickable" onClick={() => viewer?.selectByGuids([e.guid], true)}>
                  <td><button type="button" className="link-btn" onClick={(ev) => { ev.stopPropagation(); void viewer?.selectByGuids([e.guid], true); }}>{e.name || e.guid}</button><div className="dim">{ifcLabel(e.type)}{e.storey && ` · ${e.storey}`}{e.material && ` · ${e.material}`}</div></td>
                  <td className="mono">{fmtValue(e.volume_m3)}</td>
                  <td className="mono">{e.length_m.toFixed(1)}×{e.width_m.toFixed(1)}×{e.height_m.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {qRows.length > 300 && <p className="dim small">…{qRows.length - 300} ta yana — CSV da hammasi</p>}
        </>
      )}
    </div>
  );
}
