// Login sahifasi to'plami (kirish chunki + umumiy react) 500 KB dan kichik bo'lishi kerak (F10) — CI da build dan keyin.
import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";
const dir = "dist/assets";
const files = readdirSync(dir).filter((f) => f.endsWith(".js"));
const entry = files.filter((f) => /^(index|react)-/.test(f));
const size = entry.reduce((a, f) => a + statSync(join(dir, f)).size, 0);
const heavy = files.filter((f) => /^(three|thatopen|web-ifc)-/.test(f));
console.log(`login to'plami: ${entry.join(", ")} = ${(size / 1024).toFixed(0)} KB; og'ir bo'laklar alohida: ${heavy.join(", ")}`);
if (size > 500 * 1024) { console.error("XATO: login to'plami 500 KB dan katta"); process.exit(1); }
if (heavy.length < 3) { console.error("XATO: three/thatopen/web-ifc alohida bo'lakda emas"); process.exit(1); }
