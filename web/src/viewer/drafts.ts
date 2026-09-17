/* Qoralama obyektlar (web da yaratilgan elementlar): Blender/3ds Max uslubida qo'shish → joylashtirish
   (sichqoncha bilan) → G/R/S (TransformControls) → parametrlar → IFC ga commit.
   Viewer dan alohida sinf: sahna, kamera, konteynerdan foydalanadi. */
import * as THREE from "three";
import { TransformControls } from "three/examples/jsm/controls/TransformControls.js";
import type { Viewer } from "./Viewer";
import { DRAFT_KIND_BY_ID, defaultParams, derivePset, fromIfcMesh, toIfcMesh, type DraftKind } from "./draftKinds";

export interface DraftTransform { x: number; y: number; z: number; rz: number; sx: number; sy: number; sz: number }
export interface Draft {
  id: number | null; // server id (null — hali saqlanmagan)
  uid: string; // lokal kalit
  kind: string;
  name: string;
  params: Record<string, number | string>;
  transform: DraftTransform;
  psets: Record<string, Record<string, unknown>>;
  visible: boolean;
  /** kind "mesh": geometriya (IFC lokal, saqlangan); "deleted": yo'q */
  mesh?: { vertices: number[][]; faces: number[][] } | null;
  /** mavjud IFC element tahriri/o'chirish — asl GlobalId (commitda GUID saqlanadi) */
  sourceGuid?: string | null;
  ifcClass?: string | null; // mesh turi uchun asl klass
  color?: string | null;
}
export type GizmoMode = "translate" | "rotate" | "scale";
type Listener<T> = (v: T) => void;
type Snap = Pick<Draft, "name" | "params" | "psets" | "transform" | "visible">;
type HistoryEntry = ({ t: number; uid: string; kind: "edit"; before: Snap; after: Snap } | { t: number; uid: string; kind: "remove"; draft: Draft } | { t: number; uid: string; kind: "add" }) & { g?: number }; // g — guruh amali (bitta undo)
const snapOf = (d: Draft): Snap => JSON.parse(JSON.stringify({ name: d.name, params: d.params, psets: d.psets, transform: d.transform, visible: d.visible }));

let uidCounter = 1;

export class DraftManager {
  private group = new THREE.Group();
  private meshes = new Map<string, THREE.Mesh>();
  private drafts = new Map<string, Draft>();
  private selectedUid: string | null = null;
  private tc: TransformControls | null = null;
  private ghost: THREE.Mesh | null = null;
  private placingKind: DraftKind | null = null;
  private placingParams: Record<string, number | string> = {};
  private raycaster = new THREE.Raycaster();
  private ground = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  private listeners: Listener<Draft[]>[] = [];
  private selListeners: Listener<Draft | null>[] = [];
  private changeListeners: Listener<Draft>[] = []; // saqlash uchun (debounce tashqarida)
  private placeListeners: Listener<Draft>[] = [];
  private modeListeners: Listener<GizmoMode | null>[] = [];
  private onDown = (e: PointerEvent) => this.pointerDown(e);
  private onMove = (e: PointerEvent) => this.pointerMove(e);
  private onUp = (e: PointerEvent) => this.pointerUp(e);
  private downAt: [number, number] | null = null;
  private counters: Record<string, number> = {};
  private snapOff: (() => void) | null = null;
  // Bekor qilish / qaytarish (Ctrl+Z / Ctrl+Shift+Z): o'zgarish, o'chirish, qo'shish
  private history: HistoryEntry[] = [];
  private hIndex = 0;
  private gizmoBefore: Snap | null = null;
  private groupBefore = new Map<string, Snap>();
  private removeListeners: Listener<Draft>[] = []; // undo bilan olib tashlanganda (server yozuvi ham o'chsin)

  constructor(private viewer: Viewer) {
    this.group.name = "drafts";
    viewer.world.scene.three.add(this.group);
    const dom = viewer.world.renderer!.three.domElement;
    dom.addEventListener("pointerdown", this.onDown);
    dom.addEventListener("pointermove", this.onMove);
    dom.addEventListener("pointerup", this.onUp);
  }

  dispose() {
    const dom = this.viewer.world.renderer?.three.domElement;
    dom?.removeEventListener("pointerdown", this.onDown);
    dom?.removeEventListener("pointermove", this.onMove);
    dom?.removeEventListener("pointerup", this.onUp);
    this.tc?.detach();
    this.tc?.dispose();
    this.snapOff?.();
    this.viewer.world.scene.three.remove(this.group);
  }

