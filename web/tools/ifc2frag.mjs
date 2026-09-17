// IFC -> ThatOpen fragments (.frag). Server yuklashdan keyin fonda chaqiradi:
//   node ifc2frag.mjs <in.ifc> <out.frag>
// Brauzer .frag ni to'g'ridan-to'g'ri yuklaydi (IFC ni parse qilmaydi) — katta modellar tez ochiladi.
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { IfcImporter } from "@thatopen/fragments";

const [inp, out] = process.argv.slice(2);
if (!inp || !out) {
  console.error("foydalanish: node ifc2frag.mjs <in.ifc> <out.frag>");
  process.exit(2);
}
const here = dirname(fileURLToPath(import.meta.url));
const t = Date.now();
const importer = new IfcImporter();
// web-ifc wasm — shu papkadagi node_modules dan (web/ ichida ham, Docker da ham)
importer.wasm = { absolute: true, path: here + "/node_modules/web-ifc/" };
const bytes = new Uint8Array(readFileSync(inp));
const frag = await importer.process({ bytes });
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, frag);
console.log(JSON.stringify({ ok: true, ifc_bytes: bytes.length, frag_bytes: frag.length, ms: Date.now() - t }));
