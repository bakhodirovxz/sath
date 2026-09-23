import { useCallback, useMemo, useRef, useState } from "react";
import type { Sensor } from "../../api/client";
import { fmtValue } from "../../ui/format";
import { AlarmMarkSvg } from "../../ui/AlarmMark";
import { alarmStyle, qualityStyle } from "../../ui/tokens";
import { ageSeconds, fmtAge } from "./model";
import { moveElement, viewOf, type Scheme, type SchemeElement } from "./scheme";

/** Konfiguratsiyalanadigan mimika (F3) — ISA-101 / High Performance HMI uslubida (UX-01):
 *  - fon kulrang, jihozlar KONTUR; holat kulrang to'ldirish bilan (ishlayapti / yopiq — to'q, to'xtagan / ochiq —
 *    bo'sh); suv, shina, transformator — neytral, RANG FAQAT ALARM uchun (shakl + raqam + kod, AlarmMarkSvg);
 *  - normal holatda HECH QANDAY animatsiya yo'q (oqim chizig'i, aylanish olib tashlandi); faqat kvitlanmagan
 *    alarm belgisi miltillaydi, reduced-motion da — statik;
 *  - qiymat 18 px, yorliq 14 px (viewBox birligi; konteyner min-width bilan birlik ≥ 1 px), har qiymat yonida
 *    yoshi; eskirgan / aloqa yo'q — shtrix fon + "?" (UX-04). Bog'lanmagan element "ma'lumot yo'q". */

interface Props {
  scheme: Scheme;
  sensors: Sensor[];
  editing?: boolean;
  selected?: string | null;
  onSelect?: (id: string | null) => void;
  onChange?: (s: Scheme) => void;
  onOpen?: (sensorId: number) => void;
  now?: number | undefined;
  /** Kvitlanmagan alarmi bor sensorlar (belgi miltillaydi) */
  unacked?: ReadonlySet<number> | undefined;
  /** Jonli ulanish yo'q — barcha qiymatlar eskirgan deb ko'rsatiladi (UX-04) */
  offline?: boolean | undefined;
}

