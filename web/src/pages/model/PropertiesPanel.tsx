import { useEffect, useState } from "react";
import type { ItemProperties, SelectedItem, Viewer } from "../../viewer/Viewer";
import { ifcLabel } from "../../ui/format";
import Icon from "../../ui/Icon";
import { BPanel, BRow } from "../../ui/BlenderUI";

/** Properties editor (Blender): yopiladigan panellar («Element», «O'lchamlar», «Atributlar», har Pset alohida),
 *  qatorlar label (40%) / maydon (60%). Panel holati localStorage da. */

export default function PropertiesPanel({ viewer, selection, canEdit, onEdit, onDelete }: { viewer: Viewer | null; selection: SelectedItem[]; canEdit?: boolean; onEdit?: (localId: number) => void; onDelete?: (localId: number) => void }) {
  const [props, setProps] = useState<ItemProperties | null>(null);
  const [dims, setDims] = useState<{ size: [number, number, number]; center: [number, number, number] } | null>(null);
  const first = selection[0];

  useEffect(() => {
    if (!viewer || !first) return setProps(null);
    let live = true;
    viewer.getProperties(first.localId).then((p) => live && setProps(p));
    viewer.getDimensions(first.localId).then((d) => live && setDims(d)).catch(() => setDims(null));
    return () => { live = false; };
  }, [viewer, first?.localId]); // eslint-disable-line react-hooks/exhaustive-deps

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
