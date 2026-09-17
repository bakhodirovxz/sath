/* Qoralama obyekt turlari (Blender "Add" menyusi kabi): primitivlar va GES inshootlari.
   Har tur: parametrlar (forma), geometriya quruvchi (three, Y yuqoriga, metr), IFC klassi, Pset_GES_*. */
import * as THREE from "three";

export interface DraftParam { key: string; label: string; unit?: string; default: number | string; min?: number; step?: number; options?: [string, string][] }
export interface PsetField { key: string; label: string; unit?: string; type?: "number" | "text" | "int" | "select"; default?: number | string; from?: string; options?: [string, string][] }
/** Beton klasslari (KMK 2.03.01) va po'lat markalari — server katalogi bilan bir xil (ges_sim.materials). */
export const CONCRETE_CLASSES: [string, string][] = [["B10", "B10 (RCC/ichki massiv)"], ["B15", "B15 — massiv"], ["B20", "B20 — massiv/yuza"], ["B25", "B25 — yuza zonasi"], ["B30", "B30 — suv tashlagich, temir-beton"], ["B35", "B35 — yemirilishga chidamli"], ["B40", "B40 — kavitatsiya zonasi"], ["B45", "B45"], ["B50", "B50"], ["B60", "B60"]];
export const STEEL_GRADES: [string, string][] = [["S355 / 09G2S", "S355 / 09G2S (standart)"], ["St3sp (S235)", "St3sp (S235) — past bosim"], ["17G1S", "17G1S — yirik diametr"], ["10HSND", "10HSND — sovuqqa chidamli"], ["S460", "S460 — yuqori napor"]];
export interface DraftKind {
  id: string;
  title: string;
  icon: string;
  group: "Primitivlar" | "GES inshootlari" | "Mavjud"; // Mavjud — Add menyusida ko'rinmaydi (element tahriri)
  ifcClass: string;
  color: string;
  params: DraftParam[];
  pset?: { name: string; fields: PsetField[] };
  build: (p: Record<string, number | string>) => THREE.BufferGeometry;
}

const n = (v: unknown, d = 0) => (typeof v === "number" && Number.isFinite(v) ? v : Number(v) || d);

/** Ko'pburchak profil (u — ko'ndalang, v — balandlik) X o'qi bo'ylab uzunlik L ga cho'zilgan prizma.
    Profil soat miliga qarshi; natija: x ∈ [0, L], z = u (IFC −y), y = v. */
function prism(profile: [number, number][], length: number): THREE.BufferGeometry {
  const tri = THREE.ShapeUtils.triangulateShape(profile.map(([u, v]) => new THREE.Vector2(u, v)), []);
  const pos: number[] = [];
  const push = (a: THREE.Vector3, b: THREE.Vector3, c: THREE.Vector3) => pos.push(a.x, a.y, a.z, b.x, b.y, b.z, c.x, c.y, c.z);
  const P = (x: number, i: number) => new THREE.Vector3(x, profile[i][1], profile[i][0]);
  for (const [a, b, c] of tri) { push(P(0, a), P(0, c), P(0, b)); push(P(length, a), P(length, b), P(length, c)); } // ikki tomon (normal tashqariga)
  for (let i = 0; i < profile.length; i++) {
    const j = (i + 1) % profile.length;
    const a0 = P(0, i), b0 = P(0, j), a1 = P(length, i), b1 = P(length, j);
    push(a0, b0, b1); push(a0, b1, a1);
  }
  return fixWinding(pos);
}

/** Uchburchaklar yo'nalishini tashqariga (imzoli hajm > 0) keltiradi va geometriya qaytaradi. */
function fixWinding(pos: number[]): THREE.BufferGeometry {
  let vol = 0;
  for (let i = 0; i < pos.length; i += 9) {
    const ax = pos[i], ay = pos[i + 1], az = pos[i + 2], bx = pos[i + 3], by = pos[i + 4], bz = pos[i + 5], cx = pos[i + 6], cy = pos[i + 7], cz = pos[i + 8];
    vol += ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx);
  }
  if (vol < 0) for (let i = 0; i < pos.length; i += 9) for (let k = 0; k < 3; k++) { const t = pos[i + 3 + k]; pos[i + 3 + k] = pos[i + 6 + k]; pos[i + 6 + k] = t; }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.computeVertexNormals();
  return g;
}