  // --- obunalar ---
  subscribe(l: Listener<Draft[]>) { this.listeners.push(l); l(this.list()); return () => { this.listeners = this.listeners.filter((x) => x !== l); }; }
  subscribeSelection(l: Listener<Draft | null>) { this.selListeners.push(l); return () => { this.selListeners = this.selListeners.filter((x) => x !== l); }; }
  subscribeChange(l: Listener<Draft>) { this.changeListeners.push(l); return () => { this.changeListeners = this.changeListeners.filter((x) => x !== l); }; }
  subscribePlaced(l: Listener<Draft>) { this.placeListeners.push(l); return () => { this.placeListeners = this.placeListeners.filter((x) => x !== l); }; }
  subscribeRemoved(l: Listener<Draft>) { this.removeListeners.push(l); return () => { this.removeListeners = this.removeListeners.filter((x) => x !== l); }; }
  subscribeMode(l: Listener<GizmoMode | null>) { this.modeListeners.push(l); return () => { this.modeListeners = this.modeListeners.filter((x) => x !== l); }; }
  private emit() { const l = this.list(); this.listeners.forEach((f) => f(l)); }
  private emitSel() { const d = this.selected; this.selListeners.forEach((f) => f(d)); }
  private emitChange(d: Draft) { this.changeListeners.forEach((f) => f(d)); }

  list(): Draft[] { return [...this.drafts.values()]; }
  get selected(): Draft | null { return this.selectedUid ? this.drafts.get(this.selectedUid) ?? null : null; }
  get placing(): DraftKind | null { return this.placingKind; }
  get(uid: string) { return this.drafts.get(uid) ?? null; }

  // --- Material / mesh ---
  private material(kind: DraftKind, ghost = false, color?: string | null) {
    return new THREE.MeshStandardMaterial({ color: new THREE.Color(color || kind.color), roughness: 0.7, metalness: 0.05, transparent: ghost, opacity: ghost ? 0.45 : 1, side: THREE.DoubleSide });
  }
  /** Viewport shading qoralamalarga ham (Solid / Wireframe / X-ray). */
  private shadingMode: "solid" | "wire" | "xray" | "rendered" = "solid";
  setShading(mode: "solid" | "wire" | "xray" | "rendered") {
    this.shadingMode = mode;
    for (const m of this.meshes.values()) this.applyShading(m.material as THREE.MeshStandardMaterial);
  }
  private applyShading(mat: THREE.MeshStandardMaterial) {
    const mode = this.shadingMode;
    mat.wireframe = mode === "wire";
    mat.transparent = mode === "xray";
    mat.opacity = mode === "xray" ? 0.35 : 1;
    mat.depthWrite = mode !== "xray";
    mat.needsUpdate = true;
  }
  private geometryFor(d: Draft, kind: DraftKind): THREE.BufferGeometry {
    if (d.mesh && d.mesh.vertices?.length) return fromIfcMesh(d.mesh);
    return kind.build(d.params);
  }
  private applyTransform(mesh: THREE.Mesh, t: DraftTransform) {
    mesh.position.copy(this.viewer.ifcToThree([t.x, t.y, t.z]));
    mesh.rotation.set(0, THREE.MathUtils.degToRad(t.rz), 0);
    mesh.scale.set(t.sx, t.sz, t.sy);
  }
  private readTransform(mesh: THREE.Mesh): DraftTransform {
    const [x, y, z] = this.viewer.threeToIfc(mesh.position);
    return { x: r3(x), y: r3(y), z: r3(z), rz: r3(THREE.MathUtils.radToDeg(mesh.rotation.y)), sx: r3(mesh.scale.x), sy: r3(mesh.scale.z), sz: r3(mesh.scale.y) };
  }

  /** Serverdan yuklangan yoki yangi qoralamani sahnaga qo'shish. */
  add(d: Omit<Draft, "uid" | "visible"> & { uid?: string; visible?: boolean }, select = false): Draft {
    const kind = DRAFT_KIND_BY_ID[d.kind];
    if (!kind) throw new Error(`Noma'lum tur: ${d.kind}`);
    const draft: Draft = { uid: d.uid ?? `d${uidCounter++}`, visible: d.visible ?? true, ...d } as Draft;
    const mesh = new THREE.Mesh(this.geometryFor(draft, kind), this.material(kind, false, draft.color));
    this.applyShading(mesh.material as THREE.MeshStandardMaterial);
    if (draft.kind === "deleted") { draft.visible = false; mesh.visible = false; }
    mesh.name = draft.name;
    mesh.userData.uid = draft.uid;
    mesh.castShadow = true;
    this.applyTransform(mesh, draft.transform);
    mesh.visible = draft.visible;
    this.group.add(mesh);
    this.meshes.set(draft.uid, mesh);
    this.drafts.set(draft.uid, draft);
    this.emit();
    if (select) this.select(draft.uid);
    if (!this.restoring && d.id == null) this.push({ t: Date.now(), uid: draft.uid, kind: "add" });
    return draft;
  }

