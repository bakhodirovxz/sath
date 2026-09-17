import { useState } from "react";
import Icon from "./Icon";

/** Blender uslubidagi UI to'plami: yopiladigan panel, label/maydon qatori, UIList, sarlavha operatorlari. */

function loadState(): Record<string, boolean> {
  try { return JSON.parse(localStorage.getItem("sath_panels") || "{}"); } catch { return {}; }
}
function saveState(s: Record<string, boolean>) {
  try { localStorage.setItem("sath_panels", JSON.stringify(s)); } catch { /* */ }
}

/** Panel: sarlavha (ochish/yopish, holat localStorage) + ixtiyoriy o'ng tomonda operatorlar. */
export function BPanel({ id, title, children, defaultOpen = true, count, right, icon }: {
  id: string; title: string; children: React.ReactNode; defaultOpen?: boolean; count?: number | string; right?: React.ReactNode; icon?: string;
}) {
  const [open, setOpen] = useState<boolean>(() => loadState()[id] ?? defaultOpen);
  const toggle = () => { const v = !open; setOpen(v); saveState({ ...loadState(), [id]: v }); };
  return (
    <div className="bpanel">
      <div className="bpanel-head" onClick={toggle}>
        <Icon name={open ? "chevron-down" : "chevron-right"} size={11} />
        {icon && <Icon name={icon} size={12} />}
        <span className="grow">{title}</span>
        {count != null && <span className="dim" style={{ fontWeight: 400 }}>{count}</span>}
        {right && <span onClick={(e) => e.stopPropagation()} className="row" style={{ gap: 4 }}>{right}</span>}
      </div>
      {open && <div className="bpanel-body">{children}</div>}
    </div>
  );
}

/** Qator: chapda label (40%), o'ngda maydon (60%). `value` berilsa o'qish uchun maydon. */
export function BRow({ label, value, mono, children, title }: { label: string; value?: React.ReactNode; mono?: boolean; children?: React.ReactNode; title?: string }) {
  const text = typeof value === "string" ? value : title;
  return (
    <div className="brow">
      <span className="blabel" title={label}>{label}</span>
      <span className="bfield">
        {children ?? <span className={`bval${mono ? " mono" : ""}`} title={text}>{value === "" || value == null ? <span className="dim">—</span> : value}</span>}
      </span>
    </div>
  );
}

/** Blender UIList: qatorlar, faol (ko'k), ikkinchi bosish/Enter — «ochish». Klaviatura: ↑/↓. */
export function BList<T>({ items, keyOf, render, activeKey, onSelect, onActivate, rows = 5, empty }: {
  items: T[]; keyOf: (t: T) => string | number; render: (t: T, active: boolean) => React.ReactNode;
  activeKey?: string | number | null; onSelect?: (t: T) => void; onActivate?: (t: T) => void; rows?: number; empty?: string;
}) {
  return (
    <div className="blist" style={{ maxHeight: rows * 22 + 2 }} tabIndex={0}
      onKeyDown={(e) => {
        if (!items.length || !onSelect) return;
        const i = items.findIndex((t) => keyOf(t) === activeKey);
        if (e.key === "ArrowDown") { e.preventDefault(); onSelect(items[Math.min(i + 1, items.length - 1)]); }
        else if (e.key === "ArrowUp") { e.preventDefault(); onSelect(items[Math.max(i - 1, 0)]); }
        else if (e.key === "Enter" && i >= 0 && onActivate) { e.preventDefault(); onActivate(items[i]); }
      }}>
      {items.length === 0 && <div className="blist-row dim">{empty ?? "Bo'sh"}</div>}
      {items.map((t) => {
        const active = keyOf(t) === activeKey;
        return (
          <div key={keyOf(t)} className={`blist-row${active ? " active" : ""}`} onClick={() => onSelect?.(t)} onDoubleClick={() => onActivate?.(t)}>
            {render(t, active)}
          </div>
        );
      })}
    </div>
  );
}

/** Kichik belgi (badge) — holat rangi bilan. */
export function BBadge({ kind, children, title }: { kind?: string; children: React.ReactNode; title?: string }) {
  return <span className={`badge ${kind ?? ""}`} title={title}>{children}</span>;
}

/** Operatorlar qatori (Blender header): tugmalar bir qatorda, birlashgan. */
export function BOps({ children }: { children: React.ReactNode }) {
  return <div className="bops">{children}</div>;
}