function box(w: number, d: number, h: number): THREE.BufferGeometry {
  const g = new THREE.BoxGeometry(w, h, d);
  g.translate(0, h / 2, 0);
  return g;
}

export const DRAFT_KINDS: DraftKind[] = [
  // --- Primitivlar ---
  { id: "cube", title: "Kub / quti", icon: "box", group: "Primitivlar", ifcClass: "IfcBuildingElementProxy", color: "#9aa3ad",
    params: [{ key: "w", label: "Kenglik (X)", unit: "m", default: 4, min: 0.01 }, { key: "d", label: "Chuqurlik (Y)", unit: "m", default: 4, min: 0.01 }, { key: "h", label: "Balandlik (Z)", unit: "m", default: 3, min: 0.01 }],
    build: (p) => box(n(p.w, 4), n(p.d, 4), n(p.h, 3)) },
  { id: "cylinder", title: "Silindr", icon: "cylinder", group: "Primitivlar", ifcClass: "IfcBuildingElementProxy", color: "#9aa3ad",
    params: [{ key: "r", label: "Radius", unit: "m", default: 1.5, min: 0.01 }, { key: "h", label: "Balandlik", unit: "m", default: 4, min: 0.01 }, { key: "axis", label: "O'q", default: "z", options: [["z", "Vertikal (Z)"], ["x", "Gorizontal (X)"]] }],
    build: (p) => { const g = new THREE.CylinderGeometry(n(p.r, 1.5), n(p.r, 1.5), n(p.h, 4), 32); if (p.axis === "x") { g.rotateZ(-Math.PI / 2); g.translate(n(p.h, 4) / 2, n(p.r, 1.5), 0); } else g.translate(0, n(p.h, 4) / 2, 0); return g; } },
  { id: "sphere", title: "Sfera", icon: "sphere", group: "Primitivlar", ifcClass: "IfcBuildingElementProxy", color: "#9aa3ad",
    params: [{ key: "r", label: "Radius", unit: "m", default: 1.5, min: 0.01 }],
    build: (p) => { const g = new THREE.SphereGeometry(n(p.r, 1.5), 32, 20); g.translate(0, n(p.r, 1.5), 0); return g; } },
  { id: "cone", title: "Konus", icon: "cone", group: "Primitivlar", ifcClass: "IfcBuildingElementProxy", color: "#9aa3ad",
    params: [{ key: "r", label: "Radius", unit: "m", default: 1.5, min: 0.01 }, { key: "h", label: "Balandlik", unit: "m", default: 3, min: 0.01 }],
    build: (p) => { const g = new THREE.ConeGeometry(n(p.r, 1.5), n(p.h, 3), 32); g.translate(0, n(p.h, 3) / 2, 0); return g; } },
  { id: "plane", title: "Tekislik / plita", icon: "plane", group: "Primitivlar", ifcClass: "IfcSlab", color: "#9aa3ad",
    params: [{ key: "w", label: "Kenglik (X)", unit: "m", default: 10, min: 0.01 }, { key: "d", label: "Chuqurlik (Y)", unit: "m", default: 10, min: 0.01 }, { key: "t", label: "Qalinlik", unit: "m", default: 0.3, min: 0.001 }],
    build: (p) => box(n(p.w, 10), n(p.d, 10), n(p.t, 0.3)) },
  // --- GES inshootlari ---
  { id: "dam", title: "To'g'on (beton og'irlik)", icon: "dam", group: "GES inshootlari", ifcClass: "IfcWall", color: "#8d8f93",
    params: [{ key: "length", label: "Uzunlik (gerb)", unit: "m", default: 60, min: 1 }, { key: "height", label: "Balandlik", unit: "m", default: 25, min: 0.5 }, { key: "crest", label: "Gerb kengligi", unit: "m", default: 6, min: 0.2 }, { key: "mu", label: "Yuqori yuza qiyaligi", default: 0.05, min: 0, step: 0.05 }, { key: "md", label: "Quyi yuza qiyaligi", default: 0.75, min: 0, step: 0.05 }],
    pset: { name: "Pset_GES_Dam", fields: [{ key: "Turi", label: "Turi", type: "text", default: "beton og'irlik" }, { key: "Balandlik_m", label: "Balandlik", unit: "m", from: "height" }, { key: "Uzunlik_m", label: "Uzunlik", unit: "m", from: "length" }, { key: "GerbBelgisi_m", label: "Gerb belgisi", unit: "m", default: 0 }, { key: "GerbKengligi_m", label: "Gerb kengligi", unit: "m", from: "crest" }, { key: "TagKengligi_m", label: "Tag kengligi", unit: "m", from: "=base" }, { key: "TagBelgisi_m", label: "Tag belgisi", unit: "m", default: 0 }, { key: "BetonKlassi", label: "Beton klassi", type: "select", default: "B20", options: CONCRETE_CLASSES }] },
    build: (p) => { const H = n(p.height, 40), bc = n(p.crest, 6), mu = n(p.mu, 0.05), md = n(p.md, 0.75); return prism([[0, 0], [mu * H + bc + md * H, 0], [mu * H + bc, H], [mu * H, H]], n(p.length, 60)); } },
  { id: "penstock", title: "Bosimli quvur", icon: "pipe", group: "GES inshootlari", ifcClass: "IfcPipeSegment", color: "#6f8fb5",
    params: [{ key: "length", label: "Uzunlik", unit: "m", default: 30, min: 0.5 }, { key: "d", label: "Diametr", unit: "m", default: 2.5, min: 0.05, step: 0.1 }, { key: "slope", label: "Qiyalik (pastga)", unit: "°", default: 0, min: -89, step: 1 }],
    pset: { name: "Pset_GES_Penstock", fields: [{ key: "Diametr_m", label: "Diametr", unit: "m", from: "d" }, { key: "Uzunlik_m", label: "Uzunlik", unit: "m", from: "length" }, { key: "Gadirbudirlik_mm", label: "G'adir-budirlik", unit: "mm", default: 0.1 }, { key: "Material", label: "Po'lat markasi", type: "select", default: "S355 / 09G2S", options: STEEL_GRADES }, { key: "DevorQalinligi_mm", label: "Devor qalinligi", unit: "mm", default: 20 }] },
    build: (p) => { const L = n(p.length, 60), r = n(p.d, 3) / 2; const g = new THREE.CylinderGeometry(r, r, L, 28); g.rotateZ(-Math.PI / 2); g.translate(L / 2, r, 0); g.rotateZ(-THREE.MathUtils.degToRad(n(p.slope, 0))); return g; } },
  { id: "turbine", title: "Turbina agregati", icon: "turbine", group: "GES inshootlari", ifcClass: "IfcFlowMovingDevice", color: "#3aa6a0",
    params: [{ key: "r", label: "Radius (spiral kamera)", unit: "m", default: 3, min: 0.2 }, { key: "h", label: "Balandlik", unit: "m", default: 6, min: 0.2 }],
    pset: { name: "Pset_GES_Turbine", fields: [{ key: "Turi", label: "Turi", type: "text", default: "Francis" }, { key: "Quvvat_MW", label: "Quvvat", unit: "MW", default: 25 }, { key: "Napor_m", label: "Napor", unit: "m", default: 45 }, { key: "Sarf_m3s", label: "Sarf", unit: "m³/s", default: 62 }, { key: "FIK", label: "FIK", default: 0.92 }] },
    build: (p) => { const r = n(p.r, 3), h = n(p.h, 6); const a = new THREE.CylinderGeometry(r, r, h * 0.55, 32); a.translate(0, h * 0.275, 0); const b = new THREE.CylinderGeometry(r * 0.45, r * 0.45, h * 0.45, 24); b.translate(0, h * 0.55 + h * 0.225, 0); return mergeGeometries([a, b]); } },
  { id: "spillway", title: "Suv tashlagich", icon: "waves", group: "GES inshootlari", ifcClass: "IfcSlab", color: "#8d8f93",
    params: [{ key: "width", label: "Kenglik (oqim bo'ylab emas)", unit: "m", default: 20, min: 1 }, { key: "height", label: "Ostona balandligi", unit: "m", default: 12, min: 0.5 }, { key: "crest", label: "Ostona kengligi", unit: "m", default: 4, min: 0.2 }, { key: "md", label: "Chute qiyaligi", default: 0.8, min: 0.1, step: 0.05 }],
    pset: { name: "Pset_GES_Spillway", fields: [{ key: "Kenglik_m", label: "Kenglik", unit: "m", from: "width" }, { key: "OstonaBelgisi_m", label: "Ostona belgisi", unit: "m", default: 0 }, { key: "SarfKoeff", label: "Sarf koeff.", default: 0.49 }, { key: "Darvozalar", label: "Darvozalar", type: "int", default: 2 }, { key: "BetonKlassi", label: "Beton klassi", type: "select", default: "B30", options: CONCRETE_CLASSES }] },
    build: (p) => { const H = n(p.height, 20), bc = n(p.crest, 4), md = n(p.md, 0.8); return prism([[0, 0], [bc + md * H, 0], [bc, H], [0, H]], n(p.width, 40)); } },
  { id: "powerhouse", title: "Mashina zali", icon: "house", group: "GES inshootlari", ifcClass: "IfcBuildingElementProxy", color: "#b0a088",
    params: [{ key: "w", label: "Uzunlik (X)", unit: "m", default: 40, min: 1 }, { key: "d", label: "Kenglik (Y)", unit: "m", default: 20, min: 1 }, { key: "h", label: "Balandlik", unit: "m", default: 18, min: 1 }],
    pset: { name: "Pset_GES_Powerhouse", fields: [{ key: "BetonKlassi", label: "Beton klassi (karkas)", type: "select", default: "B25", options: CONCRETE_CLASSES }, { key: "Agregatlar", label: "Agregatlar soni", type: "int", default: 2 }, { key: "PolBelgisi_m", label: "Pol belgisi", unit: "m", default: 0 }] },
    build: (p) => box(n(p.w, 60), n(p.d, 25), n(p.h, 30)) },
  { id: "transformer", title: "Transformator", icon: "zap", group: "GES inshootlari", ifcClass: "IfcTransformer", color: "#b98626",
    params: [{ key: "w", label: "Uzunlik", unit: "m", default: 6, min: 0.2 }, { key: "d", label: "Kenglik", unit: "m", default: 4, min: 0.2 }, { key: "h", label: "Balandlik", unit: "m", default: 5, min: 0.2 }],
    pset: { name: "Pset_GES_Transformer", fields: [{ key: "Quvvat_MVA", label: "Quvvat", unit: "MVA", default: 40 }, { key: "KuchlanishYuqori_kV", label: "Yuqori kuchlanish", unit: "kV", default: 110 }, { key: "KuchlanishPast_kV", label: "Past kuchlanish", unit: "kV", default: 10.5 }, { key: "Sovitish", label: "Sovitish (IEC 60076)", type: "select", default: "ONAF", options: [["ONAN", "ONAN"], ["ONAF", "ONAF"], ["OFAF", "OFAF"], ["ODAF", "ODAF"]] }] },
    build: (p) => box(n(p.w, 6), n(p.d, 4), n(p.h, 5)) },
  { id: "intake", title: "Suv qabul qilgich", icon: "droplet", group: "GES inshootlari", ifcClass: "IfcBuildingElementProxy", color: "#7d9bb5",
    params: [{ key: "w", label: "Kenglik", unit: "m", default: 8, min: 0.5 }, { key: "d", label: "Chuqurlik (Y)", unit: "m", default: 8, min: 0.5 }, { key: "h", label: "Balandlik", unit: "m", default: 15, min: 0.5 }],
    pset: { name: "Pset_GES_Intake", fields: [{ key: "OstonaBelgisi_m", label: "Ostona belgisi", unit: "m", default: 0 }, { key: "HisobiySarf_m3s", label: "Hisobiy sarf", unit: "m³/s", default: 120 }, { key: "Teshiklar", label: "Teshiklar soni", type: "int", default: 2 }, { key: "PanjaraOraligi_mm", label: "Panjara oralig'i", unit: "mm", default: 100 }, { key: "Balandlik_m", label: "Balandlik", unit: "m", from: "h" }] },
    build: (p) => box(n(p.w, 12), n(p.d, 10), n(p.h, 25)) },
];

