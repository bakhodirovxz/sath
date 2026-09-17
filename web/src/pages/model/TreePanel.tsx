import { useEffect, useMemo, useState } from "react";
import Icon from "../../ui/Icon";
import type { TreeNode, Viewer } from "../../viewer/Viewer";
import { ifcLabel } from "../../ui/format";

/** Outliner (Blender kabi): daraxt, qidiruv, ko'z (ko'rinish) tugmalari, tanlash. */

function collectIds(n: TreeNode, out: number[] = []): number[] {
  if (n.localId != null) out.push(n.localId);
  n.children.forEach((c) => collectIds(c, out));
  return out;
}

function matches(n: TreeNode, q: string): boolean {
  if (!q) return true;
  return n.name.toLowerCase().includes(q) || ifcLabel(n.category).toLowerCase().includes(q) || n.children.some((c) => matches(c, q));
}

function Node({ node, depth, selected, hidden, q, onPick, onEye }: {
  node: TreeNode; depth: number; selected: Set<number>; hidden: Set<number>; q: string;
  onPick: (n: TreeNode) => void; onEye: (n: TreeNode, visible: boolean) => void;
}) {
  const [open, setOpen] = useState(depth < 2);
  const has = node.children.length > 0;
  const isSel = node.localId != null && selected.has(node.localId);
  const isHidden = node.localId != null && hidden.has(node.localId);
  const forced = q ? matches(node, q) : true;
  if (!forced) return null;
  const expanded = open || !!q;
  return (
    <div>
      <div className={`node${isSel ? " selected" : ""}${isHidden ? " hidden" : ""}`} onClick={() => onPick(node)} onDoubleClick={() => setOpen(!open)}>
        <span className="tw" onClick={(e) => { e.stopPropagation(); setOpen(!expanded); }}>{has ? <Icon name={expanded ? "chevron-down" : "chevron-right"} size={11} /> : "·"}</span>
        <span className="nm">{node.name || <span className="dim">nomsiz</span>}</span>
        <span className="cat">{ifcLabel(node.category)}</span>
        {node.localId != null && (
          <button className="eye" title={isHidden ? "Ko'rsatish" : "Yashirish"} onClick={(e) => { e.stopPropagation(); onEye(node, isHidden); }}><Icon name={isHidden ? "eye-off" : "eye"} size={13} /></button>
        )}
      </div>
      {has && expanded && (
        <div className="children">
          {node.children.map((c, i) => <Node key={c.localId ?? `n${i}`} node={c} depth={depth + 1} selected={selected} hidden={hidden} q={q} onPick={onPick} onEye={onEye} />)}
        </div>
      )}
    </div>
  );
}

export default function TreePanel({ viewer, modelKey, selectedIds }: { viewer: Viewer | null; modelKey: string | null; selectedIds: number[] }) {
  const [tree, setTree] = useState<TreeNode | null>(null);
  const [q, setQ] = useState("");
  const [hidden, setHidden] = useState<Set<number>>(new Set());
  useEffect(() => {
    if (!viewer || !modelKey) return setTree(null);
    let live = true;
    setHidden(new Set());
    viewer.getTree().then((t) => live && setTree(t));
    return () => { live = false; };
  }, [viewer, modelKey]);

  const selected = useMemo(() => new Set(selectedIds), [selectedIds]);
  if (!modelKey) return <p className="muted">Model yuklanmagan.</p>;
  if (!tree) return <p className="muted">Daraxt tuzilmoqda…</p>;
  async function pick(n: TreeNode) {
    if (!viewer || n.localId == null) return;
    const ids = n.children.length ? [n.localId, ...(await viewer.childrenOf(n.localId))] : [n.localId];
    await viewer.selectLocalIds(ids, true);
  }
  async function eye(n: TreeNode, visible: boolean) {
    if (!viewer) return;
    const ids = collectIds(n);
    await viewer.setItemsVisible(ids, visible);
    setHidden((h) => { const next = new Set(h); ids.forEach((id) => (visible ? next.delete(id) : next.add(id))); return next; });
  }
  return (
    <div className="tree">
      <div className="row" style={{ marginBottom: 4 }}>
        <input className="input" placeholder="Qidirish (nom, tur)…" value={q} onChange={(e) => setQ(e.target.value.toLowerCase())} style={{ padding: "2px 6px" }} />
        {hidden.size > 0 && <button className="btn sm" title="Hammasini ko'rsatish" onClick={() => { void viewer?.showAll(); setHidden(new Set()); }}><Icon name="eye" size={13} /> {hidden.size}</button>}
      </div>
      <Node node={tree} depth={0} selected={selected} hidden={hidden} q={q} onPick={pick} onEye={eye} />
    </div>
  );
}
