import { useCallback, useMemo, useRef, useState } from "react";
import type { Sensor } from "../../api/client";
import { fmtValue } from "../../ui/format";
import { alarmStyle, qualityStyle } from "../../ui/tokens";
import { ageSeconds } from "./model";
import { VIEW, moveElement, type Scheme, type SchemeElement } from "./scheme";

/** Konfiguratsiyalanadigan mimika (F3): sxema JSON dan chiziladi (agregatlar soni ixtiyoriy), elementlar
 * surish bilan tahrirlanadi, sensor bog'lanadi. Bog'lanmagan element "ma'lumot yo'q" holatida ko'rinadi.
 * Ranglar faqat tokenlardan; alarm — shakl + kod (F1). */

interface Props {
  scheme: Scheme;
  sensors: Sensor[];
  editing?: boolean;
  selected?: string | null;
  onSelect?: (id: string | null) => void;
  onChange?: (s: Scheme) => void;
  onOpen?: (sensorId: number) => void;
  now?: number | undefined;
}

export default function Mimic({ scheme, sensors, editing = false, selected, onSelect, onChange, onOpen, now }: Props) {
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
  const anyAlarm = sensors.some((s) => s.enabled && alarmStyle(s.alarm, s.priority).rank > 0);
  const hall = cur.elements.find((e) => e.id === "hall");
  return (
    <svg ref={svgRef} className={`mimic ${editing ? "editing" : ""}`} viewBox={`0 0 ${VIEW.w} ${VIEW.h}`} role="img" aria-label="GES sxemasi" onPointerMove={onMove} onPointerUp={onUp} onPointerLeave={onUp} data-units={cur.units}>
      <defs>
        <marker id="arr" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 Z" fill="var(--accent-2)" /></marker>
        <pattern id="nodata" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="var(--mimic-unbound)" strokeWidth="2" /></pattern>
      </defs>
      {cur.elements.map((e) => {
        const sel = selected === e.id;
        const common = { onPointerDown: onDown(e), className: `mimic-el ${e.type} ${editing ? "draggable" : ""} ${sel ? "selected" : ""}`, "data-el": e.id, "data-type": e.type } as const;
        switch (e.type) {
          case "reservoir":
          case "tailwater": {
            const w = e.w ?? 200, h = e.h ?? 120;
            return (
              <g key={e.id} {...common}>
                <path d={`M${e.x} ${e.y + 10} Q${e.x + w * 0.25} ${e.y - 2} ${e.x + w * 0.5} ${e.y + 10} T${e.x + w} ${e.y + 10} L${e.x + w} ${e.y + h} L${e.x} ${e.y + h} Z`} fill="var(--mimic-water)" opacity="0.9" />
                <path d={`M${e.x} ${e.y + 10} Q${e.x + w * 0.25} ${e.y - 2} ${e.x + w * 0.5} ${e.y + 10} T${e.x + w} ${e.y + 10}`} fill="none" stroke="var(--accent-2)" strokeWidth="2" />
                <text x={e.x + 12} y={e.y + h - 10} className="mimic-cap">{e.label}</text>
              </g>
            );
          }
          case "dam":
            return (
              <g key={e.id} {...common}>
                <path d={`M${e.x} ${e.y} L${e.x + (e.w ?? 90) * 0.55} ${e.y} L${e.x + (e.w ?? 90)} ${e.y + (e.h ?? 210)} L${e.x} ${e.y + (e.h ?? 210)} Z`} fill="var(--mimic-concrete)" stroke="var(--mimic-outline)" strokeWidth="1.5" />
                <text x={e.x + 4} y={e.y + (e.h ?? 210) + 16} className="mimic-cap">{e.label}</text>
              </g>
            );
          case "spillway":
            return (
              <g key={e.id} {...common}>
                <path d={`M${e.x + 5} ${e.y + 28} Q${e.x + (e.w ?? 110) / 2} ${e.y - 5} ${e.x + (e.w ?? 110)} ${e.y + 40}`} fill="none" stroke="var(--accent-2)" strokeWidth="2" strokeDasharray="5 4" markerEnd="url(#arr)" />
              </g>
            );
          case "penstock": {
            const w = e.w ?? 170, h = e.h ?? 50;
            const d = `M${e.x} ${e.y} L${e.x + w} ${e.y} L${e.x + w + 50} ${e.y + h}`;
            return (
              <g key={e.id} {...common}>
                <path d={d} fill="none" stroke="var(--mimic-pipe)" strokeWidth="10" strokeLinejoin="round" />
                <path d={d} fill="none" stroke="var(--accent-2)" strokeWidth="4" strokeLinejoin="round" strokeDasharray="14 10" className="mimic-flow" />
                <text x={e.x + 40} y={e.y + 22} className="mimic-cap">{e.label}</text>
              </g>
            );
          }
          case "line":
            if (e.id === "hall") {
              return (
                <g key={e.id} {...common}>
                  <rect x={e.x} y={e.y} width={e.w ?? 250} height={e.h ?? 150} fill="var(--mimic-hall)" stroke={anyAlarm ? "var(--danger)" : "var(--mimic-outline)"} strokeWidth="1.5" />
                  <text x={e.x + 10} y={e.y + 16} className="mimic-cap">{e.label}</text>
                </g>
              );
            }
            return (
              <g key={e.id} {...common}>
                <path d={`M${e.x} ${e.y + 120} V${e.y} H${e.x + (e.w ?? 60)}`} fill="none" stroke="var(--warn)" strokeWidth="2" />
                <text x={e.x + 8} y={e.y - 8} className="mimic-cap">{e.label}</text>
              </g>
            );
          case "bus":
            return (
              <g key={e.id} {...common}>
                <line x1={e.x} y1={e.y} x2={e.x + (e.w ?? 200)} y2={e.y} stroke="var(--warn)" strokeWidth="4" />
                <text x={e.x} y={e.y - 6} className="mimic-cap">{e.label}</text>
              </g>
            );
          case "transformer": {
            const s = sensorOf(e);
            return (
              <g key={e.id} {...common}>
                <path d={`M${e.x} ${e.y - 50} V${e.y - 9}`} stroke="var(--warn)" strokeWidth="2" />
                <circle cx={e.x} cy={e.y} r={9} fill="none" stroke="var(--warn)" strokeWidth="2" />
                <circle cx={e.x + 10} cy={e.y} r={9} fill="none" stroke="var(--warn)" strokeWidth="2" />
                <text x={e.x - 30} y={e.y + 26} className="mimic-cap">{e.label}</text>
                {s && <ValueBox x={e.x + 5} y={e.y + 48} w={90} s={s} label={s.unit} now={now} onOpen={onOpen} editing={editing} />}
              </g>
            );
          }
          case "unit": {
            const p = sensorOf(e);
            const run = sensorOf(e, "run");
            const st = p ? alarmStyle(p.alarm, p.priority) : null;
            const on = run ? (run.last_value ?? 0) >= 0.5 : !!p && p.last_value != null && p.last_value > 0.05 && !p.stale;
            return (
              <g key={e.id} {...common} data-testid="mimic-unit">
                <circle cx={e.x} cy={e.y} r={24} fill={p ? (on ? "var(--mimic-unit-on)" : "var(--mimic-unit-off)") : "url(#nodata)"} stroke={st ? st.color : "var(--mimic-unbound)"} strokeWidth="2" strokeDasharray={p ? undefined : "3 3"} />
                <path d={`M${e.x - 12} ${e.y} h24 M${e.x} ${e.y - 12} v24 M${e.x - 8} ${e.y - 8} l16 16 M${e.x + 8} ${e.y - 8} l-16 16`} stroke={on ? "var(--ok)" : "var(--mimic-idle)"} strokeWidth="2" className={on ? "mimic-spin" : undefined} style={{ transformOrigin: `${e.x}px ${e.y}px` }} />
                {st && st.code && <text x={e.x + 26} y={e.y - 18} className="mimic-code" fill={st.color}>{st.glyph}{st.code}</text>}
                <ValueBox x={e.x} y={e.y + 50} w={e.w ?? 64} s={p} label={e.label ?? ""} now={now} onOpen={onOpen} editing={editing} />
              </g>
            );
          }
          case "breaker": {
            const s = sensorOf(e);
            const closed = s ? (s.last_value ?? 0) >= 0.5 : null;
            return (
              <g key={e.id} {...common} data-testid="mimic-breaker" data-state={closed == null ? "unknown" : closed ? "closed" : "open"}>
                <line x1={e.x} y1={e.y - 25} x2={e.x} y2={e.y - 10} stroke="var(--warn)" strokeWidth="2" />
                <line x1={e.x} y1={e.y + 10} x2={e.x} y2={e.y + 30} stroke="var(--warn)" strokeWidth="2" />
                <rect x={e.x - 8} y={e.y - 10} width={16} height={20} fill={closed == null ? "url(#nodata)" : closed ? "var(--ok)" : "var(--mimic-unit-off)"} stroke={closed == null ? "var(--mimic-unbound)" : "var(--mimic-outline)"} strokeWidth="1.5" strokeDasharray={closed == null ? "3 3" : undefined} />
                {closed === false && <line x1={e.x - 6} y1={e.y + 8} x2={e.x + 6} y2={e.y - 8} stroke="var(--text)" strokeWidth="2" />}
                <text x={e.x + 11} y={e.y + 4} className="mimic-lbl">{e.label}{closed == null ? " ?" : closed ? "" : " OCHIQ"}</text>
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
                <rect x={e.x} y={e.y} width={w} height={h} fill="none" stroke="var(--mimic-outline)" strokeWidth="1" strokeDasharray="2 2" />
                <rect x={e.x} y={e.y} width={w} height={gateH} fill={open == null ? "url(#nodata)" : "var(--mimic-concrete)"} stroke="var(--mimic-outline)" strokeWidth="1.5" />
                <text x={e.x + w / 2} y={e.y + h + 12} textAnchor="middle" className="mimic-lbl">{e.label} {open == null ? "?" : `${Math.round(open)} %`}</text>
              </g>
            );
          }
          case "valve": {
            const s = sensorOf(e);
            const open = s ? (s.last_value ?? 0) >= 0.5 : null;
            return (
              <g key={e.id} {...common} data-testid="mimic-valve">
                <path d={`M${e.x - 10} ${e.y - 8} L${e.x + 10} ${e.y + 8} L${e.x + 10} ${e.y - 8} L${e.x - 10} ${e.y + 8} Z`} fill={open == null ? "url(#nodata)" : open ? "var(--ok)" : "var(--mimic-unit-off)"} stroke="var(--mimic-outline)" strokeWidth="1.5" />
                <text x={e.x} y={e.y - 12} textAnchor="middle" className="mimic-lbl">{e.label}{open == null ? " ?" : open ? "" : " YOPIQ"}</text>
              </g>
            );
          }
          case "value": {
            const s = sensorOf(e);
            return (
              <g key={e.id} {...common}>
                <ValueBox x={e.x} y={e.y} w={e.w ?? 96} s={s} label={e.label ?? e.id} now={now} onOpen={onOpen} editing={editing} />
              </g>
            );
          }
          default:
            return null;
        }
      })}
      {editing && hall && <text x={hall.x + (hall.w ?? 250) - 4} y={hall.y + (hall.h ?? 150) - 6} textAnchor="end" className="mimic-lbl">{cur.units} agregat</text>}
    </svg>
  );
}