/** Mavjud IFC elementni tahrirlash: geometriya modeldan olinadi (Draft.mesh), parametrlar yo'q; GUID saqlanadi. */
export const MESH_KIND: DraftKind = { id: "mesh", title: "Element (tahrir)", icon: "box", group: "Mavjud", ifcClass: "IfcBuildingElementProxy", color: "#c9a86a", params: [], build: () => new THREE.BufferGeometry() };
/** Mavjud elementni o'chirish belgisi (commitda olib tashlanadi; geometriyasi yo'q). */
export const DELETED_KIND: DraftKind = { id: "deleted", title: "O'chirilgan element", icon: "trash", group: "Mavjud", ifcClass: "", color: "#aa4444", params: [], build: () => new THREE.BufferGeometry() };

export const DRAFT_KIND_BY_ID: Record<string, DraftKind> = Object.fromEntries([...DRAFT_KINDS, MESH_KIND, DELETED_KIND].map((k) => [k.id, k]));

/** IFC lokal mesh (x, y, z — Z yuqoriga) → three geometriya (x, z, −y). */
export function fromIfcMesh(mesh: { vertices: number[][]; faces: number[][] }): THREE.BufferGeometry {
  const pos: number[] = [];
  for (const f of mesh.faces) {
    for (const i of f) { const v = mesh.vertices[i]; if (!v) continue; pos.push(v[0], v[2], -v[1]); }
  }
  return fixWinding(pos);
}

