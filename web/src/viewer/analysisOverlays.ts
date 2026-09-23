import * as THREE from "three";
import { PAL } from "./palette";

/** Tahlil qatlamlari geometriyasi (FE-06: Viewer.ts dan ajratildi) — sahna holatiga bog'liq emas: element bbox i va
 * natija ma'lumotidan THREE obyekt quradi; Viewer uni sahnaga qo'shadi/olib tashlaydi. Xatti-harakat o'zgarmagan. */

export interface SectionSpec {
  profile?: [number, number][] | undefined;
  h1?: number | undefined;
  h2?: number | undefined;
  phreatic?: { x: number[]; y: number[] } | undefined;
  forces?: { name: string; v_kn: number; h_kn: number; arm_v_m: number; arm_h_m: number }[] | undefined;
}

/** Obyekt va bolalarining geometriya/material/tekstura resurslarini bo'shatish. */
export function disposeObject3D(root: THREE.Object3D) {
  root.traverse((o) => { const m = o as THREE.Mesh; m.geometry?.dispose?.(); const mat = m.material as THREE.Material | undefined; if (mat && "map" in mat) ((mat as THREE.SpriteMaterial).map)?.dispose(); mat?.dispose?.(); });
}

/** Skalyar maydon tekisligi (CFD): elementning eng uzun gorizontal o'qi bo'ylab, vertikal bo'yicha bbox balandligi.
 * grid — nx×ny qiymatlar 0..1 (chapdan o'ngga, pastdan yuqoriga). */
export function buildFieldPlane(box: THREE.Box3, grid: { nx: number; ny: number; values: number[] }, colorAt: (t: number) => [number, number, number]): THREE.Mesh {
  const size = new THREE.Vector3();
  box.getSize(size);
  const center = new THREE.Vector3();
  box.getCenter(center);
  const alongX = size.x >= size.z; // eng uzun gorizontal o'q
  const w = alongX ? size.x : size.z;
  const h = size.y;
  const geo = new THREE.PlaneGeometry(w, h, grid.nx - 1, grid.ny - 1);
  const colors = new Float32Array(geo.attributes.position.count * 3);
  // PlaneGeometry vertexlari yuqoridan pastga qatorlar bilan keladi
  for (let j = 0; j < grid.ny; j++) {
    for (let i = 0; i < grid.nx; i++) {
      const v = grid.values[(grid.ny - 1 - j) * grid.nx + i] ?? 0;
      const [r, g, b] = colorAt(Math.max(0, Math.min(1, v)));
      const k = (j * grid.nx + i) * 3;
      colors[k] = r;
      colors[k + 1] = g;
      colors[k + 2] = b;
    }
  }
  geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  const mat = new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide, transparent: true, opacity: 0.95, depthTest: false });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.renderOrder = 10;
  if (!alongX) mesh.rotation.y = Math.PI / 2;
  mesh.position.copy(center);
  return mesh;
}

/** To'g'on ko'ndalang kesimi sxemasi (dam_stability / seepage): hisob profili, suv sathlari, depressiya egri
 * chizig'i, kuchlar (strelka + yorliq) — element bbox iga moslab. */
