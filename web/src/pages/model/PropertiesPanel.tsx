import { useEffect, useState } from "react";
import type { ItemProperties, SelectedItem, Viewer } from "../../viewer/Viewer";
import { ifcLabel } from "../../ui/format";
import Icon from "../../ui/Icon";
import { BPanel, BRow } from "../../ui/BlenderUI";
import { api, type CrsConvert, type Project } from "../../api/client";

/** Properties editor (Blender): yopiladigan panellar («Element», «O'lchamlar», «Atributlar», har Pset alohida),
 *  qatorlar label (40%) / maydon (60%). Panel holati localStorage da. */

export default function PropertiesPanel({ viewer, selection, canEdit, onEdit, onDelete, project }: { viewer: Viewer | null; selection: SelectedItem[]; canEdit?: boolean; onEdit?: (localId: number) => void; onDelete?: (localId: number) => void; project?: Project | null }) {
  const [props, setProps] = useState<ItemProperties | null>(null);
  const [dims, setDims] = useState<{ size: [number, number, number]; center: [number, number, number] } | null>(null);
  const [geo, setGeo] = useState<CrsConvert | null>(null);
  const first = selection[0];
  // G3: element markazi → global (E, N, H) va lat/lon — loyiha CRS bo'yicha
  const crsEpsg = project?.crs?.epsg;
  const projectId = project?.id;
  const cx = dims?.center[0], cy = dims?.center[1], cz = dims?.center[2];
  useEffect(() => {
    if (!crsEpsg || !projectId || cx == null || cy == null) return setGeo(null);
    let live = true;
    api.crsConvert(projectId, { x: cx, y: cy, z: cz ?? 0 }).then((g) => live && setGeo(g)).catch(() => setGeo(null));
    return () => { live = false; };
  }, [crsEpsg, projectId, cx, cy, cz]);

  const localId = first?.localId;
  useEffect(() => {
    if (!viewer || localId == null) return setProps(null);
    let live = true;
    viewer.getProperties(localId).then((p) => live && setProps(p));
    viewer.getDimensions(localId).then((d) => live && setDims(d)).catch(() => setDims(null));
    return () => { live = false; };
  }, [viewer, localId]);

  if (!first) return <p className="muted">Elementni tanlang — xususiyatlari shu yerda ko'rinadi.</p>;
  return (
    <div className="props">
      {selection.length > 1 && <p className="muted small">{selection.length} ta element tanlangan, faoli ko'rsatilmoqda.</p>}
      <BPanel id="element" title="Element">
        <BRow label="Nomi" value={props?.name || first.name || ""} />
        <BRow label="Turi" value={<>{ifcLabel(props?.category || first.category)} <span className="dim">{props?.category || first.category}</span></>} />
        {props?.guid && <BRow label="GUID" value={props.guid} mono />}
        {canEdit && selection.length === 1 && (
          <div className="row" style={{ marginTop: 6, gap: 6 }}>
            <button className="btn sm primary" title="Tahrirlash: surish (G), burish (R), masshtab (S), nom, Pset — yangi versiyada GUID saqlanadi (Tab)" onClick={() => onEdit?.(first.localId)}><Icon name="move" size={12} /> Tahrirlash</button>
            <button className="btn sm" title="O'chirish — yangi versiyada olib tashlanadi (X)" onClick={() => onDelete?.(first.localId)}><Icon name="trash" size={12} /> O'chirish</button>
          </div>
        )}
      </BPanel>
      {dims && (
        <BPanel id="dims" title="O'lchamlar">
          <BRow label="X" value={`${dims.size[0].toFixed(2)} m`} mono />
          <BRow label="Y" value={`${dims.size[1].toFixed(2)} m`} mono />
          <BRow label="Z" value={`${dims.size[2].toFixed(2)} m`} mono />
          <BRow label="Markaz (IFC)" value={dims.center.map((v) => v.toFixed(2)).join(", ") + " m"} mono />
          {geo?.global && <BRow label={`Global (EPSG:${geo.global.epsg})`} value={`E ${geo.global.e.toFixed(2)}  N ${geo.global.n.toFixed(2)}  H ${geo.global.h.toFixed(2)}`} mono />}
          {geo?.latlon && <BRow label="Lat / Lon" value={`${geo.latlon.lat.toFixed(6)}, ${geo.latlon.lon.toFixed(6)}`} mono />}
        </BPanel>
      )}
      {props && props.attributes.length > 0 && (
        <BPanel id="attrs" title="Atributlar" defaultOpen={false} count={props.attributes.length}>
          {props.attributes.map((a) => <BRow key={a.name} label={a.name} value={a.value} />)}
        </BPanel>
      )}
      {props?.psets.map((ps, i) => (
        <BPanel key={i} id={`pset:${ps.name}`} title={ps.name || "Xususiyatlar to'plami"} defaultOpen={i < 3} count={ps.props.length}>
          {ps.props.map((p, j) => <BRow key={j} label={p.name} value={p.value} />)}
        </BPanel>
      ))}
      {props && props.psets.length === 0 && <p className="dim small">Xususiyatlar to'plami (Pset) yo'q.</p>}
    </div>
  );
}
