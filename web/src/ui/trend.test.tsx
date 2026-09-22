import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import Trend from "./Trend";
import { MAX_POINTS, clampPoints, medianInterval, nearestIndex, niceTicks, normalize, panDomain, segments, yDomain, zoomDomain, type TrendPoint, type TrendSeries } from "./trendMath";

const t0 = Date.parse("2026-09-22T00:00:00Z");
const mk = (n: number, step = 60_000, f: (i: number) => number | null = (i) => Math.sin(i / 10) * 10): TrendPoint[] => Array.from({ length: n }, (_, i) => ({ t: t0 + i * step, v: f(i) }));

describe("trend mantig'i (F7)", () => {
  it("uzilishlar: bad (null) va vaqt bo'shlig'i chiziqni uzadi, interpolyatsiya yo'q", () => {
    const pts = mk(10);
    pts[4].v = null;
    pts.splice(8, 0, { t: pts[7].t + 30 * 60_000, v: 1 }); // 30 daqiqalik bo'shliq
    const segs = segments(pts);
    expect(segs.map((s) => s.length)).toEqual([4, 3, 3]);
    expect(medianInterval(pts)).toBe(60_000);
  });
  it("chiroyli o'q qadamlari; y-diapazon padding va teng qiymatlar", () => {
    expect(niceTicks(0, 100)).toEqual([0, 20, 40, 60, 80, 100]);
    expect(niceTicks(898.2, 905.7, 5)).toEqual([900, 902, 904]);
    expect(niceTicks(898.2, 905.7, 8)).toEqual([899, 900, 901, 902, 903, 904, 905]);
    const s: TrendSeries = { id: 1, name: "a", unit: "m", points: mk(5, 60_000, () => 7) };
    expect(yDomain([s], t0, t0 + 1e9)).toEqual([6, 8]);
    const [lo, hi] = yDomain([{ ...s, points: mk(100) }], t0, t0 + 1e9);
    expect(lo).toBeLessThan(-9.9); expect(hi).toBeGreaterThan(9.9);
  });
  it("normallashtirish 0…100, ikkilik qidiruv, zoom/pan chegaralari, uzunlik qo'riqchisi", () => {
    const s: TrendSeries = { id: 1, name: "a", unit: "MW", points: mk(50, 60_000, (i) => i) };
    const n = normalize([s], t0, t0 + 1e9)[0];
    expect(n.unit).toBe("%");
    expect(n.points[0].v).toBeCloseTo(4.55, 1); // 5 % padding: 0 → ~4.5 %
    expect(n.points[49].v).toBeCloseTo(95.45, 1);
    expect(nearestIndex(s.points, t0 + 10 * 60_000 + 20_000)).toBe(10);
    expect(nearestIndex(s.points, t0 + 10 * 60_000 + 40_000)).toBe(11);
    expect(nearestIndex([], 1)).toBe(-1);
    const b: [number, number] = [t0, t0 + 3600_000];
    const z = zoomDomain(b, t0 + 1800_000, 0.5, b);
    expect(z[1] - z[0]).toBe(1800_000);
    expect(zoomDomain(b, t0, 2, b)).toEqual(b); // chegaradan chiqmaydi
    expect(panDomain([t0, t0 + 600_000], -1e9, b)).toEqual([t0, t0 + 600_000]);
    expect(clampPoints(mk(MAX_POINTS * 3)).length).toBeLessThanOrEqual(MAX_POINTS);
  });
  it("turli birlikdagi 5 seriya: har birlik uchun alohida o'q; 10 000 nuqta tez chiziladi", () => {
    const units = ["m", "MW", "m³/s", "°C", "mm/s"];
    const series: TrendSeries[] = units.map((u, i) => ({ id: i, name: `S${i}`, unit: u, points: mk(2000, 30_000, (k) => (i + 1) * 100 * Math.sin(k / 50) + (i === 0 ? 900 : 0)) }));
    const start = performance.now();
    const html = renderToStaticMarkup(<Trend series={series} height={300} />);
    const ms = performance.now() - start;
    expect(html.match(/data-testid="trend-axis"/g)).toHaveLength(5);
    expect(html).toContain('data-unit="MW"');
    expect(html.match(/data-testid="trend-path"/g)!.length).toBeGreaterThanOrEqual(5);
    expect(ms).toBeLessThan(1500);
    expect(html).not.toMatch(/#[0-9a-f]{6}/i);
    const norm = renderToStaticMarkup(<Trend series={series} height={300} mode="normalized" />);
    expect(norm.match(/data-testid="trend-axis"/g)).toHaveLength(1); // bitta % o'qi
  });
  it("seriyalar uzunligi farq qilsa NaN chiqmaydi", () => {
    const series: TrendSeries[] = [{ id: 1, name: "a", unit: "m", points: mk(100) }, { id: 2, name: "b", unit: "m", points: mk(3) }, { id: 3, name: "c", unit: "x", points: [] }];
    const html = renderToStaticMarkup(<Trend series={series} />);
    expect(html).not.toContain("NaN");
    expect(html).toContain("ma&#x27;lumot yo&#x27;q");
  });
});