export function buildSectionOverlay(box: THREE.Box3, spec: SectionSpec): THREE.Group {
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const alongX = size.x >= size.z; // uzun o'q
  const H = size.y, base = box.min.y;
  // kesim koordinatalari: u — yuqori byef tovonidan quyi byef tomon (0..B), v — tagdan yuqoriga
  // three da: alongX → ko'ndalang o'q Z, yuqori byef = min.z (IFC +y); alongZ → ko'ndalang o'q X, yuqori byef = max.x
  const B = alongX ? size.z : size.x;
  const P = (u: number, v: number, t = 0): THREE.Vector3 => alongX
    ? new THREE.Vector3(center.x + t, base + v, box.min.z + u)
    : new THREE.Vector3(box.max.x - u, base + v, center.z + t);
  const g = new THREE.Group();
  g.name = "section";
  g.renderOrder = 20;
  const line = (pts: THREE.Vector3[], color: string, loop = false) => {
    const geo = new THREE.BufferGeometry().setFromPoints(pts);
    const mat = new THREE.LineBasicMaterial({ color: new THREE.Color(color), depthTest: false, transparent: true, opacity: 0.95 });
    const l = loop ? new THREE.LineLoop(geo, mat) : new THREE.Line(geo, mat);
    l.renderOrder = 20;
    g.add(l);
  };
  const label = (text: string, at: THREE.Vector3, color: string = PAL.labelInk) => {
    const c = document.createElement("canvas");
    c.width = 256; c.height = 64;
    const ctx = c.getContext("2d")!;
    ctx.fillStyle = PAL.labelBg; ctx.fillRect(0, 0, c.width, c.height);
    ctx.font = "bold 26px system-ui, sans-serif"; ctx.fillStyle = color; ctx.textBaseline = "middle"; ctx.fillText(text, 10, 32);
    const tex = new THREE.CanvasTexture(c);
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false, transparent: true }));
    const sc = Math.max(H, 4) * 0.22;
    sp.scale.set(sc * 4, sc, 1);
    sp.position.copy(at);
    sp.renderOrder = 21;
    g.add(sp);
  };
  // hisob profili (poligon) — kesim o'rtasida; masshtab: profil asosi → element asosi
  const prof = spec.profile ?? [];
  const profB = prof.length ? Math.max(...prof.map((q) => q[0])) : B;
  const su = prof.length && profB > 0 ? B / profB : 1;
  const profH = prof.length ? Math.max(...prof.map((q) => q[1])) : H;
  const sv = prof.length && profH > 0 ? H / profH : 1;
  if (prof.length) line(prof.map(([u, v]) => P(u * su, v * sv)), PAL.highlight, true);
  // suv sathlari (h1 yuqori, h2 quyi byef) — qisqa gorizontal chiziqlar
  if (spec.h1 != null && spec.h1 > 0) { line([P(-B * 0.6, spec.h1 * sv), P(0, spec.h1 * sv)], PAL.waterLine); label(`h₁ ${spec.h1.toFixed(1)} m`, P(-B * 0.6, spec.h1 * sv + H * 0.06), PAL.labelWater); }
  if (spec.h2 != null && spec.h2 > 0) { line([P(B, spec.h2 * sv), P(B * 1.6, spec.h2 * sv)], PAL.waterLine); label(`h₂ ${spec.h2.toFixed(1)} m`, P(B * 1.6, spec.h2 * sv + H * 0.06), PAL.labelWater); }
  // depressiya egri chizig'i — to'g'on bo'ylab yuza (shaffof ko'k)
  if (spec.phreatic && spec.phreatic.x.length > 1) {
    const xs = spec.phreatic.x, ys = spec.phreatic.y;
    const L = xs[xs.length - 1] || 1;
    const yMax = Math.max(...ys, 1);
    const sph = Math.min(1, H / yMax); // egri chiziq elementdan baland chiqmasin
    const len = alongX ? size.x : size.z;
    const pos: number[] = [];
    for (let i = 0; i < xs.length; i++) {
      const a = P((xs[i] / L) * B, ys[i] * sph, -len / 2), b = P((xs[i] / L) * B, ys[i] * sph, len / 2);
      pos.push(a.x, a.y, a.z, b.x, b.y, b.z);
    }
    const idx: number[] = [];
    for (let i = 0; i < xs.length - 1; i++) { const k = i * 2; idx.push(k, k + 1, k + 2, k + 1, k + 3, k + 2); }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    geo.setIndex(idx);
    geo.computeVertexNormals();
    const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: new THREE.Color(PAL.waterLine), transparent: true, opacity: 0.45, side: THREE.DoubleSide, depthTest: false }));
    m.renderOrder = 19;
    g.add(m);
    line(xs.map((x, i) => P((x / L) * B, ys[i] * sph)), PAL.waterShallow);
    label("Depressiya egri chizig'i", P(B * 0.45, ys[Math.floor(ys.length / 2)] * sph + H * 0.08), PAL.labelWater);
  }
  // kuchlar — strelkalar (uzunlik kattalikka mutanosib), yorliqlar
  if (spec.forces?.length) {
    const fmax = Math.max(...spec.forces.map((f) => Math.max(Math.abs(f.v_kn), Math.abs(f.h_kn))), 1);
    const lenOf = (f: number) => H * (0.15 + 0.45 * Math.abs(f) / fmax);
    const dirDown = alongX ? new THREE.Vector3(0, 0, 1) : new THREE.Vector3(-1, 0, 0); // quyi byef tomon
    for (const f of spec.forces) {
      const isV = Math.abs(f.v_kn) >= Math.abs(f.h_kn);
      const mag = isV ? f.v_kn : f.h_kn;
      if (!mag) continue;
      const len = lenOf(mag);
      const color = f.name.startsWith("Og'irlik") ? PAL.forceWeight : f.name.startsWith("Filtratsion") ? PAL.forceSeepage : f.name.startsWith("Inersiya") || f.name.startsWith("Westergaard") ? PAL.forceInertia : PAL.waterLine;
      let tip: THREE.Vector3, dir: THREE.Vector3;
      if (isV) {
        tip = P(B - f.arm_v_m * su, 0); // toe dan masofa → yuqori tovondan u = B − arm
        dir = new THREE.Vector3(0, mag > 0 ? -1 : 1, 0); // W pastga, U (manfiy) yuqoriga
        if (mag > 0) tip = P(B - f.arm_v_m * su, H * 0.55); // og'irlik — og'irlik markazi balandligida
      } else {
        const up = mag > 0; // yuqori byef tomonidan quyi byefga
        tip = up ? P(0, f.arm_h_m * sv) : P(B, f.arm_h_m * sv);
        dir = up ? dirDown.clone() : dirDown.clone().negate();
      }
      const origin = tip.clone().sub(dir.clone().multiplyScalar(len));
      const arrow = new THREE.ArrowHelper(dir, origin, len, new THREE.Color(color), len * 0.25, len * 0.12);
      arrow.traverse((o) => { const mm = (o as THREE.Mesh).material as THREE.Material | undefined; if (mm) { mm.depthTest = false; mm.transparent = true; } o.renderOrder = 21; });
      g.add(arrow);
      label(`${f.name.split(" ")[0]} ${Math.abs(mag).toLocaleString("en", { maximumFractionDigits: 0 })} kN/m`, origin.clone().add(new THREE.Vector3(0, H * 0.07, 0)), color);
    }
  }
  return g;
}