  // --- Tarix ---
  private restoring = false;
  private push(e: HistoryEntry) {
    this.history.length = this.hIndex;
    // ketma-ket kichik tahrirlar (panelda yozish) — bitta yozuvga birlashtiriladi
    const last = this.history[this.history.length - 1];
    if (e.kind === "edit" && last && last.kind === "edit" && last.uid === e.uid && !e.g && !last.g && e.t - last.t < 1200) { last.after = e.after; last.t = e.t; return; }
    this.history.push(e);
    if (this.history.length > 200) this.history.shift();
    this.hIndex = this.history.length;
  }
  get canUndo() { return this.hIndex > 0; }
  get canRedo() { return this.hIndex < this.history.length; }
  private applySnap(uid: string, sn: Snap) {
    this.restoring = true;
    try { this.update(uid, { name: sn.name, params: sn.params, psets: sn.psets, transform: sn.transform, visible: sn.visible }); } finally { this.restoring = false; }
  }
  undo(): string | null {
    if (!this.canUndo) return null;
    let msg = this.undoOne();
    // guruh amali — barcha a'zolar birga
    const g = this.history[this.hIndex]?.g;
    while (g && this.hIndex > 0 && this.history[this.hIndex - 1].g === g) msg = this.undoOne() ?? msg;
    return msg;
  }
  private undoOne(): string | null {
    const e = this.history[--this.hIndex];
    this.restoring = true;
    try {
      if (e.kind === "edit") { this.applySnap(e.uid, e.before); return `Bekor: ${this.drafts.get(e.uid)?.name ?? ""} o'zgarishi`; }
      if (e.kind === "add") { const d = this.drafts.get(e.uid); if (d) { this.removeListeners.forEach((f) => f(d)); this.remove(e.uid); } return `Bekor: qo'shish`; }
      const nd = this.add({ ...e.draft, id: null }, false); // o'chirilgan qaytadi (serverda yangi yozuv)
      this.placeListeners.forEach((f) => f(nd));
      return `Bekor: ${e.draft.name} o'chirilishi`;
    } finally { this.restoring = false; }
  }
  redo(): string | null {
    if (!this.canRedo) return null;
    let msg = this.redoOne();
    const g = this.history[this.hIndex - 1]?.g;
    while (g && this.hIndex < this.history.length && this.history[this.hIndex].g === g) msg = this.redoOne() ?? msg;
    return msg;
  }
  private redoOne(): string | null {
    const e = this.history[this.hIndex++];
    this.restoring = true;
    try {
      if (e.kind === "edit") { this.applySnap(e.uid, e.after); return `Qaytarildi: ${this.drafts.get(e.uid)?.name ?? ""}`; }
      if (e.kind === "remove") { const d = this.drafts.get(e.uid); if (d) { this.removeListeners.forEach((f) => f(d)); this.remove(e.uid); } return `Qaytarildi: o'chirish`; }
      return null; // add ni qayta bajarish — mumkin emas (uid yo'qolgan)
    } finally { this.restoring = false; }
  }

  private nextName(kind: DraftKind) {
    this.counters[kind.id] = (this.counters[kind.id] ?? 0) + 1;
    return `${kind.title.split(" (")[0]} ${this.counters[kind.id]}`;
  }

  /** Blender "Add": joylashtirish rejimi — sharpa kursor ostidagi yuzada yuradi, chap tugma — qo'yish. */
  startPlacing(kindId: string, params?: Record<string, number | string>) {
    const kind = DRAFT_KIND_BY_ID[kindId];
    if (!kind) return;
    this.cancelPlacing();
    this.placingKind = kind;
    this.placingParams = params ?? defaultParams(kind);
    this.ghost = new THREE.Mesh(kind.build(this.placingParams), this.material(kind, true));
    this.ghost.visible = false;
    this.group.add(this.ghost);
    this.viewer.setTool("select");
    this.viewer.highlighter.enabled = false;
    void this.viewer.clearSelection(); // model elementi tanlangan bo'lsa — ajratib qo'yamiz (yangi obyekt alohida)
    this.viewer.statusMsg("Joylashtirish: chap tugma — qo'yish, Esc — bekor. Keyin G — surish, R — burish, S — masshtab");
  }
  cancelPlacing() {
    if (this.ghost) { this.group.remove(this.ghost); this.ghost.geometry.dispose(); this.ghost = null; }
    if (this.placingKind) { this.placingKind = null; this.viewer.highlighter.enabled = true; this.viewer.statusMsg("Tanlash"); }
  }

