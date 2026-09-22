/** Trend server mantig'i (F7): shkala, o'q belgilari, uzilishlar (sifat/bo'shliq), normallashtirish, kursor. */

export interface TrendPoint { t: number; v: number | null; min?: number | undefined; max?: number | undefined }
export interface TrendSeries { id: number | string; name: string; unit: string; color?: string; points: TrendPoint[] }

export const MAX_POINTS = 20_000; // uzunlik qo'riqchisi — undan ko'p nuqta serverdan siyraklashtirilgan holda olinadi

export function clampPoints(points: TrendPoint[]): TrendPoint[] {
  if (points.length <= MAX_POINTS) return points;
  const step = Math.ceil(points.length / MAX_POINTS);
  return points.filter((_, i) => i % step === 0);
}

/** Mediana oraliq (ms) — uzilish chegarasi uchun. */
export function medianInterval(points: TrendPoint[]): number {
  if (points.length < 2) return 0;
  const d: number[] = [];
  for (let i = 1; i < points.length; i++) d.push(points[i].t - points[i - 1].t);
  d.sort((a, b) => a - b);
  return d[Math.floor(d.length / 2)];
}

/** Uzluksiz segmentlar: `null` qiymat (bad) yoki vaqt bo'shlig'i > gapFactor × mediana — chiziq uziladi
 * (jim interpolyatsiya emas). */
export function segments(points: TrendPoint[], gapFactor = 3): TrendPoint[][] {
  const out: TrendPoint[][] = [];
  const med = medianInterval(points);
  let cur: TrendPoint[] = [];
  for (let i = 0; i < points.length; i++) {
    const p = points[i];
    const gap = i > 0 && med > 0 && p.t - points[i - 1].t > gapFactor * med;
    if (p.v == null || gap) {
      if (cur.length) out.push(cur);
      cur = p.v == null ? [] : [p];
      continue;
    }
    cur.push(p);
  }
  if (cur.length) out.push(cur);
  return out;
}

/** "Chiroyli" o'q qadamlari (1/2/5 × 10^n). */
export function niceTicks(lo: number, hi: number, n = 5): number[] {
  if (!(hi > lo)) return [lo];
  const raw = (hi - lo) / n;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
  const start = Math.ceil(lo / step) * step;
  const ticks: number[] = [];
  for (let v = start; v <= hi + 1e-9; v += step) ticks.push(Number(v.toFixed(10)));
  return ticks;
}

/** Ko'rinadigan oynadagi y-diapazon (padding 5 %); qiymatlar teng bo'lsa ±1. */
export function yDomain(series: TrendSeries[], t0: number, t1: number): [number, number] {
  let lo = Infinity, hi = -Infinity;
  for (const s of series) for (const p of s.points) if (p.v != null && p.t >= t0 && p.t <= t1) { lo = Math.min(lo, p.min ?? p.v); hi = Math.max(hi, p.max ?? p.v); }
  if (!Number.isFinite(lo)) return [0, 1];
  if (hi === lo) return [lo - 1, hi + 1];
  const pad = (hi - lo) * 0.05;
  return [lo - pad, hi + pad];
}

/** Birlik bo'yicha guruhlash — har birlik uchun alohida o'q. */
export function groupByUnit(series: TrendSeries[]): Map<string, TrendSeries[]> {
  const m = new Map<string, TrendSeries[]>();
  for (const s of series) m.set(s.unit || "", [...(m.get(s.unit || "") ?? []), s]);
  return m;
}

/** Normallashtirilgan rejim: har seriya o'z [min,max] ida 0…100 %. */
export function normalize(series: TrendSeries[], t0: number, t1: number): TrendSeries[] {
  return series.map((s) => {
    const [lo, hi] = yDomain([s], t0, t1);
    const k = hi > lo ? 100 / (hi - lo) : 0;
    return { ...s, unit: "%", points: s.points.map((p) => (p.v == null ? p : { ...p, v: (p.v - lo) * k, min: p.min != null ? (p.min - lo) * k : undefined, max: p.max != null ? (p.max - lo) * k : undefined })) };
  });
}

/** Vaqt bo'yicha eng yaqin nuqta indeksi (ikkilik qidiruv, O(log n)). */
export function nearestIndex(points: TrendPoint[], t: number): number {
  if (!points.length) return -1;
  let lo = 0, hi = points.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (points[mid].t < t) lo = mid + 1; else hi = mid;
  }
  if (lo > 0 && Math.abs(points[lo - 1].t - t) < Math.abs(points[lo].t - t)) return lo - 1;
  return lo;
}

/** Zoom: [t0,t1] ni `at` atrofida `factor` marta (factor < 1 — yaqinlashtirish); chegara `[min,max]`. */
export function zoomDomain(d: [number, number], at: number, factor: number, bounds: [number, number]): [number, number] {
  const span = Math.max(1000, (d[1] - d[0]) * factor);
  const frac = (at - d[0]) / (d[1] - d[0] || 1);
  let t0 = at - span * frac, t1 = at + span * (1 - frac);
  if (t0 < bounds[0]) { t1 += bounds[0] - t0; t0 = bounds[0]; }
  if (t1 > bounds[1]) { t0 -= t1 - bounds[1]; t1 = bounds[1]; }
  return [Math.max(bounds[0], t0), Math.min(bounds[1], t1)];
}

export function panDomain(d: [number, number], dt: number, bounds: [number, number]): [number, number] {
  const span = d[1] - d[0];
  let t0 = d[0] + dt;
  t0 = Math.max(bounds[0], Math.min(bounds[1] - span, t0));
  return [t0, t0 + span];
}

export function fmtTick(t: number, spanMs: number): string {
  const d = new Date(t);
  if (spanMs > 3 * 86400_000) return d.toLocaleDateString("uz-UZ", { day: "2-digit", month: "2-digit" }) + " " + d.toLocaleTimeString("uz-UZ", { hour: "2-digit", minute: "2-digit" });
  if (spanMs > 2 * 3600_000) return d.toLocaleTimeString("uz-UZ", { hour: "2-digit", minute: "2-digit" });
  return d.toLocaleTimeString("uz-UZ", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function fmtNum(v: number): string {
  const a = Math.abs(v);
  return a >= 1000 ? v.toFixed(0) : a >= 100 ? v.toFixed(1) : a >= 1 ? v.toFixed(2) : v.toFixed(3);
}
