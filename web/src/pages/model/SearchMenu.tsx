import { useEffect, useMemo, useRef, useState } from "react";
import { searchCommands, type SearchItem } from "../../ui/blender";

/** Blender F3 — operator qidiruvi: matn yozing, ↑/↓ tanlang, Enter bajaring, Esc yoping. */
export default function SearchMenu({ items, onClose }: { items: SearchItem[]; onClose: () => void }) {
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);
  const inp = useRef<HTMLInputElement>(null);
  const list = useMemo(() => searchCommands(q, items), [q, items]);
  useEffect(() => { inp.current?.focus(); }, []);
  useEffect(() => { setIdx(0); }, [q]);
  const run = (it?: SearchItem) => { const t = it ?? list[idx]; if (t) { onClose(); t.run(); } };
  return (
    <div className="search-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="search-menu" role="dialog" aria-modal="true" aria-label="Operator qidiruvi (F3)">
        <input
          ref={inp}
          className="search-input"
          role="combobox"
          aria-expanded={list.length > 0}
          aria-controls="search-list"
          aria-autocomplete="list"
          aria-activedescendant={list.length ? `search-item-${idx}` : undefined}
          aria-label="Buyruq qidirish"
          placeholder="Buyruq qidirish… (F3)"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") { e.stopPropagation(); onClose(); }
            else if (e.key === "ArrowDown") { e.preventDefault(); setIdx((i) => Math.min(i + 1, list.length - 1)); }
            else if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)); }
            else if (e.key === "Enter") { e.preventDefault(); run(); }
            e.stopPropagation();
          }}
        />
        <div className="search-list" id="search-list" role="listbox" aria-label="Topilgan buyruqlar">
          {list.map((it, i) => (
            <div key={`${it.group}/${it.label}`} id={`search-item-${i}`} role="option" aria-selected={i === idx} tabIndex={-1} className={`search-item${i === idx ? " active" : ""}`} onMouseEnter={() => setIdx(i)} onMouseDown={(e) => { e.preventDefault(); run(it); }}>
              <span className="grp">{it.group}</span>
              <span className="lbl">{it.label}</span>
              {it.hint && <span className="hint">{it.hint}</span>}
            </div>
          ))}
          {list.length === 0 && <div className="search-item dim">Topilmadi</div>}
        </div>
      </div>
    </div>
  );
}
