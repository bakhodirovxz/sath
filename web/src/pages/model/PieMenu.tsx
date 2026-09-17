import { useEffect, useRef, useState } from "react";
import { pickPie, piePosition } from "../../ui/blender";

/** Blender pie menyu: kursor atrofida bo'laklar; sichqoncha yo'nalishi bo'lagini tanlaydi, bosish yoki
 *  tugmani qo'yib yuborish (releaseKey) tasdiqlaydi, Esc yopadi. */
export interface PieItem { label: string; hint?: string; active?: boolean; run: () => void }

export default function PieMenu({ x, y, title, items, releaseKey, onClose }: {
  x: number; y: number; title: string; items: PieItem[]; releaseKey?: string; onClose: () => void;
}) {
  const [hot, setHot] = useState<number | null>(null);
  const hotRef = useRef<number | null>(null);
  hotRef.current = hot;
  const pick = (i: number | null) => {
    // pie yopilgach shu bosishning click i canvasga tushmasin (element tanlanib ketmasin)
    window.addEventListener("click", (ev) => { ev.stopPropagation(); ev.preventDefault(); }, { capture: true, once: true });
    if (i != null) items[i]?.run();
    onClose();
  };

  useEffect(() => {
    const move = (e: MouseEvent) => { const h = pickPie(e.clientX - x, e.clientY - y, items.length); hotRef.current = h; setHot(h); };
    const up = (e: KeyboardEvent) => {
      if (releaseKey && e.key.toLowerCase() === releaseKey.toLowerCase()) {
        // Blender: tugma qo'yib yuborilganda yo'nalish bo'lsa tanlanadi, bo'lmasa menyu ochiq qoladi (bosishga)
        if (hotRef.current != null) pick(hotRef.current);
      }
    };
    const down = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.stopPropagation(); onClose(); return; }
      const n = Number(e.key);
      if (n >= 1 && n <= items.length) { e.preventDefault(); pick(n - 1); }
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("keyup", up);
    window.addEventListener("keydown", down, true);
    return () => { window.removeEventListener("mousemove", move); window.removeEventListener("keyup", up); window.removeEventListener("keydown", down, true); };
  }, [x, y, items.length]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="pie-backdrop" onMouseDown={(e) => { e.preventDefault(); pick(hotRef.current); }} onContextMenu={(e) => { e.preventDefault(); onClose(); }}>
      <div className="pie" style={{ left: x, top: y }}>
        <div className="pie-title">{title}</div>
        <div className="pie-center" />
        {items.map((it, i) => {
          const p = piePosition(i, items.length, 88);
          return (
            <div key={it.label} className={`pie-item${hot === i ? " hot" : ""}${it.active ? " active" : ""}`} style={{ left: p.x, top: p.y }}>
              <span>{it.label}</span>{it.hint && <em>{it.hint}</em>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
