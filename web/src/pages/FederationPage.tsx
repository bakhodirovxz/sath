import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { api, type Clash, type ClashReport, type Federation } from "../api/client";
import TopBar from "../ui/TopBar";
import Icon from "../ui/Icon";
import { fmtValue, ifcLabel } from "../ui/format";
import { useViewer } from "../viewer/useViewer";
import ErrorBoundary from "../ui/ErrorBoundary";
import { PAL } from "../viewer/palette";

const KIND_LABEL: Record<Clash["kind"], string> = { hard: "to'qnashuv", possible: "ehtimoliy", touch: "tegib turibdi" };
const KIND_CLASS: Record<Clash["kind"], string> = { hard: "rejected", possible: "high", touch: "archived" };

/** G5: federatsiya — bir necha model bitta koordinata fazosida (birlashtirilgan IFC) + modellar orasidagi
 * to'qnashuvlar ro'yxati; qatorga bosilsa 3D da ikkala element tanlanadi. */
export default function FederationPage() {
  const { fedId } = useParams();
  const id = Number(fedId);
  const { containerRef, viewer, ready, status } = useViewer();
  const [fed, setFed] = useState<Federation | null>(null);
  const [rep, setRep] = useState<ClashReport | null>(null);
  const [kind, setKind] = useState<Clash["kind"] | "">("hard");
  const [error, setError] = useState("");
  const [picked, setPicked] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.federation(id).then(setFed).catch((e) => setError(e.message)); }, [id]);
  useEffect(() => {
    const v = viewer.current;
    if (!ready || !v || !fed) return;
    let dead = false;
    setBusy(true);
    api.federationIfc(id).then((bytes) => { if (!dead) return v.loadIfc(bytes, fed.name); }).catch((e) => setError(e instanceof Error ? e.message : "Xato")).finally(() => setBusy(false));
    return () => { dead = true; };
  }, [ready, viewer, fed, id]);
  const load = useCallback(() => api.federationClashes(id).then(setRep).catch((e) => setError(e.message)), [id]);
  useEffect(() => { void load(); }, [load]);

  const rows = useMemo(() => (rep?.clashes ?? []).filter((c) => !kind || c.kind === kind), [rep, kind]);
  async function show(c: Clash, i: number) {
    setPicked(i);
    const v = viewer.current;
    if (!v) return;
    await v.colorByGuids({});
    await v.colorByGuids({ [c.a.guid]: PAL.fail, [c.b.guid]: PAL.warn });
    await v.selectByGuids([c.a.guid, c.b.guid], true);
  }

  return (
    <div className="page ws">
      <TopBar alarms={fed ? { pid: fed.project_id } : undefined} crumbs={[{ label: "Loyihalar", to: "/" }, ...(fed ? [{ label: "Loyiha", to: `/projects/${fed.project_id}` }, { label: `Federatsiya: ${fed.name}` }] : [])]} />
      <div className="ws-body fed-layout">
        <div className="viewport rel">
          <div ref={containerRef} className="ws-canvas-host" />
          <div className="ws-status"><span className="msg">{busy ? "Birlashtirilgan model yuklanmoqda…" : status}</span></div>
        </div>
        <ErrorBoundary name="Federatsiya to'qnashuvlari">
          <div className="dock-body overflow-auto p-8" data-testid="fed-panel">
            {error && <p className="error">{error}</p>}
            {fed && (
              <div className="panel">
                <b>{fed.name}</b> {fed.description && <span className="dim small">{fed.description}</span>}
                <table className="grid small mt-4">
                  <thead><tr><th>Model</th><th>Versiya</th><th>Siljish, m</th><th>Burilish</th></tr></thead>
                  <tbody>{fed.members.map((m) => <tr key={m.model_id}><td>{m.model_name}</td><td className="mono">v{m.version_number}</td><td className="mono">{m.dx}, {m.dy}, {m.dz}</td><td className="mono">{m.rot_deg}°</td></tr>)}</tbody>
                </table>
              </div>
            )}
            {rep && (
              <>
                <div className="tiles cols-3">
                  <button className={`tile ${kind === "hard" ? "tile-alarm" : ""}`} onClick={() => setKind("hard")}><div className="tile-t">To'qnashuv</div><div className="tile-v">{rep.hard}</div></button>
                  <button className={`tile ${kind === "possible" ? "tile-alarm" : ""}`} onClick={() => setKind("possible")}><div className="tile-t">Ehtimoliy</div><div className="tile-v">{rep.possible}</div></button>
                  <button className={`tile ${kind === "touch" ? "tile-alarm" : ""}`} onClick={() => setKind("touch")}><div className="tile-t">Tegib turadi</div><div className="tile-v">{rep.touch}</div></button>
                </div>
                <p className="dim small">Modellar orasida: {rep.element_count} element, {rep.pairs_checked} juftlik{rep.exact ? "" : " (ba'zi juftliklar aniq tekshirilmadi)"} <button className="btn sm" onClick={() => setKind("")}>hammasi</button></p>
                <div className="list">
                  {rows.map((c, i) => (
                    <button type="button" key={i} className={`list-item ${picked === i ? "selected" : ""}`} aria-pressed={picked === i} onClick={() => void show(c, i)}>
                      <span className="title"><span className={`badge ${KIND_CLASS[c.kind]}`}>{KIND_LABEL[c.kind]}</span><span className="grow" /><span className="dim small">{c.kind === "touch" ? "" : `${fmtValue(c.overlap_volume_m3)} m³`}</span></span>
                      <span className="li-line"><Icon name="square" size={11} className="clash-a" /> {c.a.name || c.a.guid} <span className="dim">{ifcLabel(c.a.type)} · {c.a.model}</span></span>
                      <span className="li-line"><Icon name="square" size={11} className="clash-b" /> {c.b.name || c.b.guid} <span className="dim">{ifcLabel(c.b.type)} · {c.b.model}</span></span>
                    </button>
                  ))}
                  {rows.length === 0 && <p className="muted">Bu turda yo'q</p>}
                </div>
              </>
            )}
          </div>
        </ErrorBoundary>
      </div>
    </div>
  );
}
