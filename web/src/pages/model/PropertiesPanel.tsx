import { useEffect, useState } from "react";
import type { ItemProperties, SelectedItem, Viewer } from "../../viewer/Viewer";
import { ifcLabel } from "../../ui/format";
import Icon from "../../ui/Icon";

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
      {selection.length > 1 && <p className="muted small">{selection.length} ta element tanlangan, birinchisi ko'rsatilmoqda.</p>}
      <h3>{ifcLabel(props?.category || first.category)} <span className="dim">{props?.category || first.category}</span></h3>
      <div><b>{props?.name || first.name || <span className="dim">nomsiz</span>}</b></div>
      {props?.guid && <div className="mono small dim" style={{ marginBottom: 6 }}>{props.guid}</div>}
      {canEdit && selection.length === 1 && (
        <div className="row" style={{ marginBottom: 8, gap: 6 }}>
          <button className="btn sm primary" title="Elementni tahrirlash: surish (G), burish (R), masshtab (S), nom, Pset — yangi versiyada GUID saqlanadi (Tab)" onClick={() => onEdit?.(first.localId)}><Icon name="move" size={12} /> Tahrirlash</button>
          <button className="btn sm" title="Elementni o'chirish — yangi versiyada olib tashlanadi (X)" onClick={() => onDelete?.(first.localId)}><Icon name="trash" size={12} /> O'chirish</button>
        </div>
      )}
      {dims && (
        <table style={{ marginBottom: 6 }}><tbody>
          <tr><td>O'lchamlar (X×Y×Z), m</td><td className="mono">{dims.size.map((v) => v.toFixed(2)).join(" × ")}</td></tr>
          <tr><td>Markaz (IFC), m</td><td className="mono">{dims.center.map((v) => v.toFixed(2)).join(", ")}</td></tr>
        </tbody></table>
      )}
      {props && (
        <>
          <table>
            <tbody>
              {props.attributes.map((a) => (
                <tr key={a.name}><td>{a.name}</td><td>{a.value}</td></tr>
              ))}
            </tbody>
          </table>
          {props.psets.map((ps, i) => (
            <details key={i} open={i < 3}>
              <summary>{ps.name || "Xususiyatlar to'plami"}</summary>
              <table><tbody>
                {ps.props.map((p, j) => <tr key={j}><td>{p.name}</td><td>{p.value}</td></tr>)}
              </tbody></table>
            </details>
          ))}
          {props.psets.length === 0 && <p className="dim small">Xususiyatlar to'plami (Pset) yo'q.</p>}
        </>
      )}
    </div>
  );
}