export default function Mimic({ scheme, sensors, editing = false, selected, onSelect, onChange, onOpen, now, unacked, offline = false }: Props) {
  const byId = useMemo(() => new Map(sensors.map((s) => [s.id, s])), [sensors]);
  const svgRef = useRef<SVGSVGElement>(null);
  const drag = useRef<{ id: string; dx: number; dy: number } | null>(null);
  const [pos, setPos] = useState<Scheme | null>(null);
  const cur = pos ?? scheme;
  const toSvg = useCallback((ev: React.PointerEvent) => {
    const svg = svgRef.current!;
    const pt = svg.createSVGPoint();
    pt.x = ev.clientX; pt.y = ev.clientY;
    const m = svg.getScreenCTM();
    if (!m) return { x: 0, y: 0 };
    const p = pt.matrixTransform(m.inverse());
    return { x: p.x, y: p.y };
  }, []);
  const onDown = (e: SchemeElement) => (ev: React.PointerEvent) => {
    if (!editing) return;
    const p = toSvg(ev);
    drag.current = { id: e.id, dx: p.x - e.x, dy: p.y - e.y };
    onSelect?.(e.id);
    (ev.target as Element).setPointerCapture?.(ev.pointerId);
  };
  const onMove = (ev: React.PointerEvent) => {
    if (!drag.current) return;
    const p = toSvg(ev);
    setPos(moveElement(cur, drag.current.id, p.x - drag.current.dx, p.y - drag.current.dy));
  };
  const onUp = () => {
    if (drag.current && pos) onChange?.(pos);
    drag.current = null;
    setPos(null);
  };
  const sensorOf = (e: SchemeElement, key?: string): Sensor | undefined => {
    const id = key ? e.extra?.[key] : e.sensor_id;
    return id ? byId.get(id) : undefined;
  };
  const vp = { now, onOpen, editing, unacked, offline };
  return (
    <svg ref={svgRef} className={`mimic ${editing ? "editing" : ""} ${offline ? "offline" : ""}`} viewBox={`0 0 ${viewOf(cur).w} ${viewOf(cur).h}`} role="group" aria-label="GES sxemasi (ISA-101)"
      onPointerMove={onMove} onPointerUp={onUp} onPointerLeave={onUp} data-units={cur.units}>
      <defs>
        <marker id="mimic-arr" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 Z" className="m-arrow" /></marker>
        {/* Bog'lanmagan / ma'lumot yo'q — kulrang shtrix; eskirgan qiymat — siyrakroq shtrix (rangsiz) */}
        <pattern id="nodata" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" className="m-hatch" /></pattern>
        <pattern id="stale-hatch" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="10" className="m-hatch light" /></pattern>
      </defs>
      {cur.elements.map((e) => {
        const sel = selected === e.id;
        const common = { onPointerDown: onDown(e), className: `mimic-el ${e.type} ${editing ? "draggable" : ""} ${sel ? "selected" : ""}`, "data-el": e.id, "data-type": e.type } as const;
        switch (e.type) {
          case "reservoir":
          case "tailwater": {
            const w = e.w ?? 200, h = e.h ?? 120;
            const surf = `M${e.x} ${e.y + 12} L${e.x + w} ${e.y + 12}`;
            return (
              <g key={e.id} {...common}>
                <rect x={e.x} y={e.y + 12} width={w} height={h - 12} className="m-liquid" />
                <path d={surf} className="m-surface" />
                <text x={e.x + 12} y={e.y + h - 12} className="mimic-cap">{e.label}</text>
              </g>
            );
          }
          case "dam":
            return (
              <g key={e.id} {...common}>
                <path d={`M${e.x} ${e.y} L${e.x + (e.w ?? 90) * 0.55} ${e.y} L${e.x + (e.w ?? 90)} ${e.y + (e.h ?? 210)} L${e.x} ${e.y + (e.h ?? 210)} Z`} className="m-concrete" />
                <text x={e.x + 4} y={e.y + (e.h ?? 210) + 20} className="mimic-cap">{e.label}</text>
              </g>
            );
          case "spillway":
            return (
              <g key={e.id} {...common}>
                <path d={`M${e.x + 5} ${e.y + 28} Q${e.x + (e.w ?? 110) / 2} ${e.y - 5} ${e.x + (e.w ?? 110)} ${e.y + 40}`} className="m-line dashed" markerEnd="url(#mimic-arr)" />
              </g>
            );
          case "penstock": {
            const w = e.w ?? 170, h = e.h ?? 50;
            const d = `M${e.x} ${e.y} L${e.x + w} ${e.y} L${e.x + w + 50} ${e.y + h}`;
            return (
              <g key={e.id} {...common}>
                <path d={d} className="m-pipe" />
                <path d={d} className="m-pipe-core" />
                <text x={e.x + 34} y={e.y + 30} className="mimic-cap">{e.label}</text>
              </g>
            );
          }
          case "line":
            if (e.id === "hall") {
              const anyAlarm = sensors.some((s) => s.enabled && alarmStyle(s.alarm, s.priority).rank > 0);
              return (
                <g key={e.id} {...common}>
                  <rect x={e.x} y={e.y} width={e.w ?? 250} height={e.h ?? 150} className={`m-hall ${anyAlarm ? "has-alarm" : ""}`} />
                  <text x={e.x + 10} y={e.y + (e.h ?? 150) - 10} className="mimic-cap">{e.label}</text>
                </g>
              );
            }
            return (
              <g key={e.id} {...common}>
                <path d={`M${e.x} ${e.y + 120} V${e.y} H${e.x + (e.w ?? 60)}`} className="m-line" />
                <text x={e.x + 8} y={e.y - 8} className="mimic-cap">{e.label}</text>
              </g>
            );
          case "bus":
            return (
              <g key={e.id} {...common}>
                <line x1={e.x} y1={e.y} x2={e.x + (e.w ?? 200)} y2={e.y} className="m-bus" />
                <text x={e.x + (e.w ?? 200)} y={e.y - 8} textAnchor="end" className="mimic-lbl">{e.label}</text>
              </g>
            );
          case "transformer": {
            const s = sensorOf(e);
            return (
              <g key={e.id} {...common}>
                <path d={`M${e.x} ${e.y - 50} V${e.y - 11}`} className="m-line" />
                <circle cx={e.x} cy={e.y} r={11} className="m-outline" />
                <circle cx={e.x + 12} cy={e.y} r={11} className="m-outline" />
                <text x={e.x - 32} y={e.y + 30} className="mimic-lbl">{e.label}</text>
                {s && <ValueBox x={e.x + 6} y={e.y + 70} w={180} s={s} label={s.name} {...vp} />}
              </g>
            );
          }
          case "unit": {
            const p = sensorOf(e);
            const run = sensorOf(e, "run");
            const on = run ? (run.last_value ?? 0) >= 0.5 : !!p && p.last_value != null && p.last_value > 0.05 && !p.stale;
            const known = !!p || !!run;
            return (
              <g key={e.id} {...common} data-testid="mimic-unit" data-state={!known ? "unknown" : on ? "running" : "stopped"}>
                {/* HP-HMI: ishlayapti — to'q kulrang to'ldirilgan, to'xtagan — bo'sh kontur; ma'lumot yo'q — shtrix */}
                <circle cx={e.x} cy={e.y} r={24} className={`m-unit ${!known ? "nodata" : on ? "on" : "off"}`} />
                <text x={e.x} y={e.y + 6} textAnchor="middle" className={`m-unit-glyph ${on ? "on" : ""}`}>G</text>
                <UnitValue x={e.x} y={e.y + 58} w={Math.max(60, e.w ?? 64)} s={p} label={e.label ?? ""} {...vp} />
              </g>
            );
          }
          case "breaker": {
            const s = sensorOf(e);
            const closed = s ? (s.last_value ?? 0) >= 0.5 : null;
            return (
              <g key={e.id} {...common} data-testid="mimic-breaker" data-state={closed == null ? "unknown" : closed ? "closed" : "open"}>
                <line x1={e.x} y1={e.y - 25} x2={e.x} y2={e.y - 11} className="m-line" />
                <line x1={e.x} y1={e.y + 11} x2={e.x} y2={e.y + 30} className="m-line" />
                <rect x={e.x - 9} y={e.y - 11} width={18} height={22} className={`m-switch ${closed == null ? "nodata" : closed ? "on" : "off"}`} />
                {closed === false && <line x1={e.x - 6} y1={e.y + 8} x2={e.x + 6} y2={e.y - 8} className="m-line strong" />}
                <text x={e.x + 13} y={e.y + 5} className="mimic-lbl">{e.label}{closed == null ? " ?" : closed ? "" : " OCHIQ"}</text>
              </g>
            );
          }
          case "gate": {
            const s = sensorOf(e);
            const h = e.h ?? 60, w = e.w ?? 40;
            const open = s?.last_value != null ? Math.max(0, Math.min(100, s.last_value)) : null;
            const gateH = open == null ? h : (h * (100 - open)) / 100;
            return (
              <g key={e.id} {...common} data-testid="mimic-gate">
                <rect x={e.x} y={e.y} width={w} height={h} className="m-outline dashed" />
                <rect x={e.x} y={e.y} width={w} height={gateH} className={`m-gate ${open == null ? "nodata" : ""}`} />
                <text x={e.x + w / 2} y={e.y + h + 18} textAnchor="middle" className="mimic-lbl">{e.label} {open == null ? "?" : `${Math.round(open)} %`}</text>
              </g>
            );
          }
          case "valve": {
            const s = sensorOf(e);
            const open = s ? (s.last_value ?? 0) >= 0.5 : null;
            return (
              <g key={e.id} {...common} data-testid="mimic-valve" data-state={open == null ? "unknown" : open ? "open" : "closed"}>
                <path d={`M${e.x - 11} ${e.y - 9} L${e.x + 11} ${e.y + 9} L${e.x + 11} ${e.y - 9} L${e.x - 11} ${e.y + 9} Z`} className={`m-switch ${open == null ? "nodata" : open ? "on" : "off"}`} />
                <text x={e.x} y={e.y - 15} textAnchor="middle" className="mimic-lbl">{e.label}{open == null ? " ?" : open ? "" : " YOPIQ"}</text>
              </g>
            );
          }
          case "value": {
            const s = sensorOf(e);
            return (
              <g key={e.id} {...common}>
                <ValueBox x={e.x} y={e.y} w={Math.max(e.w ?? 180, 140)} s={s} label={e.label ?? e.id} {...vp} />
              </g>
            );
          }
          default:
            return null;
        }
      })}
      {editing && (() => { const hall = cur.elements.find((e) => e.id === "hall"); return hall ? <text x={hall.x + (hall.w ?? 250) - 6} y={hall.y + (hall.h ?? 150) - 8} textAnchor="end" className="mimic-lbl">{cur.units} agregat</text> : null; })()}
    </svg>
  );
}

