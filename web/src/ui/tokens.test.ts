import { readFileSync } from "fs";
import { describe, expect, it } from "vitest";
import { themeForPath } from "../App";
import { THEMES, alarmRank, alarmStyle, applyTheme, contrast, currentTheme, opsTheme, qualityStyle } from "./tokens";

/** UX-05: barcha temalar WCAG AA (matn 4.5:1, grafik 3:1); alarm shakli — to'ldirish + siyoh + kontur. */
const TEXT = ["text", "text-muted", "text-dim", "link", "ok", "warn", "danger", "attention"];
const BG = ["panel", "chrome", "canvas", "field"];
const PRIOS = ["critical", "high", "medium", "low"];

describe("tokens: WCAG AA kontrast (UX-05)", () => {
  for (const [name, t] of Object.entries(THEMES)) {
    it(`${name}: matn 4.5:1, grafik 3:1, alarm shakli, to'ldirilgan belgi`, () => {
      const bad: string[] = [];
      for (const bg of BG) for (const k of TEXT) if (contrast(t[k], t[bg]) < 4.5) bad.push(`${k} on ${bg} ${contrast(t[k], t[bg]).toFixed(2)}`);
      if (contrast(t.text, t["alarm-row"]) < 4.5) bad.push("text on alarm-row");
      if (contrast(t.text, t["attention-bg"]) < 4.5) bad.push("text on attention-bg");
      if (contrast(t["on-accent"], t.accent) < 4.5) bad.push("on-accent on accent");
      if (contrast(t["on-danger"], t["danger-strong"]) < 4.5) bad.push(`on-danger on danger-strong ${contrast(t["on-danger"], t["danger-strong"]).toFixed(2)}`);
      if (contrast(t.text, t.sel) < 4.5) bad.push("text on sel");
      for (const p of PRIOS) {
        const fill = t[`alarm-${p}`], ink = t[`alarm-${p}-ink`], outline = t["alarm-outline"];
        if (contrast(ink, fill) < 4.5) bad.push(`ink on alarm-${p} ${contrast(ink, fill).toFixed(2)}`);
        // shakl fonda ko'rinadi: to'ldirish yoki kontur ≥ 3:1 (sariq kulrangda — kontur hisobiga)
        for (const bg of ["panel", "canvas", "chrome"]) if (Math.max(contrast(fill, t[bg]), contrast(outline, t[bg])) < 3) bad.push(`alarm-${p} shape on ${bg}`);
      }
      for (const bg of ["panel", "canvas", "mimic-hall"]) for (const k of ["mimic-outline", "mimic-on", "mimic-unbound", "focus"]) if (contrast(t[k], t[bg]) < 3) bad.push(`gfx ${k} on ${bg} ${contrast(t[k], t[bg]).toFixed(2)}`);
      for (let i = 1; i <= 6; i++) if (contrast(t[`pen-${i}`], t.field) < 3) bad.push(`pen-${i} on field`);
      expect(bad).toEqual([]);
    });
  }
  it("barcha temalar bir xil token to'plamiga ega", () => {
    const keys = Object.keys(THEMES.engineer).sort();
    expect(Object.keys(THEMES.operator).sort()).toEqual(keys);
    expect(Object.keys(THEMES["operator-hc"]).sort()).toEqual(keys);
  });
  it("kunduzgi variant standartdan kontrastliroq (matn va kontur)", () => {
    const o = THEMES.operator, h = THEMES["operator-hc"];
    expect(contrast(h.text, h.panel)).toBeGreaterThan(contrast(o.text, o.panel));
    expect(contrast(h["mimic-outline"], h.canvas)).toBeGreaterThan(contrast(o["mimic-outline"], o.canvas));
  });
  it("ISA-101: operator temasida 'normal' rangsiz — ok/attention neytral, alarm ranglari boshqa tokenlarda yo'q", () => {
    for (const th of ["operator", "operator-hc"] as const) {
      const t = THEMES[th];
      expect(t.ok).toBe(t["text-muted"]);
      const alarm = new Set(PRIOS.map((p) => t[`alarm-${p}`]));
      const leaks = Object.entries(t).filter(([k, v]) => alarm.has(v) && !k.startsWith("alarm-"));
      expect(leaks).toEqual([]);
    }
  });
  it("contrast(): ma'lum qiymatlar", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 0);
    expect(contrast("#777777", "#ffffff")).toBeCloseTo(4.48, 1);
  });
});

