import { readFileSync, readdirSync, statSync } from "fs";
import { join } from "path";
import { describe, expect, it } from "vitest";
import { THEMES, alarmRank, alarmStyle, applyTheme, contrast, qualityStyle, savedTheme } from "./tokens";

const TEXT = ["text", "text-muted", "text-dim", "link", "ok", "warn", "danger", "alarm-critical", "alarm-high", "alarm-medium", "alarm-low", "alarm-stale", "quality-bad", "quality-uncertain"];
const GRAPHIC = ["ok", "warn", "danger", "alarm-critical", "alarm-high", "alarm-medium", "alarm-low", "alarm-stale", "mimic-outline", "mimic-unbound", "mimic-idle"];

describe("tokens: WCAG AA kontrast (F1)", () => {
  for (const [name, t] of Object.entries(THEMES)) {
    it(`${name}: matn 4.5:1, grafik 3:1, alarm qatori ko'rinadi`, () => {
      const bad: string[] = [];
      for (const bg of ["panel", "chrome", "canvas", "field"]) for (const k of TEXT) if (contrast(t[k], t[bg]) < 4.5) bad.push(`${k} on ${bg} ${contrast(t[k], t[bg]).toFixed(2)}`);
      if (contrast(t.text, t["alarm-row"]) < 4.5) bad.push("text on alarm-row");
      for (const bg of ["panel", "canvas", "mimic-hall"]) for (const k of GRAPHIC) if (contrast(t[k], t[bg]) < 3) bad.push(`gfx ${k} on ${bg} ${contrast(t[k], t[bg]).toFixed(2)}`);
      if (contrast(t["alarm-row"], t.panel) < 1.5) bad.push("alarm-row vs panel");
      if (contrast("#ffffff", t.accent) < 4.5) bad.push("white on accent");
      if (contrast(t.text, t.sel) < 4.5) bad.push("text on sel");
      expect(bad).toEqual([]);
    });
  }
  it("ikkala tema bir xil token to'plamiga ega", () => {
    expect(Object.keys(THEMES.operator).sort()).toEqual(Object.keys(THEMES.engineer).sort());
  });
  it("contrast(): ma'lum qiymatlar", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 0);
    expect(contrast("#777777", "#ffffff")).toBeCloseTo(4.48, 1);
  });
});

describe("alarmStyle: rang yagona kanal emas", () => {
  it("ustuvorlik → shakl + kod + rang", () => {
    const c = alarmStyle("highhigh", "critical");
    expect(c).toMatchObject({ shape: "diamond", code: "HH", rank: 1, color: "var(--alarm-critical)", bg: "var(--alarm-row)" });
    expect(alarmStyle("low", "low")).toMatchObject({ shape: "circle", code: "L", rank: 4 });
    expect(alarmStyle("roc", "high").code).toBe("ROC");
    expect(alarmStyle("ok", "critical")).toMatchObject({ shape: "none", code: "", rank: 0, bg: "transparent" });
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

describe("tema almashtirish", () => {
  it("CSS o'zgaruvchilar va data-theme; saqlanadi", () => {
    applyTheme("operator");
    expect(document.documentElement.getAttribute("data-theme")).toBe("operator");
    expect(document.documentElement.style.getPropertyValue("--panel")).toBe(THEMES.operator.panel);
    expect(savedTheme("engineer")).toBe("operator");
    applyTheme("engineer");
    expect(document.documentElement.style.getPropertyValue("--panel")).toBe(THEMES.engineer.panel);
  });
});

/** Dispetcher sahifalari rangni faqat tokenlardan oladi: hex literal yo'q (theme.css/tokens.ts dan tashqari). */
describe("dispetcher sahifalarida hex rang literal yo'q", () => {
  const roots = ["src/pages/dashboard", "src/pages/operator", "src/pages/model/MonitoringPanel.tsx", "src/hooks"];
  const files: string[] = [];
  const walk = (p: string) => {
    let st;
    try { st = statSync(p); } catch { return; }
    if (st.isDirectory()) for (const f of readdirSync(p)) walk(join(p, f));
    else if (/\.(tsx?|css)$/.test(p) && !/\.test\./.test(p)) files.push(p);
  };
  roots.forEach(walk);
  it("fayllar tekshirildi", () => {
    expect(files.length).toBeGreaterThan(2);
  });
  for (const f of files) {
    it(f, () => {
      const src = readFileSync(f, "utf8");
      const hits = [...src.matchAll(/#[0-9a-fA-F]{3,8}\b/g)].map((m) => m[0]).filter((h) => /^#[0-9a-fA-F]{3}$|^#[0-9a-fA-F]{6}$|^#[0-9a-fA-F]{8}$/.test(h));
      expect(hits).toEqual([]);
    });
  }
});