interface ValueProps {
  x: number; y: number; w: number; s?: Sensor | undefined; label: string;
  now?: number | undefined; onOpen?: ((id: number) => void) | undefined; editing: boolean; unacked?: ReadonlySet<number> | undefined; offline: boolean;
}

function valueState(s: Sensor | undefined, now: number | undefined, offline: boolean) {
  const st = s ? alarmStyle(s.alarm, s.priority) : null;
  const q = s ? qualityStyle(s.last_quality) : null;
  const age = s ? ageSeconds(s.last_ts, now) : null;
  const stale = !!s && (offline || !!s.stale || (age != null && age > s.stale_after_s));
  return { st, q, age, stale };
}

/** Qiymat katakchasi: ustida yorliq (14, chapda) va alarm belgisi + kodi (o'ngda); katak ichida qiymat + birlik +
 * sifat kodi (18, chapda) va yoshi (14, o'ngda). Bosiladigan (faceplate) — klaviatura bilan ham (Enter/Space). */
function ValueBox({ x, y, w, s, label, now, onOpen, editing, unacked, offline }: ValueProps) {
  const { st, q, age, stale } = valueState(s, now, offline);
  const h = 32;
  const left = x - w / 2, right = x + w / 2, top = y - h / 2;
  const clickable = !!s && !!onOpen && !editing;
  const open = () => { if (s && clickable) onOpen?.(s.id); };
  const text = s ? `${s.last_value == null ? "—" : fmtValue(s.last_value)}${s.unit ? ` ${s.unit}` : ""}${q?.code ? ` ${q.code}` : ""}${stale ? " ?" : ""}` : "ma'lumot yo'q";
  const alarm = !!st && st.rank > 0;
  return (
    <g className={`mimic-slot ${clickable ? "clickable" : ""} ${stale ? "stale" : ""} ${alarm ? "in-alarm" : ""}`} data-testid="mimic-value" data-bound={s ? "1" : "0"} data-stale={stale ? "1" : "0"}
      {...(clickable ? { role: "button", tabIndex: 0, "aria-label": `${label || s!.name}: ${text}${stale ? ", eskirgan" : ""}${alarm ? `, ${st!.label}` : ""} — faceplate`, onClick: open, onKeyDown: (ev: React.KeyboardEvent) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); open(); } } } : {})}>
      <text x={left} y={top - 7} className="mimic-lbl">{s ? (label || s.name) : label}</text>
      {alarm && <AlarmMarkSvg x={right - 9} y={top - 12} state={s!.alarm} priority={s!.priority} unacked={!!unacked?.has(s!.id)} size={18} />}
      {alarm && st!.code && <text x={right - 22} y={top - 7} textAnchor="end" className="mimic-code">{st!.code}</text>}
      <rect x={left} y={top} width={w} height={h} className={`m-box ${s ? "" : "unbound"}`} />
      {(stale || !s) && <rect x={left + 1} y={top + 1} width={w - 2} height={h - 2} fill={s ? "url(#stale-hatch)" : "url(#nodata)"} className="m-box-hatch" />}
      <text x={left + 8} y={y + 6.5} className={`mimic-val ${stale ? "stale" : ""} ${s ? "" : "none"}`}>{text}</text>
      {s && age != null && <text x={right - 6} y={y + 5} textAnchor="end" className="mimic-age">{fmtAge(age)}</text>}
    </g>
  );
}

