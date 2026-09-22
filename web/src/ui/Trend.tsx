import { useEffect, useMemo, useRef, useState } from "react";
import { fmtNum, fmtTick, groupByUnit, nearestIndex, niceTicks, normalize, panDomain, segments, yDomain, zoomDomain, clampPoints, type TrendSeries } from "./trendMath";

/** Trend server (F7): ko'p o'qli (har birlik uchun alohida o'q) yoki normallashtirilgan rejim; zoom (g'ildirak),
 * pan (surish), kursor bilan qiymat o'qish, ikki kursor (Shift+bosish) orasidagi farq; sifat/bo'shliq uzilish
 * sifatida chiziladi; ResizeObserver; uzunlik qo'riqchisi; ranglar tokenlardan. */

export const PEN_COLORS = ["var(--pen-1)", "var(--pen-2)", "var(--pen-3)", "var(--pen-4)", "var(--pen-5)", "var(--pen-6)"];
const PAD = { l: 8, r: 8, t: 10, b: 24 };
const AXIS_W = 46;

interface Props {
  series: TrendSeries[];
  height?: number;
  mode?: "multi" | "normalized";
  /** Tashqi vaqt oynasi (ms); bo'lmasa ma'lumot bo'yicha */
  domain?: [number, number];
  onDomain?: (d: [number, number]) => void;
  refLines?: { value: number; label: string; unit?: string }[];
}