/** Qiymat katakchasi: qiymat + birlik, alarm kodi, sifat kodi; bog'lanmagan — shtrix "ma'lumot yo'q"; eskirgan — `?`. */
function ValueBox({ x, y, w, s, label, now, onOpen, editing }: { x: number; y: number; w: number; s?: Sensor | undefined; label: string; now?: number | undefined; onOpen?: ((id: number) => void) | undefined; editing: boolean }) {
  const st = s ? alarmStyle(s.alarm, s.priority) : null;
  const q = s ? qualityStyle(s.last_quality) : null;
  const age = s ? ageSeconds(s.last_ts, now) : null;
  const stale = !!s && (!!s.stale || (age != null && age > s.stale_after_s));
  return (
    <g className={`mimic-slot ${s && onOpen && !editing ? "clickable" : ""}`} onClick={() => s && !editing && onOpen?.(s.id)} data-testid="mimic-value" data-bound={s ? "1" : "0"}>
      <rect x={x - w / 2} y={y - 16} width={w} height={32} rx="2" fill="var(--panel)" stroke={st ? st.color : "var(--mimic-unbound)"} strokeWidth={st && st.rank ? 2 : 1} strokeDasharray={s ? undefined : "3 3"} />
      {!s && <rect x={x - w / 2 + 2} y={y - 14} width={8} height={28} fill="url(#nodata)" />}
      <text x={x} y={y - 4} textAnchor="middle" className="mimic-lbl">{s ? (label || s.name) : label}</text>
      <text x={x} y={y + 11} textAnchor="middle" className="mimic-val" fill={stale ? "var(--alarm-stale)" : "var(--text)"}>
        {s ? `${s.last_value == null ? "—" : fmtValue(s.last_value)} ${s.unit}${stale ? " ?" : ""}${q?.code ? ` ${q.code}` : ""}` : w < 90 ? "yo'q" : "ma'lumot yo'q"}
      </text>
      {st && st.code && <text x={x + w / 2 - 3} y={y - 6} textAnchor="end" className="mimic-code" fill={st.color}>{st.glyph}{st.code}</text>}
    </g>
  );
}
