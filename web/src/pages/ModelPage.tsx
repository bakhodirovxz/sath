import { useCallback, useEffect, useRef, useState } from "react";
import Icon from "../ui/Icon";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, getToken, type ChangeRequest, type Diff, type Issue, type Member, type Model, type Project, type Underlay, type Version } from "../api/client";
import { useViewer } from "../viewer/useViewer";
import { COMMANDS, type ParsedCommand } from "../viewer/commands";
import type { Hover, NavMode, Shading, ViewName } from "../viewer/Viewer";
import { useAuth } from "../store/auth";
import NotificationsBell from "../ui/NotificationsBell";
import CommandLine from "../ui/CommandLine";
import { ifcLabel, label } from "../ui/format";
import { MenuBar, NavGizmo, ViewportHeader, type Menu } from "./model/ViewportChrome";
import PropertiesPanel from "./model/PropertiesPanel";
import TreePanel from "./model/TreePanel";
import LayersPanel from "./model/LayersPanel";
import VersionsPanel from "./model/VersionsPanel";
import ReviewPanel from "./model/ReviewPanel";
import IssuesPanel from "./model/IssuesPanel";
import SimPanel from "./model/SimPanel";
import MonitoringPanel from "./model/MonitoringPanel";
import ViewsPanel from "./model/ViewsPanel";
import ChecksPanel from "./model/ChecksPanel";
import { AddMenu, DraftList, DraftProps, UnderlayPanel } from "./model/DraftPanel";
import type { Draft } from "../viewer/drafts";
import { DRAFT_KINDS, type DraftKind } from "../viewer/draftKinds";
import ViewportSidebar from "./model/ViewportSidebar";
import PieMenu from "./model/PieMenu";
import SearchMenu from "./model/SearchMenu";
import type { SearchItem } from "../ui/blender";

type Tab = "props" | "layers" | "versions" | "review" | "issues" | "sim" | "mon" | "checks";
/** Xususiyatlar muharriri yorliqlari (Blender Properties editor kabi — vertikal ikonkalar) */
const TABS: { id: Tab; icon: string; title: string }[] = [
  { id: "props", icon: "sliders", title: "Element xususiyatlari" },
  { id: "layers", icon: "layers", title: "Qatlamlar va ko'rinishlar" },
  { id: "versions", icon: "git-branch", title: "Versiyalar" },
  { id: "review", icon: "check-square", title: "Tasdiqlash" },
  { id: "issues", icon: "flag", title: "Issue lar" },
  { id: "sim", icon: "waves", title: "Simulyatsiya / CFD" },
  { id: "mon", icon: "activity", title: "Monitoring (SCADA)" },
  { id: "checks", icon: "shield", title: "Tekshiruv (to'qnashuv, hajm)" },
];
/** Ish maydonlari (Blender workspace tabs) — panel + boshlang'ich yorliq */
const WORKSPACES: { id: string; title: string; tab: Tab }[] = [
  { id: "view", title: "Ko'rish", tab: "props" },
  { id: "review", title: "Tasdiqlash", tab: "review" },
  { id: "sim", title: "Simulyatsiya", tab: "sim" },
  { id: "mon", title: "Monitoring", tab: "mon" },
  { id: "checks", title: "Tekshiruv", tab: "checks" },
];