  /** Kursor → 3D nuqta: avval qoralamalar/model (raycast), bo'lmasa yer tekisligi (grid sathi). */
  private pick(e: PointerEvent): Promise<THREE.Vector3 | null> { return this.pickPoint(e.clientX, e.clientY); }
  /** Ekran nuqtasi (client px) → sahnadagi 3D nuqta (qoralama, model yoki yer). */
  async pickPoint(clientX: number, clientY: number): Promise<THREE.Vector3 | null> {
    const e = { clientX, clientY };
    const dom = this.viewer.world.renderer!.three.domElement;
    const rect = dom.getBoundingClientRect();
    const ndc = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
    this.raycaster.setFromCamera(ndc, this.viewer.world.camera.three);
    const hits = this.raycaster.intersectObjects([...this.meshes.values()].filter((m) => m.visible), false);
    if (hits.length) return hits[0].point.clone();
    if (this.viewer.model) {
      try {
        const hit = await this.viewer.model.raycast({ camera: this.viewer.world.camera.three, mouse: new THREE.Vector2(e.clientX - rect.left, e.clientY - rect.top), dom });
        if (hit?.point) return new THREE.Vector3(hit.point.x, hit.point.y, hit.point.z);
      } catch { /* */ }
      const pb = this.viewer.rayBoxes(this.raycaster.ray);
      if (pb) return pb;
    }
    this.ground.constant = -this.viewer.groundY();
    const p = new THREE.Vector3();
    return this.raycaster.ray.intersectPlane(this.ground, p) ? p : null;
  }

  private pointerDown(e: PointerEvent) { if (e.button === 0) this.downAt = [e.clientX, e.clientY]; }
  private async pointerMove(e: PointerEvent) {
    if (!this.placingKind || !this.ghost) return;
    const p = await this.pick(e);
    if (!p || !this.ghost) return;
    this.ghost.position.copy(p);
    this.ghost.visible = true;
  }
  private async pointerUp(e: PointerEvent) {
    if (e.button !== 0 || !this.downAt) return;
    const moved = Math.hypot(e.clientX - this.downAt[0], e.clientY - this.downAt[1]) > 4;
    this.downAt = null;
    if (moved) return;
    if (this.placingKind) {
      const p = await this.pick(e);
      if (!p) return;
      const kind = this.placingKind;
      const [x, y, z] = this.viewer.threeToIfc(p);
      const params = { ...this.placingParams };
      const draft = this.add({ id: null, kind: kind.id, name: this.nextName(kind), params, transform: { x: r3(x), y: r3(y), z: r3(z), rz: 0, sx: 1, sy: 1, sz: 1 }, psets: kind.pset ? { [kind.pset.name]: derivePset(kind, params) } : {} }, true);
      this.cancelPlacing();
      this.placeListeners.forEach((f) => f(draft));
      return;
    }
    if (this.tc?.dragging) return;
    // Tanlash: qoralama meshiga bosilsa — tanlash (highlighterdan ustun), bo'lmasa — bekor
    const dom = this.viewer.world.renderer!.three.domElement;
    const rect = dom.getBoundingClientRect();
    const ndc = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
    this.raycaster.setFromCamera(ndc, this.viewer.world.camera.three);
    const hits = this.raycaster.intersectObjects([...this.meshes.values()].filter((m) => m.visible), false);
    if (hits.length) {
      const uid = hits[0].object.userData.uid as string;
      if (e.shiftKey && this.selectedUid && this.selectedUid !== uid) this.toggleMulti(uid); // Shift — guruhga qo'shish/olib tashlash
      else this.select(uid);
      await this.viewer.clearSelection();
    } else if (this.selectedUid) this.select(null);
  }

  // --- Guruh (bir nechta qoralama birga suriladi/buriladi): Shift+bosish ---
  private multi = new Set<string>();
  get multiSelected(): string[] { return [...this.multi]; }
  toggleMulti(uid: string) {
    if (this.multi.has(uid)) { this.multi.delete(uid); this.setHighlight(uid, false); }
    else { this.multi.add(uid); this.setHighlight(uid, true); }
    this.viewer.statusMsg(`Guruh: ${1 + this.multi.size} obyekt — G/R/S birga (Shift+bosish — qo'shish/olib tashlash)`);
    this.emit();
  }
  private clearMulti() { for (const u of this.multi) this.setHighlight(u, false); this.multi.clear(); }
  /** Gizmo o'zgarishini guruhga qo'llash: surish — bir xil siljish; burish — asosiy obyekt atrofida; masshtab — o'z-o'zicha. */
  private applyToGroup(primary: THREE.Mesh, prev: { pos: THREE.Vector3; rotY: number; scale: THREE.Vector3 }) {
    if (!this.multi.size) return;
    const dp = primary.position.clone().sub(prev.pos);
    const dr = primary.rotation.y - prev.rotY;
    const ds = primary.scale.clone().divide(prev.scale);
    for (const u of this.multi) {
      const m = this.meshes.get(u);
      const d = this.drafts.get(u);
      if (!m || !d) continue;
      if (dp.lengthSq() > 0) m.position.add(dp);
      if (Math.abs(dr) > 1e-9) {
        const rel = m.position.clone().sub(primary.position);
        rel.applyAxisAngle(new THREE.Vector3(0, 1, 0), dr);
        m.position.copy(primary.position).add(rel);
        m.rotation.y += dr;
      }
      if (Math.abs(ds.x - 1) > 1e-9 || Math.abs(ds.y - 1) > 1e-9 || Math.abs(ds.z - 1) > 1e-9) m.scale.multiply(ds);
      d.transform = this.readTransform(m);
    }
  }

