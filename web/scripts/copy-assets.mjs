// Fragments worker va web-ifc wasm ni public/ ga nusxalaydi (offline ishlashi uchun, unpkg kerak emas)
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const nm = join(root, "node_modules");
const out = join(root, "public", "engine");
mkdirSync(out, { recursive: true });
copyFileSync(join(nm, "@thatopen/fragments/dist/Worker/worker.mjs"), join(out, "worker.mjs"));
copyFileSync(join(nm, "web-ifc/web-ifc.wasm"), join(out, "web-ifc.wasm"));
copyFileSync(join(nm, "web-ifc/web-ifc-mt.wasm"), join(out, "web-ifc-mt.wasm"));
console.log("engine assets copied to public/engine");
