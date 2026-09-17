// ThatOpen (Three.js) ustidagi 3D viewer o'rami. React dan mustaqil — bitta Viewer, bitta canvas.
import * as THREE from "three";
import * as OBC from "@thatopen/components";
import * as OBF from "@thatopen/components-front";
import * as FRAGS from "@thatopen/fragments";
import { WaterSim } from "./waterSim";
import CameraControls from "camera-controls";
import type { Viewpoint } from "../api/client";
import { DraftManager } from "./drafts";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";

export interface SelectedItem {
  localId: number;
  guid: string | null;
  category: string;
  name: string;
}

export interface PropertySet {
  name: string;
  props: { name: string; value: string }[];
}

export interface ItemProperties {
  localId: number;
  guid: string | null;
  category: string;
  name: string;
  attributes: { name: string; value: string }[];
  psets: PropertySet[];
}

export interface TreeNode {
  localId: number | null;
  category: string;
  name: string;
  children: TreeNode[];
}

export type Tool = "select" | "measure" | "section";
export type ViewName = "iso" | "top" | "front" | "back" | "left" | "right" | "bottom";
export type Shading = "solid" | "wire" | "xray" | "rendered";
export type NavMode = "Orbit" | "FirstPerson" | "Plan";
export interface Hover { localId: number; x: number; y: number }

type Listener<T> = (v: T) => void;

const DIFF_COLORS = {
  added: new THREE.Color("#2ecc71"),
  deleted: new THREE.Color("#e74c3c"),
  changed: new THREE.Color("#f1c40f"),
};

export class Viewer {
  components = new OBC.Components();
  world!: OBC.SimpleWorld<OBC.SimpleScene, OBC.OrthoPerspectiveCamera, OBF.PostproductionRenderer>;
  fragments!: OBC.FragmentsManager;
  ifcLoader!: OBC.IfcLoader;
  highlighter!: OBF.Highlighter;
  clipper!: OBC.Clipper;
  measure!: OBF.LengthMeasurement;
  model: FRAGS.FragmentsModel | null = null;
  tool: Tool = "select";
  drafts!: DraftManager; // web da yaratilgan qoralama elementlar (Blender "Add")
  private grid!: OBC.SimpleGrid;
  private coords: [number, number, number] = [0, 0, 0]; // fragments koordinata siljishi (three fazoda)
  private water: THREE.Mesh | null = null;
  private water2: THREE.Mesh | null = null; // quyi byef / toshqin
  private underlays = new Map<number, THREE.Mesh>(); // rasm asoslari (id → tekislik)
  private underlayTex = new Map<string, THREE.Texture>();
  private field: THREE.Mesh | null = null;
  private bounds: THREE.Box3 | null = null;
  private elementBoxes: THREE.Box3[] = []; // elementlar bbox lari (joylashtirishda zaxira raycast)
  private container!: HTMLElement;
  private onSelect: Listener<SelectedItem[]>[] = [];
  private onTool: Listener<Tool>[] = [];
  private onStatus: Listener<string>[] = [];
  private shiftDown = false;
  private disposed = false;
  private resizeObserver: ResizeObserver | null = null;

  async init(container: HTMLElement) {
    (window as unknown as { __gesViewer?: Viewer }).__gesViewer = this; // e2e/diagnostika uchun
    this.container = container;
    const worlds = this.components.get(OBC.Worlds);
    const world = worlds.create<OBC.SimpleScene, OBC.OrthoPerspectiveCamera, OBF.PostproductionRenderer>();
    this.world = world;
    world.scene = new OBC.SimpleScene(this.components);
    world.scene.setup();
    world.scene.three.background = new THREE.Color("#3d3d3d"); // Blender viewport foni
    // Postproduction (AO, konturlar) — "Rendered" shading rejimida yoqiladi (Blender Rendered kabi)
    world.renderer = new OBF.PostproductionRenderer(this.components, container, { antialias: true });
    world.renderer.showLogo = false; // toza CAD viewport; ThatOpen ga README da minnatdorchilik
    // Muhit xaritasi — suv/metall/qoralama materiallarida aks etish (fragments Lambert materiallariga ta'sir qilmaydi)
    try {
      const pmrem = new THREE.PMREMGenerator(world.renderer.three);
      world.scene.three.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
      world.scene.three.environmentIntensity = 0.55;
      pmrem.dispose();
    } catch { /* WebGL cheklovi */ }
    world.camera = new OBC.OrthoPerspectiveCamera(this.components);
    await world.camera.controls.setLookAt(30, 20, 30, 0, 0, 0);
    if (this.disposed) return; // React StrictMode: init davomida dispose bo'lishi mumkin
    this.components.init();

    this.grid = this.components.get(OBC.Grids).create(world);
    this.grid.config.color = new THREE.Color("#4a4a4a");

    // Fragments engine — worker va wasm lokal (offline ishlaydi)
    this.fragments = this.components.get(OBC.FragmentsManager);
    this.fragments.init("/engine/worker.mjs");
    this.fragments.list.onItemSet.add(({ value: model }) => {
      model.useCamera(world.camera.three);
      world.scene.three.add(model.object);
      this.fragments.core.update(true);
    });
    world.camera.controls.addEventListener("rest", () => this.fragments.core.update(true));

    this.ifcLoader = this.components.get(OBC.IfcLoader);
    await this.ifcLoader.setup({ autoSetWasm: false, wasm: { path: "/engine/", absolute: true } });
    if (this.disposed) return;

    this.highlighter = this.components.get(OBF.Highlighter);
    this.highlighter.setup({
      world,
      selectMaterialDefinition: {
        color: new THREE.Color("#f5a623"), // Blender uslubi: tanlangan — to'q sariq
        opacity: 1,
        transparent: false,
        renderedFaces: FRAGS.RenderedFaces.TWO,
      },
    });
    this.highlighter.events.select.onHighlight.add((map) => this.emitSelection(map));
    this.highlighter.events.select.onClear.add(() => this.onSelect.forEach((l) => l([])));

    this.clipper = this.components.get(OBC.Clipper);
    this.clipper.enabled = false;
    this.setupHover();
    // Postproduction renderer konteyner o'lchamini o'zi kuzatmaydi — ResizeObserver bilan
    const ro = new ResizeObserver(() => {
      const r = this.world.renderer;
      if (!r || this.disposed) return;
      r.resize(new THREE.Vector2(container.clientWidth, container.clientHeight));
      this.world.camera.updateAspect();
    });
    ro.observe(container);
    this.resizeObserver = ro;
    this.world.renderer!.resize(new THREE.Vector2(container.clientWidth, container.clientHeight));
    this.world.camera.updateAspect();
    this.measure = this.components.get(OBF.LengthMeasurement);
    this.measure.world = world;
    this.measure.enabled = false;

    this.setupMouse();
    this.drafts = new DraftManager(this);
    this.status("Tayyor");
  }

  /** Holat satri xabari (tashqi modullar uchun). */
  statusMsg(msg: string) {
    this.status(msg);
  }
  /** Nur bilan element bbox larining eng yaqin kesishuvi (fragments raycast o'tkazib yuborganda zaxira). */
  rayBoxes(ray: THREE.Ray): THREE.Vector3 | null {
    let best: THREE.Vector3 | null = null;
    let bestD = Infinity;
    const p = new THREE.Vector3();
    for (const b of this.elementBoxes) {
      if (ray.intersectBox(b, p)) {
        const d = p.distanceTo(ray.origin);
        if (d < bestD) { bestD = d; best = p.clone(); }
      }
    }
    return best;
  }
  /** Yer sathi (three y): model tagidan; model yo'q — 0. */
  groundY(): number {
    return this.bounds ? this.bounds.min.y : 0;
  }
  private cameraObjListeners: (() => void)[] = [];
  /** Proyeksiya almashganda kamera obyekti o'zgaradi (TransformControls uchun). */
  onCameraObjectChange(cb: () => void) {
    this.cameraObjListeners.push(cb);
    return () => { this.cameraObjListeners = this.cameraObjListeners.filter((x) => x !== cb); };
  }

