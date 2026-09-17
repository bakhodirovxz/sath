import { useEffect, useMemo, useState } from "react";
import Icon from "../../ui/Icon";
import type { TreeNode, Viewer } from "../../viewer/Viewer";
import { ifcLabel } from "../../ui/format";

/** Outliner (Blender): ikonkali daraxt, qidiruv + tur filtri, ko'z/ajratish ustunlari, tanlangan (ko'k) va faol
 *  (och) qatorlar, o'ng tugma kontekst menyu (tanlash, yashirish, ajratish, moslash). */

function collectIds(n: TreeNode, out: number[] = []): number[] {
  if (n.localId != null) out.push(n.localId);
  n.children.forEach((c) => collectIds(c, out));
  return out;
}

function matches(n: TreeNode, q: string, cat: string): boolean {
  const self = (!q || n.name.toLowerCase().includes(q) || ifcLabel(n.category).toLowerCase().includes(q)) && (!cat || n.category === cat);
  return self || n.children.some((c) => matches(c, q, cat));
}

/** IFC klassi → Blender Outliner ikonkasi (collection/obyekt turlari kabi). */
export function iconFor(category: string): string {
  const c = category.toUpperCase();
  if (c.includes("PROJECT")) return "map";
  if (c.includes("SITE")) return "mountain";
  if (c.includes("BUILDING") && c.includes("STOREY")) return "layers";
  if (c.includes("BUILDING")) return "house";
  if (c.includes("WALL")) return "dam";
  if (c.includes("PIPE") || c.includes("FLOWSEGMENT")) return "pipe";
  if (c.includes("FLOWMOVING") || c.includes("TURBINE") || c.includes("ENERGYCONVERSION")) return "turbine";
  if (c.includes("TRANSFORMER") || c.includes("ELECTRIC")) return "zap";
  if (c.includes("SLAB") || c.includes("PLATE")) return "plane";
  if (c.includes("COLUMN") || c.includes("PILE")) return "cylinder";
  if (c.includes("SPACE") || c.includes("ZONE")) return "box";
  return "box";
}

function allCategories(n: TreeNode, out = new Set<string>()): Set<string> {
  if (n.localId != null && n.children.length === 0) out.add(n.category);
  n.children.forEach((c) => allCategories(c, out));
  return out;
}

interface Ctx { x: number; y: number; node: TreeNode }

function Node({ node, depth, selected, active, hidden, q, cat, onPick, onEye, onCtx }: {
  node: TreeNode; depth: number; selected: Set<number>; active: number | null; hidden: Set<number>; q: string; cat: string;
  onPick: (n: TreeNode, e: React.MouseEvent) => void; onEye: (n: TreeNode, visible: boolean) => void; onCtx: (c: Ctx) => void;
}) {
  const [open, setOpen] = useState(depth < 2);
  const has = node.children.length > 0;
  const isSel = node.localId != null && selected.has(node.localId);
  const isActive = node.localId != null && node.localId === active;
  const isHidden = node.localId != null && hidden.has(node.localId);
  if (!matches(node, q, cat)) return null;
  // Blender: tanlangan elementgacha daraxt ochiladi
  const holdsSel = has && selected.size > 0 && !isSel && collectIds(node).some((id) => selected.has(id));
  const expanded = open || !!q || !!cat || holdsSel;
  return (
    <div>
      <div
        className={`node${isSel ? " selected" : ""}${isActive ? " active" : ""}${isHidden ? " hidden" : ""}`}
        style={{ paddingLeft: 4 + depth * 14 }}
        onClick={(e) => onPick(node, e)}
        onDoubleClick={() => setOpen(!open)}
        onContextMenu={(e) => { e.preventDefault(); onCtx({ x: e.clientX, y: e.clientY, node }); }}
      >
        <span className="tw" onClick={(e) => { e.stopPropagation(); setOpen(!expanded); }}>{has ? <Icon name={expanded ? "chevron-down" : "chevron-right"} size={11} /> : ""}</span>
        <span className="ic"><Icon name={iconFor(node.category)} size={13} /></span>
        <span className="nm">{node.name || <span className="dim">nomsiz</span>}</span>
        <span className="cat">{ifcLabel(node.category)}</span>
        {node.localId != null && (
          <span className="cols">
            <button className="eye" title={isHidden ? "Ko'rsatish" : "Yashirish (H)"} onClick={(e) => { e.stopPropagation(); onEye(node, isHidden); }}><Icon name={isHidden ? "eye-off" : "eye"} size={13} /></button>
          </span>
        )}
      </div>
      {has && expanded && node.children.map((c, i) => (
        <Node key={c.localId ?? `n${i}`} node={c} depth={depth + 1} selected={selected} active={active} hidden={hidden} q={q} cat={cat} onPick={onPick} onEye={onEye} onCtx={onCtx} />
      ))}
    </div>
  );
}