export default function ModelPage() {
  const { modelId } = useParams();
  const mid = Number(modelId);
  const [params, setParams] = useSearchParams();
  const { containerRef, viewer, ready, selection, tool, status } = useViewer();

  const [model, setModel] = useState<Model | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [versions, setVersions] = useState<Version[]>([]);
  const [crs, setCrs] = useState<ChangeRequest[]>([]);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [current, setCurrent] = useState<Version | null>(null);
  const [loadedKey, setLoadedKey] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [diff, setDiff] = useState<Diff | null>(null);
  const [tab, setTab] = useState<Tab>("versions");
  const [dockOpen, setDockOpen] = useState(true);
  const [toolsOpen, setToolsOpen] = useState(true);
  const [outlinerOpen, setOutlinerOpen] = useState(true);
  const [workspace, setWorkspace] = useState("view");
  const [shading, setShadingState] = useState<Shading>("solid");
  const [gridOn, setGridOn] = useState(true);
  const [labelsOn, setLabelsOn] = useState(false); // element nomlari 3D da
  const toggleLabels = async () => { const vw = viewer.current; if (!vw) return; await vw.setLabels(!labelsOn); setLabelsOn(!labelsOn); };
  const [projection, setProjection] = useState<"Perspective" | "Orthographic">("Perspective");
  const [navMode, setNavMode] = useState<NavMode>("Orbit");
  const [colorScheme, setColorScheme] = useState<"none" | "type" | "storey">("none");
  const [legend, setLegend] = useState<{ name: string; color: string }[] | null>(null);
  const [hover, setHover] = useState<(Hover & { name?: string; category?: string }) | null>(null);
  const [help, setHelp] = useState<boolean>(() => { try { return localStorage.getItem("ges_help_seen") !== "1"; } catch { return false; } });
  const closeHelp = () => { setHelp(false); try { localStorage.setItem("ges_help_seen", "1"); } catch { /* */ } };
  const nav = useNavigate();
  const { user, logout } = useAuth();
  const [log, setLog] = useState("");
  const [openIssue, setOpenIssue] = useState<number | null>(null);
  const [issueTrigger, setIssueTrigger] = useState(0);
  const [viewsRefresh, setViewsRefresh] = useState(0);
  const [simKind, setSimKind] = useState<string | null>(null);
  // Qoralama obyektlar (web da yaratilgan elementlar)
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [underlays, setUnderlays] = useState<Underlay[]>([]); // rasm asoslari (foto/chizma tekisliklari)
  const [npu, setNpu] = useState<{ level: number; zero: number } | null>(null); // maydon pasporti: NPU va model 0
  const [waterOn, setWaterOn] = useState(false);
  useEffect(() => {
    if (!project) return;
    api.site(project.id).then((s) => { const lvl = Number(s.values.normal_level_m); if (s.filled && Number.isFinite(lvl)) setNpu({ level: lvl, zero: Number(s.values.model_zero_m ?? 0) }); }).catch(() => undefined);
  }, [project?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const vw = viewer.current;
    if (!vw || !loadedKey) return;
    if (waterOn && npu) vw.setWaterLevel(npu.level - npu.zero, { upstreamOnly: true });
    else if (tab !== "sim" && tab !== "mon") vw.setWaterLevel(null);
  }, [waterOn, npu, loadedKey]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { void viewer.current?.setUnderlays(underlays, getToken()); }, [underlays, loadedKey]); // eslint-disable-line react-hooks/exhaustive-deps
  // Balandlik xaritasi — suv yuzasi relyef va inshootlarga moslashadi (ombor qirg'og'i, to'g'on to'sadi, quyi byef)
  useEffect(() => {
    const vw = viewer.current;
    if (!vw || !loadedKey || !current) return;
    let dead = false;
    vw.setHeightmap(null);
    api.heightmap(current.id).then((hm) => { if (!dead) { vw.setHeightmap(hm); if (waterOn && npu) vw.setWaterLevel(npu.level - npu.zero, { upstreamOnly: true }); } }).catch(() => undefined);
    return () => { dead = true; };
  }, [loadedKey, current?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  // URL: ?sel=<guid> — elementni tanlab kamerani moslash, ?tab=mon|sim|... — panelni ochish (dashboard/alarm havolalari)
  useEffect(() => {
    if (!loadedKey) return;
    const sel = params.get("sel");
    const t = params.get("tab") as Tab | null;
    if (t && TABS.some((x) => x.id === t)) { setTab(t); setDockOpen(true); }
    if (sel) void viewer.current?.selectByGuids([sel], true);
  }, [loadedKey]); // eslint-disable-line react-hooks/exhaustive-deps
  // Versiya almashganda tahrirlanayotgan/o'chirilgan asl elementlar yana yashiriladi
  useEffect(() => { if (loadedKey) { void viewer.current?.drafts?.syncHidden(); if (labelsOn) void viewer.current?.setLabels(true); } }, [loadedKey]); // eslint-disable-line react-hooks/exhaustive-deps
  const [draftSel, setDraftSel] = useState<Draft | null>(null);
  const [addMenu, setAddMenu] = useState<{ x: number; y: number } | null>(null);
  // Blender: N — viewport yon paneli, Z — shading pie, F3 — operator qidiruvi, Ctrl+Space — maksimal viewport
  const [sideOpen, setSideOpen] = useState(false);
  const [pie, setPie] = useState<{ x: number; y: number } | null>(null);
  const [search, setSearch] = useState(false);
  const maximized = useRef<{ dock: boolean; tools: boolean; outliner: boolean } | null>(null);
  const [draftBusy, setDraftBusy] = useState(false);
  const saveTimers = useRef(new Map<string, number>());
  const [error, setError] = useState("");
  const loadingRef = useRef<number | null>(null);
  const lastMouse = useRef<[number, number]>([300, 200]);

  const role = project?.my_role ?? null;
  const canEdit = role === "engineer" || role === "approver";

  // --- Ma'lumotlar ---
  const reload = useCallback(async () => {
    try {
      const m = await api.model(mid);
      const [p, mem, vs, c, is] = await Promise.all([api.project(m.project_id), api.members(m.project_id), api.versions(m.id), api.changeRequests(m.id), api.issues(m.id)]);
      setModel(m);
      setProject(p);
      setMembers(mem);
      setVersions(vs);
      setCrs(c);
      setIssues(is);
      return vs;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Xatolik");
      return [];
    }
  }, [mid]);

  useEffect(() => {
    void reload();
  }, [reload]);

  // Boshlang'ich versiya: ?v= yoki tasdiqlangan yoki oxirgi
  useEffect(() => {
    if (!ready || versions.length === 0 || current) return;
    const wanted = Number(params.get("v"));
    const v = versions.find((x) => x.id === wanted) ?? versions.find((x) => x.state === "published") ?? versions[0];
    void openVersion(v);
  }, [ready, versions]); // eslint-disable-line react-hooks/exhaustive-deps

  async function openVersion(v: Version) {
    const vw = viewer.current;
    if (!vw || loadingRef.current === v.id) return;
    loadingRef.current = v.id;
    setCurrent(v);
    setDiff(null);
    setParams((prev) => { const n = new URLSearchParams(prev); n.set("v", String(v.id)); return n; }, { replace: true });
    setProgress(0);
    try {
      const label = `${model?.name ?? "model"} v${v.number}`;
      // Avval serverda tayyor fragments (katta IFC ni brauzer parse qilmaydi), bo'lmasa IFC
      const frag = await api.versionFragments(v.id).catch(() => null);
      if (frag) await vw.loadFragments(frag, label);
      else await vw.loadIfc(await api.versionFile(v.id), label, (p) => setProgress(p));
      setLoadedKey(`${v.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Model yuklanmadi");
    } finally {
      setProgress(null);
      loadingRef.current = null;
    }
  }

  async function showDiff(v: Version, from?: number) {
    const vw = viewer.current;
    if (!vw) return;
    try {
      const d = await api.diff(v.id, from);
      setDiff(d);
      await vw.applyDiff(d);
      setLog(`Farq: +${d.summary.added} ~${d.summary.changed} −${d.summary.deleted}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Farqni hisoblab bo'lmadi");
    }
  }
  async function clearDiff() {
    setDiff(null);
    await viewer.current?.clearDiff();
  }

  // --- Buyruqlar ---
  const onCommand = useCallback(
    async (cmd: ParsedCommand) => {
      const vw = viewer.current;
      if (!vw) return;
      const a0 = (cmd.args[0] ?? "").toUpperCase();
      const say = (s: string) => setLog(s);
      switch (cmd.name) {
        case "ZOOM":
          if (a0 === "S" || a0 === "SEL") await vw.fitSelection(); else await vw.fitAll();
          break;
        case "HIDE": await vw.hideSelected(); break;
        case "ISOLATE": await vw.isolateSelected(); break;
        case "SHOWALL": await vw.showAll(); break;
        case "MEASURE": vw.setTool("measure"); break;
        case "SECTION": vw.setTool("section"); break;
        case "CLEAR": vw.deleteMeasurements(); vw.deleteSections(); await vw.clearDiff(); setDiff(null); say("O'lchov va kesimlar o'chirildi"); break;
        case "SELECT":
          if (cmd.args.length) { await vw.selectByGuids(cmd.args, true); say(`Tanlandi: ${cmd.args.length}`); }
          else { await vw.clearSelection(); }
          break;
        case "FIND": {
          const q = cmd.args.join(" ").toLowerCase();
          if (!q || !vw.model) break;
          const tree = await vw.getTree();
          const found: number[] = [];
          const walk = (n: NonNullable<typeof tree>) => { if (n.localId != null && n.name.toLowerCase().includes(q)) found.push(n.localId); n.children.forEach(walk); };
          if (tree) walk(tree);
          await vw.selectLocalIds(found, true);
          say(found.length ? `Topildi: ${found.length}` : "Topilmadi");
          break;
        }
        case "VIEW": {
          const v = a0.toLowerCase() as ViewName;
          const ok: ViewName[] = ["iso", "top", "front", "back", "left", "right", "bottom"];
          if (ok.includes(v)) { await vw.setView(v); break; }
          if (model && cmd.args.length) {
            const wanted = cmd.args.join(" ").toLowerCase();
            const saved = (await api.views(model.id)).find((x) => x.name.toLowerCase() === wanted);
            if (saved) { await vw.setViewpoint(saved.viewpoint); say(`Ko'rinish: ${saved.name}`); break; }
          }
          say("VIEW TOP|FRONT|BACK|LEFT|RIGHT|BOTTOM|ISO yoki saqlangan nom");
          break;
        }
        case "VSAVE": {
          const nm = cmd.args.join(" ").trim();
          if (!model || !nm) { say("VSAVE <nom>"); break; }
          await api.saveView(model.id, nm, await vw.getViewpoint());
          setViewsRefresh((n) => n + 1);
          say(`Saqlandi: ${nm}`);
          break;
        }
        case "PROJ": await vw.toggleProjection(); say(`Proyeksiya: ${vw.world.camera.projection.current}`); break;
        case "LAYER": setTab("layers"); setDockOpen(true); break;
        case "PROPS": setTab("props"); setDockOpen(true); break;
        case "TREE": setOutlinerOpen(true); setDockOpen(true); break;
        case "DIFF": if (current) { setTab("versions"); setDockOpen(true); await showDiff(current); } break;
        case "ISSUE": setTab("issues"); setDockOpen(true); setIssueTrigger((n) => n + 1); break;
        case "SIM": setTab("sim"); setDockOpen(true); setSimKind(cmd.args[0] ? cmd.args[0].toLowerCase() : null); break;
        case "CFD": setTab("sim"); setDockOpen(true); setSimKind("cfd"); break;
        case "MON": setTab("mon"); setDockOpen(true); break;
        case "CLASH": case "QTO": setTab("checks"); setDockOpen(true); break;
        case "ESC": vw.escape(); break;
        case "HELP": say(COMMANDS.map((c) => c.name).join("  ")); break;
        default: say(`Noma'lum buyruq: ${cmd.args[0]}. HELP — ro'yxat`);
      }
    },
    [viewer, current, model], // eslint-disable-line react-hooks/exhaustive-deps
  );

  // Canvas ustida bosish: o'lchash asbobi
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onClick = () => { if (viewer.current?.tool === "measure") viewer.current.measureClick(); };
    el.addEventListener("click", onClick);
    return () => el.removeEventListener("click", onClick);
  }, [containerRef, viewer, ready]);

  const activeCount = { review: crs.filter((c) => c.status === "open" || c.status === "changes_requested").length, issues: issues.filter((i) => i.status === "open" || i.status === "in_progress").length };

  const setShading = (m: Shading) => { setShadingState(m); viewer.current?.setShading(m); };
  const pickNavMode = (m: NavMode) => { setNavMode(m); viewer.current?.setNavMode(m); };
  const pickColorScheme = async (m: "none" | "type" | "storey") => { setColorScheme(m); const lg = await viewer.current?.colorScheme(m); setLegend(m === "none" ? null : (lg ?? null)); };
  const render = () => {
    const url = viewer.current?.screenshot(2);
    if (!url) return;
    const a = document.createElement("a"); a.href = url; a.download = `${model?.name ?? "model"}${current ? `_v${current.number}` : ""}.png`; a.click();
  };
  // Hover tooltip: kursor ostidagi element nomi/turi
  useEffect(() => {
    if (!ready || !viewer.current) return;
    let last = -1;
    return viewer.current.subscribeHover(async (h) => {
      if (!h) { last = -1; setHover(null); return; }
      if (h.localId === last) { setHover((p) => (p ? { ...p, x: h.x, y: h.y } : p)); return; }
      last = h.localId;
      const p = await viewer.current?.getProperties(h.localId);
      setHover({ ...h, name: p?.name, category: p?.category });
    });
  }, [ready, viewer]);
  const toggleProjection = async () => { await viewer.current?.toggleProjection(); setProjection(viewer.current?.world.camera.projection.current ?? "Perspective"); };

  // --- Qoralamalar: serverdan yuklash, o'zgarishlarni saqlash (debounce), tanlash ---
  useEffect(() => {
    const vw = viewer.current;
    if (!ready || !vw || !model) return;
    const dm = vw.drafts;
    const offs = [
      dm.subscribe(setDrafts),
      dm.subscribeSelection((d) => { setDraftSel(d); if (d) { setTab("props"); setDockOpen(true); } }),
      dm.subscribeMode(() => setDraftSel((d) => (d ? { ...d } : d))), // G/R/S rejimi o'zgarganda panelni yangilash
      dm.subscribePlaced((d) => {
        if (!canEdit) { setLog("Qoralama saqlanmaydi: faqat muhandis/tasdiqlovchi"); return; }
        const body = dm.payload(d.uid);
        if (!body) return;
        api.createDraft(model.id, body).then((row) => dm.setServerId(d.uid, row.id)).catch((e) => setError(e.message));
      }),
      dm.subscribeRemoved((d) => { if (canEdit && d.id) { void dm.restoreSource(d.uid); api.deleteDraft(d.id).catch((e) => setError(e.message)); } }),
      dm.subscribeChange((d) => {
        if (!canEdit) return;
        const timers = saveTimers.current;
        if (timers.has(d.uid)) window.clearTimeout(timers.get(d.uid));
        timers.set(d.uid, window.setTimeout(() => {
          timers.delete(d.uid);
          const body = dm.payload(d.uid);
          if (!body) return;
          if (d.id) api.updateDraft(d.id, body).catch((e) => setError(e.message));
        }, 600));
      }),
    ];
    api.underlays(model.id).then(setUnderlays).catch(() => undefined);
    api.drafts(model.id).then((rows) => {
      dm.clear();
      for (const r of rows) {
        try {
          dm.add({ id: r.id, kind: r.kind, name: r.name, params: r.params, transform: { x: r.transform.x ?? 0, y: r.transform.y ?? 0, z: r.transform.z ?? 0, rz: r.transform.rz ?? 0, sx: r.transform.sx ?? 1, sy: r.transform.sy ?? 1, sz: r.transform.sz ?? 1 }, psets: r.psets, mesh: r.mesh ?? null, sourceGuid: r.source_guid ?? null, ifcClass: r.ifc_class || null });
        } catch { /* noma'lum tur */ }
      }
      void dm.syncHidden();
    }).catch(() => undefined);
    return () => { offs.forEach((f) => f()); };
  }, [ready, viewer, model?.id, canEdit]); // eslint-disable-line react-hooks/exhaustive-deps

  const startAdd = (k: DraftKind) => { setAddMenu(null); if (!canEdit) { setLog("Element qo'shish — muhandis/tasdiqlovchi uchun"); return; } viewer.current?.drafts.startPlacing(k.id); setLog(`${k.title}: joylashtirish — model/yer ustiga bosing (Esc — bekor)`); };
  const deleteDraft = async (uid: string) => {
    const dm = viewer.current?.drafts; const d = dm?.get(uid);
    if (!dm || !d) return;
    if (d.id) await api.deleteDraft(d.id).catch((e) => setError(e.message));
    await dm.restoreSource(uid); // mavjud element tahriri/o'chirishi bekor — asli qayta ko'rinadi
    dm.remove(uid);
  };
  /** Mavjud IFC elementni tahrirlash: qoralamaga aylantirish (G/R/S, nom, Pset), asli yashiriladi, GUID saqlanadi. */
  const editElement = async (localId: number) => {
    const vw = viewer.current;
    if (!vw || !canEdit) { setLog("Tahrirlash — muhandis/tasdiqlovchi uchun"); return; }
    const p = await vw.getProperties(localId);
    if (!p?.guid) { setError("Element GUID topilmadi"); return; }
    if (vw.drafts.list().some((d) => d.sourceGuid === p.guid)) { setLog("Bu element allaqachon tahrirlanmoqda (Qoralama ro'yxati)"); return; }
    const psets: Record<string, Record<string, unknown>> = {};
    for (const ps of p.psets) { const o: Record<string, unknown> = {}; for (const pr of ps.props) if (pr.name && pr.value !== "") o[pr.name] = Number.isFinite(Number(pr.value)) && pr.value.trim() !== "" ? Number(pr.value) : pr.value; if (Object.keys(o).length) psets[ps.name] = o; }
    setLog("Geometriya olinmoqda…");
    const d = await vw.drafts.fromElement(localId, { guid: p.guid, name: p.name, category: p.category, psets }).catch((e: Error) => { setError(e.message); return null; });
    if (!d) { setLog("Elementning geometriyasi olinmadi"); return; }
    setLog(`«${d.name}» tahrirlanmoqda: G surish · R burish · S masshtab · o'ng panelda nom/Pset · «IFC ga qo'shish» — yangi versiya (GUID saqlanadi)`);
  };
  /** Mavjud elementni o'chirish belgisi — darhol yashiriladi, commitda IFC dan olib tashlanadi. */
  const deleteElement = async (localId: number, skipConfirm = false) => {
    const vw = viewer.current;
    if (!vw || !canEdit) { setLog("O'chirish — muhandis/tasdiqlovchi uchun"); return; }
    const p = await vw.getProperties(localId);
    if (!p?.guid) { setError("Element GUID topilmadi"); return; }
    if (vw.drafts.list().some((d) => d.sourceGuid === p.guid)) { setLog("Bu element allaqachon qoralamada"); return; }
    if (!skipConfirm && !confirm(`«${p.name || p.category}» elementini o'chirish? (yangi versiyada olib tashlanadi; «Qoralama» ro'yxatidan qaytarish mumkin)`)) return;
    await vw.drafts.markDeleted(localId, { guid: p.guid, name: p.name, category: p.category });
    setLog(`«${p.name || p.category}» o'chirishga belgilandi — «IFC ga qo'shish» bilan yangi versiya`);
  };
  const duplicateDraft = (uid: string) => viewer.current?.drafts.duplicate(uid);
  const commitDrafts = async () => {
    if (!model || !viewer.current) return;
    const msg = prompt("Versiya izohi (commit):", `Web 3D: ${drafts.length} ta element qo'shildi`);
    if (msg === null) return;
    setDraftBusy(true);
    try {
      // saqlanmagan o'zgarishlarni avval yuborish
      for (const [uid, t] of saveTimers.current) { window.clearTimeout(t); const d = viewer.current.drafts.get(uid); const body = d && viewer.current.drafts.payload(uid); if (d?.id && body) await api.updateDraft(d.id, body); }
      saveTimers.current.clear();
      const v = await api.commitDrafts(model.id, { message: msg, base_version_id: current?.id ?? null });
      viewer.current.drafts.clear();
      const vs = await reload();
      const nv = vs.find((x) => x.id === v.id);
      if (nv) await openVersion(nv);
      setLog(`Yangi versiya v${v.number}: ${v.guids.length} ta element IFC ga qo'shildi`);
    } catch (e) { setError(e instanceof Error ? e.message : "Xatolik"); } finally { setDraftBusy(false); }
  };
  const pickWorkspace = (id: string) => { setWorkspace(id); const w = WORKSPACES.find((x) => x.id === id); if (w) { setTab(w.tab); setDockOpen(true); } };
  const cmd = (name: string, ...args: string[]) => onCommand({ name, args, raw: [name, ...args].join(" ") });
  /** Ctrl+Space (Blender): viewportni maksimal — dock, asboblar, outliner yashiriladi; qayta bosilsa qaytadi. */
  const toggleMaximize = () => {
    if (maximized.current) {
      const m = maximized.current; maximized.current = null;
      setDockOpen(m.dock); setToolsOpen(m.tools); setOutlinerOpen(m.outliner);
    } else {
      maximized.current = { dock: dockOpen, tools: toolsOpen, outliner: outlinerOpen };
      setDockOpen(false); setToolsOpen(false);
    }
  };
  /** A (Blender): hamma elementni tanlash. */
  const selectAll = async () => {
    const vw = viewer.current; if (!vw) return;
    const t = await vw.getTree(); if (!t) return;
    const ids: number[] = [];
    const walk = (n: { localId: number | null; children: { localId: number | null; children: unknown[] }[] }) => { if (n.localId != null) ids.push(n.localId); n.children.forEach((c) => walk(c as typeof n)); };
    walk(t as unknown as Parameters<typeof walk>[0]);
    await vw.selectLocalIds(ids, false);
  };
  const sideAction = (a: "upload" | "submit" | "issue" | "diff" | "props" | "fit") => {
    if (a === "upload" || a === "submit") { setTab(a === "upload" ? "versions" : "review"); setDockOpen(true); }
    else if (a === "issue") cmd("ISSUE");
    else if (a === "diff") cmd("DIFF");
    else if (a === "props") cmd("PROPS");
    else if (a === "fit") { if (selection.length) void viewer.current?.fitSelection(); else void viewer.current?.fitAll(); }
  };
  const searchItems: SearchItem[] = [
    ...COMMANDS.map((c) => ({ label: c.description, hint: c.name, group: "Buyruq", run: () => cmd(c.name) })),
  ];

  // Tezkor tugmalar (Blender): H yashirish, Alt+H hammasi, / ajratish, Home moslash, . tanlanganga,
  // numpad 1/3/7 (Ctrl — qarama-qarshi), 5 proyeksiya, Z shading, N panel, T asboblar, Esc bekor
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
      const vw = viewer.current;
      if (!vw) return;
      const k = e.key;
      // Qoralamalar (Blender): Shift+A qo'shish, G/R/S, X, Shift+D, Esc
      if ((k === "A" || k === "a") && e.shiftKey) { e.preventDefault(); setAddMenu({ x: lastMouse.current[0], y: lastMouse.current[1] }); return; }
      const dr = vw.drafts.handleKey(e);
      if (dr === "handled") { e.preventDefault(); return; }
      if (dr === "delete") { const d = vw.drafts.selected; if (d) void deleteDraft(d.uid); e.preventDefault(); return; }
      if (dr === "duplicate") { const d = vw.drafts.selected; if (d) duplicateDraft(d.uid); e.preventDefault(); return; }
      // Mavjud IFC element tanlangan: Tab — tahrirlash (Blender edit mode), X/Delete — o'chirish
      if (!vw.drafts.selected && vw.selection.length >= 1) {
        const ids = [...vw.selection];
        if (k === "Tab") { e.preventDefault(); void (async () => { for (const id of ids) await editElement(id); })(); return; }
        if (k === "x" || k === "X" || k === "Delete") { e.preventDefault(); if (ids.length > 1 && !confirm(`${ids.length} ta elementni o'chirish?`)) return; void (async () => { for (const id of ids) await deleteElement(id, ids.length > 1); })(); return; }
      }
      const views: Record<string, [ViewName, ViewName]> = { Numpad1: ["front", "back"], Numpad3: ["right", "left"], Numpad7: ["top", "bottom"], "1": ["front", "back"], "3": ["right", "left"], "7": ["top", "bottom"] };
      const vk = views[e.code] ?? views[k];
      if (vk && (e.code.startsWith("Numpad") || !e.shiftKey)) { void vw.setView(e.ctrlKey ? vk[1] : vk[0]); e.preventDefault(); return; }
      let used = true;
      if (k === "h" && e.altKey) { void vw.showAll(); }
      else if (k === "h" || k === "H") { void vw.hideSelected(); }
      else if (k === "/" || e.code === "NumpadDivide") { void vw.isolateSelected(); }
      else if (k === "Home") { void vw.fitAll(); }
      else if (k === "." || e.code === "NumpadDecimal") { void vw.fitSelection(); }
      else if (e.code === "Numpad5" || k === "5") { void toggleProjection(); }
      else if ((k === "z" || k === "Z") && !e.ctrlKey && !e.repeat) { setPie({ x: lastMouse.current[0], y: lastMouse.current[1] }); }
      else if (k === "n" || k === "N") { setSideOpen((v) => !v); }
      else if (k === "F3") { setSearch(true); }
      else if (k === " " && e.ctrlKey) { toggleMaximize(); }
      else if ((k === "a" || k === "A") && e.altKey) { vw.escape(); }
      else if ((k === "a" || k === "A") && !e.ctrlKey) { void selectAll(); }
      else if ((k === "c" || k === "C") && e.shiftKey) { void vw.fitAll(); }
      else if (k === "t" || k === "T") { setToolsOpen((v) => !v); }
      else if (k === "Escape") { vw.escape(); used = false; }
      else if (k === "F2") { cmd("VSAVE", prompt("Ko'rinish nomi:") ?? ""); }
      else if (k === "F12") { render(); }
      else if (k === "?" || (k === "/" && e.shiftKey)) { setHelp((h) => !h); }
      else if (k === "b" || k === "B") { void vw.sectionBox(); }
      else if (k === "l" || k === "L") { void toggleLabels(); }
      else used = false;
      // ishlatilgan tezkor tugma buyruqlar qatoriga tushmasin (AutoCAD «yozishni boshlash» faqat boshqa harflar uchun)
      if (used) e.preventDefault();
    };
    const onMove = (e: MouseEvent) => { lastMouse.current = [e.clientX, e.clientY]; };
    window.addEventListener("keydown", onKey, true); // capture: buyruqlar qatori fokusidan oldin
    window.addEventListener("mousemove", onMove);
    return () => { window.removeEventListener("keydown", onKey, true); window.removeEventListener("mousemove", onMove); };
  }, [shading, viewer, canEdit, labelsOn]); // eslint-disable-line react-hooks/exhaustive-deps

  const menus: Menu[] = [
    { title: "Fayl", items: [
      { label: "Loyihaga qaytish", onClick: () => nav(project ? `/projects/${project.id}` : "/") },
      { label: "Versiyalar", hint: "yon panel", onClick: () => { setTab("versions"); setDockOpen(true); } },
      { label: "IFC ni yuklab olish", disabled: !current, onClick: () => current && api.downloadCsv(api.versionFileUrl(current.id), `${model?.name ?? "model"}_v${current.number}.ifc`).catch((e) => setError(e.message)) },
      { label: "Ko'rinishni saqlash…", hint: "F2", onClick: () => cmd("VSAVE", prompt("Ko'rinish nomi:") ?? "") },
      { sep: true, label: "" },
      { label: "Dispetcher paneli (SCADA)", onClick: () => project && nav(`/projects/${project.id}/dashboard`) },
      { label: "Chiqish", onClick: () => { logout(); nav("/login"); } },
    ] },
    { title: "Tahrir", items: [
      { label: "Bekor qilish", hint: "Ctrl+Z", disabled: !viewer.current?.drafts?.canUndo, onClick: () => { const m = viewer.current?.drafts.undo(); if (m) setLog(m); } },
      { label: "Qaytarish", hint: "Ctrl+Shift+Z", disabled: !viewer.current?.drafts?.canRedo, onClick: () => { const m = viewer.current?.drafts.redo(); if (m) setLog(m); } },
      { sep: true, label: "" },
      { label: selection.length > 1 ? `${selection.length} ta elementni tahrirlash` : "Elementni tahrirlash (surish/burish/masshtab)", hint: "Tab", disabled: !canEdit || selection.length === 0, onClick: () => void (async () => { for (const s of [...selection]) await editElement(s.localId); })() },
      { label: selection.length > 1 ? `${selection.length} ta elementni o'chirish` : "Elementni o'chirish", hint: "X", disabled: !canEdit || selection.length === 0, onClick: () => void (async () => { const ids = [...selection]; if (ids.length > 1 && !confirm(`${ids.length} ta elementni o'chirish?`)) return; for (const s of ids) await deleteElement(s.localId, ids.length > 1); })() },
      { sep: true, label: "" },
      { label: "Tanlashni bekor qilish", hint: "Esc", onClick: () => viewer.current?.escape() },
      { label: "Yashirish", hint: "H", onClick: () => viewer.current?.hideSelected() },
      { label: "Ajratish (local view)", hint: "/", onClick: () => viewer.current?.isolateSelected() },
      { label: "Hammasini ko'rsatish", hint: "Alt+H", onClick: () => viewer.current?.showAll() },
      { sep: true, label: "" },
      { label: "O'lchash", hint: "DIST", onClick: () => viewer.current?.setTool("measure") },
      { label: "Kesim tekisligi", hint: "SEC", onClick: () => viewer.current?.setTool("section") },
      { label: "O'lchov/kesimlarni tozalash", onClick: () => cmd("CLEAR") },
    ] },
    { title: "Qo'shish", items: [
      { label: "Qo'shish menyusi (kursor yonida)", hint: "Shift+A", onClick: () => setAddMenu({ x: 320, y: 80 }) },
      { sep: true, label: "" },
      ...DRAFT_KINDS.filter((k) => k.group === "Primitivlar").map((k) => ({ label: k.title, onClick: () => startAdd(k) })),
      { sep: true, label: "" },
      ...DRAFT_KINDS.filter((k) => k.group === "GES inshootlari").map((k) => ({ label: k.title, onClick: () => startAdd(k) })),
      { sep: true, label: "" },
      { label: "Qoralamalarni IFC ga qo'shish (yangi versiya)", disabled: drafts.length === 0 || !canEdit, onClick: () => void commitDrafts() },
    ] },
    { title: "Ko'rinish", items: [
      { label: "Hammasiga moslash", hint: "Home", onClick: () => viewer.current?.fitAll() },
      { label: "Tanlanganga moslash", hint: ".", onClick: () => viewer.current?.fitSelection() },
      { sep: true, label: "" },
      { label: "Tepa", hint: "7", onClick: () => viewer.current?.setView("top") },
      { label: "Old", hint: "1", onClick: () => viewer.current?.setView("front") },
      { label: "O'ng", hint: "3", onClick: () => viewer.current?.setView("right") },
      { label: "Izometrik", onClick: () => viewer.current?.setView("iso") },
      { label: projection === "Perspective" ? "Ortografik" : "Perspektiva", hint: "5", onClick: () => void toggleProjection() },
      { sep: true, label: "" },
      { label: "Shading: Solid", hint: "Z", onClick: () => setShading("solid") },
      { label: "Shading: Wireframe", onClick: () => setShading("wire") },
      { label: "Shading: X-ray", onClick: () => setShading("xray") },
      { label: "Shading: Rendered (AO, konturlar)", onClick: () => setShading("rendered") },
      { label: "Kamera: aylantirish / yurish / plan", onClick: () => pickNavMode(navMode === "Orbit" ? "FirstPerson" : navMode === "FirstPerson" ? "Plan" : "Orbit") },
      { label: "Kesim qutisi (tanlangan atrofida)", hint: "B", onClick: () => void viewer.current?.sectionBox() },
      { label: "Render (rasm)", hint: "F12", onClick: render },
      { label: gridOn ? "Gridni yashirish" : "Gridni ko'rsatish", onClick: () => { setGridOn(!gridOn); viewer.current?.setGridVisible(!gridOn); } },
      { label: labelsOn ? "Element nomlarini yashirish" : "Element nomlari (yorliqlar)", hint: "L", onClick: () => void toggleLabels() },
      { sep: true, label: "" },
      { label: dockOpen ? "Yon panelni yashirish" : "Yon panel", hint: "N", onClick: () => setDockOpen(!dockOpen) },
      { label: toolsOpen ? "Asboblarni yashirish" : "Asboblar", hint: "T", onClick: () => setToolsOpen(!toolsOpen) },
      { label: outlinerOpen ? "Outlinerni yig'ish" : "Outliner", onClick: () => setOutlinerOpen(!outlinerOpen) },
    ] },
    { title: "Tanlash", items: [
      { label: "Nomi bo'yicha qidirish…", hint: "FIND", onClick: () => { const q = prompt("Qidiruv (nom):"); if (q) cmd("FIND", ...q.split(" ")); } },
      { label: "GUID bo'yicha…", hint: "SELECT", onClick: () => { const q = prompt("GUID:"); if (q) cmd("SELECT", q); } },
      { label: "Kategoriya bo'yicha (qatlamlar)", onClick: () => { setTab("layers"); setDockOpen(true); } },
      { label: "Outliner", onClick: () => { setOutlinerOpen(true); setDockOpen(true); } },
    ] },
    { title: "Tekshiruv", items: [
      { label: "To'qnashuvlar (clash)", hint: "CLASH", onClick: () => cmd("CLASH") },
      { label: "Hajm-miqdor (QTO)", hint: "QTO", onClick: () => cmd("QTO") },
      { label: "Oldingi versiya bilan farq", hint: "DIFF", onClick: () => cmd("DIFF") },
      { label: "Issue ochish (joriy ko'rinish)", hint: "ISSUE", onClick: () => cmd("ISSUE") },
    ] },
    { title: "Simulyatsiya", items: [
      { label: "Katalog (barcha simulyatsiyalar)", hint: "SIM", onClick: () => cmd("SIM") },
      { label: "Suv ombori / turbina / energiya", onClick: () => cmd("SIM", "hydro") },
      { label: "CFD (OpenFOAM)", hint: "CFD", onClick: () => cmd("CFD") },
      { sep: true, label: "" },
      { label: "Gidravlik zarba (bosim oshishi)", onClick: () => cmd("SIM", "water_hammer") },
      { label: "Agregat–regulyator dinamikasi", onClick: () => cmd("SIM", "governor") },
      { label: "To'g'on barqarorligi", onClick: () => cmd("SIM", "dam_stability") },
      { label: "Yorilish xavfi", onClick: () => cmd("SIM", "cracking") },
      { label: "Qaysi to'g'on turi mos?", onClick: () => cmd("SIM", "dam_type") },
      { label: "Zilzila ta'siri", onClick: () => cmd("SIM", "seismic") },
      { label: "Yog'ingarchilik → toshqin (sel, GLOF)", onClick: () => cmd("SIM", "rainfall") },
      { label: "Suv toshqini / yorilish", onClick: () => cmd("SIM", "flood") },
      { label: "Tog' ko'chishi → to'lqin", onClick: () => cmd("SIM", "landslide") },
      { label: "Filtratsiya / suffoziya", onClick: () => cmd("SIM", "seepage") },
      { label: "Loyqa bosishi", onClick: () => cmd("SIM", "sediment") },
      { label: "Optimal yuk taqsimoti", onClick: () => cmd("SIM", "dispatch") },
      { label: "Transformator yuklanishi (IEC 60076-7)", onClick: () => cmd("SIM", "transformer") },
      { label: "Maxsus (formulalar)", onClick: () => cmd("SIM", "custom") },
      { sep: true, label: "" },
      { label: "Maydon pasporti (yer, tuproq, sathlar)…", onClick: () => project && nav(`/projects/${project.id}/site`) },
      { label: "Monitoring (jonli)", hint: "MON", onClick: () => cmd("MON") },
      { label: "Dispetcher paneli", onClick: () => project && nav(`/projects/${project.id}/dashboard`) },
    ] },
    { title: "Yordam", items: [
      { label: "Qisqa yo'riqnoma", hint: "?", onClick: () => setHelp(true) },
      { label: "Buyruqlar ro'yxati", hint: "HELP", onClick: () => cmd("HELP") },
      { label: "Tezkor tugmalar", onClick: () => setLog("H yashirish · Alt+H hammasi · / ajratish · Home moslash · . tanlanganga · 1/3/7 old/o'ng/tepa (Ctrl — qarama-qarshi) · 5 proyeksiya · Z shading pie · N yon panel · T asboblar · F3 qidiruv · Ctrl+Space maksimal · A hammasi · F2 ko'rinish · Esc bekor") },
      { label: "Sichqoncha", onClick: () => setLog("O'rta tugma — surish, Shift+o'rta — aylantirish, g'ildirak — masshtab (kursorga), chap — tanlash") },
    ] },
  ];

  return (
    <div className={`workspace${dockOpen ? " dock-open" : " dock-hidden"}${toolsOpen ? "" : " tools-hidden"}`}>
      {/* Yuqori satr: brend, menyular, ish maydonlari (Blender), o'ngda versiya/qo'ng'iroq/foydalanuvchi */}
      <div className="topbar ws-top blender-top">
        <Link to="/" className="brand">Sath</Link>
        <MenuBar menus={menus} />
        <div className="ws-tabs">
          {WORKSPACES.map((w) => (
            <button key={w.id} className={workspace === w.id ? "active" : ""} onClick={() => pickWorkspace(w.id)}>
              {w.title}
              {w.id === "review" && activeCount.review > 0 && <span className="count">{activeCount.review}</span>}
            </button>
          ))}
        </div>
        <div className="spacer" />
        {project && model && <span className="crumb-lite"><Link to={`/projects/${project.id}`}>{project.name}</Link> › {model.name}</span>}
        {current && <span className="small muted">v{current.number} <span className={`badge ${current.state}`}>{label(current.state)}</span></span>}
        <NotificationsBell />
        {user?.is_admin && <Link to="/admin" className="small">Boshqaruv</Link>}
        <span className="muted small">{user?.full_name || user?.username}</span>
      </div>

      <ViewportHeader viewer={ready ? viewer.current : null} shading={shading} onShading={setShading} grid={gridOn}
        onGrid={(v) => { setGridOn(v); viewer.current?.setGridVisible(v); }} projection={projection} onProjection={() => void toggleProjection()}
        navMode={navMode} onNavMode={pickNavMode} colorScheme={colorScheme} onColorScheme={(m) => void pickColorScheme(m)} onSectionBox={() => void viewer.current?.sectionBox()} onRender={render} water={{ on: waterOn, level: npu?.level ?? null, onToggle: () => setWaterOn(!waterOn) }}
        right={<span className="dim small">{model?.name}{current ? ` · v${current.number}` : ""}{current?.meta?.element_count ? ` · ${current.meta.element_count} element` : ""}</span>} />

      <div className="ws-tools">
        <ToolBtn title="Tanlash (Esc)" active={tool === "select"} onClick={() => viewer.current?.setTool("select")}><Icon name="cursor" /></ToolBtn>
        <ToolBtn title="O'lchash (DIST)" active={tool === "measure"} onClick={() => viewer.current?.setTool("measure")}><Icon name="ruler" /></ToolBtn>
        <ToolBtn title="Kesim (SEC)" active={tool === "section"} onClick={() => viewer.current?.setTool("section")}><Icon name="scissors" /></ToolBtn>
        <div className="sep" />
        <ToolBtn title="Hammasiga moslash (Home)" onClick={() => viewer.current?.fitAll()}><Icon name="maximize" /></ToolBtn>
        <ToolBtn title="Yashirish (H)" onClick={() => viewer.current?.hideSelected()}><Icon name="eye-off" /></ToolBtn>
        <ToolBtn title="Ajratish (/)" onClick={() => viewer.current?.isolateSelected()}><Icon name="isolate" /></ToolBtn>
        <ToolBtn title="Hammasini ko'rsatish (Alt+H)" onClick={() => viewer.current?.showAll()}><Icon name="eye" /></ToolBtn>
        <div className="sep" />
        <ToolBtn title="Element qo'shish (Shift+A)" active={!!viewer.current?.drafts?.placing} onClick={() => setAddMenu({ x: 60, y: 120 })}><Icon name="plus" /></ToolBtn>
        {draftSel && <>
          <ToolBtn title="Surish (G)" active={viewer.current?.drafts.mode === "translate"} onClick={() => viewer.current?.drafts.setMode("translate")}><Icon name="move" /></ToolBtn>
          <ToolBtn title="Burish (R)" active={viewer.current?.drafts.mode === "rotate"} onClick={() => viewer.current?.drafts.setMode("rotate")}><Icon name="rotate" /></ToolBtn>
          <ToolBtn title="Masshtab (S)" active={viewer.current?.drafts.mode === "scale"} onClick={() => viewer.current?.drafts.setMode("scale")}><Icon name="scale" /></ToolBtn>
        </>}
        <div className="sep" />
        <ToolBtn title="Issue (ISSUE)" onClick={() => cmd("ISSUE")}><Icon name="flag" /></ToolBtn>
        <ToolBtn title="Tozalash (CLEAR)" onClick={() => cmd("CLEAR")}><Icon name="trash" /></ToolBtn>
      </div>

      <div className="ws-canvas">
        <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
        {progress !== null && (
          <div className="overlay">
            <div style={{ width: 240 }}>
              <div style={{ marginBottom: 6 }}>Model yuklanmoqda… {Math.round(progress * 100)}%</div>
              <div className="progress"><i style={{ width: `${progress * 100}%` }} /></div>
            </div>
          </div>
        )}
        {ready && versions.length === 0 && model && (
          <div className="overlay"><div>{canEdit ? "Bu modelda hali versiya yo'q — o'ngdagi «Versiyalar» dan IFC yuklang." : "Bu modelda hali versiya yo'q."}</div></div>
        )}
        {error && <div className="overlay" style={{ pointerEvents: "auto", placeItems: "start center" }}><div className="section-box error" style={{ marginTop: 20 }}>{error} <button className="btn sm" onClick={() => setError("")}>Yopish</button></div></div>}
        <NavGizmo viewer={viewer.current} ready={ready} />
        {addMenu && <AddMenu x={addMenu.x} y={addMenu.y} onPick={startAdd} onClose={() => setAddMenu(null)} />}
        {hover && hover.name !== undefined && <div className="vp-tip" style={{ left: hover.x + 14, top: hover.y + 14 }}><b>{hover.name || "nomsiz"}</b><div className="dim">{ifcLabel(hover.category ?? "")}</div></div>}
        {legend && <div className="vp-legend">{legend.map((l) => <div key={l.name}><i style={{ background: l.color }} />{colorScheme === "type" ? ifcLabel(l.name) : l.name}</div>)}</div>}
        {sideOpen && (
          <ViewportSidebar
            viewer={ready ? viewer.current : null} selection={selection}
            shading={shading} onShading={setShading} projection={projection} onProjection={() => void toggleProjection()}
            gridOn={gridOn} onGrid={(v) => { setGridOn(v); viewer.current?.setGridVisible(v); }}
            labelsOn={labelsOn} onLabels={() => void toggleLabels()}
            version={current} modelName={model?.name ?? ""} canEdit={canEdit} onAction={sideAction}
          />
        )}
        <div className="vp-info">
          <div>{projection === "Perspective" ? "Perspektiva" : "Ortografik"} · {shading === "solid" ? "Solid" : shading === "wire" ? "Wireframe" : shading === "xray" ? "X-ray" : "Rendered"}{navMode !== "Orbit" && ` · ${navMode === "FirstPerson" ? "Yurish" : "Plan"}`}</div>
          {selection.length > 0 && <div>{selection.length === 1 ? (selection[0].name || selection[0].category) : `${selection.length} ta tanlangan`}</div>}
        </div>
      </div>

      <div className="ws-dock">
        {/* Outliner (Blender): model daraxti */}
        <div className={`outliner${outlinerOpen ? "" : " collapsed"}`}>
          <div className="dock-head" onClick={() => setOutlinerOpen(!outlinerOpen)}>
            <span className="tw"><Icon name={outlinerOpen ? "chevron-down" : "chevron-right"} size={12} /></span> Outliner
            <span className="grow" />
            {current?.meta?.element_count != null && <span className="dim small">{current.meta.element_count}</span>}
          </div>
          {outlinerOpen && <div className="outliner-body">
            {viewer.current && <DraftList drafts={drafts} selected={draftSel} dm={viewer.current.drafts} canEdit={canEdit} onCommit={() => void commitDrafts()} onDelete={(uid) => void deleteDraft(uid)} busy={draftBusy} />}
            {model && (canEdit || underlays.length > 0) && <UnderlayPanel modelId={model.id} list={underlays} canEdit={canEdit} onChange={setUnderlays} centerIfc={() => { const vw = viewer.current; if (!vw) return null; const b = vw.boundsIfc; return b ? [(b.min[0] + b.max[0]) / 2, (b.min[1] + b.max[1]) / 2, b.min[2]] : [0, 0, 0]; }} />}
            <TreePanel viewer={viewer.current} modelKey={loadedKey} selectedIds={selection.map((s) => s.localId)} />
          </div>}
        </div>
        {/* Xususiyatlar muharriri: vertikal ikonka yorliqlari */}
        <div className="props-editor">
          <div className="props-tabs">
            {TABS.map((t) => (
              <button key={t.id} className={tab === t.id ? "active" : ""} onClick={() => setTab(t.id)} title={t.title} aria-label={t.title}>
                <Icon name={t.icon} size={17} />
                {t.id === "review" && activeCount.review > 0 && <span className="count">{activeCount.review}</span>}
                {t.id === "issues" && activeCount.issues > 0 && <span className="count">{activeCount.issues}</span>}
              </button>
            ))}
          </div>
          <div className="props-body">
            <div className="dock-head static">{tab === "props" && draftSel ? "Qoralama obyekt" : TABS.find((t) => t.id === tab)?.title}</div>
            <div className="dock-body">
              {model && tab === "versions" && (
                <VersionsPanel model={model} versions={versions} current={current} canEdit={canEdit} diff={diff}
                  onOpen={openVersion}
                  onUploaded={async (v) => { await reload(); await openVersion(v); }}
                  onDiff={showDiff} onClearDiff={clearDiff}
                  onPickGuid={(g) => viewer.current?.selectByGuids([g], true)} />
              )}
              {model && tab === "review" && (
                <ReviewPanel modelId={model.id} role={role} versions={versions} current={current} crs={crs}
                  onChanged={async () => { const vs = await reload(); if (current) { const c = vs.find((x) => x.id === current.id); if (c) setCurrent(c); } }}
                  onOpenVersion={(id) => { const v = versions.find((x) => x.id === id); if (v) void openVersion(v); }} />
              )}
              {model && tab === "issues" && (
                <IssuesPanel modelId={model.id} role={role} members={members} current={current} issues={issues}
                  openIssueId={openIssue} createRequested={issueTrigger}
                  getViewpoint={() => viewer.current!.getViewpoint()}
                  applyViewpoint={(vp) => viewer.current!.setViewpoint(vp)}
                  onChanged={reload} onOpenIssue={setOpenIssue} />
              )}
              {model && tab === "sim" && <SimPanel modelId={model.id} projectId={project?.id} current={current} viewer={ready ? viewer.current : null} selection={selection} canEdit={canEdit} initialKind={simKind} />}
              {model && project && tab === "mon" && <MonitoringPanel projectId={project.id} modelId={model.id} role={role} viewer={ready ? viewer.current : null} selection={selection} />}
              {model && tab === "checks" && <ChecksPanel current={current} viewer={ready ? viewer.current : null} onCreateIssue={() => { setTab("issues"); setIssueTrigger((n) => n + 1); }} />}
              {tab === "props" && draftSel && viewer.current && <DraftProps draft={draftSel} dm={viewer.current.drafts} canEdit={canEdit} onDelete={(uid) => void deleteDraft(uid)} onDuplicate={duplicateDraft} />}
              {tab === "props" && !draftSel && <PropertiesPanel viewer={viewer.current} selection={selection} canEdit={canEdit} onEdit={(id) => void editElement(id)} onDelete={(id) => void deleteElement(id)} />}
              {tab === "layers" && (<><LayersPanel viewer={viewer.current} modelKey={loadedKey} />{model && <ViewsPanel modelId={model.id} viewer={ready ? viewer.current : null} refresh={viewsRefresh} />}</>)}
            </div>
          </div>
        </div>
      </div>

      {pie && (
        <PieMenu
          x={pie.x} y={pie.y} title="Viewport Shading" releaseKey="z" onClose={() => setPie(null)}
          items={[
            { label: "Wireframe", hint: "1", active: shading === "wire", run: () => setShading("wire") },
            { label: "Solid", hint: "2", active: shading === "solid", run: () => setShading("solid") },
            { label: "Rendered", hint: "3", active: shading === "rendered", run: () => setShading("rendered") },
            { label: "X-ray", hint: "4", active: shading === "xray", run: () => setShading("xray") },
          ]}
        />
      )}
      {search && (
        <SearchMenu
          onClose={() => setSearch(false)}
          items={[
            ...searchItems,
            ...menus.flatMap((m) => m.items.filter((i) => !i.sep && !i.disabled && i.onClick).map((i) => ({ label: i.label, hint: i.hint, group: m.title, run: () => i.onClick?.() }))),
          ]}
        />
      )}
      {help && (
        <div className="help-overlay" onClick={closeHelp}>
          <div className="help-card" onClick={(e) => e.stopPropagation()}>
            <h2>Sath — qisqa yo'riqnoma</h2>
            <div className="help-grid">
              <div><b>1 · Ko'rish</b><p>Chap tugma — tanlash, o'rta — surish, g'ildirak — masshtab, Shift+o'rta — aylantirish. Yuqorida shading (Solid/Wire/X-ray/Rendered), o'ngda Outliner va xususiyatlar.</p></div>
              <div><b>Element qo'shish / tahrirlash</b><p>Shift+A yoki «Qo'shish» menyusi: primitiv yoki GES inshooti (to'g'on, quvur, turbina…) — model/yer ustiga bosib joylashtiring, G/R/S bilan sozlang, o'ng panelda o'lchamlar va Pset_GES. Mavjud elementni tanlab <b>Tab</b> — tahrirlash (surish/burish/masshtab, nom, Pset), <b>X</b> — o'chirish. «IFC ga qo'shish» — yangi versiya (commit), GUID lar saqlanadi.</p></div>
              <div><b>2 · Versiyalar va tasdiqlash</b><p>Har IFC yuklash — versiya. Muhandis «Tasdiqqa yuboradi», tasdiqlovchi farqni ko'rib ma'qullaydi/merge qiladi. Issue — 3D ko'rinish bilan.</p></div>
              <div><b>3 · Tekshiruv va simulyatsiya</b><p>To'qnashuvlar, hajm-miqdor (Tekshiruv); suv ombori/turbina rejimi va CFD (Simulyatsiya); jonli SCADA va raqamli egizak (Monitoring, Dispetcher paneli).</p></div>
              <div><b>Tezkor tugmalar</b><p>Shift+A qo'shish · G/R/S surish/burish/masshtab · X o'chirish · Shift+D nusxa · H yashir · Alt+H hammasi · / ajrat · Home moslash · . tanlanganga · 1/3/7 ko'rinish · 5 orto · Z shading pie · B kesim qutisi · N yon panel · T asboblar · F3 qidiruv · Ctrl+Space maksimal · A hammasi / Alt+A bekor · F12 render · ? yo'riqnoma</p></div>
            </div>
            <div className="actions"><button className="btn primary" onClick={closeHelp}>Tushunarli</button></div>
          </div>
        </div>
      )}
      <CommandLine onCommand={onCommand} log={log} />

      <div className="ws-status">
        <span className="msg">{status}</span>
        <span>{tool === "select" ? "Tanlash" : tool === "measure" ? "O'lchash" : "Kesim"}</span>
        <span>{selection.length > 0 ? `Tanlangan: ${selection.length}` : "—"}</span>
        {current?.meta?.element_count != null && <span>Elementlar: {current.meta.element_count}</span>}
        <span className="log" title="H yashirish · Alt+H hammasi · / ajratish · Home moslash · 1/3/7 ko'rinish · Z shading pie · N yon panel · F3 qidiruv">? tugmalar</span>
      </div>
    </div>
  );
}

function ToolBtn({ title, active, onClick, children }: { title: string; active?: boolean; onClick: () => void; children: React.ReactNode }) {
  return <button className={`btn icon${active ? " active" : ""}`} title={title} onClick={onClick} aria-label={title}>{children}</button>;
}
