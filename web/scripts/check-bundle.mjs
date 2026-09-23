// Build natijasi tekshiruvi (CI da `vite build` dan keyin):
//  1) Login sahifasi to'plami (kirish chunki + umumiy react) 500 KB dan kichik (F10);
//  2) three/thatopen/web-ifc alohida bo'laklarda;
//  3) WEB-01: dist da tashqi (https:// yoki //cdn) import YO'Q — ichki OT tarmoqda internet bo'lmaydi.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { findRemoteImports } from "./remote-imports.mjs";

const dist = "dist";
const dir = join(dist, "assets");
const files = readdirSync(dir).filter((f) => f.endsWith(".js"));
const entry = files.filter((f) => /^(index|react)-/.test(f));
const size = entry.reduce((a, f) => a + statSync(join(dir, f)).size, 0);
const heavy = files.filter((f) => /^(three|thatopen|web-ifc)-/.test(f));
console.log(`login to'plami: ${entry.join(", ")} = ${(size / 1024).toFixed(0)} KB; og'ir bo'laklar alohida: ${heavy.join(", ")}`);
let failed = false;
if (size > 500 * 1024) { console.error("XATO: login to'plami 500 KB dan katta"); failed = true; }
if (heavy.length < 3) { console.error("XATO: three/thatopen/web-ifc alohida bo'lakda emas"); failed = true; }

/** dist ichidagi barcha matn fayllari (js/mjs/html/css) — ishchi (worker) fayllari ham. */
function walk(p, out = []) {
  for (const f of readdirSync(p)) {
    const q = join(p, f);
    if (statSync(q).isDirectory()) walk(q, out);
    else if (/\.(m?js|html|css)$/.test(f)) out.push(q);
  }
  return out;
}
const remote = [];
for (const f of walk(dist)) {
  for (const hit of findRemoteImports(readFileSync(f, "utf8"))) remote.push(`${relative(dist, f)}: ${hit}`);
}
if (remote.length) {
  console.error(`XATO (WEB-01): dist da tashqi import bor — offline ishlamaydi:\n  ${remote.join("\n  ")}`);
  failed = true;
} else {
  console.log("tashqi (https://) import yo'q — offline OK");
}
if (failed) process.exit(1);