  private setHighlight(uid: string | null, on: boolean) {
    const m = uid ? this.meshes.get(uid) : null;
    if (!m) return;
    const mat = m.material as THREE.MeshStandardMaterial;
    mat.emissive = new THREE.Color(on ? "#f5a623" : "#000000"); // Blender uslubi: tanlangan — to'q sariq tus
    mat.emissiveIntensity = on ? 0.35 : 0;
  }

  select(uid: string | null) {
    if (uid === this.selectedUid) return;
    this.clearMulti();
    this.setHighlight(this.selectedUid, false);
    this.selectedUid = uid;
    this.setHighlight(uid, true);
    const mesh = uid ? this.meshes.get(uid) : null;
    if (mesh) {
      this.ensureGizmo();
      this.tc!.attach(mesh);
      void this.viewer.clearSelection();
      this.viewer.statusMsg(`Tanlangan: ${mesh.name} — G surish · R burish · S masshtab · Ctrl — qadam bilan · Shift+D nusxa · X o'chirish`);
    } else { this.tc?.detach(); }
    this.emitSel();
  }

  private ensureGizmo() {
    if (this.tc) return;
    const dom = this.viewer.world.renderer!.three.domElement;
    const tc = new TransformControls(this.viewer.world.camera.three, dom);
    tc.setSize(0.9);
    tc.showY = true;
    // Ctrl bosib turilsa — qadam bilan (Blender): 1 m surish, 15° burish, 0.1 masshtab
    const snap = (e: KeyboardEvent) => {
      const on = e.type === "keydown" ? e.ctrlKey || e.key === "Control" : e.key !== "Control" && e.ctrlKey;
      tc.translationSnap = on ? 1 : null;
      tc.rotationSnap = on ? THREE.MathUtils.degToRad(15) : null;
      tc.scaleSnap = on ? 0.1 : null;
    };
    window.addEventListener("keydown", snap);
    window.addEventListener("keyup", snap);
    this.snapOff = () => { window.removeEventListener("keydown", snap); window.removeEventListener("keyup", snap); };
    tc.addEventListener("dragging-changed", (ev) => { this.viewer.world.camera.controls.enabled = !(ev as unknown as { value: boolean }).value; });
    let prev: { pos: THREE.Vector3; rotY: number; scale: THREE.Vector3 } | null = null;
    tc.addEventListener("objectChange", () => {
      const obj = tc.object as THREE.Mesh | undefined;
      if (!obj) return;
      // Burilish faqat vertikal o'q atrofida (IFC z) — X/Z burilishni nolga
      obj.rotation.x = 0; obj.rotation.z = 0;
      const d = this.drafts.get(obj.userData.uid as string);
      if (d) d.transform = this.readTransform(obj);
      if (prev) this.applyToGroup(obj, prev);
      prev = { pos: obj.position.clone(), rotY: obj.rotation.y, scale: obj.scale.clone() };
    });
    tc.addEventListener("mouseDown", () => {
      const obj = tc.object as THREE.Mesh | undefined;
      const d = obj ? this.drafts.get(obj.userData.uid as string) : null;
      this.gizmoBefore = d ? snapOf(d) : null;
      prev = obj ? { pos: obj.position.clone(), rotY: obj.rotation.y, scale: obj.scale.clone() } : null;
      this.groupBefore = new Map([...this.multi].map((u) => [u, snapOf(this.drafts.get(u)!)]));
    });
    tc.addEventListener("mouseUp", () => {
      const obj = tc.object as THREE.Mesh | undefined;
      const d = obj ? this.drafts.get(obj.userData.uid as string) : null;
      if (d) {
        const g = this.groupBefore.size ? Date.now() : undefined;
        if (this.gizmoBefore) this.push({ t: Date.now(), uid: d.uid, kind: "edit", before: this.gizmoBefore, after: snapOf(d), g });
        this.gizmoBefore = null;
        // guruh a'zolari: tarix (bitta undo) + saqlash
        for (const [u, before] of this.groupBefore) { const gd = this.drafts.get(u); if (gd) { this.push({ t: Date.now() + 1, uid: u, kind: "edit", before, after: snapOf(gd), g }); this.emitChange(gd); } }
        this.groupBefore = new Map();
        this.emit(); this.emitChange(d);
      }
      prev = null;
    });
    this.viewer.world.scene.three.add(tc.getHelper());
    this.tc = tc;
    this.viewer.onCameraObjectChange(() => { tc.camera = this.viewer.world.camera.three; });
  }

