import { useEffect, useRef, useState } from "react";
import Icon from "../../ui/Icon";
import type { Quaternion } from "three";
import type { NavMode, Shading, ViewName, Viewer } from "../../viewer/Viewer";

/* Blender/3ds Max uslubidagi viewport atrofi: menyu satri, viewport sarlavhasi, navigatsiya gizmosi. */

export interface MenuItem { label: string; hint?: string; onClick?: () => void; disabled?: boolean; sep?: boolean }
export interface Menu { title: string; items: MenuItem[] }

/** Yuqori menyu satri (Fayl / Tahrir / Ko'rinish …) — bosilganda ochiladi, tashqariga bosilsa yopiladi. */
export function MenuBar({ menus }: { menus: Menu[] }) {
  const [open, setOpen] = useState<number | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (open == null) return;
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(null); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  return (
    <div className="menubar" ref={ref}>
      {menus.map((m, i) => (
        <div key={m.title} className={`menu ${open === i ? "open" : ""}`}>
          <button className="menu-title" onClick={() => setOpen(open === i ? null : i)} onMouseEnter={() => open != null && setOpen(i)}>{m.title}</button>
          {open === i && (
            <div className="menu-list">
              {m.items.map((it, k) => it.sep ? <div key={k} className="menu-sep" /> : (
                <button key={k} className="menu-item" disabled={it.disabled} onClick={() => { setOpen(null); it.onClick?.(); }}>
                  <span>{it.label}</span>{it.hint && <span className="hint">{it.hint}</span>}
                </button>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

const SHADINGS: { id: Shading; icon: string; title: string }[] = [
  { id: "solid", icon: "shade-solid", title: "Solid (Z)" },
  { id: "wire", icon: "shade-wire", title: "Wireframe (Z)" },
  { id: "xray", icon: "shade-xray", title: "X-ray (Z)" },
  { id: "rendered", icon: "shade-rendered", title: "Rendered — AO + konturlar (Z)" },
];

interface HeaderProps {
  viewer: Viewer | null;
  shading: Shading;
  onShading: (s: Shading) => void;
  grid: boolean;
  onGrid: (v: boolean) => void;
  projection: "Perspective" | "Orthographic";
  onProjection: () => void;
  navMode: NavMode;
  onNavMode: (m: NavMode) => void;
  colorScheme: "none" | "type" | "storey";
  onColorScheme: (m: "none" | "type" | "storey") => void;
  onSectionBox: () => void;
  water?: { on: boolean; level: number | null; onToggle: () => void };
  onRender: () => void;
  right?: React.ReactNode;
}

/** Viewport sarlavhasi (Blender 3D viewport header): shading, overlay, proyeksiya, ko'rinishlar. */
export function ViewportHeader({ viewer, shading, onShading, grid, onGrid, projection, onProjection, navMode, onNavMode, colorScheme, onColorScheme, onSectionBox, onRender, water, right }: HeaderProps) {
  const views: [ViewName, string][] = [["top", "Tepa"], ["front", "Old"], ["right", "O'ng"], ["left", "Chap"], ["back", "Orqa"], ["bottom", "Past"], ["iso", "Izometrik"]];
  return (
    <div className="vp-header">
      <select className="vp-select" value={navMode} onChange={(e) => onNavMode(e.target.value as NavMode)} title="Kamera rejimi">
        <option value="Orbit">Aylantirish</option><option value="FirstPerson">Yurish (WASD)</option><option value="Plan">Plan</option>
      </select>
      <span className="vp-group" title="Viewport shading">
        {SHADINGS.map((s) => <button key={s.id} className={shading === s.id ? "on" : ""} title={s.title} onClick={() => onShading(s.id)}><Icon name={s.icon} size={14} /></button>)}
      </span>
      <span className="vp-group">
        <button className={grid ? "on" : ""} title="Overlay: grid" onClick={() => onGrid(!grid)}><Icon name="grid" size={14} /></button>
        <button className={projection === "Orthographic" ? "on" : ""} title="Ortografik/perspektiva (5)" onClick={onProjection}>{projection === "Orthographic" ? "Ortho" : "Persp"}</button>
      </span>
      <select className="vp-select" value={colorScheme} onChange={(e) => onColorScheme(e.target.value as "none" | "type" | "storey")} title="Rang sxemasi (Blender: viewport color)">
        <option value="none">Rang: material</option><option value="type">Rang: IFC turi</option><option value="storey">Rang: qavat</option>
      </select>
      <span className="vp-group">
        <button title="Kesim qutisi — tanlangan (yoki butun model) atrofida" onClick={onSectionBox}><Icon name="section-box" size={14} /> Kesim</button>
        <button title="Render — viewport rasmini saqlash (F12)" onClick={onRender}><Icon name="camera" size={14} /></button>
        {water && water.level != null && <button className={water.on ? "on" : ""} title={`Suv ombori NPU sathida (${water.level} m, maydon pasporti) — to'lqinli suv yuzasi`} onClick={water.onToggle}><Icon name="waves" size={14} /> Suv</button>}
      </span>
      <select className="vp-select" value="" onChange={(e) => { if (e.target.value) void viewer?.setView(e.target.value as ViewName); }} title="Ko'rinish (numpad 1/3/7)">
        <option value="">Ko'rinish</option>
        {views.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
      <span className="grow" />
      {right}
    </div>
  );
}

/** Navigatsiya gizmosi (Blender): X/Y/Z o'qlari kamera bilan aylanadi; o'qni bosish — shu tomondan ko'rinish. */
export function NavGizmo({ viewer, ready }: { viewer: Viewer | null; ready: boolean }) {
  const [q, setQ] = useState<[number, number, number, number]>([0, 0, 0, 1]);
  useEffect(() => {
    if (!viewer || !ready) return;
    return viewer.onCameraChange((qq: Quaternion) => setQ([qq.x, qq.y, qq.z, qq.w]));
  }, [viewer, ready]);
  // Dunyo o'qlarini kamera fazosiga: v' = q^-1 * v (kamera quaternioni teskarisi)
  const [x, y, z, w] = q;
  const rot = (v: [number, number, number]): [number, number, number] => {
    // q* = (-x,-y,-z,w); v' = q* v q
    const ix = w * v[0] - y * v[2] + z * v[1];
    const iy = w * v[1] - z * v[0] + x * v[2];
    const iz = w * v[2] - x * v[1] + y * v[0];
    const iw = x * v[0] + y * v[1] + z * v[2];
    return [ix * w + iw * x + iy * z - iz * y, iy * w + iw * y + iz * x - ix * z, iz * w + iw * z + ix * y - iy * x];
  };
  // IFC o'qlari three fazoda: X→x, Y→-z, Z→y
  const axes: { name: string; v: [number, number, number]; color: string; view: ViewName; neg: ViewName }[] = [
    { name: "X", v: [1, 0, 0], color: "#e0656a", view: "right", neg: "left" },
    { name: "Y", v: [0, 0, -1], color: "#3aa864", view: "back", neg: "front" },
    { name: "Z", v: [0, 1, 0], color: "#3d8ee6", view: "top", neg: "bottom" },
  ];
  const R = 34, C = 44;
  const pts = axes.flatMap((a) => {
    const p = rot(a.v);
    const n = rot([-a.v[0], -a.v[1], -a.v[2]] as [number, number, number]);
    return [
      { ...a, x: C + p[0] * R, y: C - p[1] * R, depth: p[2], pos: true },
      { ...a, x: C + n[0] * R, y: C - n[1] * R, depth: n[2], pos: false },
    ];
  }).sort((a, b) => a.depth - b.depth);
  return (
    <svg className="nav-gizmo" viewBox="0 0 88 88" width="88" height="88">
      <circle cx={C} cy={C} r={42} className="gizmo-bg" />
      {pts.filter((p) => p.pos).map((p) => <line key={p.name} x1={C} y1={C} x2={p.x} y2={p.y} stroke={p.color} strokeWidth="2" />)}
      {pts.map((p) => (
        <g key={p.name + (p.pos ? "+" : "-")} className="gizmo-axis" onClick={() => viewer?.setView(p.pos ? p.view : p.neg)}>
          <circle cx={p.x} cy={p.y} r={p.pos ? 9 : 7} fill={p.pos ? p.color : "var(--panel)"} stroke={p.color} strokeWidth="1.5" opacity={p.depth < -0.2 ? 0.55 : 1} />
          {p.pos && <text x={p.x} y={p.y + 3.5} textAnchor="middle" className="gizmo-lbl">{p.name}</text>}
        </g>
      ))}
    </svg>
  );
}
