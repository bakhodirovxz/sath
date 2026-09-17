import { useEffect, useMemo, useState } from "react";
import Icon from "../../ui/Icon";
import { api, type Clash, type ClashReport, type Qto, type Version } from "../../api/client";
import type { Viewer } from "../../viewer/Viewer";
import { fmtValue, ifcLabel } from "../../ui/format";

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
  const [mode, setMode] = useState<"qto" | "clash">("clash");
  const [qto, setQto] = useState<Qto | null>(null);
  const [clash, setClash] = useState<ClashReport | null>(null);
  const [kind, setKind] = useState<Clash["kind"] | "">("hard");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [picked, setPicked] = useState<number | null>(null);
  const [qFilter, setQFilter] = useState("");

  useEffect(() => { setQto(null); setClash(null); setPicked(null); }, [current?.id]);

  async function run() {
    if (!current) return;
    setBusy(true); setError("");
    try {
      if (mode === "qto") setQto(await api.qto(current.id));
      else setClash(await api.clashes(current.id));
    } catch (e) { setError(e instanceof Error ? e.message : "Xatolik"); }
    finally { setBusy(false); }
  }
  useEffect(() => {
    if (current && ((mode === "qto" && !qto) || (mode === "clash" && !clash))) void run();
  }, [mode, current?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function show(c: Clash, i: number) {
    setPicked(i);
    if (!viewer) return;
    await viewer.colorByGuids({});
    await viewer.colorByGuids({ [c.a.guid]: "#d95c5c", [c.b.guid]: "#e0a93a" });
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
        <span className="grow" />
        {busy && <span className="muted small">hisoblanmoqda…</span>}
      </div>
      {error && <p className="error">{error}</p>}

      {mode === "clash" && clash && (
        <>
          <div className="tiles" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
            <button className={`tile ${kind === "hard" ? "tile-alarm" : ""}`} onClick={() => setKind("hard")}><div className="tile-t">To'qnashuv</div><div className="tile-v">{clash.hard}</div></button>
            <button className={`tile ${kind === "possible" ? "tile-alarm" : ""}`} onClick={() => setKind("possible")}><div className="tile-t">Ehtimoliy</div><div className="tile-v">{clash.possible}</div></button>
            <button className={`tile ${kind === "touch" ? "tile-alarm" : ""}`} onClick={() => setKind("touch")}><div className="tile-t">Tegib turadi</div><div className="tile-v">{clash.touch}</div></button>
          </div>
          <p className="dim small">{clash.element_count} element, {clash.pairs_checked} juftlik tekshirildi{clash.exact ? "" : " (katta model — faqat bbox)"}. <button className="btn sm" onClick={() => setKind("")}>hammasi</button></p>
          {rows.length === 0 ? <p className="muted">Bu turda yo'q</p> : (
            <div className="list">
              {rows.map((c, i) => (
                <div key={i} className={`list-item ${picked === i ? "selected" : ""}`} onClick={() => show(c, i)}>
                  <div className="title"><span className={`badge ${KIND_CLASS[c.kind]}`}>{KIND_LABEL[c.kind]}</span><span className="grow" /><span className="dim small">{c.kind === "touch" ? "" : `${fmtValue(c.overlap_volume_m3)} m³`}</span></div>
                  <div><Icon name="square" size={11} style={{ color: "#d95c5c" }} /> {c.a.name || c.a.guid} <span className="dim">{ifcLabel(c.a.type)}</span></div>
                  <div><Icon name="square" size={11} style={{ color: "#e0a93a" }} /> {c.b.name || c.b.guid} <span className="dim">{ifcLabel(c.b.type)}</span></div>
                  {picked === i && c.kind !== "touch" && (
                    <div className="row" style={{ marginTop: 4 }}>
                      <span className="dim small mono">{c.point.map((v) => v.toFixed(2)).join(", ")} m · kesishuv {c.overlap_m.map((v) => v.toFixed(2)).join("×")} m</span>
                      <span className="grow" />
                      <button className="btn sm" onClick={(e) => { e.stopPropagation(); onCreateIssue(); }}>Issue ochish</button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
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
          <div className="row" style={{ margin: "8px 0 4px" }}>
            <input className="input" placeholder="Element/tur/qavat bo'yicha filtr" value={qFilter} onChange={(e) => setQFilter(e.target.value)} />
            <button className="btn sm" onClick={() => api.downloadCsv(`/api/versions/${current.id}/qto?format=csv`, `qto_v${current.number}.csv`).catch((e) => setError(e.message))}>CSV</button>
          </div>
          <table className="grid small">
            <thead><tr><th>Element</th><th>Hajm m³</th><th>L×W×H m</th></tr></thead>
            <tbody>
              {qRows.slice(0, 300).map((e) => (
                <tr key={e.guid} className="clickable" onClick={() => viewer?.selectByGuids([e.guid], true)}>
                  <td>{e.name || e.guid}<div className="dim">{ifcLabel(e.type)}{e.storey && ` · ${e.storey}`}{e.material && ` · ${e.material}`}</div></td>
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