  setMode(mode: GizmoMode) {
    if (!this.tc || !this.selectedUid) return;
    this.tc.setMode(mode);
    this.modeListeners.forEach((f) => f(mode));
  }
  get mode(): GizmoMode | null { return this.tc && this.selectedUid ? (this.tc.mode as GizmoMode) : null; }

  /** Parametrlar/nom/pset/transform o'zgarganda (panel). */
  update(uid: string, patch: Partial<Pick<Draft, "name" | "params" | "psets" | "visible">> & { transform?: Partial<DraftTransform> }) {
    const d = this.drafts.get(uid);
    const mesh = this.meshes.get(uid);
    if (!d || !mesh) return;
    const kind = DRAFT_KIND_BY_ID[d.kind];
    const before = this.restoring ? null : snapOf(d);
    if (patch.params) {
      d.params = { ...d.params, ...patch.params };
      mesh.geometry.dispose();
      mesh.geometry = this.geometryFor(d, kind);
      if (kind.pset) d.psets = { ...d.psets, [kind.pset.name]: derivePset(kind, d.params, d.psets[kind.pset.name]) };
    }
    if (patch.name !== undefined) { d.name = patch.name; mesh.name = patch.name; }
    if (patch.psets) d.psets = patch.psets;
    if (patch.transform) { d.transform = { ...d.transform, ...patch.transform }; this.applyTransform(mesh, d.transform); }
    if (patch.visible !== undefined && d.kind !== "deleted") { d.visible = patch.visible; mesh.visible = patch.visible; if (!patch.visible && this.selectedUid === uid) this.select(null); }
    if (before) this.push({ t: Date.now(), uid, kind: "edit", before, after: snapOf(d) });
    this.emit();
    this.emitChange(d);
  }
  setServerId(uid: string, id: number) { const d = this.drafts.get(uid); if (d) { d.id = id; this.emit(); } }

  remove(uid: string) {
    const mesh = this.meshes.get(uid);
    const d = this.drafts.get(uid);
    this.multi.delete(uid);
    if (d && !this.restoring) this.push({ t: Date.now(), uid, kind: "remove", draft: JSON.parse(JSON.stringify(d)) });
    if (mesh) { if (this.selectedUid === uid) this.select(null); this.group.remove(mesh); mesh.geometry.dispose(); (mesh.material as THREE.Material).dispose(); }
    this.meshes.delete(uid);
    this.drafts.delete(uid);
    this.emit();
  }
  clear() { this.restoring = true; try { for (const uid of [...this.drafts.keys()]) this.remove(uid); } finally { this.restoring = false; } this.history = []; this.hIndex = 0; }

  duplicate(uid: string): Draft | null {
    const d = this.drafts.get(uid);
    if (!d) return null;
    const kind = DRAFT_KIND_BY_ID[d.kind];
    if (d.kind === "deleted") return null;
    const nd = this.add({ id: null, kind: d.kind, name: d.kind === "mesh" ? `${d.name} (nusxa)` : this.nextName(kind), params: { ...d.params }, transform: { ...d.transform, x: d.transform.x + 2, y: d.transform.y + 2 }, psets: JSON.parse(JSON.stringify(d.psets)), mesh: d.mesh, ifcClass: d.ifcClass, color: d.color }, true);
    this.placeListeners.forEach((f) => f(nd));
    return nd;
  }

  /** Massiv (AutoCAD ARRAY / Blender Array modifier): obyektdan n−1 nusxa qadam bilan X yoki Y o'qi bo'ylab
   *  (obyektning o'z burilishini hisobga olib). Qaytaradi: yangi qoralamalar. */
  arrayCopies(uid: string, count: number, step: number, axis: "x" | "y"): Draft[] {
    const d = this.drafts.get(uid);
    if (!d || d.kind === "deleted" || count < 2) return [];
    const kind = DRAFT_KIND_BY_ID[d.kind];
    const a = THREE.MathUtils.degToRad(d.transform.rz);
    const dir = axis === "x" ? [Math.cos(a), Math.sin(a)] : [-Math.sin(a), Math.cos(a)];
    const out: Draft[] = [];
    for (let i = 1; i < count; i++) {
      const nd = this.add({ id: null, kind: d.kind, name: d.kind === "mesh" ? `${d.name} (${i + 1})` : this.nextName(kind), params: { ...d.params }, transform: { ...d.transform, x: r3(d.transform.x + dir[0] * step * i), y: r3(d.transform.y + dir[1] * step * i) }, psets: JSON.parse(JSON.stringify(d.psets)), mesh: d.mesh, ifcClass: d.ifcClass, color: d.color }, false);
      this.placeListeners.forEach((f) => f(nd));
      out.push(nd);
    }
    this.viewer.statusMsg(`Massiv: ${count - 1} ta nusxa, qadam ${step} m (${axis.toUpperCase()})`);
    return out;
  }

