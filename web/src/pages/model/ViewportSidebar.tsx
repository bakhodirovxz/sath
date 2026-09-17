import { useEffect, useState } from "react";
import type { ItemProperties, SelectedItem, Shading, ViewName, Viewer } from "../../viewer/Viewer";
import type { Version } from "../../api/client";
import { ifcLabel } from "../../ui/format";
import Icon from "../../ui/Icon";

/** Blender N-panel (viewport yon paneli): Element · Ko'rinish · Sath yorliqlari. */
type SideTab = "item" | "view" | "sath";
const SIDE_TABS: { id: SideTab; title: string }[] = [
  { id: "item", title: "Element" },
  { id: "view", title: "Ko'rinish" },
  { id: "sath", title: "Sath" },
];
const VIEWS: { id: ViewName; label: string; key: string }[] = [
  { id: "front", label: "Old", key: "1" }, { id: "right", label: "O'ng", key: "3" }, { id: "top", label: "Tepa", key: "7" },
  { id: "back", label: "Orqa", key: "Ctrl+1" }, { id: "left", label: "Chap", key: "Ctrl+3" }, { id: "bottom", label: "Past", key: "Ctrl+7" },
  { id: "iso", label: "Izometrik", key: "" },
];

export interface SidebarProps {
  viewer: Viewer | null;
  selection: SelectedItem[];
  shading: Shading; onShading: (s: Shading) => void;
  projection: "Perspective" | "Orthographic"; onProjection: () => void;
  gridOn: boolean; onGrid: (v: boolean) => void;
  labelsOn: boolean; onLabels: () => void;
  version: Version | null; modelName: string;
  canEdit: boolean;
  onAction: (a: "upload" | "submit" | "issue" | "diff" | "props" | "fit") => void;
}

function Panel({ title, children, open = true }: { title: string; children: React.ReactNode; open?: boolean }) {
  const [o, setO] = useState(open);
  return (
    <div className="bpanel">
      <div className="bpanel-head" onClick={() => setO(!o)}><Icon name={o ? "chevron-down" : "chevron-right"} size={11} /> {title}</div>
      {o && <div className="bpanel-body">{children}</div>}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="brow"><span className="blabel">{label}</span><span className="bfield">{children}</span></div>;
}

export default function ViewportSidebar(p: SidebarProps) {
  const [tab, setTab] = useState<SideTab>("item");
  const [props, setProps] = useState<ItemProperties | null>(null);
  const [dims, setDims] = useState<{ size: [number, number, number]; center: [number, number, number] } | null>(null);
  const first = p.selection[0];
  useEffect(() => {
    if (!p.viewer || !first) { setProps(null); setDims(null); return; }
    let live = true;
    p.viewer.getProperties(first.localId).then((r) => live && setProps(r));
    p.viewer.getDimensions(first.localId).then((d) => live && setDims(d)).catch(() => setDims(null));
    return () => { live = false; };
  }, [p.viewer, first?.localId]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="vp-sidebar" onKeyDown={(e) => e.stopPropagation()}>
      <div className="vp-sidebar-body">
        {tab === "item" && (
          <>
            <Panel title="Element">
              {!first && <div className="dim">Elementni tanlang</div>}
              {first && (
                <>
                  <Row label="Nomi"><span className="bval">{props?.name || first.name || "nomsiz"}</span></Row>
                  <Row label="Turi"><span className="bval">{ifcLabel(props?.category || first.category)}</span></Row>
                  {props?.guid && <Row label="GUID"><span className="bval mono small">{props.guid}</span></Row>}
                  {p.selection.length > 1 && <div className="dim small">{p.selection.length} ta tanlangan</div>}
                </>
              )}
            </Panel>
            {dims && (
              <Panel title="Transform">
                <Row label="Joylashuv X"><span className="bval mono">{dims.center[0].toFixed(2)} m</span></Row>
                <Row label="Y"><span className="bval mono">{dims.center[1].toFixed(2)} m</span></Row>
                <Row label="Z"><span className="bval mono">{dims.center[2].toFixed(2)} m</span></Row>
                <Row label="O'lcham X"><span className="bval mono">{dims.size[0].toFixed(2)} m</span></Row>
                <Row label="Y"><span className="bval mono">{dims.size[1].toFixed(2)} m</span></Row>
                <Row label="Z"><span className="bval mono">{dims.size[2].toFixed(2)} m</span></Row>
              </Panel>
            )}
            {first && (
              <Panel title="Amallar">
                <div className="row wrap" style={{ gap: 4 }}>
                  <button className="btn sm" onClick={() => p.onAction("fit")}>Moslash (.)</button>
                  <button className="btn sm" onClick={() => p.onAction("props")}>Xususiyatlar</button>
                  <button className="btn sm" onClick={() => p.onAction("issue")}>Issue</button>
                </div>
              </Panel>
            )}
          </>
        )}
        {tab === "view" && (
          <>
            <Panel title="Ko'rinish">
              <Row label="Proyeksiya">
                <button className="btn sm" onClick={p.onProjection}>{p.projection === "Perspective" ? "Perspektiva" : "Ortografik"} (5)</button>
              </Row>
              <Row label="Shading">
                <select className="vp-select" value={p.shading} onChange={(e) => p.onShading(e.target.value as Shading)}>
                  <option value="wire">Wireframe</option><option value="solid">Solid</option><option value="xray">X-ray</option><option value="rendered">Rendered</option>
                </select>
              </Row>
              <Row label="Grid"><input type="checkbox" checked={p.gridOn} onChange={(e) => p.onGrid(e.target.checked)} /></Row>
              <Row label="Yorliqlar (L)"><input type="checkbox" checked={p.labelsOn} onChange={p.onLabels} /></Row>
            </Panel>
            <Panel title="Kamera">
              <div className="bgrid">
                {VIEWS.map((v) => <button key={v.id} className="btn sm" title={v.key} onClick={() => void p.viewer?.setView(v.id)}>{v.label}</button>)}
              </div>
              <button className="btn sm" style={{ marginTop: 6 }} onClick={() => p.onAction("fit")}>Hammasiga moslash (Home)</button>
            </Panel>
          </>
        )}
        {tab === "sath" && (
          <>
            <Panel title="Model">
              <Row label="Model"><span className="bval">{p.modelName}</span></Row>
              <Row label="Versiya"><span className="bval">{p.version ? `v${p.version.number} · ${p.version.state}` : "—"}</span></Row>
            </Panel>
            <Panel title="Server">
              <div className="row wrap" style={{ gap: 4 }}>
                {p.canEdit && <button className="btn sm primary" onClick={() => p.onAction("upload")}>Yangi versiya</button>}
                {p.canEdit && <button className="btn sm" onClick={() => p.onAction("submit")}>Tasdiqqa</button>}
                <button className="btn sm" onClick={() => p.onAction("diff")}>Ota bilan farq</button>
                <button className="btn sm" onClick={() => p.onAction("issue")}>Issue</button>
              </div>
            </Panel>
            <Panel title="Desktop">
              <div className="dim small">Sath desktop (Blender) da ochish: Sath → Model → versiyani tanlang → Ochish.</div>
            </Panel>
          </>
        )}
      </div>
      <div className="vp-sidebar-tabs">
        {SIDE_TABS.map((t) => <button key={t.id} className={tab === t.id ? "active" : ""} onClick={() => setTab(t.id)}>{t.title}</button>)}
      </div>
    </div>
  );
}
