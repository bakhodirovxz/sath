import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Sensor } from "../../api/client";
import Mimic from "./Mimic";
import { VIEW, viewOf, bindFromSlots, defaultScheme, loadScheme, moveElement, overlappingUnits, setUnits, validateScheme } from "./scheme";

const mk = (o: Partial<Sensor>): Sensor => ({
  id: 1, project_id: 1, model_id: null, key: "X", name: "x", kind: "value", unit: "", element_guid: null, protocol: "http", address: {},
  low_alarm: null, high_alarm: null, stale_after_s: 600, enabled: true, last_value: 1, last_ts: new Date().toISOString(), alarm: "ok", priority: "medium", writable: false,
  ...o,
} as Sensor);

describe("mimika sxemasi (F3)", () => {
  for (const n of [1, 2, 3, 6, 12]) {
    it(`${n} agregatli standart sxema to'g'ri: element soni, ustma-ust tushmaydi, viewBox ichida`, () => {
      const s = defaultScheme(n);
      expect(s.units).toBe(n);
      expect(s.elements.filter((e) => e.type === "unit")).toHaveLength(n);
      expect(s.elements.filter((e) => e.type === "breaker")).toHaveLength(n);
      expect(validateScheme(s)).toEqual([]);
      expect(overlappingUnits(s)).toBe(0);
      const hall = s.elements.find((e) => e.id === "hall")!;
      for (const u of s.elements.filter((e) => e.type === "unit")) expect(u.x).toBeGreaterThan(hall.x);
      expect(s.elements.every((e) => e.x <= VIEW.w && e.y <= viewOf(s).h)).toBe(true);
      // qiymat katagi (180) va agregat qiymati (w) viewBox dan chiqmaydi
      for (const e of s.elements.filter((x) => x.type === "value")) expect(e.x + 90).toBeLessThanOrEqual(VIEW.w);
      for (const u of s.elements.filter((x) => x.type === "unit")) expect(u.w).toBeGreaterThanOrEqual(70);
      expect(new Set(s.elements.map((e) => e.id)).size).toBe(s.elements.length);
    });
  }
  it("chegaralar: 0 → 1, 99 → 12", () => {
    expect(defaultScheme(0).units).toBe(1);
    expect(defaultScheme(99).units).toBe(12);
  });
  it("eski slotlardan bog'lash va yuklash", () => {
    const s = bindFromSlots(defaultScheme(3), { upstream_level: 7, unit2_power: 9, total_power: null });
    expect(s.elements.find((e) => e.id === "upstream_level")?.sensor_id).toBe(7);
    expect(s.elements.find((e) => e.id === "unit2")?.sensor_id).toBe(9);
    expect(s.elements.find((e) => e.id === "total_power")?.sensor_id).toBeUndefined();
    expect(loadScheme(null, { upstream_level: 7 }, 2).units).toBe(2);
    expect(loadScheme(s, {}, 5)).toBe(s);
    expect(loadScheme({ version: 2 }, {}, 4).units).toBe(4);
  });
  it("surish viewBox ga cheklanadi; agregat sonini o'zgartirish bog'lanishlarni saqlaydi", () => {
    const s = moveElement(defaultScheme(2), "inflow", -50, 9999);
    expect(s.elements.find((e) => e.id === "inflow")).toMatchObject({ x: 0, y: VIEW.h });
    const bound = { ...defaultScheme(2), elements: defaultScheme(2).elements.map((e) => (e.id === "unit1" ? { ...e, sensor_id: 5, x: 123 } : e)) };
    const six = setUnits(bound, 6);
    expect(six.units).toBe(6);
    expect(six.elements.filter((e) => e.type === "unit")).toHaveLength(6);
    expect(six.elements.find((e) => e.id === "unit1")).toMatchObject({ sensor_id: 5, x: 123, unit: 1 });
    expect(validateScheme({ ...six, units: 4 })).toContain("agregat elementlari 6, units=4");
    expect(validateScheme({ ...six, elements: [...six.elements, { ...six.elements[0] }] })[0]).toMatch(/takror id/);
  });
  it("2 va 6 agregatli sxema chiziladi; bog'lanmagan element yashirilmaydi; holat belgilari", () => {
    const sensors = [
      mk({ id: 1, key: "AGG1.P", kind: "power", unit: "MW", last_value: 35, alarm: "high", priority: "critical" }),
      mk({ id: 2, key: "AGG1.RUN", kind: "status", last_value: 1 }),
      mk({ id: 3, key: "AGG1.CB", kind: "status", last_value: 0 }),
      mk({ id: 4, key: "GATE1.POS", kind: "position", unit: "%", last_value: 40 }),
      mk({ id: 5, key: "RES.H", kind: "level", unit: "m", last_value: 903, last_quality: "bad" }),
    ];
    for (const n of [2, 6]) {
      let s = defaultScheme(n);
      s = { ...s, elements: s.elements.map((e) => (e.id === "unit1" ? { ...e, sensor_id: 1, extra: { run: 2 } } : e.id === "cb1" ? { ...e, sensor_id: 3 } : e.id === "gate1" ? { ...e, sensor_id: 4 } : e.id === "upstream_level" ? { ...e, sensor_id: 5 } : e)) };
      const html = renderToStaticMarkup(<Mimic scheme={s} sensors={sensors} />);
      expect(html).toContain(`data-units="${n}"`);
      expect(html.match(/data-testid="mimic-unit"/g)).toHaveLength(n);
      expect(html.match(/data-testid="mimic-breaker"/g)).toHaveLength(n);
      expect(html).toContain('data-state="open"'); // Q1 ochiq
      expect(html.match(/data-testid="mimic-breaker" data-state="unknown"/g)).toHaveLength(n - 1); // bog'lanmagan uzgichlar ko'rinadi, "?"
      expect(html.match(/data-testid="mimic-unit" data-state="unknown"/g)).toHaveLength(n - 1); // ma'lumotsiz agregat — shtrix, rangsiz
      expect(html).toContain('data-testid="mimic-unit" data-state="running"');
      expect(html).toContain("ma&#x27;lumot yo&#x27;q"); // bog'lanmagan qiymat katakchasi yashirilmaydi
      // kritik alarm: romb shakli + ustuvorlik raqami + kod (rang — uchinchi kanal)
      expect(html).toMatch(/data-prio="critical" data-testid="mimic-alarm"/);
      expect(html).toMatch(/am-shape prio-critical/);
      expect(html).toMatch(/class="mimic-code"[^>]*>H</);
      expect(html).not.toMatch(/alarm-mark-svg unacked/); // kvitlangan — miltillamaydi
      expect(html).not.toMatch(/animate|m-flow|spin/); // normal holatda hech narsa harakatlanmaydi (UX-01)
      expect(html).toContain("40 %"); // zatvor ochilishi
      expect(html).toContain("903.0 m ✕"); // bad sifat kodi
      expect(html).not.toMatch(/#[0-9a-f]{6}/i); // rang faqat tokenlardan
      expect(html).not.toMatch(/fill="(?!url)[a-z]/i); // rang atributi yo'q — faqat CSS sinflari
    }
  });

  it("kvitlanmagan alarm miltillaydi; aloqa yo'q — qiymatlar eskirgan (shtrix, '?')", () => {
    const sensors = [mk({ id: 1, key: "RES.H", kind: "level", unit: "m", last_value: 905, alarm: "highhigh", priority: "high" })];
    const s = { ...defaultScheme(2), elements: defaultScheme(2).elements.map((e) => (e.id === "upstream_level" ? { ...e, sensor_id: 1 } : e)) };
    const html = renderToStaticMarkup(<Mimic scheme={s} sensors={sensors} unacked={new Set([1])} />);
    expect(html).toMatch(/alarm-mark-svg unacked/);
    expect(html).toMatch(/data-prio="high"/);
    expect(html).toMatch(/class="mimic-code"[^>]*>HH</);
    const off = renderToStaticMarkup(<Mimic scheme={s} sensors={sensors} offline />);
    expect(off).toMatch(/data-stale="1"/);
    expect(off).toContain("905.0 m ?");
  });
});