/** Agregat ostidagi qiymat: tor joy — yorliq + birlik ustida (14), qiymat katakda (18), ostida alarm kodi + yoshi (14);
 * alarm shakli katak burchagida. */
function UnitValue({ x, y, w, s, label, now, onOpen, editing, unacked, offline }: ValueProps) {
  const { st, age, stale } = valueState(s, now, offline);
  const h = 30;
  const clickable = !!s && !!onOpen && !editing;
  const open = () => { if (s && clickable) onOpen?.(s.id); };
  const text = s ? (s.last_value == null ? "—" : fmtValue(s.last_value)) : "yo'q";
  const alarm = !!st && st.rank > 0;
  const sub = [alarm ? st!.code : "", s && age != null ? fmtAge(age) : ""].filter(Boolean);
  return (
    <g className={`mimic-slot unit-slot ${clickable ? "clickable" : ""} ${stale ? "stale" : ""} ${alarm ? "in-alarm" : ""}`} data-testid="mimic-value" data-bound={s ? "1" : "0"} data-stale={stale ? "1" : "0"}
      {...(clickable ? { role: "button", tabIndex: 0, "aria-label": `${label}: ${text} ${s?.unit ?? ""}${stale ? ", eskirgan" : ""}${alarm ? `, ${st!.label}` : ""} — faceplate`, onClick: open, onKeyDown: (ev: React.KeyboardEvent) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); open(); } } } : {})}>
      <text x={x} y={y - h / 2 - 7} textAnchor="middle" className="mimic-lbl">{label}{s?.unit ? ` · ${s.unit}` : ""}</text>
      <rect x={x - w / 2} y={y - h / 2} width={w} height={h} className={`m-box ${s ? "" : "unbound"}`} />
      {(stale || !s) && <rect x={x - w / 2 + 1} y={y - h / 2 + 1} width={w - 2} height={h - 2} fill={s ? "url(#stale-hatch)" : "url(#nodata)"} className="m-box-hatch" />}
      <text x={x} y={y + 6.5} textAnchor="middle" className={`mimic-val ${stale ? "stale" : ""} ${s ? "" : "none"}`}>{text}</text>
      {alarm && <AlarmMarkSvg x={x + w / 2 - 1} y={y - h / 2 - 1} state={s!.alarm} priority={s!.priority} unacked={!!unacked?.has(s!.id)} size={18} />}
      {sub.length > 0 && <text x={x} y={y + h / 2 + 17} textAnchor="middle">{alarm && <tspan className="mimic-code">{st!.code}</tspan>}{alarm && sub.length > 1 ? " " : ""}{s && age != null && <tspan className="mimic-age">{fmtAge(age)}</tspan>}</text>}
    </g>
  );
}
