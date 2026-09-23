// tokens.ts (THEMES) → src/ui/tokens.css rang bloklari. Ishga tushirish: `npx vite-node scripts/gen-tokens-css.ts`.
// tokens.test.ts CSS va JS qiymatlari bir xilligini tekshiradi (qo'lda tahrirlanmasin — shu skript bilan).
import { readFileSync, writeFileSync } from "node:fs";
import { THEMES } from "../src/ui/tokens";

const file = "src/ui/tokens.css";
const START = "/* @generated-colors:start */";
const END = "/* @generated-colors:end */";

function block(selector: string, vars: Record<string, string>): string {
  return `${selector} {\n${Object.entries(vars).map(([k, v]) => `  --${k}: ${v};`).join("\n")}\n}`;
}

const generated = [
  START,
  "/* tokens.ts dan avtomatik (scripts/gen-tokens-css.ts) — qo'lda tahrirlamang */",
  block(':root,\n:root[data-theme="engineer"]', THEMES.engineer),
  block(':root[data-theme="operator"]', THEMES.operator),
  block(':root[data-theme="operator-hc"]', THEMES["operator-hc"]),
  END,
].join("\n");

const src = readFileSync(file, "utf8");
const a = src.indexOf(START), b = src.indexOf(END);
if (a < 0 || b < 0) throw new Error("tokens.css da @generated-colors belgilari yo'q");
writeFileSync(file, src.slice(0, a) + generated + src.slice(b + END.length));
console.log("tokens.css yangilandi");
