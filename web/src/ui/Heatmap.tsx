import { useEffect, useMemo, useRef, useState } from "react";

/** Bitta rangli ketma-ket shkala (ko'k, och → to'q emas: qora fonda to'qdan ochga). */
export function seqColor(t: number): [number, number, number] {
  const a: [number, number, number] = [0.07, 0.22, 0.37]; // #12395f
  const b: [number, number, number] = [0.62, 0.82, 1.0]; // #9ed0ff
  const k = Math.max(0, Math.min(1, t));
  return [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k];
}

export interface Grid {
  nx: number;
  ny: number;
  values: number[]; // 0..1 normalizatsiya qilingan, qator-qator (pastdan yuqoriga)
  min: number;
  max: number;
  x0: number;
  x1: number;
  y0: number;
  y1: number;
}

/** Tarqoq nuqtalardan (x,y,v) muntazam to'r — eng yaqin nuqta bo'yicha (bo'sh katak → qo'shnidan). */
export function gridFromPoints(points: { x: number; y: number }[], value: (p: { x: number; y: number }) => number | undefined, nx = 120, ny = 40): Grid | null {
  const pts = points.filter((p) => value(p) != null && Number.isFinite(value(p)!));
  if (pts.length < 4) return null;
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity, vmin = Infinity, vmax = -Infinity;
  for (const p of pts) {
    const v = value(p)!;
    if (p.x < x0) x0 = p.x; if (p.x > x1) x1 = p.x; if (p.y < y0) y0 = p.y; if (p.y > y1) y1 = p.y;
    if (v < vmin) vmin = v; if (v > vmax) vmax = v;
  }
  if (x1 - x0 < 1e-9 || y1 - y0 < 1e-9) return null;
  const sum = new Float64Array(nx * ny), cnt = new Uint32Array(nx * ny);
  for (const p of pts) {
    const i = Math.min(nx - 1, Math.floor(((p.x - x0) / (x1 - x0)) * nx));
    const j = Math.min(ny - 1, Math.floor(((p.y - y0) / (y1 - y0)) * ny));
    sum[j * nx + i] += value(p)!;
    cnt[j * nx + i]++;
  }
  const raw = new Float64Array(nx * ny).fill(NaN);
  for (let k = 0; k < nx * ny; k++) if (cnt[k]) raw[k] = sum[k] / cnt[k];
  // bo'sh kataklarni to'ldirish (bir necha o'tishda qo'shnilar o'rtachasi)
  for (let pass = 0; pass < 6; pass++) {
    let filled = 0;
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      const k = j * nx + i;
      if (!Number.isNaN(raw[k])) continue;
      let s = 0, c = 0;
      for (const [di, dj] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
        const ii = i + di, jj = j + dj;
        if (ii >= 0 && ii < nx && jj >= 0 && jj < ny && !Number.isNaN(raw[jj * nx + ii])) { s += raw[jj * nx + ii]; c++; }
      }
      if (c) { raw[k] = s / c; filled++; }
    }
    if (!filled) break;
  }
  const span = vmax - vmin || 1;
  return { nx, ny, values: Array.from(raw, (v) => (Number.isNaN(v) ? 0 : (v - vmin) / span)), min: vmin, max: vmax, x0, x1, y0, y1 };
}

interface Props { grid: Grid; title: string; unit: string; height?: number }

/** 2D issiqlik xaritasi (canvas) + shkala + kursor qiymati. */
export default function Heatmap({ grid, title, unit, height = 160 }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [hover, setHover] = useState<{ x: number; y: number; v: number } | null>(null);
  const img = useMemo(() => {
    const data = new Uint8ClampedArray(grid.nx * grid.ny * 4);
    for (let j = 0; j < grid.ny; j++) for (let i = 0; i < grid.nx; i++) {
      const [r, g, b] = seqColor(grid.values[j * grid.nx + i]);
      const k = ((grid.ny - 1 - j) * grid.nx + i) * 4; // canvas yuqoridan
      data[k] = r * 255; data[k + 1] = g * 255; data[k + 2] = b * 255; data[k + 3] = 255;
    }
    return data;
  }, [grid]);

  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    c.width = grid.nx; c.height = grid.ny;
    c.getContext("2d")!.putImageData(new ImageData(img, grid.nx, grid.ny), 0, 0);
  }, [img, grid.nx, grid.ny]);

  const fmt = (v: number) => (Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(3));
  return (
    <div className="chart">
      <div className="chart-head"><span className="chart-title">{title}</span><span className="dim small">{unit}</span></div>
      <canvas
        ref={ref}
        style={{ width: "100%", height, imageRendering: "auto", display: "block", border: "1px solid var(--line)" }}
        onMouseMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          const fx = (e.clientX - r.left) / r.width, fy = 1 - (e.clientY - r.top) / r.height;
          const i = Math.min(grid.nx - 1, Math.floor(fx * grid.nx)), j = Math.min(grid.ny - 1, Math.floor(fy * grid.ny));
          setHover({ x: grid.x0 + fx * (grid.x1 - grid.x0), y: grid.y0 + fy * (grid.y1 - grid.y0), v: grid.min + grid.values[j * grid.nx + i] * (grid.max - grid.min) });
        }}
        onMouseLeave={() => setHover(null)}
        aria-label={title}
      />
      <div className="chart-tip">
        <span><i className="hm-swatch" style={{ background: "#12395f" }} />{fmt(grid.min)}</span>
        <span><i className="hm-swatch" style={{ background: "#9ed0ff" }} />{fmt(grid.max)} {unit}</span>
        {hover && <span className="grow" style={{ textAlign: "right" }}>x={hover.x.toFixed(2)} y={hover.y.toFixed(2)} → <b>{fmt(hover.v)}</b> {unit}</span>}
      </div>
    </div>
  );
}
