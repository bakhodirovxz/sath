import { useEffect, useState } from "react";
import type { Viewer } from "../../viewer/Viewer";
import { ifcLabel } from "../../ui/format";

/** Qatlamlar = IFC kategoriyalar (AutoCAD layer paneliga o'xshash yoqish/o'chirish). */
export default function LayersPanel({ viewer, modelKey }: { viewer: Viewer | null; modelKey: string | null }) {
  const [cats, setCats] = useState<{ category: string; count: number }[]>([]);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (!viewer || !modelKey) return setCats([]);
    setHidden(new Set());
    viewer.getCategories().then(setCats);
  }, [viewer, modelKey]);

  async function toggle(cat: string) {
    if (!viewer) return;
    const next = new Set(hidden);
    const visible = next.has(cat);
    if (visible) next.delete(cat); else next.add(cat);
    setHidden(next);
    await viewer.setCategoryVisible(cat, visible);
  }
  async function all(visible: boolean) {
    if (!viewer) return;
    setHidden(visible ? new Set() : new Set(cats.map((c) => c.category)));
    for (const c of cats) await viewer.setCategoryVisible(c.category, visible);
  }

  if (!modelKey) return <p className="muted">Model yuklanmagan.</p>;
  return (
    <div className="layers">
      <div className="row" style={{ marginBottom: 6 }}>
        <button className="btn sm" onClick={() => all(true)}>Hammasi</button>
        <button className="btn sm" onClick={() => all(false)}>Hech biri</button>
      </div>
      {cats.map((c) => (
        <label key={c.category}>
          <input type="checkbox" checked={!hidden.has(c.category)} onChange={() => toggle(c.category)} />
          <span>{ifcLabel(c.category)}</span>
          <span className="n">{c.count}</span>
        </label>
      ))}
    </div>
  );
}