  /** Server uchun to'liq yozuv (mesh bilan). */
  payload(uid: string) {
    const d = this.drafts.get(uid);
    const mesh = this.meshes.get(uid);
    if (!d || !mesh) return null;
    const kind = DRAFT_KIND_BY_ID[d.kind];
    const t = d.transform;
    const base = { kind: d.kind, name: d.name, ifc_class: d.ifcClass || kind.ifcClass, params: d.params, transform: { x: t.x, y: t.y, z: t.z, rz: t.rz, sx: t.sx, sy: t.sy, sz: t.sz }, psets: d.psets, source_guid: d.sourceGuid ?? null };
    if (d.kind === "deleted") return { ...base, mesh: {} };
    return { ...base, mesh: toIfcMesh(mesh.geometry, [t.sx, t.sy, t.sz]) };
  }

  /** Mavjud IFC elementni tahrirlanadigan qoralamaga aylantirish (Blender «make editable»): geometriya
   * fragments dan olinadi, asl element yashiriladi, GUID saqlanadi — commitda o'rniga yoziladi. */
  async fromElement(localId: number, info: { guid: string; name: string; category: string; psets: Record<string, Record<string, unknown>> }): Promise<Draft | null> {
    const model = this.viewer.model;
    if (!model) return null;
    const groups = await model.getItemsGeometry([localId]);
    const parts = groups[0] ?? [];
    // world (three) nuqtalar
    const pts: THREE.Vector3[] = [];
    const tris: number[][] = [];
    for (const md of parts) {
      if (!md.positions) continue;
      const base = pts.length;
      const m = md.transform;
      for (let i = 0; i < md.positions.length; i += 3) pts.push(new THREE.Vector3(md.positions[i], md.positions[i + 1], md.positions[i + 2]).applyMatrix4(m));
      if (md.indices) for (let i = 0; i + 2 < md.indices.length; i += 3) tris.push([base + md.indices[i], base + md.indices[i + 1], base + md.indices[i + 2]]);
      else for (let i = 0; i + 2 < (md.positions.length / 3); i += 3) tris.push([base + i, base + i + 1, base + i + 2]);
    }
    if (!pts.length || !tris.length) return null;
    // asos nuqtasi: bbox markazi (x, z), tubi (y) — gizmo va «Yerga» tabiiy ishlasin
    const box = new THREE.Box3().setFromPoints(pts);
    const origin = new THREE.Vector3((box.min.x + box.max.x) / 2, box.min.y, (box.min.z + box.max.z) / 2);
    const [ox, oy, oz] = this.viewer.threeToIfc(origin);
    // lokal IFC mesh: three lokal (p − origin) → IFC (x, −z, y)
    const vertices = pts.map((p) => [r5(p.x - origin.x), r5(-(p.z - origin.z)), r5(p.y - origin.y)]);
    const mesh = { vertices, faces: tris };
    const psets: Record<string, Record<string, unknown>> = {};
    for (const [k, v] of Object.entries(info.psets)) if (k !== "Pset_GES_Object" && !/^Qto_/.test(k)) psets[k] = v;
    const draft = this.add({ id: null, kind: "mesh", name: info.name || info.category, params: {}, transform: { x: r3(ox), y: r3(oy), z: r3(oz), rz: 0, sx: 1, sy: 1, sz: 1 }, psets, mesh, sourceGuid: info.guid, ifcClass: info.category }, true);
    await this.viewer.setItemsVisible([localId], false);
    await this.viewer.clearSelection();
    this.placeListeners.forEach((f) => f(draft));
    return draft;
  }

  /** Mavjud elementni o'chirish belgisi (commitda olib tashlanadi); element darhol yashiriladi. */
  async markDeleted(localId: number, info: { guid: string; name: string; category: string }): Promise<Draft> {
    const draft = this.add({ id: null, kind: "deleted", name: info.name || info.category, params: {}, transform: { x: 0, y: 0, z: 0, rz: 0, sx: 1, sy: 1, sz: 1 }, psets: {}, sourceGuid: info.guid, ifcClass: info.category }, false);
    await this.viewer.setItemsVisible([localId], false);
    await this.viewer.clearSelection();
    this.placeListeners.forEach((f) => f(draft));
    return draft;
  }

  /** Model (qayta) yuklanganda: tahrirlanayotgan/o'chirilgan asl elementlarni yashirish. */
  async syncHidden() {
    const model = this.viewer.model;
    if (!model) return;
    const guids = this.list().map((d) => d.sourceGuid).filter((g): g is string => !!g);
    if (!guids.length) return;
    const ids = (await model.getLocalIdsByGuids(guids)).filter((x): x is number => x != null);
    if (ids.length) await this.viewer.setItemsVisible(ids, false);
  }