export default function TreePanel({ viewer, modelKey, selectedIds }: { viewer: Viewer | null; modelKey: string | null; selectedIds: number[] }) {
  const [tree, setTree] = useState<TreeNode | null>(null);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const [hidden, setHidden] = useState<Set<number>>(new Set());
  const [ctx, setCtx] = useState<Ctx | null>(null);
  useEffect(() => {
    if (!viewer || !modelKey) return setTree(null);
    let live = true;
    setHidden(new Set());
    viewer.getTree().then((t) => live && setTree(t));
    return () => { live = false; };
  }, [viewer, modelKey]);
  useEffect(() => {
    if (!ctx) return;
    const close = () => setCtx(null);
    window.addEventListener("click", close);
    window.addEventListener("keydown", close);
    return () => { window.removeEventListener("click", close); window.removeEventListener("keydown", close); };
  }, [ctx]);

  const selected = useMemo(() => new Set(selectedIds), [selectedIds]);
  const active = selectedIds.length ? selectedIds[selectedIds.length - 1] : null;
  const cats = useMemo(() => (tree ? [...allCategories(tree)].sort() : []), [tree]);
  if (!modelKey) return <p className="muted">Model yuklanmagan.</p>;
  if (!tree) return <p className="muted">Daraxt tuzilmoqda…</p>;

  const idsOf = async (n: TreeNode) => (n.localId == null ? [] : n.children.length ? [n.localId, ...(await viewer!.childrenOf(n.localId))] : [n.localId]);
  async function pick(n: TreeNode, e: React.MouseEvent) {
    if (!viewer || n.localId == null) return;
    const ids = await idsOf(n);
    if (e.ctrlKey || e.shiftKey) await viewer.selectLocalIds([...new Set([...selectedIds, ...ids])], false); // Blender: Ctrl — qo'shib tanlash
    else await viewer.selectLocalIds(ids, true);
  }
  async function eye(n: TreeNode, visible: boolean) {
    if (!viewer) return;
    const ids = collectIds(n);
    await viewer.setItemsVisible(ids, visible);
    setHidden((h) => { const next = new Set(h); ids.forEach((id) => (visible ? next.delete(id) : next.add(id))); return next; });
  }
  async function ctxAction(a: "select" | "hide" | "isolate" | "showall" | "fit") {
    const n = ctx?.node; setCtx(null);
    if (!viewer || !n) return;
    if (a === "select") { await viewer.selectLocalIds(await idsOf(n), false); }
    else if (a === "hide") { await eye(n, false); }
    else if (a === "isolate") { await viewer.selectLocalIds(await idsOf(n), false); await viewer.isolateSelected(); }
    else if (a === "showall") { await viewer.showAll(); setHidden(new Set()); }
    else if (a === "fit") { await viewer.selectLocalIds(await idsOf(n), true); }
  }
  return (
    <div className="tree">
      <div className="row" style={{ marginBottom: 4, gap: 4 }}>
        <input className="input" placeholder="Qidirish…" value={q} onChange={(e) => setQ(e.target.value.toLowerCase())} style={{ padding: "2px 6px" }} />
        <select className="vp-select" value={cat} onChange={(e) => setCat(e.target.value)} title="Tur bo'yicha filtr" style={{ maxWidth: 110 }}>
          <option value="">Barcha turlar</option>
          {cats.map((c) => <option key={c} value={c}>{ifcLabel(c)}</option>)}
        </select>
        {hidden.size > 0 && <button className="btn sm" title="Hammasini ko'rsatish (Alt+H)" onClick={() => { void viewer?.showAll(); setHidden(new Set()); }}><Icon name="eye" size={13} /> {hidden.size}</button>}
      </div>
      <Node node={tree} depth={0} selected={selected} active={active} hidden={hidden} q={q} cat={cat} onPick={pick} onEye={eye} onCtx={setCtx} />
      {ctx && (
        <div className="ctx-menu" style={{ left: ctx.x, top: ctx.y }} onClick={(e) => e.stopPropagation()}>
          <div className="ctx-title">{ctx.node.name || ifcLabel(ctx.node.category)}</div>
          <button className="menu-item" onClick={() => void ctxAction("select")}><span>Tanlash (ierarxiya)</span></button>
          <button className="menu-item" onClick={() => void ctxAction("fit")}><span>Moslash</span><span className="hint">.</span></button>
          <div className="menu-sep" />
          <button className="menu-item" onClick={() => void ctxAction("hide")}><span>Yashirish</span><span className="hint">H</span></button>
          <button className="menu-item" onClick={() => void ctxAction("isolate")}><span>Ajratish (local view)</span><span className="hint">/</span></button>
          <button className="menu-item" onClick={() => void ctxAction("showall")}><span>Hammasini ko'rsatish</span><span className="hint">Alt+H</span></button>
        </div>
      )}
    </div>
  );
}