describe("tokens.css ↔ tokens.ts sinxron", () => {
  const css = readFileSync("src/ui/tokens.css", "utf8");
  const blocks: Record<string, Record<string, string>> = {};
  for (const m of css.matchAll(/((?::root[^{]*))\{([^}]*)\}/g)) {
    const vars = Object.fromEntries([...m[2].matchAll(/--([\w-]+):\s*([^;]+);/g)].map((x) => [x[1], x[2].trim()]));
    for (const sel of m[1].split(",").map((x) => x.trim())) {
      const theme = /data-theme="([\w-]+)"\]$/.exec(sel)?.[1] ?? (sel === ":root" ? "root" : "");
      blocks[theme] = { ...(blocks[theme] ?? {}), ...vars };
    }
  }
  for (const th of Object.keys(THEMES)) {
    it(`${th}: CSS rang qiymatlari tokens.ts bilan bir xil (npx vite-node scripts/gen-tokens-css.ts)`, () => {
      const t = THEMES[th as keyof typeof THEMES];
      const diff = Object.entries(t).filter(([k, v]) => blocks[th]?.[k]?.toLowerCase() !== v.toLowerCase()).map(([k]) => k);
      expect(diff).toEqual([]);
    });
  }
  it("tipografiya shkalasi: operator tana ≥ 14 px, qiymat ≥ 18 px; muhandis tana 13 px", () => {
    expect(blocks.engineer["fs-body"] ?? blocks.root["fs-body"]).toBe("13px");
    expect(blocks["operator-hc"]["fs-value"] ?? blocks.operator["fs-value"]).toBe("18px");
    expect(parseInt(blocks.operator["fs-body"])).toBeGreaterThanOrEqual(14);
  });
});

describe("alarmStyle: rang yagona kanal emas", () => {
  it("ustuvorlik → shakl (◆ kritik, ▲ yuqori, ■ o'rta, ● past) + kod + rang + siyoh", () => {
    const c = alarmStyle("highhigh", "critical");
    expect(c).toMatchObject({ shape: "diamond", glyph: "◆", code: "HH", rank: 1, color: "var(--alarm-critical)", ink: "var(--alarm-critical-ink)", priority: "critical" });
    expect(alarmStyle("high", "high")).toMatchObject({ shape: "triangle", glyph: "▲", rank: 2 });
    expect(alarmStyle("high", "medium")).toMatchObject({ shape: "square", glyph: "■", rank: 3 });
    expect(alarmStyle("low", "low")).toMatchObject({ shape: "circle", glyph: "●", code: "L", rank: 4 });
    expect(alarmStyle("roc", "high").code).toBe("ROC");
    expect(alarmStyle("ok", "critical")).toMatchObject({ shape: "none", code: "", rank: 0, bg: "transparent", priority: null });
    expect(alarmStyle("stale", "critical")).toMatchObject({ code: "?", color: "var(--alarm-stale)" });
    expect(alarmStyle("nimadir", "yoq").code).toBe("");
  });
  it("saralash: kritik birinchi, keyin holat og'irligi", () => {
    const order = [["low", "low"], ["highhigh", "critical"], ["high", "high"], ["stale", "critical"], ["high", "critical"]]
      .sort((a, b) => alarmRank(a[0], a[1]) - alarmRank(b[0], b[1]))
      .map((x) => x.join(":"));
    expect(order).toEqual(["highhigh:critical", "high:critical", "high:high", "low:low", "stale:critical"]);
  });
  it("sifat kodi", () => {
    expect(qualityStyle("bad").code).toBe("✕");
    expect(qualityStyle("good").code).toBe("");
    expect(qualityStyle(undefined).label).toBe("yaxshi");
  });
});

describe("tema marshrutga bog'langan", () => {
  it("dispetcher → operator varianti (saqlanadi), BIM → engineer", () => {
    expect(themeForPath("/projects/3/ops/alarms")).toBe(opsTheme());
    expect(themeForPath("/projects/3/dashboard")).toBe(opsTheme());
    expect(themeForPath("/models/4")).toBe("engineer");
    expect(themeForPath("/projects/3")).toBe("engineer");
    applyTheme("operator-hc");
    expect(currentTheme()).toBe("operator-hc");
    expect(opsTheme()).toBe("operator-hc");
    applyTheme("engineer"); // muhandis temasi saqlanmaydi — operator tanlovi qoladi
    expect(opsTheme()).toBe("operator-hc");
    expect(document.documentElement.getAttribute("data-theme")).toBe("engineer");
    applyTheme("operator");
  });
});