export function defaultParams(kind: DraftKind): Record<string, number | string> {
  return Object.fromEntries(kind.params.map((p) => [p.key, p.default]));
}

/** Pset qiymatlari: parametrlardan olinadiganlar (from) yangilanadi, qolganlari saqlanadi. */
export function derivePset(kind: DraftKind, params: Record<string, number | string>, prev: Record<string, unknown> = {}): Record<string, unknown> {
  if (!kind.pset) return {};
  const out: Record<string, unknown> = {};
  for (const f of kind.pset.fields) {
    if (f.from === "=base" && kind.id === "dam") { const H = n(params.height), out_ = n(params.mu) * H + n(params.crest) + n(params.md) * H; out[f.key] = Math.round(out_ * 100) / 100; continue; }
    if (f.from) out[f.key] = params[f.from];
    else out[f.key] = prev[f.key] ?? f.default ?? "";
  }
  return out;
}

/** Bir nechta geometriyani birlashtirish (faqat position/normal). */
function mergeGeometries(gs: THREE.BufferGeometry[]): THREE.BufferGeometry {
  const pos: number[] = [];
  for (const g of gs) {
    const ng = g.index ? g.toNonIndexed() : g;
    const a = ng.getAttribute("position");
    for (let i = 0; i < a.count; i++) pos.push(a.getX(i), a.getY(i), a.getZ(i));
  }
  return fixWinding(pos);
}