export default function Trend({ series: raw, height = 260, mode = "multi", domain: extDomain, onDomain, refLines = [] }: Props) {
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(800);
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver((es) => { const w = es[0]?.contentRect.width; if (w) setWidth(Math.max(240, Math.floor(w))); });
    ro.observe(el);
    setWidth(Math.max(240, Math.floor(el.getBoundingClientRect().width || 800)));
    return () => ro.disconnect();
  }, []);
  const series = useMemo(() => raw.map((s, i) => ({ ...s, color: s.color ?? PEN_COLORS[i % PEN_COLORS.length], points: clampPoints(s.points) })), [raw]);
  const bounds = useMemo<[number, number]>(() => {
    let lo = Infinity, hi = -Infinity;
    for (const s of series) if (s.points.length) { lo = Math.min(lo, s.points[0].t); hi = Math.max(hi, s.points[s.points.length - 1].t); }
    return Number.isFinite(lo) && hi > lo ? [lo, hi] : [Date.now() - 3600_000, Date.now()];
  }, [series]);
  const [localDomain, setLocalDomain] = useState<[number, number] | null>(null);
  const domain = extDomain ?? localDomain ?? bounds;
  const setDomain = (d: [number, number]) => { setLocalDomain(d); onDomain?.(d); };
  const [b0, b1] = bounds;
  useEffect(() => { setLocalDomain(null); }, [b0, b1]);
  const shown = mode === "normalized" ? normalize(series, domain[0], domain[1]) : series;
  const units = useMemo(() => [...groupByUnit(shown).entries()], [shown]);
  const nAxes = Math.max(1, units.length);
  const leftAxes = 1, rightAxes = nAxes - 1;
  const plotX = PAD.l + AXIS_W * leftAxes;
  const plotW = Math.max(60, width - plotX - PAD.r - AXIS_W * rightAxes);
  const plotH = height - PAD.t - PAD.b;
  const x = (t: number) => plotX + ((t - domain[0]) / (domain[1] - domain[0] || 1)) * plotW;
  const yScales = useMemo(() => units.map(([, ss]) => { const [lo, hi] = yDomain(ss, domain[0], domain[1]); return { lo, hi, y: (v: number) => PAD.t + plotH - ((v - lo) / (hi - lo || 1)) * plotH }; }), [units, domain, plotH]);
  const [cursorA, setCursorA] = useState<number | null>(null);
  const [cursorB, setCursorB] = useState<number | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const drag = useRef<{ x: number; d: [number, number]; moved: boolean } | null>(null);
  const tAt = (clientX: number) => { const r = wrap.current!.getBoundingClientRect(); return domain[0] + ((clientX - r.left - plotX) / plotW) * (domain[1] - domain[0]); };
  const onWheel = (e: React.WheelEvent) => { e.preventDefault(); setDomain(zoomDomain(domain, tAt(e.clientX), e.deltaY > 0 ? 1.25 : 0.8, bounds)); };
  const onDown = (e: React.PointerEvent) => { drag.current = { x: e.clientX, d: domain, moved: false }; (e.target as Element).setPointerCapture?.(e.pointerId); };
  const onMove = (e: React.PointerEvent) => {
    setHover(tAt(e.clientX));
    if (!drag.current) return;
    const dx = e.clientX - drag.current.x;
    if (Math.abs(dx) > 3) drag.current.moved = true;
    if (drag.current.moved) setDomain(panDomain(drag.current.d, -(dx / plotW) * (drag.current.d[1] - drag.current.d[0]), bounds));
  };
  const onUp = (e: React.PointerEvent) => {
    if (drag.current && !drag.current.moved) { const t = tAt(e.clientX); if (e.shiftKey) setCursorB(t); else { setCursorA(t); if (!e.ctrlKey) setCursorB(null); } }
    drag.current = null;
  };
  const readAt = (t: number | null) => (t == null ? null : series.map((s) => { const k = nearestIndex(s.points, t); return { s, p: k >= 0 ? s.points[k] : null }; }));
  const rA = readAt(cursorA), rB = readAt(cursorB), rH = readAt(hover);
  const xTicks = niceTicks(domain[0], domain[1], Math.max(3, Math.floor(plotW / 110)));
  return (
    <div ref={wrap} className="trend" data-testid="trend" data-mode={mode}>
      <svg width={width} height={height} onWheel={onWheel} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerLeave={() => { setHover(null); drag.current = null; }} style={{ cursor: "crosshair", touchAction: "none" }}>
        <rect x={plotX} y={PAD.t} width={plotW} height={plotH} fill="var(--field)" stroke="var(--line)" />
        {xTicks.map((t) => <g key={t}><line x1={x(t)} x2={x(t)} y1={PAD.t} y2={PAD.t + plotH} stroke="var(--line)" /><text x={x(t)} y={height - 8} textAnchor="middle" className="trend-tick">{fmtTick(t, domain[1] - domain[0])}</text></g>)}
        {units.map(([unit, ss], ui) => {
          const sc = yScales[ui];
          const ax = ui === 0 ? plotX : plotX + plotW + AXIS_W * (ui - 1);
          const anchor = ui === 0 ? "end" : "start";
          const tx = ui === 0 ? ax - 4 : ax + 4;
          return (
            <g key={unit} className="trend-axis" data-testid="trend-axis" data-unit={unit}>
              <line x1={ax} x2={ax} y1={PAD.t} y2={PAD.t + plotH} stroke={ss[0].color} strokeWidth={1.5} />
              {niceTicks(sc.lo, sc.hi, 5).map((v) => <text key={v} x={tx} y={sc.y(v) + 4} textAnchor={anchor} className="trend-tick" fill={ss[0].color}>{fmtNum(v)}</text>)}
              <text x={tx} y={PAD.t - 2} textAnchor={anchor} className="trend-tick" fill={ss[0].color}>{unit || "—"}</text>
            </g>
          );
        })}
        {refLines.map((r) => { const ui = Math.max(0, units.findIndex(([u]) => u === (r.unit ?? units[0]?.[0]))); const sc = yScales[ui]; if (!sc || r.value < sc.lo || r.value > sc.hi) return null; return <g key={r.label}><line x1={plotX} x2={plotX + plotW} y1={sc.y(r.value)} y2={sc.y(r.value)} stroke="var(--warn)" strokeDasharray="4 3" /><text x={plotX + plotW - 3} y={sc.y(r.value) - 2} textAnchor="end" className="trend-tick" fill="var(--warn)">{r.label}</text></g>; })}
        <clipPath id="trend-clip"><rect x={plotX} y={PAD.t} width={plotW} height={plotH} /></clipPath>
        <g clipPath="url(#trend-clip)">
          {units.map(([, ss], ui) => ss.map((s) => segments(s.points.filter((p) => p.t >= domain[0] - 1 && p.t <= domain[1] + 1)).map((seg, k) => (
            <path key={`${s.id}-${k}`} d={seg.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)} ${yScales[ui].y(p.v as number).toFixed(1)}`).join(" ")} fill="none" stroke={s.color} strokeWidth={1.4} data-testid="trend-path" />
          ))))}
        </g>
        {hover != null && <line x1={x(hover)} x2={x(hover)} y1={PAD.t} y2={PAD.t + plotH} stroke="var(--text-dim)" strokeDasharray="2 2" />}
        {cursorA != null && <line x1={x(cursorA)} x2={x(cursorA)} y1={PAD.t} y2={PAD.t + plotH} stroke="var(--accent-2)" strokeWidth={1.5} />}
        {cursorB != null && <line x1={x(cursorB)} x2={x(cursorB)} y1={PAD.t} y2={PAD.t + plotH} stroke="var(--warn)" strokeWidth={1.5} />}
      </svg>
      <div className="trend-legend row wrap" style={{ gap: 10 }}>
        {raw.map((s, i) => { const h = rH?.[i]?.p; return <span key={s.id} className="row" style={{ gap: 4 }}><i style={{ background: series[i].color, width: 10, height: 3, display: "inline-block" }} /> {s.name} <span className="mono dim">{h && h.v != null ? `${fmtNum(h.v)} ${s.unit}` : s.points.length ? "" : "ma'lumot yo'q"}</span></span>; })}
        <span className="grow" />
        <span className="dim small">g'ildirak — zoom · surish — pan · bosish — kursor A · Shift+bosish — kursor B{cursorA || cursorB ? " · " : ""}{(cursorA || cursorB) && <button className="btn sm" onClick={() => { setCursorA(null); setCursorB(null); }}>kursorlarni tozalash</button>}</span>
      </div>
      {(rA || rB) && (
        <table className="grid small mono trend-readout" data-testid="trend-readout">
          <thead><tr><th>Seriya</th>{cursorA != null && <th>A: {fmtTick(cursorA, 0)}</th>}{cursorB != null && <th>B: {fmtTick(cursorB, 0)}</th>}{cursorA != null && cursorB != null && <th>Δ (B − A)</th>}</tr></thead>
          <tbody>
            {raw.map((s, i) => { const a = rA?.[i]?.p, b = rB?.[i]?.p; return <tr key={s.id}><td>{s.name}</td>{cursorA != null && <td>{a && a.v != null ? `${fmtNum(a.v)} ${s.unit}` : "—"}</td>}{cursorB != null && <td>{b && b.v != null ? `${fmtNum(b.v)} ${s.unit}` : "—"}</td>}{cursorA != null && cursorB != null && <td>{a && b && a.v != null && b.v != null ? `${fmtNum(b.v - a.v)} ${s.unit} / ${fmtNum((cursorB - cursorA) / 60000)} daq` : "—"}</td>}</tr>; })}
          </tbody>
        </table>
      )}
    </div>
  );
}
