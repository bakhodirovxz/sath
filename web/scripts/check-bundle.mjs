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
// FE-06: ilova bo'laklari byudjeti — og'ir kutubxonalar faqat vendor bo'laklarida (three/thatopen/web-ifc/react)
const APP_CHUNK_MAX = 350 * 1024;
const big = files.filter((f) => !/^(three|thatopen|web-ifc|react)-/.test(f)).map((f) => [f, statSync(join(dir, f)).size]).filter(([, n]) => n > APP_CHUNK_MAX);
if (big.length) { console.error(`XATO: ilova bo'lagi ${APP_CHUNK_MAX / 1024} KB dan katta: ${big.map(([f, n]) => `${f} ${(n / 1024).toFixed(0)} KB`).join(", ")}`); failed = true; }
else console.log(`ilova bo'laklari ≤ ${APP_CHUNK_MAX / 1024} KB (eng kattasi: ${files.filter((f) => !/^(three|thatopen|web-ifc|react)-/.test(f)).map((f) => [f, statSync(join(dir, f)).size]).sort((a, b) => b[1] - a[1])[0]?.join(" ")} B)`);

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