/** Geometriyani IFC lokal mesh ga (vertices/faces) aylantirish: IFC (x, y, z) = three (x, −z, y), masshtab qo'llangan. */
export function toIfcMesh(geom: THREE.BufferGeometry, scale: [number, number, number] = [1, 1, 1]): { vertices: number[][]; faces: number[][] } {
  const ng = geom.index ? geom.toNonIndexed() : geom;
  const a = ng.getAttribute("position");
  const key = new Map<string, number>();
  const vertices: number[][] = [];
  const faces: number[][] = [];
  const idx = (x: number, y: number, z: number) => {
    const k = `${x.toFixed(5)},${y.toFixed(5)},${z.toFixed(5)}`;
    let i = key.get(k);
    if (i === undefined) { i = vertices.length; key.set(k, i); vertices.push([x, y, z]); }
    return i;
  };
  for (let i = 0; i < a.count; i += 3) {
    const f: number[] = [];
    for (let j = 0; j < 3; j++) {
      const x = a.getX(i + j) * scale[0], y = a.getY(i + j) * scale[2], z = a.getZ(i + j) * scale[1];
      f.push(idx(Math.round(x * 1e5) / 1e5, Math.round(-z * 1e5) / 1e5, Math.round(y * 1e5) / 1e5));
    }
    if (f[0] !== f[1] && f[1] !== f[2] && f[0] !== f[2]) faces.push(f);
  }
  // Imzoli hajm manfiy bo'lsa (o'qlar almashuvi tufayli) — yo'nalishni teskari qilamiz
  let vol = 0;
  for (const [i, j, k] of faces) { const A = vertices[i], B = vertices[j], C = vertices[k]; vol += A[0] * (B[1] * C[2] - B[2] * C[1]) - A[1] * (B[0] * C[2] - B[2] * C[0]) + A[2] * (B[0] * C[1] - B[1] * C[0]); }
  if (vol < 0) for (const f of faces) { const t = f[1]; f[1] = f[2]; f[2] = t; }
  return { vertices, faces };
}
