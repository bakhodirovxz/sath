import { useMemo, useState } from "react";

/** Grafik palitrasi — qora fonda tekshirilgan (CVD ajralish, kontrast). Tartib qat'iy. */
export const CHART_COLORS = ["#3d8ee6", "#b98626", "#3aa864", "#b46dcc", "#e0656a"];

export interface Series {
  name: string;
  values: number[];
  color?: string;
  dashed?: boolean;
}

interface Props {
  title: string;
  unit: string;
  x: (string | number)[];
  series: Series[];
  height?: number;
  /** Tashqaridan boshqariladigan kursor (vaqt slayderi) */
  cursor?: number | null;
  onCursor?: (i: number | null) => void;
  /** Y o'qida ko'rsatiladigan chegara chiziqlari (masalan NPU, o'lik sath) */
  refLines?: { value: number; label: string }[];
}

const PAD = { l: 44, r: 12, t: 8, b: 22 };

/** Bitta o'qli chiziqli grafik (SVG): ingichka chiziqlar, xira to'r, kursor + tooltip, ≥2 qator uchun legenda. */
export default function LineChart({ title, unit, x, series, height = 150, cursor, onCursor, refLines = [] }: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const [w, setW] = useState(600);
  const n = x.length;
  const idx = cursor ?? hover;

  const { min, max } = useMemo(() => {
    const all = series.flatMap((s) => s.values).concat(refLines.map((r) => r.value)).filter((v) => Number.isFinite(v));
    let lo = Math.min(...all), hi = Math.max(...all);
    if (!Number.isFinite(lo)) { lo = 0; hi = 1; }
    if (hi - lo < 1e-9) { hi = lo + 1; lo = lo - 1; }
    const pad = (hi - lo) * 0.08;
    return { min: lo - pad, max: hi + pad };
  }, [series, refLines]);

  const iw = w - PAD.l - PAD.r;
  const ih = height - PAD.t - PAD.b;
  const sx = (i: number) => PAD.l + (n > 1 ? (i / (n - 1)) * iw : iw / 2);
  const sy = (v: number) => PAD.t + ih - ((v - min) / (max - min)) * ih;
  const ticks = niceTicks(min, max, 4);
  const xTicks = [0, Math.floor((n - 1) / 2), n - 1].filter((v, i, a) => n > 0 && a.indexOf(v) === i);
  const fmt = (v: number) => (Math.abs(v) >= 1000 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2));

  function onMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * w;
    const i = Math.round(((px - PAD.l) / iw) * (n - 1));
    const c = Math.max(0, Math.min(n - 1, i));
    setHover(c);
    onCursor?.(c);
  }

  return (
    <div className="chart" ref={(el) => el && el.clientWidth && el.clientWidth !== w && setW(el.clientWidth)}>
      <div className="chart-head">
        <span className="chart-title">{title}</span>
        <span className="dim small">{unit}</span>
        {series.length > 1 && (
          <span className="chart-legend">
            {series.map((s, i) => (
              <span key={s.name}><i style={{ background: s.color ?? CHART_COLORS[i % CHART_COLORS.length] }} />{s.name}</span>
            ))}
          </span>
        )}
      </div>
      <svg viewBox={`0 0 ${w} ${height}`} width="100%" height={height} onMouseMove={onMove} onMouseLeave={() => { setHover(null); onCursor?.(null); }} role="img" aria-label={title}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.l} x2={w - PAD.r} y1={sy(t)} y2={sy(t)} className="chart-grid" />
            <text x={PAD.l - 6} y={sy(t) + 3} className="chart-tick" textAnchor="end">{fmt(t)}</text>
          </g>
        ))}
        {xTicks.map((i) => (
          <text key={i} x={sx(i)} y={height - 6} className="chart-tick" textAnchor={i === 0 ? "start" : i === n - 1 ? "end" : "middle"}>{String(x[i]).slice(0, 10)}</text>
        ))}
        {refLines.map((r) => (
          <g key={r.label}>
            <line x1={PAD.l} x2={w - PAD.r} y1={sy(r.value)} y2={sy(r.value)} className="chart-ref" />
            <text x={w - PAD.r} y={sy(r.value) - 3} className="chart-tick" textAnchor="end">{r.label}</text>
          </g>
        ))}
        {series.map((s, si) => (
          <path
            key={s.name}
            d={s.values.map((v, i) => `${i === 0 ? "M" : "L"}${sx(i).toFixed(1)},${sy(v).toFixed(1)}`).join(" ")}
            fill="none"
            stroke={s.color ?? CHART_COLORS[si % CHART_COLORS.length]}
            strokeWidth={2}
            strokeDasharray={s.dashed ? "4 3" : undefined}
            strokeLinejoin="round"
          />
        ))}
        {idx != null && n > 0 && (
          <g>
            <line x1={sx(idx)} x2={sx(idx)} y1={PAD.t} y2={PAD.t + ih} className="chart-cursor" />
            {series.map((s, si) => (
              <circle key={s.name} cx={sx(idx)} cy={sy(s.values[idx])} r={4} fill={s.color ?? CHART_COLORS[si % CHART_COLORS.length]} stroke="var(--panel)" strokeWidth={2} />
            ))}
          </g>
        )}
      </svg>
      {idx != null && n > 0 && (
        <div className="chart-tip">
          <span className="dim">{String(x[idx])}</span>
          {series.map((s) => (
            <span key={s.name}>{series.length > 1 ? `${s.name}: ` : ""}<b>{fmt(s.values[idx])}</b> {unit}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function niceTicks(min: number, max: number, count: number): number[] {
  const span = max - min;
  const raw = span / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(+v.toFixed(6));
  return out;
}