  // --- AutoCAD sichqoncha odatlari: o'rta tugma pan, Shift+o'rta orbit, g'ildirak zoom, chap tanlash ---
  private setupMouse() {
    const c = this.world.camera.controls;
    c.mouseButtons.left = CameraControls.ACTION.NONE;
    c.mouseButtons.middle = CameraControls.ACTION.TRUCK;
    c.mouseButtons.right = CameraControls.ACTION.ROTATE;
    c.mouseButtons.wheel = CameraControls.ACTION.DOLLY;
    c.dollyToCursor = true;
    c.infinityDolly = false;
    // ThatOpen default maxDistance = 300 m — katta modellarni (vodiy 3 km) butunlay ko'rib bo'lmasdi
    c.maxDistance = Infinity;
    c.minDistance = 0.1;
    const onKey = (e: KeyboardEvent) => {
      const down = e.type === "keydown";
      if (e.key === "Shift" && this.shiftDown !== down) {
        this.shiftDown = down;
        c.mouseButtons.middle = down ? CameraControls.ACTION.ROTATE : CameraControls.ACTION.TRUCK;
      }
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("keyup", onKey);
    this.container.addEventListener("contextmenu", (e) => e.preventDefault());
    this.container.addEventListener("click", () => {
      if (this.tool === "section") void this.clipper.create(this.world);
    });
    this.setupBoxSelect();
    // Ikki marta bosish — orbit markazi shu nuqtaga (Blender «orbit around selection», AutoCAD «orbit center»)
    this.container.addEventListener("dblclick", async (e) => {
      if (this.tool !== "select" || !this.drafts) return;
      const p = await this.drafts.pickPoint(e.clientX, e.clientY);
      if (p) { await this.setOrbitTarget(p); this.status("Aylantirish markazi ko'chirildi"); }
    });
  }

  /** AutoCAD uslubidagi to'rtburchak tanlash: chap tugma bilan bo'sh joydan torting — chapdan o'ngga (window) —
   *  to'liq ichidagi elementlar, o'ngdan chapga (crossing) — kesib o'tganlar ham. Shift — mavjud tanlovga qo'shish. */
  private boxSel: { x0: number; y0: number; el: HTMLDivElement } | null = null;
  private setupBoxSelect() {
    const dom = this.world.renderer!.three.domElement;
    const rectEl = document.createElement("div");
    Object.assign(rectEl.style, { position: "absolute", pointerEvents: "none", border: "1px dashed #f5a623", background: "rgba(245,166,35,0.10)", display: "none", zIndex: "5" } as CSSStyleDeclaration);
    this.container.style.position = this.container.style.position || "relative";
    this.container.appendChild(rectEl);
    dom.addEventListener("pointerdown", (e) => {
      if (e.button !== 0 || this.tool !== "select" || this.drafts?.placing || this.drafts?.selected) return;
      this.boxSel = { x0: e.clientX, y0: e.clientY, el: rectEl };
    });
    window.addEventListener("pointermove", (e) => {
      const b = this.boxSel;
      if (!b) return;
      const dx = e.clientX - b.x0, dy = e.clientY - b.y0;
      if (Math.hypot(dx, dy) < 6) return;
      const r = this.container.getBoundingClientRect();
      Object.assign(b.el.style, { display: "block", left: `${Math.min(b.x0, e.clientX) - r.left}px`, top: `${Math.min(b.y0, e.clientY) - r.top}px`, width: `${Math.abs(dx)}px`, height: `${Math.abs(dy)}px`, borderStyle: dx < 0 ? "dashed" : "solid", background: dx < 0 ? "rgba(61,168,100,0.10)" : "rgba(245,166,35,0.10)", borderColor: dx < 0 ? "#3aa864" : "#f5a623" });
    });
    window.addEventListener("pointerup", async (e) => {
      const b = this.boxSel;
      if (!b) return;
      this.boxSel = null;
      if (b.el.style.display === "none") return;
      b.el.style.display = "none";
      const x1 = Math.min(b.x0, e.clientX), x2 = Math.max(b.x0, e.clientX), y1 = Math.min(b.y0, e.clientY), y2 = Math.max(b.y0, e.clientY);
      const crossing = e.clientX < b.x0;
      // highlighter o'zi sichqoncha surilganini (moveThreshold) hisobga oladi — tortishdan keyin bosish tanlovni buzmaydi
      const ids = await this.itemsInRect(x1, y1, x2, y2, crossing);
      if (!this.model) return;
      const cur = e.shiftKey ? new Set(this.selection) : new Set<number>();
      ids.forEach((i) => cur.add(i));
      if (cur.size) await this.highlighter.highlightByID("select", { [this.model.modelId]: cur }, true, false);
      else await this.clearSelection();
      this.status(`To'rtburchak tanlash: ${cur.size} element${crossing ? " (kesib o'tganlar bilan)" : ""}`);
    });
  }
  /** Ekran to'rtburchagidagi elementlar (bbox proyeksiyasi bo'yicha). */
  private async itemsInRect(x1: number, y1: number, x2: number, y2: number, crossing: boolean): Promise<number[]> {
    if (!this.model) return [];
    const ids = await this.model.getItemsIdsWithGeometry();
    const vis = await this.model.getVisible(ids);
    const boxes = await this.model.getBoxes(ids);
    const r = this.world.renderer!.three.domElement.getBoundingClientRect();
    const cam = this.world.camera.three;
    cam.updateMatrixWorld();
    const out: number[] = [];
    const v = new THREE.Vector3();
    ids.forEach((id, i) => {
      if (!vis[i]) return;
      const bx = boxes[i];
      if (!bx || bx.isEmpty()) return;
      const sz = bx.getSize(new THREE.Vector3());
      if (Math.max(sz.x, sz.y, sz.z) > 2000) return; // relyef kabi ulkan yuzalar tanlanmaydi
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity, behind = false;
      for (let c = 0; c < 8; c++) {
        v.set(c & 1 ? bx.max.x : bx.min.x, c & 2 ? bx.max.y : bx.min.y, c & 4 ? bx.max.z : bx.min.z).project(cam);
        if (v.z > 1) behind = true;
        const sx = r.left + (v.x + 1) / 2 * r.width, sy = r.top + (1 - v.y) / 2 * r.height;
        minX = Math.min(minX, sx); maxX = Math.max(maxX, sx); minY = Math.min(minY, sy); maxY = Math.max(maxY, sy);
      }
      if (behind) return;
      const inside = minX >= x1 && maxX <= x2 && minY >= y1 && maxY <= y2;
      const overlap = maxX >= x1 && minX <= x2 && maxY >= y1 && minY <= y2;
      if (inside || (crossing && overlap)) out.push(id);
    });
    return out;
  }

  // --- Hodisalar ---
  subscribeSelection(l: Listener<SelectedItem[]>) {
    this.onSelect.push(l);
    return () => (this.onSelect = this.onSelect.filter((x) => x !== l));
  }
  subscribeTool(l: Listener<Tool>) {
    this.onTool.push(l);
    return () => (this.onTool = this.onTool.filter((x) => x !== l));
  }
  subscribeStatus(l: Listener<string>) {
    this.onStatus.push(l);
    return () => (this.onStatus = this.onStatus.filter((x) => x !== l));
  }
  private status(msg: string) {
    this.onStatus.forEach((l) => l(msg));
  }

  private async emitSelection(map: OBC.ModelIdMap) {
    if (!this.model) return;
    const ids = [...(map[this.model.modelId] ?? [])];
    const items = await this.describe(ids);
    this.onSelect.forEach((l) => l(items));
  }

  private async describe(localIds: number[]): Promise<SelectedItem[]> {
    if (!this.model || localIds.length === 0) return [];
    const data = await this.model.getItemsData(localIds, { attributesDefault: false, attributes: ["Name"] });
    const guids = await this.model.getGuidsByLocalIds(localIds);
    return localIds.map((localId, i) => ({
      localId,
      guid: guids[i] ?? null,
      category: attr(data[i], "_category"),
      name: attr(data[i], "Name"),
    }));
  }

  // --- Model ---
  async loadIfc(bytes: Uint8Array, name: string, onProgress?: (p: number) => void) {
    await this.clearModel();
    this.status("IFC o'qilmoqda…");
    const model = await this.ifcLoader.load(bytes, false, name, {
      processData: { progressCallback: (p) => onProgress?.(p) },
    });
    this.model = model;
    await this.fragments.core.update(true);
    const c = await model.getCoordinates();
    this.coords = [c[0] ?? 0, c[1] ?? 0, c[2] ?? 0];
    this.drafts?.refreshTransforms(); // qoralamalar modeldan oldin yuklangan bo'lsa — siljish bilan qayta joylash
    await this.placeGridUnderModel();
    await this.isoFit();
    await this.planIfFlat();
    if (this.shading !== "solid") this.setShading(this.shading);
    this.status(`Yuklandi: ${name}`);
    return model;
  }

  /** Yuklashdan keyin: izometrik yo'nalishdan butun sahnaga moslash (animatsiyasiz). */
  private async isoFit() {
    const box = await this.sceneBox();
    if (!box) return;
    const c = box.getCenter(new THREE.Vector3());
    const d = box.getSize(new THREE.Vector3()).length() || 50;
    await this.world.camera.controls.setLookAt(c.x + d, c.y + d * 0.8, c.z + d, c.x, c.y, c.z, false);
    await this.fitBox(box, false);
  }

  /** Tekis 2D chizma (DWG/DXF import — balandligi ≈ 0) bo'lsa AutoCAD kabi yuqoridan (plan) ko'rsatamiz. */
  private async planIfFlat() {
    const b = this.bounds;
    if (!b) return;
    const size = new THREE.Vector3();
    b.getSize(size);
    if (size.y < 0.01 && Math.max(size.x, size.z) > 1) {
      await this.setView("top");
      await this.fitAll();
    }
  }

  /** Tayyor fragments (.frag, serverda konvertatsiya qilingan) — IFC parse qilinmaydi, tez. */
  async loadFragments(bytes: Uint8Array, name: string) {
    await this.clearModel();
    this.status("Model yuklanmoqda…");
    const model = await this.fragments.core.load(bytes, { modelId: name });
    this.model = model;
    await this.fragments.core.update(true);
    const c = await model.getCoordinates();
    this.coords = [c[0] ?? 0, c[1] ?? 0, c[2] ?? 0];
    this.drafts?.refreshTransforms(); // qoralamalar modeldan oldin yuklangan bo'lsa — siljish bilan qayta joylash
    await this.placeGridUnderModel();
    await this.isoFit();
    await this.planIfFlat();
    this.status(`Yuklandi: ${name}`);
    return model;
  }

  /** Viewport shading (Blender: Solid / Wireframe / X-ray / Rendered). Fragments materiallariga to'g'ridan-to'g'ri;
   * Rendered — postproduction (ambient occlusion + konturlar). */
  shading: Shading = "solid";
  private wire: THREE.LineSegments | null = null; // Wireframe rejimi: elementlar qirralari (fragments CPU massivlarini bo'shatadi — material.wireframe ishlamaydi)
  private wireKey = "";
  setShading(mode: Shading) {
    this.shading = mode;
    try {
      const pp = this.world.renderer!.postproduction;
      pp.enabled = mode === "rendered";
      if (mode === "rendered") { pp.outlinesEnabled = true; }
    } catch { /* postproduction hali tayyor emas */ }
    this.drafts?.setShading(mode);
    if (!this.model) return;
    const eff = mode === "rendered" ? "solid" : mode;
    this.model.object.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (!mesh.isMesh) return;
      const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      for (const m of mats as THREE.Material[]) {
        const mm = m as THREE.MeshLambertMaterial;
        if (mm.userData.gesOpacity === undefined) { mm.userData.gesOpacity = mm.opacity; mm.userData.gesTransparent = mm.transparent; }
        mm.wireframe = false;
        // wire: model yuzalari deyarli ko'rinmas (qirralar alohida chiziladi), x-ray: shaffof
        mm.transparent = eff === "xray" || eff === "wire" ? true : (mm.userData.gesTransparent as boolean);
        mm.opacity = eff === "xray" ? 0.35 : eff === "wire" ? 0.06 : (mm.userData.gesOpacity as number);
        mm.depthWrite = eff === "solid";
        mm.needsUpdate = true;
      }
    });
    if (eff === "wire") void this.buildWire();
    else if (this.wire) this.wire.visible = false;
    this.status(`Shading: ${this.shading}`);
  }

  /** Qirralar (EdgesGeometry, 25°) — barcha ko'rinadigan elementlar geometriyasidan; model/ko'rinish o'zgarsa qayta. */
  private async buildWire() {
    const model = this.model;
    if (!model || !this.alive()) return;
    const ids = await model.getItemsIdsWithGeometry();
    const vis = await model.getVisible(ids);
    const shown = ids.filter((_, i) => vis[i]);
    const key = `${model.modelId}:${shown.length}:${shown[0]}:${shown[shown.length - 1]}`;
    if (this.wire && this.wireKey === key) { this.wire.visible = true; return; }
    if (this.wire) { this.world.scene.three.remove(this.wire); this.wire.geometry.dispose(); (this.wire.material as THREE.Material).dispose(); this.wire = null; }
    const groups = await model.getItemsGeometry(shown);
    const segs: number[] = [];
    let tris = 0;
    const v = new THREE.Vector3();
    for (const parts of groups) {
      for (const md of parts) {
        if (!md.positions) continue;
        const g = new THREE.BufferGeometry();
        g.setAttribute("position", new THREE.Float32BufferAttribute(Float32Array.from(md.positions), 3));
        if (md.indices) g.setIndex(new THREE.BufferAttribute(Uint32Array.from(md.indices), 1));
        tris += (md.indices ? md.indices.length : md.positions.length / 3) / 3;
        const e = new THREE.EdgesGeometry(g, 25);
        const a = e.getAttribute("position");
        for (let i = 0; i < a.count; i++) { v.set(a.getX(i), a.getY(i), a.getZ(i)).applyMatrix4(md.transform); segs.push(v.x, v.y, v.z); }
        g.dispose(); e.dispose();
        if (tris > 1_500_000) break; // juda katta model — qolgani tashlab ketiladi (x-ray yuzasi baribir ko'rinadi)
      }
    }
    if (!this.alive() || this.shading !== "wire") return;
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(segs, 3));
    this.wire = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: new THREE.Color("#c9ced6"), transparent: true, opacity: 0.9 }));
    this.wire.name = "wireframe";
    this.wireKey = key;
    this.world.scene.three.add(this.wire);
  }

  /** Kamera rejimi (Blender: orbit / yurish (first person) / plan) */
  setNavMode(mode: NavMode) {
    this.world.camera.set(mode);
    if (mode === "Plan") void this.setView("top");
    this.status(mode === "Orbit" ? "Kamera: aylantirish" : mode === "FirstPerson" ? "Kamera: yurish (WASD, sichqoncha)" : "Kamera: plan");
  }

  /** Kesim qutisi: tanlangan elementlar (yoki butun model) atrofida 6 ta kesim tekisligi. */
  async sectionBox(pad = 0.3) {
    if (!this.model) return;
    const ids = this.selection;
    const boxes = await this.model.getBoxes(ids.length ? ids : undefined);
    if (!boxes.length) return;
    const b = boxes.reduce((acc, x) => acc.union(x), boxes[0].clone()).expandByScalar(pad);
    this.clipper.deleteAll();
    this.clipper.enabled = true;
    const w = this.world;
    const c = b.getCenter(new THREE.Vector3());
    const mk = (n: THREE.Vector3, pt: THREE.Vector3) => this.clipper.createFromNormalAndCoplanarPoint(w, n, pt);
    mk(new THREE.Vector3(1, 0, 0), new THREE.Vector3(b.min.x, c.y, c.z));
    mk(new THREE.Vector3(-1, 0, 0), new THREE.Vector3(b.max.x, c.y, c.z));
    mk(new THREE.Vector3(0, 1, 0), new THREE.Vector3(c.x, b.min.y, c.z));
    mk(new THREE.Vector3(0, -1, 0), new THREE.Vector3(c.x, b.max.y, c.z));
    mk(new THREE.Vector3(0, 0, 1), new THREE.Vector3(c.x, c.y, b.min.z));
    mk(new THREE.Vector3(0, 0, -1), new THREE.Vector3(c.x, c.y, b.max.z));
    await this.fragments.core.update(true);
    this.status(`Kesim qutisi: ${ids.length ? ids.length + " element" : "butun model"} (CLEAR — olib tashlash)`);
  }

  /** Elementlar ko'rinishi (outliner ko'zlari) */
  async setItemsVisible(ids: number[], visible: boolean) {
    await this.setVisible(ids, visible);
  }

  /** Tanlangan/berilgan element o'lchamlari (m) va markazi (IFC koordinatalari) */
  async getDimensions(localId: number): Promise<{ size: [number, number, number]; center: [number, number, number] } | null> {
    if (!this.model) return null;
    const [box] = await this.model.getBoxes([localId]);
    if (!box) return null;
    const sz = box.getSize(new THREE.Vector3());
    const c = this.threeToIfc(box.getCenter(new THREE.Vector3()));
    return { size: [sz.x, sz.z, sz.y], center: c };
  }

  /** Rang sxemasi (Blender viewport color): tur bo'yicha / qavat bo'yicha / yo'q */
  async colorScheme(mode: "none" | "type" | "storey") {
    if (!this.model) return;
    if (mode === "none") { await this.colorByGuids({}); this.status("Rang: material"); return; }
    const palette = ["#4da3ff", "#e0a93a", "#3aa864", "#b46dcc", "#e0656a", "#39b7c9", "#c9ced6", "#f5c542", "#8fd3a9", "#d98ec7"];
    const groups: Record<string, number[]> = {};
    if (mode === "type") {
      const cats = (await this.getCategories()).map((c) => c.category); // faqat geometriyali turlar
      const items = await this.model.getItemsOfCategories(cats.map((c) => new RegExp(`^${c}$`)));
      for (const [cat, ids] of Object.entries(items)) if (ids.length) groups[cat] = ids;
    } else {
      const tree = await this.getTree();
      const walk = (n: TreeNode, storey: string | null) => {
        const st = n.category === "IFCBUILDINGSTOREY" ? n.name : storey;
        if (n.localId != null && st && n.category !== "IFCBUILDINGSTOREY") (groups[st] ??= []).push(n.localId);
        n.children.forEach((c) => walk(c, st));
      };
      if (tree) walk(tree, null);
    }
    const colors: Record<string, string> = {};
    let i = 0;
    for (const ids of Object.values(groups)) {
      const guids = await this.model.getGuidsByLocalIds(ids);
      const col = palette[i++ % palette.length];
      for (const g of guids) if (g) colors[g] = col;
    }
    await this.colorByGuids(colors);
    this.status(`Rang: ${mode === "type" ? "IFC turi" : "qavat"} bo'yicha (${Object.keys(groups).length} guruh)`);
    return Object.keys(groups).map((k, j) => ({ name: k, color: palette[j % palette.length] }));
  }

  /** Render — viewport rasmi (F12), scale — o'lchov (2 = 2x). PNG data URL. */
  screenshot(scale = 2): string {
    const r = this.world.renderer!.three;
    const cam = this.world.camera.three;
    const size = r.getSize(new THREE.Vector2());
    const ratio = r.getPixelRatio();
    r.setPixelRatio(ratio * scale);
    r.render(this.world.scene.three, cam);
    const url = r.domElement.toDataURL("image/png");
    r.setPixelRatio(ratio);
    r.setSize(size.x, size.y, false);
    this.status("Rasm tayyor");
    return url;
  }

  /** Kursor ostidagi element (tooltip uchun) — 80 ms da bir marta */
  private hoverListeners: Listener<Hover | null>[] = [];
  private hoverTimer: number | null = null;
  subscribeHover(l: Listener<Hover | null>) {
    this.hoverListeners.push(l);
    return () => { this.hoverListeners = this.hoverListeners.filter((x) => x !== l); };
  }
  private setupHover() {
    const dom = this.world.renderer!.three.domElement;
    dom.addEventListener("pointermove", (e) => {
      if (this.hoverTimer != null || !this.model || this.hoverListeners.length === 0) return;
      this.hoverTimer = window.setTimeout(async () => {
        this.hoverTimer = null;
        const rect = dom.getBoundingClientRect();
        const mouse = new THREE.Vector2(e.clientX - rect.left, e.clientY - rect.top);
        try {
          const hit = await this.model!.raycast({ camera: this.world.camera.three, mouse, dom });
          const h = hit && hit.localId != null ? { localId: hit.localId, x: e.clientX, y: e.clientY } : null;
          this.hoverListeners.forEach((l) => l(h));
        } catch { /* raycast xatosi — tooltip yo'q */ }
      }, 80);
    });
    dom.addEventListener("pointerleave", () => this.hoverListeners.forEach((l) => l(null)));
  }

  /** Kamera o'zgarganda (gizmo, statistika uchun). Qaytaradi: obunani bekor qilish. */
  onCameraChange(cb: (q: THREE.Quaternion) => void): () => void {
    const c = this.world.camera.controls;
    const h = () => cb(this.world.camera.three.quaternion);
    c.addEventListener("update", h);
    h();
    return () => c.removeEventListener("update", h);
  }

  /** Grid ko'rinishi (overlay) */
  setGridVisible(v: boolean) {
    this.grid.three.visible = v;
  }

  /** Grid model tagida tursin (fragments modelni markazlashtiradi, yer sathi o'zgaradi). */
  private async placeGridUnderModel() {
    if (!this.model) return;
    const boxes = await this.model.getBoxes();
    if (boxes.length === 0) return;
    const union = boxes.reduce((acc, b) => acc.union(b), boxes[0].clone());
    this.bounds = union;
    this.elementBoxes = boxes;
    this.grid.three.position.y = union.min.y - 0.05;
    // Katta modellar (GES egizagi: vodiy 3 km) — far tekislik model diagonalining 20 barobari
    const diag = union.getSize(new THREE.Vector3()).length();
    this.setClipPlanes(diag);
  }
  /** Yaqin/uzoq tekisliklar ikkala kameraga (perspektiva va ortografik) — katta modelda ortoda relyef kesilmasin. */
  private setClipPlanes(diag: number) {
    const persp = this.world.camera.threePersp;
    persp.far = Math.max(persp.far, 1000, diag * 20);
    persp.near = Math.max(0.02, Math.min(persp.near, diag / 20000));
    persp.updateProjectionMatrix();
    const ortho = this.world.camera.threeOrtho;
    ortho.far = Math.max(ortho.far, 1000, diag * 20);
    ortho.near = Math.min(ortho.near, -diag * 20); // orto: kamera orqasidagi geometriya ham kesilmasin
    ortho.updateProjectionMatrix();
  }

  // --- Koordinatalar: IFC (x, y, z — Z yuqoriga, metr) ↔ three (x, y — yuqoriga, z) + siljish ---
  ifcToThree(p: [number, number, number]): THREE.Vector3 {
    const [cx, cy, cz] = this.coords;
    return new THREE.Vector3(p[0] + cx, p[2] + cy, -p[1] + cz);
  }
  threeToIfc(v: THREE.Vector3): [number, number, number] {
    const [cx, cy, cz] = this.coords;
    return [v.x - cx, -(v.z - cz), v.y - cy];
  }

  /** Suv sathi tekisligi (IFC z, metr). null — olib tashlash. */
  /** Quyi byef (tailwater / toshqin) suv tekisligi — ikkinchi, jigarrang-ko'k, model markazidan quyi tomonda. */
  /** Viewer yopilgandan keyin (sahifa almashdi) React cleanup lar chaqirsa — jim chiqamiz. */
  private alive(): boolean {
    try { return !!this.world?.scene?.three; } catch { return false; }
  }

  setTailwaterLevel(ifcZ: number | null) {
    if (!this.alive()) return;
    if (this.water2) {
      this.world.scene.three.remove(this.water2);
      this.water2.geometry.dispose();
      (this.water2.material as THREE.Material).dispose();
      this.water2 = null;
      this.water2Anim = null;
    }
    if (ifcZ == null || !this.bounds || this.dyn) return; // jonli suv o'zi quyi byefni ko'rsatadi
    if (this.hm) {
      const built = this.conformingWater(ifcZ, "downstream", 0.5);
      if (built) { this.water2 = built.mesh; this.water2Anim = built; this.world.scene.three.add(this.water2); this.startWaterAnim(); return; }
    }
    const b = this.bounds;
    const sx = (b.max.x - b.min.x) * 1.4 + 20;
    const sz = (b.max.z - b.min.z) * 1.4 + 20;
    const geo = new THREE.PlaneGeometry(sx, sz);
    geo.rotateX(-Math.PI / 2);
    const mat = new THREE.MeshStandardMaterial({ color: new THREE.Color("#6b8fb3"), transparent: true, opacity: 0.5, side: THREE.DoubleSide, depthWrite: false, roughness: 0.3 });
    this.water2 = new THREE.Mesh(geo, mat);
    this.water2.position.set((b.min.x + b.max.x) / 2, ifcZ + this.coords[1], (b.min.z + b.max.z) / 2);
    this.world.scene.three.add(this.water2);
  }

  // ---- Jonli suv (sayoz suv gidrodinamikasi, waterSim.ts) ----
  dyn: { sim: WaterSim; mesh: THREE.Mesh; timeScale: number; running: boolean; onTick?: (sim: WaterSim) => void; last: number } | null = null;

  /** Dinamik suvni boshlash: sathgacha to'ldirib (region), so'ng har kadr gidrodinamika. timeScale — 1 s haqiqiy
   * vaqt = timeScale s simulyatsiya. Statik suv olib tashlanadi. */
  startDynamicWater(level: number, region: "upstream" | "downstream" | "all" = "upstream", timeScale = 1) {
    if (!this.hm || !this.alive()) return null;
    this.stopDynamicWater();
    this.setWaterLevel(null);
    this.setTailwaterLevel(null);
    // katak o'lchami ≥ ~6 m (CFL qadami juda kichik bo'lmasin — kichik maketda sim vaqti sekin yurardi), 48–128 katak
    const extent = Math.max(this.hm.nx * this.hm.dx, this.hm.ny * this.hm.dy);
    const sim = new WaterSim(this.hm, Math.max(48, Math.min(128, Math.floor(extent / 6))));
    sim.fill(level, region);
    const { nx, ny } = sim;
    const pos = new Float32Array(nx * ny * 3);
    const col = new Float32Array(nx * ny * 3);
    const idx: number[] = [];
    for (let j = 0; j < ny - 1; j++) for (let i = 0; i < nx - 1; i++) { const a = j * nx + i; idx.push(a, a + 1, a + nx, a + 1, a + nx + 1, a + nx); } // normal yuqoriga (three Y)
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
    geo.setIndex(idx);
    const mat = new THREE.MeshStandardMaterial({ vertexColors: true, transparent: true, opacity: 0.66, side: THREE.DoubleSide, depthWrite: false, roughness: 0.1, metalness: 0.15 });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.renderOrder = 2;
    this.world.scene.three.add(mesh);
    this.dyn = { sim, mesh, timeScale, running: true, last: performance.now() };
    this.updateDynamicMesh();
    this.startWaterAnim();
    return sim;
  }

  /** Toshqin xaritasi (jonli suvdan): maks. chuqurlik bo'yicha rangli qatlam relyef ustida (ombor tashqarisi).
   *  Rang — xavf sinfi (h·v): sariq (past) → to'q sariq → qizil → to'q qizil (o'ta yuqori). null — olib tashlash. */
  floodMap: THREE.Mesh | null = null;
  showFloodMap(sim: WaterSim | null) {
    if (this.floodMap) {
      if (this.alive()) this.world.scene.three.remove(this.floodMap);
      this.floodMap.geometry.dispose();
      (this.floodMap.material as THREE.Material).dispose();
      this.floodMap = null;
    }
    if (!sim || !this.alive()) return;
    const { nx, ny, dx, dy, x0, y0, hMax, hvMax, initial } = sim;
    const b = sim.base;
    const pos = new Float32Array(nx * ny * 3);
    const col = new Float32Array(nx * ny * 3);
    const idx: number[] = [];
    const wet = (k: number) => !initial[k] && hMax[k] >= 0.3;
    for (let j = 0; j < ny - 1; j++) for (let i = 0; i < nx - 1; i++) {
      const a = j * nx + i;
      if (wet(a) || wet(a + 1) || wet(a + nx) || wet(a + nx + 1)) idx.push(a, a + 1, a + nx, a + 1, a + nx + 1, a + nx);
    }
    const palette = [new THREE.Color("#f2d94e"), new THREE.Color("#f0902e"), new THREE.Color("#d9392b"), new THREE.Color("#7a1010")];
    const c = new THREE.Color();
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      const k = j * nx + i;
      const p = this.ifcToThree([x0 + (i + 0.5) * dx, y0 + (j + 0.5) * dy, wet(k) ? b[k] + hMax[k] : b[k] - 3 * Math.max(dx, dy)]);
      pos[k * 3] = p.x; pos[k * 3 + 1] = p.y; pos[k * 3 + 2] = p.z;
      const hv = hvMax[k];
      c.copy(palette[hv < 0.3 ? 0 : hv < 0.6 ? 1 : hv < 1.2 ? 2 : 3]);
      col[k * 3] = c.r; col[k * 3 + 1] = c.g; col[k * 3 + 2] = c.b;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
    geo.setIndex(idx);
    geo.computeVertexNormals();
    const mat = new THREE.MeshStandardMaterial({ vertexColors: true, transparent: true, opacity: 0.75, side: THREE.DoubleSide, depthWrite: false, roughness: 0.9 });
    this.floodMap = new THREE.Mesh(geo, mat);
    this.floodMap.renderOrder = 3;
    this.world.scene.three.add(this.floodMap);
  }

  /** Suv bosgan inshootlar: har elementning tag markazida maks. chuqurlik (jonli suv xaritasi bo'yicha). */
  async floodedElements(sim: WaterSim, minDepth = 0.3): Promise<{ localId: number; guid: string | null; name: string; category: string; depth: number; t_arrive: number; hv: number }[]> {
    if (!this.model) return [];
    const ids = await this.model.getItemsIdsWithGeometry();
    const boxes = await this.model.getBoxes(ids);
    const out: { localId: number; guid: string | null; name: string; category: string; depth: number; t_arrive: number; hv: number }[] = [];
    const hits: { id: number; f: ReturnType<WaterSim["floodAt"]>; bottom: number }[] = [];
    ids.forEach((id, i) => {
      const bx = boxes[i];
      if (!bx || bx.isEmpty()) return;
      const sz = bx.getSize(new THREE.Vector3());
      if (Math.max(sz.x, sz.z) > 400) return; // relyef/ombor kabi katta yuzalar emas
      const c = bx.getCenter(new THREE.Vector3());
      const [x, y] = this.threeToIfc(c);
      const [, , bottom] = this.threeToIfc(new THREE.Vector3(c.x, bx.min.y, c.z));
      const f = sim.floodAt(x, y);
      if (f.initial || f.h_max < minDepth) return;
      // element tubi suv sathidan past bo'lsa — bosgan
      if (bottom > f.ground + f.h_max) return;
      hits.push({ id, f, bottom });
    });
    if (!hits.length) return [];
    const items = await this.describe(hits.map((h) => h.id));
    hits.forEach((h, i) => out.push({ localId: h.id, guid: items[i]?.guid ?? null, name: items[i]?.name ?? "", category: items[i]?.category ?? "", depth: Math.max(0, h.f.ground + h.f.h_max - h.bottom), t_arrive: h.f.t_arrive, hv: h.f.hv_max }));
    return out.sort((a, b) => b.depth - a.depth);
  }

  stopDynamicWater() {
    const d = this.dyn;
    if (!d) return;
    this.dyn = null;
    try {
      if (this.alive()) this.world.scene.three.remove(d.mesh);
      d.mesh.geometry?.dispose();
      (d.mesh.material as THREE.Material | null)?.dispose();
    } catch { /* allaqachon tozalangan */ }
  }

  private updateDynamicMesh() {
    const d = this.dyn;
    if (!d) return;
    const { sim, mesh } = d;
    const { nx, ny, b, h, dx, dy, x0, y0 } = sim;
    const pos = mesh.geometry.attributes.position as THREE.BufferAttribute;
    const col = mesh.geometry.attributes.color as THREE.BufferAttribute;
    const shallow = new THREE.Color("#7cc4ee"), deep = new THREE.Color("#12386b"), foam = new THREE.Color("#d9eef8"), c = new THREE.Color();
    for (let j = 0; j < ny; j++) {
      for (let i = 0; i < nx; i++) {
        const k = j * nx + i;
        const wet = h[k] > 0.12; // yupqa parda (< 12 sm) ko'rsatilmaydi
        // quruq katak: yer ostiga chuqur (tik yonbag'irda ham ko'rinmasin) — qirg'oq chizig'i uchburchak ichida hosil bo'ladi
        const p = this.ifcToThree([x0 + (i + 0.5) * dx, y0 + (j + 0.5) * dy, wet ? b[k] + h[k] : b[k] - 6 * Math.max(dx, dy)]);
        pos.setXYZ(k, p.x, p.y, p.z);
        // sayoz (< 0.6 m) — qirg'oq ko'pigi (oqish), 0.6–25 m — och → to'q ko'k
        if (h[k] < 0.6) c.copy(foam).lerp(shallow, h[k] / 0.6);
        else c.copy(shallow).lerp(deep, Math.min(1, (h[k] - 0.6) / 25));
        col.setXYZ(k, c.r, c.g, c.b);
      }
    }
    pos.needsUpdate = true;
    col.needsUpdate = true;
    mesh.geometry.computeVertexNormals();
  }

  /** Yer/inshoot yuzasi balandligi (IFC z) berilgan nuqtada — balandlik xaritasidan bilinear; xarita yo'q → null. */
  groundZ(x: number, y: number): number | null {
    const hm = this.hm;
    if (!hm) return null;
    const fx = (x - hm.x0) / hm.dx - 0.5, fy = (y - hm.y0) / hm.dy - 0.5;
    const i0 = Math.max(0, Math.min(hm.nx - 2, Math.floor(fx))), j0 = Math.max(0, Math.min(hm.ny - 2, Math.floor(fy)));
    const tx = Math.max(0, Math.min(1, fx - i0)), ty = Math.max(0, Math.min(1, fy - j0));
    const z = (i: number, j: number) => hm.z[j * hm.nx + i];
    return (z(i0, j0) * (1 - tx) + z(i0 + 1, j0) * tx) * (1 - ty) + (z(i0, j0 + 1) * (1 - tx) + z(i0 + 1, j0 + 1) * tx) * ty;
  }

  /** Balandlik xaritasi (server: /versions/{id}/heightmap) — suv yuzasini relyef/inshootlarga moslash uchun. */
  private hm: { x0: number; y0: number; dx: number; dy: number; nx: number; ny: number; z: number[] } | null = null;
  private water2Anim: { base: Float32Array; wet: Uint8Array; amp: number } | null = null;
  setHeightmap(hm: { x0: number; y0: number; dx: number; dy: number; nx: number; ny: number; z: number[] } | null) {
    this.hm = hm;
  }

  /** Suv yuzasi relyefga moslashadi (Blender shrinkwrap kabi): sathdan past kataklar — suv, boshqalari yer
   * ostiga yashirinadi; region — qaysi bog'langan havza (yuqori byef / quyi byef / hammasi): to'g'on to'sadi,
   * gerbdan oshsa suv o'zi quyi byefga o'tadi. Rang chuqurlikka qarab (sayoz — och, chuqur — to'q). */
  private conformingWater(ifcZ: number, region: "upstream" | "downstream" | "all", opacity = 0.62, waves = 0.15, colors?: { shallow: string; deep: string; rough?: number }) {
    const hm = this.hm;
    if (!hm) return null;
    const { nx, ny, x0, y0, dx, dy, z } = hm;
    const wetCell = new Uint8Array(nx * ny);
    for (let k = 0; k < nx * ny; k++) wetCell[k] = z[k] < ifcZ ? 1 : 0;
    let mask = wetCell;
    if (region !== "all") {
      // BFS: urug' — yuqori byefda eng katta Y (j = ny-1) qatoridagi eng past ho'l katak, quyi byefda j = 0
      mask = new Uint8Array(nx * ny);
      const rows = region === "upstream" ? [ny - 1, ny - 2, ny - 3] : [0, 1, 2];
      const queue: number[] = [];
      for (const j of rows) {
        let best = -1, bz = Infinity;
        for (let i = 0; i < nx; i++) { const k = j * nx + i; if (wetCell[k] && z[k] < bz) { bz = z[k]; best = k; } }
        if (best >= 0) { queue.push(best); mask[best] = 1; }
      }
      // yuqori byef uchun ombor ichidagi eng past 5 % kataklarni ham urug' qilamiz (bir nechta havza bo'lsa)
      while (queue.length) {
        const k = queue.pop()!;
        const i = k % nx, j = (k - i) / nx;
        const nb = [k - 1, k + 1, k - nx, k + nx];
        if (i === 0) nb[0] = -1; if (i === nx - 1) nb[1] = -1; if (j === 0) nb[2] = -1; if (j === ny - 1) nb[3] = -1;
        for (const n of nb) if (n >= 0 && wetCell[n] && !mask[n]) { mask[n] = 1; queue.push(n); }
      }
      if (!queue.length && !mask.some((v) => v)) mask = wetCell; // urug' topilmadi — hamma ho'l kataklar
    }
    let any = false;
    for (let k = 0; k < nx * ny; k++) if (mask[k]) { any = true; break; }
    if (!any) return null;
    const pos = new Float32Array(nx * ny * 3);
    const col = new Float32Array(nx * ny * 3);
    const shallow = new THREE.Color(colors?.shallow ?? "#5fb3e6"), deep = new THREE.Color(colors?.deep ?? "#173f75"), c = new THREE.Color();
    for (let j = 0; j < ny; j++) {
      for (let i = 0; i < nx; i++) {
        const k = j * nx + i;
        const p = this.ifcToThree([x0 + (i + 0.5) * dx, y0 + (j + 0.5) * dy, mask[k] ? ifcZ : z[k] - 6 * Math.max(dx, dy)]);
        pos[k * 3] = p.x; pos[k * 3 + 1] = p.y; pos[k * 3 + 2] = p.z;
        const depth = Math.max(0, ifcZ - z[k]);
        c.copy(shallow).lerp(deep, Math.min(1, depth / 25));
        col[k * 3] = c.r; col[k * 3 + 1] = c.g; col[k * 3 + 2] = c.b;
      }
    }
    const idx: number[] = [];
    for (let j = 0; j < ny - 1; j++) {
      for (let i = 0; i < nx - 1; i++) {
        const a = j * nx + i, b = a + 1, d = a + nx, e = d + 1;
        if (!(mask[a] || mask[b] || mask[d] || mask[e])) continue; // to'liq quruq katak — chizilmaydi
        idx.push(a, b, d, b, e, d); // normal yuqoriga
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
    geo.setIndex(idx);
    geo.computeVertexNormals();
    const mat = colors?.rough
      ? new THREE.MeshStandardMaterial({ vertexColors: true, transparent: opacity < 1, opacity, side: THREE.DoubleSide, depthWrite: opacity >= 1, roughness: colors.rough, metalness: 0 })
      // suv: fizik material — yaltiroq yuza, muhit aks etishi, yengil «tiniqlik» (clearcoat), chuqurlik rangi vertex rangdan
      : new THREE.MeshPhysicalMaterial({ vertexColors: true, transparent: true, opacity, side: THREE.DoubleSide, depthWrite: false, roughness: 0.18, metalness: 0.0, clearcoat: 0.3, clearcoatRoughness: 0.3, envMapIntensity: 0.35 });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.renderOrder = 2;
    return { mesh, base: pos.slice(), wet: mask, amp: waves };
  }

  /** Loyqa (cho'kindi) qatlami — ombor tubida jigarrang yuza berilgan belgigacha (sediment simulyatsiyasi, yil kursori). */
  private sediment: THREE.Mesh | null = null;
  setSedimentLevel(ifcZ: number | null) {
    if (!this.alive()) return;
    if (this.sediment) { this.world.scene.three.remove(this.sediment); this.sediment.geometry.dispose(); (this.sediment.material as THREE.Material).dispose(); this.sediment = null; }
    if (ifcZ == null || !this.hm) return;
    const built = this.conformingWater(ifcZ, "upstream", 1, 0, { shallow: "#a07a4a", deep: "#6b4a2a", rough: 0.95 });
    if (!built) return;
    this.sediment = built.mesh;
    this.sediment.renderOrder = 1;
    this.world.scene.three.add(this.sediment);
  }

  /** Rasm asoslari (foto/chizma/sun'iy yo'ldosh) — teksturali tekisliklar; ro'yxat DB dan (Underlay). */
  async setUnderlays(list: { id: number; url: string; x: number; y: number; z: number; width_m: number; height_m: number; rotation_deg: number; opacity: number; vertical: boolean; visible: boolean }[], token: string | null) {
    const keep = new Set(list.map((u) => u.id));
    for (const [id, mesh] of this.underlays) {
      if (!keep.has(id)) { this.world.scene.three.remove(mesh); mesh.geometry.dispose(); this.underlays.delete(id); }
    }
    for (const u of list) {
      let mesh = this.underlays.get(u.id);
      if (!mesh) {
        let tex = this.underlayTex.get(u.url);
        if (!tex) {
          try {
            const r = await fetch(u.url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
            const blob = await r.blob();
            const bmp = await createImageBitmap(blob, { imageOrientation: "flipY" });
            tex = new THREE.Texture(bmp);
            tex.colorSpace = THREE.SRGBColorSpace;
            tex.needsUpdate = true;
            this.underlayTex.set(u.url, tex);
          } catch { continue; }
        }
        const mat = new THREE.MeshBasicMaterial({ map: tex, transparent: true, side: THREE.DoubleSide, depthWrite: false });
        mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), mat);
        mesh.renderOrder = -1;
        mesh.userData.underlayId = u.id;
        this.underlays.set(u.id, mesh);
        this.world.scene.three.add(mesh);
      }
      (mesh.material as THREE.MeshBasicMaterial).opacity = u.opacity;
      mesh.visible = u.visible;
      mesh.scale.set(u.width_m, u.height_m, 1);
      mesh.position.copy(this.ifcToThree([u.x, u.y, u.z]));
      mesh.rotation.set(0, 0, 0);
      if (u.vertical) {
        // XZ (IFC) tekisligi — vertikal varaq, gorizontal burish Z (IFC) atrofida
        mesh.rotateY((u.rotation_deg * Math.PI) / 180);
      } else {
        mesh.rotateX(-Math.PI / 2); // yotiq (XY IFC)
        mesh.rotateZ((u.rotation_deg * Math.PI) / 180);
      }
    }
  }

  /** Berilgan GUID lar ichida eng katta (bbox hajmi) element — maydon/tasma qaysi to'g'onga chizilishini tanlash. */
  async largestGuid(guids: string[]): Promise<string | null> {
    if (!this.model || !guids.length) return null;
    const ids = await this.model.getLocalIdsByGuids(guids);
    let best: string | null = null;
    let bestV = -1;
    for (let i = 0; i < guids.length; i++) {
      const id = ids[i];
      if (id == null) continue;
      const [box] = await this.model.getBoxes([id]);
      if (!box) continue;
      const sz = new THREE.Vector3();
      box.getSize(sz);
      const v = sz.x * sz.y * sz.z;
      if (v > bestV) { bestV = v; best = guids[i]; }
    }
    return best;
  }

  /** Model tubi (IFC Z, metr) — suv tekisliklari uchun. */
  /** Model chegarasi IFC koordinatalarda (m): {min:[x,y,z], max:[x,y,z]} yoki null. */
  get boundsIfc(): { min: [number, number, number]; max: [number, number, number] } | null {
    if (!this.bounds) return null;
    const a = this.threeToIfc(this.bounds.min);
    const b = this.threeToIfc(this.bounds.max);
    return { min: [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.min(a[2], b[2])], max: [Math.max(a[0], b[0]), Math.max(a[1], b[1]), Math.max(a[2], b[2])] };
  }

  get baseIfcZ(): number | null {
    return this.bounds ? this.bounds.min.y - this.coords[1] : null;
  }

  /** Zilzila animatsiyasi: modelni (va qoralamalarni) gorizontal silkitish — PGA va davr bo'yicha sintetik
   * tebranish (so'nuvchi sinus paketi), ko'rinishi uchun `scale` marta kattalashtirilgan. */
  shake(pgaG: number, periodS: number, seconds = 6, scale = 60): () => void {
    const obj = this.model?.object;
    if (!obj) return () => undefined;
    const base = obj.position.clone();
    // Haqiqiy siljish (mm lar) ko'rinmaydi — ko'rinish uchun kattalashtiramiz: PGA ga proporsional, model
    // o'lchamining ~0.5 % (0.1 g) … 2 % (0.4 g) atrofida
    const diag = this.bounds ? this.bounds.getSize(new THREE.Vector3()).length() : 100;
    const phys = pgaG * 9.81 * Math.pow(Math.max(periodS, 0.1) / (2 * Math.PI), 2) * scale;
    const amp = Math.max(phys, diag * Math.min(0.05, 0.05 * pgaG));
    const w = (2 * Math.PI) / Math.max(periodS, 0.1);
    const t0 = performance.now();
    let raf = 0;
    const tick = () => {
      const t = (performance.now() - t0) / 1000;
      if (t > seconds) { obj.position.copy(base); this.world.renderer?.update(); return; }
      const env = t < 1 ? t : Math.exp(-(t - 1) / (seconds / 2.5)); // o'sish → so'nish
      obj.position.set(base.x + amp * env * Math.sin(w * t), base.y + amp * env * 0.25 * Math.sin(w * t * 1.7), base.z + amp * env * 0.6 * Math.sin(w * t * 0.8 + 1));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(raf); obj.position.copy(base); };
  }

  private waterAnim = { amp: 0, t0: 0, raf: 0, base: null as Float32Array | null, wet: null as Uint8Array | null };
  private overflow: THREE.Mesh[] = [];
  private overflowTex: THREE.CanvasTexture | null = null;

  /** Suv sathi tekisligi (IFC Z, m). waves — to'lqin amplitudasi (m; 0 — tinch), shamol/ko'chki to'lqini,
   * toshqin uchun; upstreamOnly — faqat to'g'onning yuqori byef (+Y IFC) tomonida (ombor). */
  setWaterLevel(ifcZ: number | null, opts: { waves?: number; upstreamOnly?: boolean } = {}) {
    if (!this.alive()) { this.stopWaterAnim(); return; }
    if (this.dyn && ifcZ != null) return; // jonli suv ishlayapti — statik tekislik qo'yilmaydi
    if (this.water) {
      this.world.scene.three.remove(this.water);
      this.water.geometry.dispose();
      (this.water.material as THREE.Material).dispose();
      this.water = null;
    }
    if (ifcZ == null || !this.bounds) { this.stopWaterAnim(); return; }
    if (this.hm) {
      const amp0 = opts.waves ?? 0.15;
      const built = this.conformingWater(ifcZ, opts.upstreamOnly ? "upstream" : "all", 0.62, amp0);
      if (built) {
        this.water = built.mesh;
        this.world.scene.three.add(this.water);
        this.waterAnim.amp = amp0;
        this.waterAnim.base = built.base;
        this.waterAnim.wet = built.wet;
        this.startWaterAnim();
        return;
      }
    }
    const b = this.bounds;
    const sx = (b.max.x - b.min.x) * 1.4 + 20;
    const full = (b.max.z - b.min.z) * 1.4 + 20;
    const sz = opts.upstreamOnly ? full / 2 : full;
    const seg = Math.min(96, Math.max(24, Math.round(Math.max(sx, sz) / 8)));
    const geo = new THREE.PlaneGeometry(sx, sz, seg, Math.max(8, Math.round(seg * sz / sx)));
    geo.rotateX(-Math.PI / 2);
    const mat = new THREE.MeshStandardMaterial({
      color: new THREE.Color("#2b7fd6"),
      transparent: true,
      opacity: 0.55,
      side: THREE.DoubleSide,
      depthWrite: false,
      roughness: 0.15,
      metalness: 0.1,
    });
    this.water = new THREE.Mesh(geo, mat);
    // upstreamOnly: +Y IFC = −Z three → tekislik markazi model markazidan ombor tomonga suriladi
    const cz = opts.upstreamOnly ? (b.min.z + b.max.z) / 2 - full / 4 : (b.min.z + b.max.z) / 2;
    this.water.position.set((b.min.x + b.max.x) / 2, ifcZ + this.coords[1], cz);
    this.world.scene.three.add(this.water);
    const amp = opts.waves ?? Math.min(0.25, Math.max(0.03, sx / 4000));
    this.waterAnim.amp = amp;
    this.waterAnim.base = (geo.attributes.position.array as Float32Array).slice();
    this.waterAnim.wet = null;
    this.startWaterAnim();
  }

  private startWaterAnim() {
    if (this.waterAnim.raf) return;
    this.waterAnim.t0 = performance.now();
    const tick = () => {
      if (this.disposed || !this.alive()) { this.stopWaterAnim(); return; } // viewer yopilgan (HMR/sahifa) — sikl to'xtaydi
      this.waterAnim.raf = requestAnimationFrame(tick);
      const t = (performance.now() - this.waterAnim.t0) / 1000;
      const animate = (w: THREE.Mesh | null, base: Float32Array | null, wet: Uint8Array | null, a: number) => {
        if (!w || !base || !w.geometry?.attributes?.position) return;
        const pos = w.geometry.attributes.position as THREE.BufferAttribute;
        const k1 = 2 * Math.PI / Math.max(12, a * 60), k2 = 2 * Math.PI / Math.max(19, a * 90);
        for (let i = 0; i < pos.count; i++) {
          if (wet && !wet[i]) continue; // quruq nuqtalar yer ostida qoladi
          const x = base[i * 3], z = base[i * 3 + 2];
          pos.setY(i, base[i * 3 + 1] + a * (Math.sin(k1 * x + 1.3 * t) + 0.6 * Math.sin(k2 * z + 0.9 * t + 1.7) + 0.35 * Math.sin(k1 * 0.7 * (x + z) - 1.1 * t)));
        }
        pos.needsUpdate = true;
        w.geometry.computeVertexNormals();
      };
      if (this.dyn && this.dyn.running) {
        const now = performance.now();
        const real = Math.min(0.1, (now - this.dyn.last) / 1000);
        this.dyn.last = now;
        this.dyn.sim.advance(real * this.dyn.timeScale);
        this.dyn.onTick?.(this.dyn.sim);
        this.updateDynamicMesh();
      }
      animate(this.water, this.waterAnim.base, this.waterAnim.wet, this.waterAnim.amp);
      if (this.water2Anim) animate(this.water2, this.water2Anim.base, this.water2Anim.wet, this.water2Anim.amp);
      const w = this.water;
      if (this.overflowTex) { this.overflowTex.offset.y -= 0.02; this.overflowTex.needsUpdate = true; }
      if (!w && !this.overflow.length && !this.dyn) this.stopWaterAnim();
    };
    tick();
  }

  private stopWaterAnim() {
    if (this.waterAnim.raf) cancelAnimationFrame(this.waterAnim.raf);
    this.waterAnim.raf = 0;
  }

  /** Toshib chiqish / suv tashlagichdan oqim: element ustidan (bbox tepasi) quyi byef tomonga (+Z three)
   * oqadigan yarim shaffof «parda» — chiziqlar pastga harakatlanadi. items: {guid, topZ (IFC), bottomZ (IFC),
   * intensity 0..1}. Bo'sh — olib tashlash. */
  async setOverflow(items: { guid: string; topZ: number; bottomZ: number; intensity: number }[]) {
    if (!this.alive()) return;
    for (const m of this.overflow) { this.world.scene.three.remove(m); m.geometry.dispose(); }
    this.overflow = [];
    if (!items.length || !this.model) return;
    if (!this.overflowTex) {
      const c = document.createElement("canvas");
      c.width = 64; c.height = 256;
      const g = c.getContext("2d")!;
      g.fillStyle = "rgba(180,220,255,0.55)"; g.fillRect(0, 0, 64, 256);
      g.fillStyle = "rgba(255,255,255,0.85)";
      for (let y = 0; y < 256; y += 32) g.fillRect(0, y, 64, 10);
      this.overflowTex = new THREE.CanvasTexture(c);
      this.overflowTex.wrapS = this.overflowTex.wrapT = THREE.RepeatWrapping;
    }
    for (const it of items) {
      const [id] = await this.model.getLocalIdsByGuids([it.guid]);
      if (id == null) continue;
      const [box] = await this.model.getBoxes([id]);
      if (!box) continue;
      const top = it.topZ + this.coords[1];
      const bottom = it.bottomZ + this.coords[1];
      const drop = Math.max(top - bottom, 1);
      const w = box.max.x - box.min.x;
      // profil: gerbdan (yuqori byef chekkasi) quyi byef etagigacha — parabola (erkin tushuvchi oqim)
      const n = 12;
      const pts: THREE.Vector3[] = [];
      for (let i = 0; i <= n; i++) {
        const f = i / n;
        const y = top - drop * f * f;
        const z = box.min.z + (box.max.z - box.min.z) * Math.min(1, 0.3 + 0.9 * f) + 6 * f;
        pts.push(new THREE.Vector3(0, y, z));
      }
      const geo = new THREE.BufferGeometry();
      const verts: number[] = [];
      const uvs: number[] = [];
      const idx: number[] = [];
      const thick = 0.6 + 2.5 * it.intensity;
      for (let i = 0; i <= n; i++) {
        const q = pts[i];
        verts.push(box.min.x, q.y + thick, q.z, box.max.x, q.y + thick, q.z);
        uvs.push(0, i / n * 6, w / 40, i / n * 6);
      }
      for (let i = 0; i < n; i++) {
        const a = i * 2;
        idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
      }
      geo.setAttribute("position", new THREE.Float32BufferAttribute(verts, 3));
      geo.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
      geo.setIndex(idx);
      geo.computeVertexNormals();
      const mat = new THREE.MeshBasicMaterial({ map: this.overflowTex, transparent: true, opacity: 0.35 + 0.5 * it.intensity, side: THREE.DoubleSide, depthWrite: false });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.renderOrder = 5;
      this.overflow.push(mesh);
      this.world.scene.three.add(mesh);
    }
    if (this.overflow.length) this.startWaterAnim();
  }

  /** Skalyar maydon tekisligi (CFD): elementning eng uzun gorizontal o'qi bo'ylab, vertikal bo'yicha
   * bbox balandligi. grid — nx×ny qiymatlar 0..1 (chapdan o'ngga, pastdan yuqoriga). null — olib tashlash. */
  async showFieldPlane(guid: string | null, grid: { nx: number; ny: number; values: number[] } | null, colorAt: (t: number) => [number, number, number]) {
    if (!this.alive()) return;
    if (this.field) {
      this.world.scene.three.remove(this.field);
      this.field.geometry.dispose();
      (this.field.material as THREE.Material).dispose();
      this.field = null;
    }
    if (!guid || !grid || !this.model) return;
    const [id] = await this.model.getLocalIdsByGuids([guid]);
    if (id == null) return;
    const [box] = await this.model.getBoxes([id]);
    if (!box) return;
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
    this.field = new THREE.Mesh(geo, mat);
    this.field.renderOrder = 10;
    if (!alongX) this.field.rotation.y = Math.PI / 2;
    this.field.position.copy(center);
    this.world.scene.three.add(this.field);
  }

  /** To'g'on ko'ndalang kesimi ustiga simulyatsiya sxemasi (dam_stability / seepage): hisob profili, kuchlar
   *  (strelkalar + yorliqlar), depressiya egri chizig'i (filtratsiya) — element bbox iga moslab. Konvensiya:
   *  to'g'on uzun o'qi bo'ylab, ko'ndalang o'q — qisqa gorizontal tomon, yuqori byef — IFC koordinatasi katta tomon
   *  (conformingWater bilan bir xil). spec null — olib tashlash. */
  private section: THREE.Group | null = null;
  async showSection(guid: string | null, spec: { profile?: [number, number][]; h1?: number; h2?: number; phreatic?: { x: number[]; y: number[] }; forces?: { name: string; v_kn: number; h_kn: number; arm_v_m: number; arm_h_m: number }[] } | null) {
    if (!this.alive()) return;
    if (this.section) {
      this.world.scene.three.remove(this.section);
      this.section.traverse((o) => { const m = o as THREE.Mesh; m.geometry?.dispose?.(); const mat = m.material as THREE.Material | undefined; if (mat && "map" in mat) ((mat as THREE.SpriteMaterial).map)?.dispose(); mat?.dispose?.(); });
      this.section = null;
    }
    if (!guid || !spec || !this.model) return;
    const [id] = await this.model.getLocalIdsByGuids([guid]);
    if (id == null) return;
    const [box] = await this.model.getBoxes([id]);
    if (!box || box.isEmpty()) return;
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
    const label = (text: string, at: THREE.Vector3, color = "#ffffff") => {
      const c = document.createElement("canvas");
      c.width = 256; c.height = 64;
      const ctx = c.getContext("2d")!;
      ctx.fillStyle = "rgba(20,22,26,0.75)"; ctx.fillRect(0, 0, c.width, c.height);
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
    if (prof.length) line(prof.map(([u, v]) => P(u * su, v * sv)), "#f5a623", true);
    // suv sathlari (h1 yuqori, h2 quyi byef) — qisqa gorizontal chiziqlar
    if (spec.h1 != null && spec.h1 > 0) { line([P(-B * 0.6, spec.h1 * sv), P(0, spec.h1 * sv)], "#3d8ee6"); label(`h₁ ${spec.h1.toFixed(1)} m`, P(-B * 0.6, spec.h1 * sv + H * 0.06), "#9cc8ff"); }
    if (spec.h2 != null && spec.h2 > 0) { line([P(B, spec.h2 * sv), P(B * 1.6, spec.h2 * sv)], "#3d8ee6"); label(`h₂ ${spec.h2.toFixed(1)} m`, P(B * 1.6, spec.h2 * sv + H * 0.06), "#9cc8ff"); }
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
      const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: new THREE.Color("#3d8ee6"), transparent: true, opacity: 0.45, side: THREE.DoubleSide, depthTest: false }));
      m.renderOrder = 19;
      g.add(m);
      line(xs.map((x, i) => P((x / L) * B, ys[i] * sph)), "#7cc4ee");
      label("Depressiya egri chizig'i", P(B * 0.45, ys[Math.floor(ys.length / 2)] * sph + H * 0.08), "#9cc8ff");
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
        const color = f.name.startsWith("Og'irlik") ? "#e0e0e0" : f.name.startsWith("Filtratsion") ? "#e0656a" : f.name.startsWith("Inersiya") || f.name.startsWith("Westergaard") ? "#b46dcc" : "#3d8ee6";
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
    this.section = g;
    this.world.scene.three.add(g);
  }

  /** Ekran o'lchamidagi matnli sprite (yorliq): matn, rang, fon. */
  private makeLabel(text: string, color = "#e8eaee", bg = "rgba(20,22,26,0.72)", scale = 0.055): THREE.Sprite {
    const c = document.createElement("canvas");
    c.width = 512; c.height = 56;
    const ctx = c.getContext("2d")!;
    ctx.font = "600 24px system-ui, sans-serif";
    const w = Math.min(500, ctx.measureText(text).width + 20);
    ctx.fillStyle = bg; ctx.fillRect(0, 0, w, 56);
    ctx.fillStyle = color; ctx.textBaseline = "middle"; ctx.fillText(text, 10, 28, 490);
    const tex = new THREE.CanvasTexture(c);
    tex.repeat.x = w / 512;
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false, transparent: true, sizeAttenuation: false }));
    sp.scale.set(scale * (w / 56), scale, 1);
    sp.center.set(0.5, 0);
    sp.renderOrder = 30;
    return sp;
  }
  private disposeLabelGroup(g: THREE.Group | null) {
    if (!g) return;
    if (this.alive()) this.world.scene.three.remove(g);
    g.traverse((o) => { const sp = o as THREE.Sprite; if (sp.isSprite) { (sp.material as THREE.SpriteMaterial).map?.dispose(); sp.material.dispose(); } });
  }

  /** Jonli qiymat yorliqlari (monitoring): GUID → matn (masalan «Sath 890.2 m»), rang — alarm bo'yicha. null — olib tashlash. */
  private valueLabels: THREE.Group | null = null;
  async setValueLabels(items: { guid: string; text: string; color?: string; alarm?: boolean }[] | null) {
    if (!this.alive()) return;
    this.disposeLabelGroup(this.valueLabels);
    this.valueLabels = null;
    if (!items?.length || !this.model) return;
    const ids = await this.model.getLocalIdsByGuids(items.map((i) => i.guid));
    const valid = ids.map((id, i) => ({ id, it: items[i] })).filter((x): x is { id: number; it: { guid: string; text: string; color?: string; alarm?: boolean } } => x.id != null);
    if (!valid.length) return;
    const boxes = await this.model.getBoxes(valid.map((v) => v.id));
    const g = new THREE.Group();
    g.name = "value-labels";
    valid.forEach((v, i) => {
      const bx = boxes[i];
      if (!bx || bx.isEmpty()) return;
      const sp = this.makeLabel(v.it.text, "#ffffff", v.it.color ? `${v.it.color}cc` : "rgba(20,22,26,0.8)", 0.05);
      const sz = bx.getSize(new THREE.Vector3());
      sp.position.set((bx.min.x + bx.max.x) / 2, bx.max.y + Math.max(0.3, sz.y * 0.05), (bx.min.z + bx.max.z) / 2);
      sp.center.set(0.5, this.labels ? -0.25 : 0); // nom yorliqlari yoqiq bo'lsa — ularning ustida
      sp.userData.alarm = !!v.it.alarm; // alarm — miltillaydi (SCADA HMI kabi)
      g.add(sp);
    });
    this.valueLabels = g;
    this.world.scene.three.add(g);
    if (valid.some((v) => v.it.alarm)) this.startLiveAnim();
  }

  /** SCADA → 3D animatsiya (raqamli egizak HMI): darvoza ochilishi (element ko'tariladi), agregat ishlayapti
   *  (aylanuvchi halqa), quvurdagi oqim (harakatlanuvchi punktir, yo'nalish va tezlik sarfga qarab).
   *  items: {guid, kind: position|status|power|flow, value, running?}. null/[] — olib tashlash. */
  private live = new Map<string, { kind: string; obj: THREE.Object3D; localId: number; base?: THREE.Vector3; height?: number; speed: number; on: boolean; len?: number }>();
  private liveRaf = 0;
  async setLiveBindings(items: { guid: string; kind: string; value: number | null; running?: boolean }[] | null) {
    if (!this.alive()) return;
    const keep = new Set((items ?? []).map((i) => i.guid));
    for (const [g, b] of this.live) if (!keep.has(g)) { await this.dropLive(g, b); }
    if (!items?.length || !this.model) { this.stopLiveAnim(); return; }
    const guids = items.map((i) => i.guid);
    const ids = await this.model.getLocalIdsByGuids(guids);
    const valid = items.map((it, i) => ({ it, id: ids[i] })).filter((x): x is { it: typeof items[number]; id: number } => x.id != null);
    const boxes = await this.model.getBoxes(valid.map((v) => v.id));
    for (let i = 0; i < valid.length; i++) {
      const { it, id } = valid[i];
      const bx = boxes[i];
      if (!bx || bx.isEmpty()) continue;
      const sz = bx.getSize(new THREE.Vector3()), c = bx.getCenter(new THREE.Vector3());
      let b = this.live.get(it.guid);
      if (b && b.kind !== it.kind) { await this.dropLive(it.guid, b); b = undefined; }
      if (it.kind === "position") {
        // darvoza: asl element yashiriladi, nusxasi ochilish % ga ko'tariladi
        if (!b) {
          const geo = await this.cloneGeometry(id);
          if (!geo) continue;
          const mesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: new THREE.Color("#c8553d"), roughness: 0.6, metalness: 0.2 }));
          mesh.renderOrder = 1;
          this.world.scene.three.add(mesh);
          await this.setItemsVisible([id], false);
          b = { kind: it.kind, obj: mesh, localId: id, base: new THREE.Vector3(0, 0, 0), height: sz.y, speed: 0, on: false };
          this.live.set(it.guid, b);
        }
        const open = Math.max(0, Math.min(1, (it.value ?? 0) / 100));
        b.obj.position.y = (b.height ?? sz.y) * open; // to'liq ochiq — o'z balandligiga ko'tariladi
      } else if (it.kind === "status" || it.kind === "power") {
        // agregat: halqa (ishlayotganda yashil, aylanadi)
        if (!b) {
          const r = Math.max(sz.x, sz.z) * 0.65;
          const ring = new THREE.Mesh(new THREE.TorusGeometry(r, Math.max(0.15, r * 0.06), 8, 40), new THREE.MeshStandardMaterial({ color: new THREE.Color("#3aa864"), emissive: new THREE.Color("#1c5c36"), roughness: 0.4 }));
          ring.rotation.x = Math.PI / 2;
          ring.position.set(c.x, bx.max.y + Math.max(0.5, sz.y * 0.08), c.z);
          ring.renderOrder = 5;
          this.world.scene.three.add(ring);
          b = { kind: it.kind, obj: ring, localId: id, speed: 0, on: false };
          this.live.set(it.guid, b);
        }
        const running = it.running ?? (it.kind === "status" ? (it.value ?? 0) >= 0.5 : (it.value ?? 0) > 0.5);
        b.on = running;
        b.speed = running ? 1.5 : 0;
        const m = (b.obj as THREE.Mesh).material as THREE.MeshStandardMaterial;
        m.color.set(running ? "#3aa864" : "#6a6e76");
        m.emissive.set(running ? "#1c5c36" : "#222");
      } else if (it.kind === "flow") {
        // quvur/kanal: uzun o'q bo'ylab harakatlanuvchi punktir (yo'nalish — sarf ishorasi, tezlik — |Q|)
        const axis = sz.x >= sz.z ? "x" : "z";
        const len = axis === "x" ? sz.x : sz.z;
        if (!b) {
          const a = c.clone(), e = c.clone();
          if (axis === "x") { a.x = bx.min.x; e.x = bx.max.x; } else { a.z = bx.min.z; e.z = bx.max.z; }
          a.y = e.y = bx.max.y + 0.3;
          const geo = new THREE.BufferGeometry().setFromPoints([a, e]);
          const line = new THREE.Line(geo, new THREE.LineDashedMaterial({ color: new THREE.Color("#4fc3f7"), dashSize: Math.max(0.5, len / 24), gapSize: Math.max(0.3, len / 40), depthTest: false, transparent: true, opacity: 0.95 }));
          line.computeLineDistances();
          line.renderOrder = 25;
          this.world.scene.three.add(line);
          b = { kind: it.kind, obj: line, localId: id, speed: 0, on: false, len };
          this.live.set(it.guid, b);
        }
        const q = it.value ?? 0;
        b.on = Math.abs(q) > 1e-6;
        // IFC +y (yuqori byef) → quyi byef oqim: three −z → +z; x o'qi bo'ylab — musbat X
        b.speed = (axis === "z" ? 1 : 1) * Math.sign(q) * Math.min(3, 0.2 + Math.abs(q) / 100) * (len / 24);
        ((b.obj as THREE.Line).material as THREE.LineDashedMaterial).opacity = b.on ? 0.95 : 0.25;
      }
    }
    if ([...this.live.values()].some((b) => b.on) || this.valueLabels?.children.some((o) => o.userData.alarm)) this.startLiveAnim(); else this.stopLiveAnim();
  }
  private async cloneGeometry(localId: number): Promise<THREE.BufferGeometry | null> {
    if (!this.model) return null;
    const groups = await this.model.getItemsGeometry([localId]);
    const pos: number[] = [];
    const v = new THREE.Vector3();
    for (const md of groups[0] ?? []) {
      if (!md.positions) continue;
      const P = md.positions, I = md.indices;
      const n = I ? I.length : P.length / 3;
      for (let i = 0; i < n; i++) { const k = I ? I[i] : i; v.set(P[k * 3], P[k * 3 + 1], P[k * 3 + 2]).applyMatrix4(md.transform); pos.push(v.x, v.y, v.z); }
    }
    if (!pos.length) return null;
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.computeVertexNormals();
    return g;
  }
  private async dropLive(guid: string, b: { obj: THREE.Object3D; localId: number; kind: string }) {
    this.live.delete(guid);
    if (this.alive()) this.world.scene.three.remove(b.obj);
    const m = b.obj as THREE.Mesh;
    m.geometry?.dispose?.();
    (m.material as THREE.Material | undefined)?.dispose?.();
    if (b.kind === "position" && this.model) await this.setItemsVisible([b.localId], true).catch(() => undefined);
  }
  private startLiveAnim() {
    if (this.liveRaf) return;
    let last = performance.now();
    const tick = () => {
      if (this.disposed || !this.alive()) { this.liveRaf = 0; return; }
      this.liveRaf = requestAnimationFrame(tick);
      const now = performance.now(), dt = Math.min(0.1, (now - last) / 1000); last = now;
      for (const b of this.live.values()) {
        if (!b.on) continue;
        if (b.kind === "status" || b.kind === "power") b.obj.rotation.z += b.speed * dt * 2;
        else if (b.kind === "flow") { const mat = (b.obj as THREE.Line).material as THREE.LineDashedMaterial; mat.dashOffset = (mat.dashOffset ?? 0) - b.speed * dt * 4; mat.needsUpdate = true; }
      }
      // alarm yorliqlari miltillaydi
      const ph = 0.6 + 0.4 * Math.sin(now / 160);
      this.valueLabels?.children.forEach((o) => { const sp = o as THREE.Sprite; if (sp.userData.alarm) (sp.material as THREE.SpriteMaterial).opacity = ph; });
    };
    this.liveRaf = requestAnimationFrame(tick);
  }
  private stopLiveAnim() { if (this.liveRaf) cancelAnimationFrame(this.liveRaf); this.liveRaf = 0; }

  /** Element nomlari 3D da (raqamli egizak yorliqlari): kichik/o'rta inshootlar ustida sprite; relyef kabi ulkan
   *  yuzalar va 300 dan ko'p element bo'lsa — faqat GES turlari. on=false — olib tashlash. */
  private labels: THREE.Group | null = null;
  async setLabels(on: boolean) {
    if (!this.alive()) return;
    this.disposeLabelGroup(this.labels);
    this.labels = null;
    if (!on || !this.model) return;
    const ids = await this.model.getItemsIdsWithGeometry();
    const vis = await this.model.getVisible(ids);
    const shown = ids.filter((_, i) => vis[i]);
    const boxes = await this.model.getBoxes(shown);
    const data = await this.model.getItemsData(shown, { attributesDefault: false, attributes: ["Name"] });
    const diag = this.bounds ? this.bounds.getSize(new THREE.Vector3()).length() : 200;
    const g = new THREE.Group();
    g.name = "labels";
    let n = 0;
    shown.forEach((id, i) => {
      const bx = boxes[i];
      if (!bx || bx.isEmpty()) return;
      const sz = bx.getSize(new THREE.Vector3());
      if (Math.max(sz.x, sz.z) > diag * 0.5) return; // relyef/maydon
      const name = attr(data[i], "Name");
      if (!name || n >= 300) return;
      const sp = this.makeLabel(name);
      sp.position.set((bx.min.x + bx.max.x) / 2, bx.max.y + Math.max(0.3, sz.y * 0.05), (bx.min.z + bx.max.z) / 2);
      sp.userData.localId = id;
      g.add(sp);
      n++;
    });
    this.labels = g;
    this.world.scene.three.add(g);
    this.status(`Yorliqlar: ${n} element`);
  }
  get labelsOn() { return !!this.labels; }

  /** GUID → rang (simulyatsiya holati, monitoring). Bo'sh map — ranglarni tozalash. */
  async colorByGuids(colors: Record<string, string>) {
    if (!this.model || !this.alive()) return;
    await this.model.resetHighlight();
    const byColor = new Map<string, string[]>();
    for (const [g, c] of Object.entries(colors)) byColor.set(c, [...(byColor.get(c) ?? []), g]);
    for (const [c, guids] of byColor) {
      const ids = (await this.model.getLocalIdsByGuids(guids)).filter((x): x is number => x != null);
      if (ids.length) await this.model.highlight(ids, { color: new THREE.Color(c), opacity: 1, transparent: false, renderedFaces: FRAGS.RenderedFaces.TWO });
    }
    await this.fragments.core.update(true);
  }

  async clearModel() {
    this.stopLiveAnim();
    for (const [g, b] of this.live) { this.live.delete(g); if (this.alive()) this.world.scene.three.remove(b.obj); }
    void this.setLabels(false);
    void this.setValueLabels(null);
    void this.showSection(null, null);
    this.setSedimentLevel(null);
    if (this.wire) { this.world.scene.three.remove(this.wire); this.wire.geometry.dispose(); (this.wire.material as THREE.Material).dispose(); this.wire = null; this.wireKey = ""; }
    this.showFloodMap(null);
    this.stopDynamicWater();
    this.setWaterLevel(null);
    this.setTailwaterLevel(null);
    await this.setOverflow([]);
    this.hm = null;
    await this.showFieldPlane(null, null, () => [0, 0, 0]);
    this.bounds = null;
    if (!this.model) return;
    await this.highlighter.clear();
    await this.fragments.core.disposeModel(this.model.modelId);
    this.model = null;
  }

  get selection(): number[] {
    if (!this.model) return [];
    return [...(this.highlighter.selection.select?.[this.model.modelId] ?? [])];
  }

  async selectByGuids(guids: string[], zoom = false) {
    if (!this.model) return;
    const ids = (await this.model.getLocalIdsByGuids(guids)).filter((x): x is number => x != null);
    await this.highlighter.highlightByID("select", { [this.model.modelId]: new Set(ids) }, true, zoom);
  }

  async clearSelection() {
    await this.highlighter.clear("select");
  }

  // --- Ko'rinish/yashirish ---
  private async setVisible(ids: number[] | undefined, visible: boolean) {
    if (!this.model) return;
    await this.model.setVisible(ids, visible);
    await this.fragments.core.update(true);
    if (this.shading === "wire") void this.buildWire();
  }
  async hideSelected() {
    const ids = this.selection;
    await this.clearSelection();
    await this.setVisible(ids, false);
    this.status(`${ids.length} element yashirildi`);
  }
  async isolateSelected() {
    if (!this.model) return;
    const ids = this.selection;
    if (ids.length === 0) return;
    await this.clearSelection();
    await this.setVisible(undefined, false);
    await this.setVisible(ids, true);
    this.status(`${ids.length} element ajratildi`);
  }
  async showAll() {
    if (!this.model) return;
    await this.model.resetVisible();
    await this.fragments.core.update(true);
    if (this.shading === "wire") void this.buildWire();
    this.status("Hammasi ko'rsatildi");
  }
  async setCategoryVisible(category: string, visible: boolean) {
    if (!this.model) return;
    const items = await this.model.getItemsOfCategories([new RegExp(`^${category}$`)]);
    await this.setVisible(items[category] ?? [], visible);
  }
  /** Faqat geometriyali kategoriyalar (PropertySet, Unit kabi yordamchi obyektlar chiqmaydi). */
  async getCategories(): Promise<{ category: string; count: number }[]> {
    if (!this.model) return [];
    const withGeom = new Set(await this.model.getItemsIdsWithGeometry());
    const cats = await this.model.getCategories();
    const items = await this.model.getItemsOfCategories(cats.map((c) => new RegExp(`^${c}$`)));
    return cats
      .map((category) => ({ category, count: (items[category] ?? []).filter((id) => withGeom.has(id)).length }))
      .filter((c) => c.count > 0)
      .sort((a, b) => a.category.localeCompare(b.category));
  }

  // --- Xususiyatlar / daraxt ---
  async getProperties(localId: number): Promise<ItemProperties | null> {
    if (!this.model) return null;
    const [data] = await this.model.getItemsData([localId], {
      attributesDefault: true,
      relations: {
        IsDefinedBy: { attributes: true, relations: true },
        DefinesOccurrence: { attributes: false, relations: false },
      },
    });
    if (!data) return null;
    const attributes: { name: string; value: string }[] = [];
    const psets: PropertySet[] = [];
    for (const [key, val] of Object.entries(data)) {
      if (Array.isArray(val)) {
        if (key !== "IsDefinedBy") continue;
        for (const pset of val) {
          const props = (Array.isArray(pset.HasProperties) ? pset.HasProperties : [])
            .map((p: FRAGS.ItemData) => ({ name: attr(p, "Name"), value: attr(p, "NominalValue") }))
            .filter((p) => p.name);
          const qtos = (Array.isArray(pset.Quantities) ? pset.Quantities : []).map((q: FRAGS.ItemData) => {
            const qk = Object.keys(q).find((k) => /Value$/.test(k) && k !== "NominalValue");
            return { name: attr(q, "Name"), value: qk ? attr(q, qk) : "" };
          });
          psets.push({ name: attr(pset, "Name") || attr(pset, "_category"), props: [...props, ...qtos] });
        }
      } else if (!key.startsWith("_") && val && val.value != null && val.value !== "") {
        attributes.push({ name: key, value: String(val.value) });
      }
    }
    const [guid] = await this.model.getGuidsByLocalIds([localId]);
    return { localId, guid: guid ?? null, category: attr(data, "_category"), name: attr(data, "Name"), attributes, psets };
  }

  /** Fazoviy daraxt. Fragments tuzilmasi "kategoriya guruhi → element" tarzida keladi — guruhlarni yig'ib, elementlarga kategoriya beramiz. */
  async getTree(): Promise<TreeNode | null> {
    if (!this.model) return null;
    const root = await this.model.getSpatialStructure();
    const ids: number[] = [];
    const walk = (n: FRAGS.SpatialTreeItem) => {
      if (n.localId != null) ids.push(n.localId);
      n.children?.forEach(walk);
    };
    walk(root);
    const data = await this.model.getItemsData(ids, { attributesDefault: false, attributes: ["Name"] });
    const names = new Map<number, string>();
    ids.forEach((id, i) => names.set(id, attr(data[i], "Name")));
    const item = (n: FRAGS.SpatialTreeItem, category: string): TreeNode => ({
      localId: n.localId,
      category,
      name: n.localId != null ? names.get(n.localId) || "" : "",
      children: (n.children ?? []).flatMap((c) => group(c, category)),
    });
    // Guruh tuguni (localId yo'q) — bolalarini o'z kategoriyasi bilan qaytaradi; element tuguni — o'zini
    const group = (n: FRAGS.SpatialTreeItem, parentCat: string): TreeNode[] =>
      n.localId == null ? (n.children ?? []).map((c) => item(c, n.category ?? parentCat)) : [item(n, parentCat)];
    const top = group(root, root.category ?? "");
    if (top.length === 1) return top[0];
    return { localId: null, category: "", name: "Model", children: top };
  }

  async selectLocalIds(ids: number[], zoom = false) {
    if (!this.model) return;
    await this.highlighter.highlightByID("select", { [this.model.modelId]: new Set(ids) }, true, zoom);
  }

  async childrenOf(localId: number): Promise<number[]> {
    if (!this.model) return [];
    return this.model.getItemsChildren([localId]);
  }

  // --- Diff ranglari ---
  async applyDiff(diff: { added: { guid: string }[]; deleted: { guid: string }[]; changed: { guid: string }[] }) {
    if (!this.model) return;
    await this.clearDiff();
    const paint = async (guids: string[], color: THREE.Color) => {
      if (guids.length === 0) return;
      const ids = (await this.model!.getLocalIdsByGuids(guids)).filter((x): x is number => x != null);
      await this.model!.highlight(ids, { color, opacity: 1, transparent: false, renderedFaces: FRAGS.RenderedFaces.TWO });
    };
    await paint(diff.added.map((x) => x.guid), DIFF_COLORS.added);
    await paint(diff.changed.map((x) => x.guid), DIFF_COLORS.changed);
    // o'chirilganlar yangi modelda yo'q — ularni ro'yxatda ko'rsatamiz
    await this.fragments.core.update(true);
  }
  async clearDiff() {
    if (!this.model) return;
    await this.model.resetHighlight();
    await this.fragments.core.update(true);
  }

  // --- Asboblar ---
  setTool(tool: Tool) {
    if (this.tool === tool) return;
    if (this.tool === "measure") this.measure.cancelCreation();
    this.tool = tool;
    this.measure.enabled = tool === "measure";
    this.clipper.enabled = tool === "section";
    this.highlighter.enabled = tool === "select";
    this.onTool.forEach((l) => l(tool));
    this.status(
      tool === "measure"
        ? "O'lchash: ikki nuqta bosing, Esc — bekor"
        : tool === "section"
          ? "Kesim: yuzaga bosing, tekislik yaratiladi. Esc — chiqish"
          : "Tanlash",
    );
  }
  measureClick() {
    void this.measure.create();
  }
  deleteMeasurements() {
    this.measure.list.clear();
  }
  deleteSections() {
    this.clipper.deleteAll();
  }
  escape() {
    if (this.tool === "measure") this.measure.cancelCreation();
    this.setTool("select");
  }

  // --- Kamera ---
  /** Sahna chegarasi: model (ko'rinadigan elementlar) + qoralamalar. */
  private async sceneBox(): Promise<THREE.Box3 | null> {
    const box = new THREE.Box3();
    if (this.model) {
      try {
        const boxes = await this.model.getBoxes();
        for (const b of boxes) if (!b.isEmpty()) box.union(b);
      } catch { /* */ }
      if (box.isEmpty() && this.bounds) box.copy(this.bounds);
    }
    const dg = this.drafts?.boundingBox();
    if (dg && !dg.isEmpty()) box.union(dg);
    return box.isEmpty() ? null : box;
  }
  /** Qutiga moslash (camera-controls fitToBox; ThatOpen fitToItems katta/siljigan modellarda nishonni 0 da qoldiradi). */
  private async fitBox(box: THREE.Box3, animate = true) {
    const c = this.world.camera.controls;
    const size = box.getSize(new THREE.Vector3());
    // fitToBox kamerani eng yaqin o'qqa «yopishtiradi» (yon ko'rinish) — sfera bilan joriy yo'nalish saqlanadi
    const sphere = box.getBoundingSphere(new THREE.Sphere());
    // quti burchaklari sfera radiusidan kichik — ekranni to'liqroq band qilsin; lekin cho'zilgan model (vodiy) kesilmasin
    sphere.radius = Math.max(sphere.radius * 0.85, Math.max(size.x, size.y, size.z) * 0.52);
    await c.fitToSphere(sphere, animate);
    // yaqin/uzoq tekisliklar sahnaga mos (kichik detal ham, 3 km vodiy ham)
    this.setClipPlanes(size.length());
  }
  async fitAll(animate = true) {
    const box = await this.sceneBox();
    if (box) await this.fitBox(box, animate);
    else await this.world.camera.fitToItems();
  }
  async fitSelection() {
    if (!this.model || this.selection.length === 0) {
      const d = this.drafts?.selected;
      if (d) { this.drafts.fit(d.uid); return; }
      return this.fitAll();
    }
    const boxes = await this.model.getBoxes(this.selection);
    const box = new THREE.Box3();
    for (const b of boxes) if (!b.isEmpty()) box.union(b);
    if (box.isEmpty()) return this.fitAll();
    await this.fitBox(box);
  }
  /** Orbit markazini nuqtaga o'tkazish (Blender: «orbit around selection», ikki marta bosish). */
  async setOrbitTarget(p: THREE.Vector3) {
    const c = this.world.camera.controls;
    const pos = new THREE.Vector3();
    c.getPosition(pos);
    await c.setLookAt(pos.x, pos.y, pos.z, p.x, p.y, p.z, true);
  }
  async setProjection(p: "Perspective" | "Orthographic") {
    await this.world.camera.projection.set(p);
    this.cameraObjListeners.forEach((f) => f());
  }
  async toggleProjection() {
    await this.world.camera.projection.toggle();
    this.cameraObjListeners.forEach((f) => f());
  }
  async setView(view: ViewName) {
    const c = this.world.camera.controls;
    const t = new THREE.Vector3();
    c.getTarget(t);
    const d = c.distance || 50;
    const dirs: Record<ViewName, [number, number, number]> = {
      iso: [1, 0.8, 1],
      top: [0, 1, 0.0001],
      bottom: [0, -1, 0.0001],
      front: [0, 0, 1],
      back: [0, 0, -1],
      left: [-1, 0, 0],
      right: [1, 0, 0],
    };
    const v = new THREE.Vector3(...dirs[view]).normalize().multiplyScalar(d);
    await c.setLookAt(t.x + v.x, t.y + v.y, t.z + v.z, t.x, t.y, t.z, true);
  }

  // --- BCF ko'rinish (viewpoint) ---
  async getViewpoint(): Promise<Viewpoint> {
    const c = this.world.camera.controls;
    const p = new THREE.Vector3();
    const t = new THREE.Vector3();
    c.getPosition(p);
    c.getTarget(t);
    const guids = this.model
      ? (await this.model.getGuidsByLocalIds(this.selection)).filter((g): g is string => !!g)
      : [];
    const section = [...this.clipper.list.values()].map((pl) => ({
      normal: pl.normal.toArray(),
      origin: pl.origin.toArray(),
    }));
    return {
      camera: {
        space: "ifc",
        position: this.threeToIfc(p),
        target: this.threeToIfc(t),
        projection: this.world.camera.projection.current,
      },
      selected_guids: guids,
      section,
    };
  }
  async setViewpoint(vp: Viewpoint) {
    if (vp.camera) {
      const conv = (a: number[]) =>
        vp.camera!.space === "ifc" ? this.ifcToThree(a as [number, number, number]).toArray() : a;
      const [px, py, pz] = conv(vp.camera.position);
      const [tx, ty, tz] = conv(vp.camera.target);
      if (vp.camera.projection === "Orthographic" || vp.camera.projection === "Perspective") {
        await this.setProjection(vp.camera.projection);
      }
      await this.world.camera.controls.setLookAt(px, py, pz, tx, ty, tz, true);
    }
    this.clipper.deleteAll();
    for (const s of vp.section ?? []) {
      this.clipper.createFromNormalAndCoplanarPoint(
        this.world,
        new THREE.Vector3(...(s.normal as [number, number, number])),
        new THREE.Vector3(...(s.origin as [number, number, number])),
      );
    }
    if (vp.selected_guids?.length) await this.selectByGuids(vp.selected_guids);
    else await this.clearSelection();
  }

  dispose() {
    this.resizeObserver?.disconnect();
    if (this.disposed) return;
    this.disposed = true;
    this.drafts?.dispose();
    this.components.dispose();
  }
}

function attr(d: FRAGS.ItemData | undefined, key: string): string {
  const v = d?.[key];
  if (!v || Array.isArray(v)) return "";
  const val = (v as FRAGS.ItemAttribute).value;
  return val == null ? "" : String(val);
}
