import { readFileSync, readdirSync, statSync } from "fs";
import { join } from "path";
import { describe, expect, it } from "vitest";

/** UX-08: dizayn tizimi qoidalari kod darajasida — rang faqat token fayllarida, inline style faqat dinamik
 * qiymatlar uchun (joylashuv, foiz, ma'lumotdan kelgan rang). */

const TOKEN_FILES = new Set(["src/ui/tokens.ts", "src/viewer/palette.ts", "src/ui/print.ts"].map((p) => p.replace(/\//g, "/")));

function walk(p: string, out: string[] = []): string[] {
  for (const f of readdirSync(p)) {
    const q = join(p, f);
    if (statSync(q).isDirectory()) walk(q, out);
    else if (/\.(ts|tsx)$/.test(f) && !/\.test\./.test(f)) out.push(q.replace(/\\/g, "/"));
  }
  return out;
}
const files = walk("src");

describe("rang literallari faqat token fayllarida", () => {
  it("fayllar topildi", () => expect(files.length).toBeGreaterThan(50));
  it("hex (#rgb/#rrggbb/#rrggbbaa) va rgb()/rgba()/hsl() yo'q (tokens.ts, viewer/palette.ts, ui/print.ts dan tashqari)", () => {
    const bad: string[] = [];
    for (const f of files) {
      if (TOKEN_FILES.has(f)) continue;
      const src = readFileSync(f, "utf8").replace(/\/\/.*$|\/\*[\s\S]*?\*\//gm, "");
      for (const m of src.matchAll(/["'`][^"'`\n]*?(#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\()[^"'`\n]*?["'`]/g)) {
        if (/^#[0-9a-fA-F]{3}$|^#[0-9a-fA-F]{6}$|^#[0-9a-fA-F]{8}$|^rgba?\($|^hsla?\($/.test(m[1])) bad.push(`${f}: ${m[0].slice(0, 60)}`);
      }
    }
    expect(bad).toEqual([]);
  });
});

describe("inline style — faqat dinamik qiymatlar", () => {
  const styles: { f: string; body: string }[] = [];
  for (const f of files.filter((x) => x.endsWith(".tsx"))) {
    for (const m of readFileSync(f, "utf8").matchAll(/style=\{\{([^{}]*)\}\}/g)) styles.push({ f, body: m[1] });
  }
  it("faqat literal qiymatli style={{…}} yo'q (sinf/utilitadan foydalaning)", () => {
    const staticOnly = styles.filter(({ body }) => {
      const rest = body.replace(/"[^"]*"|'[^']*'|`[^`$]*`/g, "").replace(/\b\w+\s*:/g, "").replace(/-?\d+(\.\d+)?/g, "").replace(/[\s,]/g, "");
      return rest === "";
    });
    expect(staticOnly.map((s) => `${s.f}: {${s.body.trim()}}`)).toEqual([]);
  });
  it("umumiy soni cheklangan (audit: 402 → ≤ 45)", () => {
    expect(styles.length).toBeLessThanOrEqual(45);
  });
});

describe("theme.css", () => {
  const css = readFileSync("src/ui/theme.css", "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  it("hex/rgb yo'q — faqat var(--…)", () => {
    expect(css.match(/#[0-9a-fA-F]{3,8}\b|rgba?\(/g) ?? []).toEqual([]);
  });
  it("dispetcher konteyneri to'liq kenglikda (tablar sakramaydi)", () => {
    expect(css).toMatch(/\.dash \{ width: 100%; max-width: \d+px; margin: 0 auto; \}/);
  });
});