  /** Qoralama olib tashlanganda asl element (bo'lsa) qayta ko'rsatiladi. */
  async restoreSource(uid: string) {
    const d = this.drafts.get(uid);
    const model = this.viewer.model;
    if (!d?.sourceGuid || !model) return;
    const ids = (await model.getLocalIdsByGuids([d.sourceGuid])).filter((x): x is number => x != null);
    if (ids.length) await this.viewer.setItemsVisible(ids, true);
  }

  /** Klaviatura (Blender): G/R/S rejim, X/Delete o'chirish, Shift+D nusxa, Esc. Qaytaradi: ishlatildimi. */
  handleKey(e: KeyboardEvent): "handled" | "delete" | "duplicate" | null {
    if (e.key === "Escape") { if (this.placingKind) { this.cancelPlacing(); return "handled"; } if (this.selectedUid) { this.select(null); return "handled"; } return null; }
    if (e.ctrlKey && (e.key === "z" || e.key === "Z" || e.key === "y" || e.key === "Y")) {
      const msg = e.shiftKey || e.key.toLowerCase() === "y" ? this.redo() : this.undo();
      if (msg) { this.viewer.statusMsg(msg); return "handled"; }
      return null;
    }
    if (!this.selectedUid) return null;
    const k = e.key.toLowerCase();
    if (k === "g") { this.setMode("translate"); return "handled"; }
    if (k === "r") { this.setMode("rotate"); return "handled"; }
    if (k === "s") { this.setMode("scale"); return "handled"; }
    if (k === "x" || e.key === "Delete") return "delete";
    if (k === "d" && e.shiftKey) return "duplicate";
    return null;
  }

  /** Tanlangan qoralamaga kamerani moslash. */
  /** Yerga o'tqazish (Blender shrinkwrap/«snap to surface» kabi): obyekt tubi relyef/inshoot yuzasiga.
   * Balandlik xaritasi (server) bo'yicha; obyektning to'rt burchagi va markazi o'rtacha olinadi, yon-bag'irda
   * eng past nuqtaga tushmasin uchun maks. (chuqurga kirmaydi). */
  snapToGround(uid: string): boolean {
    const d = this.drafts.get(uid);
    if (!d) return false;
    const mesh = this.meshes.get(uid);
    if (!mesh) return false;
    mesh.geometry.computeBoundingBox();
    const bb = mesh.geometry.boundingBox!;
    const t = d.transform;
    const sx = (bb.max.x - bb.min.x) * (t.sx ?? 1), sy = (bb.max.z - bb.min.z) * (t.sz ?? 1);
    const bottom = bb.min.y * (t.sy ?? 1); // mesh lokal: three Y — yuqoriga
    const pts: [number, number][] = [[t.x, t.y], [t.x - sx / 2, t.y - sy / 2], [t.x + sx / 2, t.y - sy / 2], [t.x - sx / 2, t.y + sy / 2], [t.x + sx / 2, t.y + sy / 2]];
    let z = -Infinity;
    for (const [x, y] of pts) { const g = this.viewer.groundZ(x, y); if (g != null && g > z) z = g; }
    if (!Number.isFinite(z)) return false;
    this.update(uid, { transform: { z: z - bottom } });
    return true;
  }

  /** Barcha ko'rinadigan qoralamalar chegarasi (three). */
  boundingBox(): THREE.Box3 | null {
    const box = new THREE.Box3();
    for (const m of this.meshes.values()) if (m.visible) box.expandByObject(m);
    return box.isEmpty() ? null : box;
  }

  /** Model (fragments siljishi) yuklangach — barcha meshlarni IFC transformidan qayta joylash (qoralamalar modeldan oldin kelgan bo'lsa). */
  refreshTransforms() {
    for (const [uid, m] of this.meshes) { const d = this.drafts.get(uid); if (d) this.applyTransform(m, d.transform); }
  }

  /** Barcha qoralamalarni yerga o'tqazish (DEM/relyef almashganda). Qaytaradi: nechtasi o'tqazildi. */
  snapAllToGround(): number {
    let n = 0;
    for (const d of this.drafts.values()) if (d.kind !== "deleted" && this.snapToGround(d.uid)) n++;
    return n;
  }

  fit(uid: string) {
    const mesh = this.meshes.get(uid);
    if (!mesh) return;
    const box = new THREE.Box3().setFromObject(mesh);
    void this.viewer.world.camera.controls.fitToBox(box, true, { paddingLeft: 2, paddingRight: 2, paddingTop: 2, paddingBottom: 2 });
  }
}

const r3 = (v: number) => Math.round(v * 1000) / 1000;
const r5 = (v: number) => Math.round(v * 1e5) / 1e5;
