import { useCallback, useEffect, useState } from "react";
import Icon from "../../ui/Icon";
import { api, type SavedView } from "../../api/client";
import type { Viewer } from "../../viewer/Viewer";

interface Props { modelId: number; viewer: Viewer | null; refresh: number }

/** Saqlangan ko'rinishlar (AutoCAD "named views"): kamera + tanlov + kesimlar. */
export default function ViewsPanel({ modelId, viewer, refresh }: Props) {
  const [views, setViews] = useState<SavedView[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const load = useCallback(() => api.views(modelId).then(setViews).catch((e) => setError(e.message)), [modelId]);
  useEffect(() => { void load(); }, [load, refresh]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!viewer || !name.trim()) return;
    try { await api.saveView(modelId, name.trim(), await viewer.getViewpoint()); setName(""); await load(); } catch (err) { setError(err instanceof Error ? err.message : "Xatolik"); }
  }
  return (
    <div className="views">
      <h3>Saqlangan ko'rinishlar</h3>
      {error && <p className="error small">{error}</p>}
      <form className="row mb-6" onSubmit={save}>
        <input className="input" placeholder="Nomi (VSAVE nom)" value={name} onChange={(e) => setName(e.target.value)} />
        <button className="btn sm" type="submit" disabled={!name.trim()}>Saqlash</button>
      </form>
      {views.length === 0 && <p className="dim small">Joriy kamera/tanlovni nom bilan saqlang; VIEW nom bilan qaytasiz.</p>}
      {views.map((v) => (
        <div key={v.id} className="row view-row">
          <button type="button" className="link-btn grow" onClick={() => viewer?.setViewpoint(v.viewpoint)}>{v.name}</button>
          <span className="dim small">{v.author_username}</span>
          <button className="btn sm" title="O'chirish" onClick={() => api.deleteView(v.id).then(load).catch((e) => setError(e.message))}><Icon name="trash" size={13} /></button>
        </div>
      ))}
    </div>
  );
}
