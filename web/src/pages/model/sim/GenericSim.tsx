import { useEffect, useRef, useState } from "react";
import { api, type GenericParams, type GenericResult, type SimJob, type SimKind, type Version } from "../../../api/client";
import type { Viewer } from "../../../viewer/Viewer";
import type { WaterSim } from "../../../viewer/waterSim";
import Icon from "../../../ui/Icon";
import LineChart, { CHART_COLORS } from "../../../ui/LineChart";
import { fmtDate } from "../../../ui/format";
import SimForm, { fieldDefaults } from "./SimForm";

interface Props {
  kind: SimKind;
  modelId: number;
  projectId?: number;
  current: Version | null;
  viewer: Viewer | null;
  jobs: SimJob[];
  onJobsChanged: () => void;
  onBack: () => void;
  initialJobId?: number | null; // ochilganda shu hisob natijasi (xavfsizlik tekshiruvidan)
}

/** Vaqt qatorlari sarlavhalari (server kalitlari → o'zbekcha) */
const SERIES_LABELS: Record<string, [string, string]> = {
  h_valve: ["Napor zadvijkada", "m"], q_valve: ["Sarf zadvijkada", "m³/s"], h_mid: ["Napor quvur o'rtasida", "m"],
  z: ["Minora sathi (ombor sathidan)", "m"], v_tunnel: ["Tunnel tezligi", "m/s"], q_turbine: ["Turbina sarfi", "m³/s"],
  fs_overturning: ["Ag'darilish zaxirasi", ""], fs_sliding: ["Sirpanish zaxirasi", ""], sigma_toe: ["Tovon kuchlanishi", "MPa"],
  exit_gradient: ["Chiqish gradiyenti", ""], phreatic: ["Depressiya egri chizig'i", "m"],
  se_g: ["Javob spektri S_e", "g"],
  inflow: ["Kiruvchi sarf", "m³/s"], outflow: ["Chiqim", "m³/s"], level: ["Ombor sathi", "m"], spill: ["Suv tashlagich", "m³/s"], overtop: ["Gerbdan oshish", "m³/s"],
  amplitude: ["To'lqin amplitudasi", "m"],
  capacity_mcm: ["Sig'im", "mln m³"], trap_eff_pct: ["Ushlab qolish", "%"], dead_fill_pct: ["O'lik hajm to'lishi", "%"], energy_gwh: ["Ishlab chiqarish", "GVt·soat"],
  h_max_x: ["Maksimal napor", "m"], h_min_x: ["Minimal napor", "m"], p_kpa: ["Gidrodinamik bosim", "kPa"],
  q: ["Sarf", "m³/s"], depth: ["Suv chuqurligi", "m"],
  sigma_up: ["Yuqori yuza kuchlanishi (siqilish +, cho'zilish −)", "MPa"], sigma_down: ["Quyi yuza kuchlanishi", "MPa"], sigma_principal_down: ["Quyi yuza bosh kuchlanishi", "MPa"], allow_tension: ["Ruxsat etilgan cho'zilish chegarasi (−R_bt)", "MPa"],
  k_hydraulic: ["Gidravlik yorilish zaxirasi K", ""], score: ["Ball", "/100"],
  frequency_hz: ["Chastota", "Hz"], gate: ["Yo'naltiruvchi apparat ochilishi", "p.u."], p_mech: ["Mexanik quvvat", "p.u."], flow_pu: ["Sarf", "p.u."],
  flow_m3s: ["Jami sarf", "m³/s"], units_on: ["Ishlaydigan agregatlar", ""], level_change_m: ["Sath o'zgarishi", "m"],
  hot_spot_c: ["Issiq nuqta harorati", "°C"], top_oil_c: ["Yuqori moy harorati", "°C"], load_factor: ["Yuklanish K", "p.u."], power_mw: ["Faol quvvat", "MW"],
  rain_mm: ["Yog'in", "mm/soat"], excess_mm: ["Samarali yog'in", "mm/soat"],
};
const X_KEYS = ["t", "x", "level", "year", "cutoff_m", "kh", "y"];
const X_LABEL: Record<string, string> = { t: "vaqt", x: "masofa, m", level: "sath, m", year: "yil", cutoff_m: "shpunt chuqurligi, m", kh: "k_h", y: "chuqurlik, m" };

function lbl(k: string): [string, string] { return SERIES_LABELS[k] ?? [k, ""]; }
/** CSV katagi: qo'shtirnoq ichida; formula belgisi (= + - @) bilan boshlansa oldiga ' — Excel da formula sifatida bajarilmasin. */
function csvCell(v: string) { const t = /^[=+\-@\t\r]/.test(v) ? `'${v}` : v; return `"${t.replace(/"/g, '""')}"`; }
function fmtNum(v: number) { return Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2); }
/** Boshqa hisobning qatorini joriy x o'qiga (chiziqli interpolyatsiya) keltirish — x lar son bo'lsa; aks holda indeks bo'yicha. */
function resample(xs: number[] | undefined, ys: number[], xt: number[]): number[] {
  if (!xs || !xs.length || typeof xs[0] !== "number" || typeof xt[0] !== "number") return xt.map((_, i) => ys[i] ?? NaN);
  return xt.map((x) => {
    if (x <= xs[0]) return ys[0];
    if (x >= xs[xs.length - 1]) return ys[ys.length - 1];
    let k = 0;
    while (k < xs.length - 2 && xs[k + 1] < x) k++;
    const t = (x - xs[k]) / (xs[k + 1] - xs[k] || 1);
    return ys[k] + (ys[k + 1] - ys[k]) * t;
  });
}
function hazardLabel(hv: number) { return hv < 0.3 ? "past" : hv < 0.6 ? "o'rtacha" : hv < 1.2 ? "yuqori" : "o'ta yuqori"; }

export default function GenericSim({ kind, modelId, projectId, current, viewer, jobs, onJobsChanged, onBack, initialJobId = null }: Props) {
  const [values, setValues] = useState<GenericParams>(() => fieldDefaults(kind.fields));
  const [sources, setSources] = useState<Record<string, string>>({});
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [active, setActive] = useState<SimJob | null>(null);
  const [result, setResult] = useState<GenericResult | null>(null);
  const [view, setView] = useState<"form" | "results">("form");
  // Ssenariylarni solishtirish: shu turdagi boshqa hisob natijasi grafiklarga punktir bilan qo'shiladi
  const [cmp, setCmp] = useState<{ job: SimJob; result: GenericResult } | null>(null);
  async function pickCompare(id: number) {
    if (!id) { setCmp(null); return; }
    try { const job = await api.simJob(id); setCmp({ job, result: await api.genericResult(id) }); } catch (e) { setError(e instanceof Error ? e.message : "Xatolik"); }
  }
  const [cursor, setCursor] = useState<number | null>(null);
  const [showFormulas, setShowFormulas] = useState(false);
  const zeroRef = useRef(0);
  const npuRef = useRef<number | null>(null); // maydon pasporti NPU (jonli suv boshlang'ich sathi)
  const siteRef = useRef<Record<string, unknown>>({}); // pasport qiymatlari (sath–hajm egri chizig'i — loyqa sathi uchun)
  // GES elementlari GUID lari — state (ref emas): yuklangach 3D effektlar qayta ishlasin
  const [guids, setGuids] = useState<{ dams: string[]; pens: string[]; units: string[]; damCrest: number | null; spill: { guid: string; crest: number } | null }>({ dams: [], pens: [], units: [], damCrest: null, spill: null });
  const [frame, setFrame] = useState<number | null>(null); // gidrozarba kadri (x bo'ylab napor)
  const [shaking, setShaking] = useState(false);
  const [showField, setShowField] = useState(true);
  const [showSection, setShowSection] = useState(true); // 3D kesim sxemasi (kuchlar / depressiya egri chizig'i)
  // To'g'on kesimi ustida sxema: dam_stability — profil, kuchlar, h1/h2; seepage — depressiya egri chizig'i
  useEffect(() => {
    if (!viewer) return;
    const hasSec = result && (kind.id === "dam_stability" || kind.id === "seepage") && guids.dams.length && showSection;
    if (!hasSec) { void viewer.showSection(null, null); return; }
    viewer.largestGuid(guids.dams).then((g) => {
      if (!g) return;
      const prof = result.profile as { points?: [number, number][]; h1?: number; h2?: number } | undefined;
      const p = (active?.params ?? {}) as Record<string, unknown>;
      const spec = kind.id === "dam_stability"
        ? { profile: prof?.points, h1: prof?.h1, h2: prof?.h2, forces: result.forces as { name: string; v_kn: number; h_kn: number; arm_v_m: number; arm_h_m: number }[] | undefined }
        : { phreatic: { x: result.series.x as number[], y: result.series.phreatic as number[] }, h1: Number(p.h1_m) || undefined, h2: Number(p.h2_m) || undefined };
      void viewer.showSection(g, spec);
    });
  }, [viewer, result, kind.id, guids, showSection, active?.id]);
  const [dyn, setDyn] = useState<{ t: number; note: string } | null>(null); // jonli suv holati (sim vaqti, soat)
  // Toshqin xaritasi (jonli suvdan): oxirgi sim, xulosa, suv bosgan inshootlar
  const lastSim = useRef<WaterSim | null>(null);
  const [flood, setFlood] = useState<{ sum: ReturnType<WaterSim["floodSummary"]>; elements: Awaited<ReturnType<Viewer["floodedElements"]>> } | null>(null);
  const [floodOn, setFloodOn] = useState(false);
  async function refreshFloodMap() {
    const sim = lastSim.current;
    if (!viewer || !sim) return;
    viewer.showFloodMap(sim);
    setFloodOn(true);
    setFlood({ sum: sim.floodSummary(), elements: await viewer.floodedElements(sim) });
  }
  async function toggleFloodMap() {
    if (!viewer || !lastSim.current) { setInfo("Avval «Jonli suv (oqim)» ni ishga tushiring — xarita undan yig'iladi"); return; }
    if (floodOn) { viewer.showFloodMap(null); setFloodOn(false); return; }
    await refreshFloodMap();
  }
  /** Suv bosgan inshootlar bo'yicha issue (BCF): ko'rinish + tanlangan elementlar, tavsifda ro'yxat. */
  async function floodIssue() {
    if (!flood || !viewer || !active) return;
    try {
      const vp = await viewer.getViewpoint();
      vp.selected_guids = flood.elements.map((e) => e.guid).filter((g): g is string => !!g);
      const lines = flood.elements.map((e) => `• ${e.name || e.category}: chuqurlik ${e.depth.toFixed(1)} m, kelish ${e.t_arrive >= 0 ? (e.t_arrive / 3600).toFixed(1) + " soat" : "—"}, xavf ${hazardLabel(e.hv)}`);
      const issue = await api.createIssue(modelId, {
        title: `Toshqin xavfi: ${flood.elements.length} ta inshoot suv ostida (${kind.title}, #${active.id})`,
        description: `Simulyatsiya «${active.name || kind.title}» (#${active.id}) jonli suv xaritasi bo'yicha: suv bosgan maydon ${(flood.sum.flooded_area_m2 / 1e4).toFixed(1)} ga, maks. chuqurlik ${flood.sum.h_max.toFixed(1)} m.\n${lines.join("\n")}`,
        version_id: current?.id ?? null, priority: "high", viewpoint: vp,
      });
      setInfo(`Issue #${issue.id} yaratildi (Issue lar panelida)`);
    } catch (e) { setError(e instanceof Error ? e.message : "Issue yaratilmadi"); }
  }
  /** Hisobot (chop etish / PDF): sarlavha, xulosa, ko'rsatkichlar, parametrlar jadvali, grafiklar (SVG nusxa), formulalar. */
  function printReport() {
    if (!result || !active) return;
    const esc = (v: unknown) => String(v ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c] as string));
    const s = result.summary;
    const params = (active.params ?? {}) as Record<string, unknown>;
    const rows = kind.fields.filter((f) => f.key in params).map((f) => `<tr><td>${esc(f.label)}</td><td class="n">${esc(Array.isArray(params[f.key]) ? (params[f.key] as unknown[]).join(", ") : params[f.key])}</td><td>${esc(f.unit)}</td><td class="dim">${esc(sources[f.key] === "site" ? "pasport" : sources[f.key] === "model" ? "model" : sources[f.key] === "live" ? "jonli" : "")}</td></tr>`).join("");
    const tiles = kind.outputs.map((o) => `<div class="tile"><b>${esc(typeof s[o.key] === "number" ? fmtNum(s[o.key] as number) : s[o.key] ?? "—")}</b> <span>${esc(o.unit)}</span><div>${esc(o.label)}</div></div>`).join("");
    const charts = Array.from(document.querySelectorAll(".dock-body .chart")).map((el) => {
      const title = el.querySelector(".chart-title")?.textContent ?? "";
      const unit = el.querySelector(".chart-head .dim")?.textContent ?? "";
      const svg = el.querySelector("svg")?.outerHTML ?? "";
      return `<div class="chart"><div class="ct">${esc(title)} <span class="dim">${esc(unit)}</span></div>${svg}</div>`;
    }).join("");
    const html = `<!doctype html><html lang="uz"><head><meta charset="utf-8"><title>${esc(kind.title)} — ${esc(active.name || "#" + active.id)}</title>
<style>body{font:13px/1.45 system-ui,Segoe UI,sans-serif;color:#111;margin:28px;max-width:900px}h1{font-size:20px;margin:0 0 4px}h2{font-size:15px;margin:18px 0 6px;border-bottom:1px solid #ccc}
.meta{color:#555;margin-bottom:10px}.verdict{padding:8px 12px;border-left:4px solid ${s.ok === false ? "#c0392b" : "#27ae60"};background:#f6f7f8;margin:10px 0}
.tiles{display:flex;flex-wrap:wrap;gap:8px}.tile{border:1px solid #ddd;border-radius:6px;padding:8px 12px;min-width:140px}.tile b{font-size:18px}.tile div{color:#555;font-size:12px}
table{border-collapse:collapse;width:100%;font-size:12px}td,th{border-bottom:1px solid #e3e3e3;padding:3px 6px;text-align:left}td.n{text-align:right;font-family:ui-monospace,monospace}.dim{color:#777}
.chart{margin:10px 0;page-break-inside:avoid;max-width:520px}.ct{font-weight:600;margin-bottom:2px}svg{width:100%;height:auto;background:#fff}
.chart-grid{stroke:#e5e5e5}.chart-tick{fill:#666;font-size:10px;font-family:ui-monospace,monospace}.chart-ref{stroke:#999;stroke-dasharray:4 3}.chart-cursor{display:none}
.mono{font-family:ui-monospace,monospace;font-size:12px;color:#333}footer{margin-top:20px;color:#777;font-size:11px}@media print{body{margin:10mm}}</style></head><body>
<h1>${esc(kind.title)}</h1>
<div class="meta">${esc(active.name || "#" + active.id)} · #${active.id} · ${esc(fmtDate(active.created_at))} · ${esc(active.author_username ?? "")}${current ? ` · model versiyasi v${current.number}` : ""}</div>
<div class="verdict">${esc(s.verdict ?? "")}</div>
<h2>Asosiy ko'rsatkichlar</h2><div class="tiles">${tiles}</div>
<h2>Kirish parametrlari</h2><table><thead><tr><th>Parametr</th><th>Qiymat</th><th>Birlik</th><th>Manba</th></tr></thead><tbody>${rows}</tbody></table>
<h2>Grafiklar</h2>${charts || "<div class='dim'>—</div>"}
<h2>Formulalar va manbalar</h2>${kind.formulas.map((f) => `<div class="mono">${esc(f)}</div>`).join("")}
<footer>Sath · ${esc(new Date().toLocaleString("uz"))} · hisob serverda bajarilgan (ges_sim ${esc(kind.id)})</footer>
<script>window.addEventListener("load",()=>setTimeout(()=>window.print(),300))</script></body></html>`;
    const w = window.open("", "_blank");
    if (!w) { setError("Brauzer yangi oynani bloklagan — ruxsat bering"); return; }
    w.document.write(html);
    w.document.close();
  }
  function floodCsv() {
    if (!flood) return;
    const rows = [["Element", "Turi", "GUID", "Suv chuqurligi (m)", "Kelish vaqti (soat)", "h·v (m²/s)", "Xavf"].join(";")];
    for (const e of flood.elements) rows.push([csvCell(e.name), csvCell(e.category), csvCell(e.guid ?? ""), e.depth.toFixed(2), e.t_arrive >= 0 ? (e.t_arrive / 3600).toFixed(2) : "", e.hv.toFixed(2), hazardLabel(e.hv)].join(";"));
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob(["\ufeff" + rows.join("\n")], { type: "text/csv;charset=utf-8" }));
    a.download = `toshqin_inshootlar_${active?.id ?? ""}.csv`;
    a.click();
  }

  // Pasportdan avtomatik to'ldirish (bir marta), model GUID lari (3D bo'yash uchun)
  const [prefilling, setPrefilling] = useState(true);
  useEffect(() => {
    let dead = false;
    setPrefilling(true);
    (async () => {
      try {
        const pf = await api.simPrefill(modelId, kind.id, current?.id);
        if (dead) return;
        if (pf.site_filled && Object.keys(pf.site).length) {
          setValues((v) => ({ ...v, ...pf.site }));
          setSources(Object.fromEntries(Object.keys(pf.site).map((k) => [k, "site"])));
          setInfo("Maydon pasportidan to'ldirildi");
        } else if (projectId) setInfo("Maydon pasporti to'ldirilmagan — loyiha sahifasida «Maydon pasporti» ni kiriting, parametrlar avtomatik keladi.");
      } catch { /* ixtiyoriy */ }
      if (!dead) setPrefilling(false);
      if (projectId) api.site(projectId).then((s) => { zeroRef.current = Number(s.values.model_zero_m ?? 0); const n = Number(s.values.normal_level_m); npuRef.current = Number.isFinite(n) && n !== 0 ? n : null; siteRef.current = s.values as Record<string, unknown>; }).catch(() => undefined);
    })();
    return () => { dead = true; };
  }, [kind.id, modelId, current?.id, projectId]); // eslint-disable-line react-hooks/exhaustive-deps
  // GES elementlari (to'g'on, quvur, agregat GUID lari) — 3D ko'rsatish uchun; prefill dan alohida, kutmasdan
  useEffect(() => {
    if (!current) return;
    let dead = false;
    api.gesParams(current.id).then((g) => {
      if (dead) return;
      const crest = g.dams.map((d) => d.crest_elevation_m).find((c): c is number => typeof c === "number") ?? null;
      const sp = g.spillways[0];
      setGuids({ dams: g.dams.map((d) => d.guid), pens: g.penstocks.map((p) => p.guid), units: g.units.map((u) => u.guid), damCrest: crest, spill: sp ? { guid: sp.guid, crest: sp.crest_m } : null });
    }).catch((e) => console.warn("ges-params", e));
    return () => { dead = true; };
  }, [current?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const applyPrefill = async (src: "model" | "live") => {
    try {
      const pf = await api.simPrefill(modelId, kind.id, current?.id);
      const vals = pf[src];
      if (!Object.keys(vals).length) { setError(src === "model" ? "Modelda Pset_GES_* parametrlari ham, qoralama obyektlar ham topilmadi (Shift+A bilan to'g'on/quvur qo'shing yoki desktopda GES obyektlari bilan chizing)" : "Jonli sensorlar (sxema) bog'lanmagan yoki ma'lumot yo'q"); return; }
      setValues((v) => ({ ...v, ...vals }));
      setSources((s) => ({ ...s, ...Object.fromEntries(Object.keys(vals).map((k) => [k, src])) }));
      setError("");
      setInfo(`${Object.keys(vals).length} maydon ${src === "model" ? "modeldan" : "jonli holatdan"} to'ldirildi`);
    } catch (e) { setError(e instanceof Error ? e.message : "Xatolik"); }
  };

  // Tashqaridan berilgan hisobni ochish (xavfsizlik tekshiruvi jadvalidan)
  useEffect(() => {
    if (initialJobId == null) return;
    api.simJob(initialJobId).then((j) => { if (j.kind === kind.id) void openResult(j); }).catch(() => undefined);
  }, [initialJobId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Poll
  useEffect(() => {
    if (!active || (active.status !== "queued" && active.status !== "running")) return;
    const id = window.setInterval(async () => {
      const j = await api.simJob(active.id);
      if (j.status === "done" || j.status === "failed") { setActive(j); onJobsChanged(); if (j.status === "done") void openResult(j); else setError(j.error); }
    }, 600);
    return () => window.clearInterval(id);
  }, [active?.id, active?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  async function openResult(j: SimJob) {
    try {
      const full = await api.simJob(j.id);
      setActive(full);
      setResult(await api.genericResult(j.id));
      setCursor(null);
      setCmp(null);
      setView("results");
      setError("");
    } catch (e) { setError(e instanceof Error ? e.message : "Xatolik"); }
  }

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      const job = await api.createSim(modelId, { name, version_id: current?.id ?? null, kind: kind.id, params: values });
      setActive(job);
      onJobsChanged();
    } catch (err) { setError(err instanceof Error ? err.message : "Xatolik"); } finally { setBusy(false); }
  }

  // --- 3D: loyqa qatlami (sediment): yo'qotilgan sig'im → sath–hajm egri chizig'i (pasport) orqali belgi; yil kursori
  const sedSeries = kind.id === "sediment" && result && Array.isArray(result.series.capacity_mcm) ? (result.series.capacity_mcm as number[]) : null;
  useEffect(() => {
    if (!viewer) return;
    if (!sedSeries || !active) { viewer.setSedimentLevel(null); return; }
    const i = cursor ?? sedSeries.length - 1;
    const cap0 = Number((active.params as Record<string, unknown> | undefined)?.capacity_mcm) || sedSeries[0];
    const lost = Math.max(0, cap0 - sedSeries[i]); // mln m³ cho'kindi (tubdan)
    const sv = siteRef.current;
    const toNums = (v: unknown) => (Array.isArray(v) ? v.map(Number) : typeof v === "string" ? v.split(/[\s,;]+/).map(Number) : []).filter((x) => Number.isFinite(x));
    const ce = toNums(sv.curve_elev), cv = toNums(sv.curve_vol);
    let z: number | null = null;
    if (ce.length >= 2 && ce.length === cv.length) {
      // hajm → sath (chiziqli interpolyatsiya)
      let k = 0;
      while (k < cv.length - 2 && cv[k + 1] < lost) k++;
      const t = (lost - cv[k]) / ((cv[k + 1] - cv[k]) || 1);
      z = ce[k] + (ce[k + 1] - ce[k]) * Math.max(0, Math.min(1, t)) - zeroRef.current;
    } else {
      const base = viewer.boundsIfc?.min[2] ?? 0, top = (npuRef.current ?? base + 50) - zeroRef.current;
      z = base + (top - base) * Math.pow(Math.min(1, lost / Math.max(cap0, 1e-6)), 1 / 2.5); // V ∝ h^2.5 taxmini
    }
    viewer.setSedimentLevel(lost > 0 ? z : null);
    // ustida suv — NPU (pasport), ko'rinish uchun
    if (npuRef.current != null) viewer.setWaterLevel(npuRef.current - zeroRef.current, { upstreamOnly: true });
  }, [viewer, sedSeries, cursor, active?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // --- 3D: suv sathi, elementlarni bo'yash ---
  const waterKey = kind.viz.water_level ?? null;
  const levelSeries = result && waterKey && Array.isArray(result.series[waterKey]) ? (result.series[waterKey] as number[]) : null;
  useEffect(() => {
    if (!viewer || !result || !active) return;
    let lvl: number | null = null;
    if (levelSeries) lvl = levelSeries[cursor ?? levelSeries.length - 1];
    else if (waterKey && typeof result.summary[waterKey] === "number") lvl = result.summary[waterKey] as number;
    else if (waterKey && typeof active.params?.[waterKey] === "number") lvl = active.params[waterKey] as number;
    // Mutlaq belgi (masalan 906 m) va model 0 belgisi noma'lum (0) bo'lsa — tekislik ko'rinmaydi; pasportda kiritish kerak
    // To'lqin: ko'chki (Heller–Hager) — o'sish balandligi runup ning 1/3 i; toshqin — sarfga qarab; boshqalari — tinch
    const runup = typeof result.summary.runup_m === "number" ? (result.summary.runup_m as number) : 0;
    const waves = kind.id === "landslide" ? Math.max(0.3, runup / 3) : kind.id === "flood" || kind.id === "rainfall" ? 0.4 : undefined;
    // Model 0 belgisi kiritilmagan (0) va sath model balandliklaridan tashqarida bo'lsa — tekislik ma'nosiz
    const bz = viewer.boundsIfc;
    const zeroOk = zeroRef.current !== 0 || lvl == null || Math.abs(lvl) <= 150 || (bz != null && lvl >= bz.min[2] - 60 && lvl <= bz.max[2] + 60);
    if (lvl != null && zeroOk) viewer.setWaterLevel(lvl - zeroRef.current, { waves, upstreamOnly: true });
    else if (lvl != null) setInfo("3D da suv sathini ko'rish uchun maydon pasportida «3D model 0 belgisi» ni kiriting");
    // Toshib chiqish: sath gerbdan yuqori → to'g'on ustidan parda; suv tashlagich ostonasidan yuqori → nov bo'ylab oqim
    const over: { guid: string; topZ: number; bottomZ: number; intensity: number }[] = [];
    const tw = typeof active.params?.tailwater_m === "number" ? (active.params.tailwater_m as number) : null;
    if (lvl != null && guids.damCrest != null && lvl > guids.damCrest && guids.dams.length) {
      const bottom = (tw ?? guids.damCrest - 50) - zeroRef.current;
      for (const g of guids.dams) over.push({ guid: g, topZ: lvl - zeroRef.current, bottomZ: bottom, intensity: Math.min(1, (lvl - guids.damCrest) / 2) });
      setInfo(`DIQQAT: sath ${lvl.toFixed(2)} m gerbdan (${guids.damCrest} m) yuqori — to'g'on ustidan toshib chiqmoqda`);
    }
    if (lvl != null && guids.spill && lvl > guids.spill.crest) {
      over.push({ guid: guids.spill.guid, topZ: lvl - zeroRef.current, bottomZ: (tw ?? guids.spill.crest - 60) - zeroRef.current, intensity: Math.min(1, (lvl - guids.spill.crest) / 3) });
    }
    void viewer.setOverflow(over);
    const ok = result.summary.ok !== false;
    const colors: Record<string, string> = {};
    const target = kind.viz.color_by === "dam" || kind.viz.color_by === "structures" ? guids.dams : kind.viz.penstock_profile ? guids.pens : [];
    for (const g of target) colors[g] = ok ? "#3aa864" : "#d95c5c";
    if (kind.viz.color_by === "structures") for (const g of guids.pens) colors[g] = ok ? "#3aa864" : "#d95c5c";
    // Dispetcherlik: agregatlar yuklanish bo'yicha (0 % — kulrang, 100 % — to'q yashil)
    if (result.units && guids.units.length) {
      result.units.forEach((u, i) => {
        const g = guids.units[i];
        const pct = Number(u.load_pct ?? 0);
        if (g) colors[g] = pct <= 0 ? "#6b7280" : `hsl(${120 - Math.max(0, pct - 100)} ${40 + Math.min(pct, 100) * 0.5}% ${55 - Math.min(pct, 100) * 0.2}%)`;
      });
    }
    void viewer.colorByGuids(colors);
    // Quyi byef / toshqin chuqurligi (Manning) — ikkinchi suv tekisligi
    const dsKey = kind.viz.downstream_depth as string | undefined;
    if (dsKey && result.downstream?.depth) {
      const d = result.downstream.depth;
      const k = cursor != null ? Math.min(Math.round(cursor / Math.max(1, (levelSeries?.length ?? 1) - 1) * (d.length - 1)), d.length - 1) : d.length - 1;
      const tw = typeof active.params?.tailwater_m === "number" ? (active.params.tailwater_m as number) : null;
      const base = tw != null ? tw - zeroRef.current : (viewer.baseIfcZ ?? 0);
      viewer.setTailwaterLevel(d[k] > 0.05 ? base + d[k] : null);
    } else viewer.setTailwaterLevel(null);
  }, [viewer, result, cursor, active, levelSeries, waterKey, kind.viz, guids]);
  // Yoriq xavfi xaritasi to'g'on yuzasida (cracking) — ko'k → sariq → qizil
  useEffect(() => {
    if (!viewer) return;
    if (result?.field && kind.viz.field && guids.dams.length && showField) {
      const field = result.field;
      void viewer.largestGuid(guids.dams).then((g) => {
        if (g) void viewer.showFieldPlane(g, field, (t) => [Math.min(1, t * 2), t < 0.5 ? t * 2 : 2 - t * 2, Math.max(0, 1 - t * 2)]);
      });
    } else void viewer.showFieldPlane(null, null, () => [0, 0, 0]);
  }, [viewer, result, kind.viz, showField, guids]);
  // Gidrozarba: quvur bo'ylab napor kadrlari — quvurga rangli tasma (moviy → qizil)
  const frames = (result?.profile?.frames as { t: number; h: number[] }[] | undefined) ?? null;
  useEffect(() => {
    if (!viewer || !frames || !guids.pens.length) return;
    const f = frames[frame ?? 0];
    const allH = frames.flatMap((x) => x.h);
    const lo = Math.min(...allH), hi = Math.max(...allH);
    const norm = f.h.map((h) => (hi > lo ? (h - lo) / (hi - lo) : 0.5));
    void viewer.largestGuid(guids.pens).then((g) => {
      if (g) void viewer.showFieldPlane(g, { nx: norm.length, ny: 2, values: [...norm, ...norm] }, (t) => [t, 0.3 + 0.4 * (1 - Math.abs(t - 0.5) * 2), 1 - t]);
    });
  }, [viewer, frames, frame, guids]);
  useEffect(() => () => { viewer?.stopDynamicWater(); viewer?.showFloodMap(null); viewer?.setWaterLevel(null); viewer?.setTailwaterLevel(null); viewer?.setSedimentLevel(null); void viewer?.setOverflow([]); void viewer?.colorByGuids({}); void viewer?.showFieldPlane(null, null, () => [0, 0, 0]); void viewer?.showSection(null, null); }, [viewer]);
  /** Jonli suv (sayoz suv gidrodinamikasi relyefda): toshqin — kiruvchi gidrograf yuqori byefdan, inshootlar
   * orqali chiqim (suv tashlagich/turbina) quyi byefga o'tkaziladi, gerbdan oshish va yorilish o'z-o'zidan;
   * ko'chki — impuls to'lqin. 1 s haqiqiy = timeScale s simulyatsiya. */
  function startLiveWater() {
    if (!viewer || !result || !active) return;
    const zero = zeroRef.current;
    const bz = viewer.boundsIfc;
    if (!bz) { setInfo("Model chegarasi noma'lum"); return; }
    const cx = (bz.min[0] + bz.max[0]) / 2;
    const p: Record<string, unknown> = (active.params ?? {}) as Record<string, unknown>;
    const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) && v !== 0 ? v : null);
    const lvl0 = num(p.initial_level_m) ?? num(p.headwater_m) ?? num(p.water_level_m) ?? num(p.normal_level_m) ?? (npuRef.current ?? null) ?? (typeof result.summary.max_level_m === "number" ? Number(result.summary.max_level_m) - 5 : null);
    if (lvl0 == null) { setInfo("Boshlang'ich sath topilmadi"); return; }
    const crest = guids.damCrest ?? lvl0 + 5;
    if (kind.id === "landslide") {
      const sim = viewer.startDynamicWater(lvl0 - zero, "upstream", 4);
      if (!sim) { setInfo("Balandlik xaritasi hali yuklanmagan"); return; }
      lastSim.current = sim; viewer.showFloodMap(null); setFloodOn(false); setFlood(null);
      const dist = Number(p.distance_m ?? p.slide_distance_m ?? 1500);
      const a = Number(result.summary.a_max_m ?? 10);
      const side = (bz.max[0] - bz.min[0]) * 0.25;
      // ko'chki qirg'oqdan (o'ng) to'g'onga qarab: impuls to'g'on tomon (−Y) va vodiy markaziga
      sim.impulse(cx + side, Math.min(dist, bz.max[1] - 100) - zero * 0, 180, a * 1.5, -0.7, -0.7, Number(result.summary.slide_velocity_ms ?? 20) * 0.5);
      setDyn({ t: 0, note: `Ko'chki to'lqini: a_max ${a} m, to'g'onga yetib borish ~${result.summary.arrival_s ?? "?"} s` });
      viewer.dyn!.onTick = (s) => setDyn({ t: s.time, note: `t = ${s.time.toFixed(0)} s · maks. chuqurlik ${s.stats().h_max.toFixed(1)} m` });
      return;
    }
    // Toshqin / yog'ingarchilik: kiruvchi gidrograf va inshoot chiqimi
    const ts = (result.series.t as number[]) ?? [];
    const inflow = (result.series.inflow as number[]) ?? [];
    const outflow = (result.series.outflow as number[]) ?? [];
    const spill = (result.series.spill as number[]) ?? [];
    if (!ts.length) { setInfo("Vaqt qatori yo'q"); return; }
    const timeScale = 3600 / 3; // 1 soat = 3 s
    const sim = viewer.startDynamicWater(lvl0 - zero, "upstream", timeScale);
    if (!sim) { setInfo("Balandlik xaritasi hali yuklanmagan"); return; }
    lastSim.current = sim; viewer.showFloodMap(null); setFloodOn(false); setFlood(null);
    const [iUp, jUp] = sim.cellAt(cx, bz.max[1] - 30);
    // Modeldagi vodiy haqiqiy omborning kichik bir qismi — shuning uchun sath Puls hisobi (level) bo'yicha
    // boshqariladi: kirim = (maqsad sath − sim sathi)·A_sim/τ; gerbdan oshish, yorilish, quyi byef — fizika
    const levels = (result.series.level as number[]) ?? [];
    const [iL, jL] = sim.cellAt(cx, 220);
    let aSim = 0;
    for (let k = 0; k < sim.h.length; k++) if (sim.h[k] > 0.05) aSim++;
    aSim = Math.max(aSim, 4) * sim.dx * sim.dx;
    // inshoot chiqimi: to'g'on quyi etagi (y = 0 dan 300 m quyida) — suv tashlagich/turbina orqali o'tgan suv
    const [iDn, jDn] = sim.cellAt(cx, Math.max(bz.min[1] + 30, -Math.abs(crest - lvl0) * 2 - 320));
    const [iRes, jRes] = sim.cellAt(cx, 150);
    const breach = result.breach as { width_m: number; height_m: number; formation_h: number } | null | undefined;
    const overStart = typeof result.summary.overtop_start_h === "number" ? Number(result.summary.overtop_start_h) : null;
    let breached = false;
    viewer.dyn!.onTick = (s) => {
      const th = s.time / 3600;
      let k = 0;
      while (k < ts.length - 1 && ts[k + 1] <= th) k++;
      const qi = inflow[k] ?? 0;
      // chiqim: inshootlar orqali (gerbdan oshish sayoz suvda o'zi bo'ladi) — suv tashlagich + turbina ≈ outflow − overtop
      const qo = Math.max(0, Math.min(outflow[k] ?? 0, (spill[k] ?? 0) + Number(p.turbine_m3s ?? 0) + Number(p.base_m3s ?? 0)));
      const target = (levels[k] ?? lvl0) - zero;
      const kL = jL * s.nx + iL;
      const eta = s.b[kL] + s.h[kL];
      // sath boshqaruvi (yorilishgacha): 15 daqiqada farqni yopadigan kirim; chegara — haqiqiy kirimning 3 barobari
      const qCtl = breached ? 0 : Math.max(-3 * Math.max(qi, 100), Math.min(3 * Math.max(qi, 100), ((target - eta) * aSim) / 900));
      s.sources = [{ i: iUp, j: jUp, q: qCtl }, { i: iRes, j: jRes, q: -qo }, { i: iDn, j: jDn, q: qo }];
      if (breach && !breached && overStart != null && th >= overStart + Math.min(breach.formation_h, 2) * 0.5) {
        breached = true;
        const w = Math.max(20, breach.width_m);
        s.breach(cx - w / 2, cx + w / 2, -400, 400, crest - breach.height_m - zero);
        setInfo(`Yorilish: kenglik ${w.toFixed(0)} m, tub ${(crest - breach.height_m).toFixed(0)} m — suv to'g'ondan otilib chiqmoqda`);
      }
      setDyn({ t: th, note: `t = ${th.toFixed(1)} soat · kirim ${qi.toFixed(0)} m³/s · inshoot chiqimi ${qo.toFixed(0)} m³/s${breached ? " · YORILISH" : th >= (overStart ?? Infinity) ? " · gerbdan oshmoqda" : ""}` });
    };
    setDyn({ t: 0, note: "Jonli suv boshlandi" });
  }
  function stopLiveWater() { viewer?.stopDynamicWater(); setDyn(null); }

  // Kadrlarni avtomatik aylantirish (gidrozarba)
  useEffect(() => {
    if (!frames || frame == null) return;
    const id = window.setTimeout(() => setFrame((frame + 1) % frames.length), 120);
    return () => window.clearTimeout(id);
  }, [frames, frame]);

  const myJobs = jobs.filter((j) => j.kind === kind.id);
  const head = (
    <div className="bhead">
      <button className="btn sm" onClick={view === "results" ? () => setView("form") : onBack} title={view === "results" ? "Parametrlarga qaytish" : "Katalogga qaytish"}><Icon name="chevron-left" size={13} /></button>
      <Icon name={kind.icon} size={14} />
      <b className="grow">{kind.title}</b>
      <span className="dim small">{view === "results" ? "natija" : "parametrlar"}</span>
      <button className="btn sm" title="Formulalar va manbalar" onClick={() => setShowFormulas(!showFormulas)}><Icon name="book-open" size={13} /></button>
    </div>
  );
  const formulas = showFormulas && (
    <div className="section-box small">
      <div className="muted" style={{ marginBottom: 4 }}>{kind.description}</div>
      {kind.formulas.map((f, i) => <div key={i} className="mono">{f}</div>)}
    </div>
  );

  if (view === "results" && result && active) {
    const s = result.summary;
    const ok = s.ok !== false;
    const xKey = X_KEYS.find((k) => k in result.series) ?? Object.keys(result.series)[0];
    const x = (result.series[xKey] ?? []) as (number | string)[];
    const ySeries = Object.keys(result.series).filter((k) => k !== xKey && (result.series[k] as unknown[]).every((v) => typeof v === "number"));
    const i = cursor ?? (levelSeries ? levelSeries.length - 1 : 0);
    return (
      <div className="sim">
        {head}
        {formulas}
        <div className="row small" style={{ marginBottom: 6, alignItems: "center" }}><b>{active.name || `#${active.id}`}</b><span className="dim">{fmtDate(active.created_at)}</span><span className="grow" />
          <button className="btn sm" onClick={printReport} title="Hisobot: chop etish / PDF ga saqlash (xulosa, ko'rsatkichlar, parametrlar, grafiklar, formulalar)"><Icon name="printer" size={12} /> Hisobot</button>
          {myJobs.filter((j) => j.id !== active.id && j.status === "done").length > 0 && (
            <select className="select sm" value={cmp?.job.id ?? 0} onChange={(e) => void pickCompare(Number(e.target.value))} title="Boshqa ssenariy bilan solishtirish — grafiklarda punktir chiziq">
              <option value={0}>Solishtirish…</option>
              {myJobs.filter((j) => j.id !== active.id && j.status === "done").map((j) => <option key={j.id} value={j.id}>#{j.id} {j.name}</option>)}
            </select>
          )}
        </div>
        {cmp && (
          <div className="section-box small" style={{ marginBottom: 6 }}>
            <div className="row" style={{ alignItems: "center" }}><b>Solishtirish: #{cmp.job.id} {cmp.job.name}</b><span className="grow" /><button className="btn sm" onClick={() => setCmp(null)}><Icon name="x" size={11} /></button></div>
            <table style={{ marginTop: 4 }}><thead><tr><th>Ko'rsatkich</th><th>#{active.id}</th><th>#{cmp.job.id}</th><th>Farq</th></tr></thead><tbody>
              {kind.outputs.map((o) => { const a = s[o.key], b = cmp.result.summary[o.key]; const na = typeof a === "number", nb = typeof b === "number"; return (
                <tr key={o.key}><td>{o.label}</td><td className="mono">{na ? fmtNum(a as number) : String(a ?? "—")} {o.unit}</td><td className="mono">{nb ? fmtNum(b as number) : String(b ?? "—")} {o.unit}</td><td className="mono">{na && nb ? `${(a as number) - (b as number) >= 0 ? "+" : ""}${fmtNum((a as number) - (b as number))}` : ""}</td></tr>
              ); })}
            </tbody></table>
            <div className="dim">Farq qilgan parametrlar: {(() => { const pa = (active.params ?? {}) as Record<string, unknown>, pb = (cmp.job.params ?? {}) as Record<string, unknown>; return Object.keys(pa).filter((k) => JSON.stringify(pa[k]) !== JSON.stringify(pb[k])).map((k) => `${kind.fields.find((f) => f.key === k)?.label ?? k}: ${String(pb[k])} → ${String(pa[k])}`).join("; ") || "yo'q"; })()}</div>
          </div>
        )}
        <div className={`verdict ${ok ? "ok" : "bad"}`}><Icon name={ok ? "check-circle" : "alert-triangle"} size={16} /> <span>{String(s.verdict ?? "")}</span></div>
        <div className="tiles">
          {kind.outputs.map((o) => <Tile key={o.key} v={s[o.key]} u={o.unit} t={o.label} />)}
        </div>
        {(frames || result.field || kind.id === "seismic" || kind.id === "flood" || kind.id === "rainfall" || kind.id === "landslide" || kind.id === "dam_stability" || kind.id === "seepage") && (
          <div className="row small wrap" style={{ gap: 6, marginBottom: 6, alignItems: "center" }}>
            <span className="dim">3D:</span>
            {(kind.id === "flood" || kind.id === "rainfall" || kind.id === "landslide") && (
              <button className={`btn sm${dyn ? " active" : ""}`} onClick={() => (dyn ? stopLiveWater() : startLiveWater())} title="Sayoz suv gidrodinamikasi relyefda: toshqin to'lqini, gerbdan oshish, yorilish oqimi, ko'chki to'lqini — jonli"><Icon name="waves" size={12} /> {dyn ? "Jonli suvni to'xtatish" : "Jonli suv (oqim)"}</button>
            )}
            {(kind.id === "flood" || kind.id === "rainfall" || kind.id === "landslide") && (
              <button className={`btn sm${floodOn ? " active" : ""}`} onClick={() => void toggleFloodMap()} title="Jonli suvdan yig'ilgan toshqin xaritasi: maks. chuqurlik, xavf sinfi (h·v), suv bosgan inshootlar, kelish vaqti"><Icon name="map" size={12} /> Toshqin xaritasi</button>
            )}
            {dyn && <span className="mono dim">{dyn.note}</span>}
            {frames && (
              <button className="btn sm" onClick={() => setFrame(frame == null ? 0 : null)} title="Quvur bo'ylab napor to'lqini (rangli tasma)"><Icon name={frame == null ? "play" : "pause"} size={12} /> {frame == null ? "Gidrozarba to'lqini" : `t = ${frames[frame].t.toFixed(2)} s`}</button>
            )}
            {(kind.id === "dam_stability" || kind.id === "seepage") && (
              <button className={`btn sm${showSection ? " active" : ""}`} onClick={() => setShowSection(!showSection)} title={kind.id === "dam_stability" ? "To'g'on kesimida hisob profili, kuchlar (W, P, U, zilzila) strelkalar bilan, suv sathlari" : "To'g'on tanasida depressiya egri chizig'i (Dyupyui) — filtratsiya yuzasi"}><Icon name="activity" size={12} /> {kind.id === "dam_stability" ? "Kuchlar sxemasi" : "Depressiya egri chizig'i"}</button>
            )}
            {result.field && (
              <button className={`btn sm${showField ? " active" : ""}`} onClick={() => setShowField(!showField)} title={result.field.legend}><Icon name="layers" size={12} /> Yoriq xaritasi</button>
            )}
            {kind.id === "seismic" && viewer && (
              <button className="btn sm" disabled={shaking} onClick={() => { setShaking(true); const stop = viewer.shake(Number(s.pga_g ?? 0.2), Number(s.dam_period_s ?? 0.3), 6); window.setTimeout(() => { stop(); setShaking(false); }, 6200); }} title="Modelni PGA va davr bo'yicha silkitish (ko'rinish uchun 60× kattalashtirilgan)"><Icon name="activity" size={12} /> {shaking ? "Zilzila…" : "Zilzilani ko'rsatish"}</button>
            )}
          </div>
        )}
        {floodOn && flood && (
          <div className="section-box small" style={{ marginBottom: 8 }}>
            <div className="row" style={{ alignItems: "center", marginBottom: 4 }}><b>Toshqin xaritasi</b> <span className="dim">t = {(flood.sum.t / 3600).toFixed(1)} soat</span><span className="grow" /><button className="btn sm" onClick={() => void refreshFloodMap()} title="Joriy holat bo'yicha yangilash"><Icon name="rotate" size={11} /></button><button className="btn sm" onClick={floodCsv} disabled={!flood.elements.length}><Icon name="download" size={11} /> CSV</button><button className="btn sm" onClick={() => void floodIssue()} disabled={!flood.elements.length} title="Suv bosgan inshootlar bo'yicha issue (BCF) — ko'rinish va elementlar bilan"><Icon name="flag" size={11} /> Issue</button></div>
            <div className="tiles">
              <Tile v={flood.sum.flooded_area_m2 / 1e4} u="ga" t="Suv bosgan maydon (ombor tashqarisi)" />
              <Tile v={flood.sum.h_max} u="m" t="Maks. chuqurlik" />
              <Tile v={flood.sum.v_max} u="m/s" t="Maks. tezlik" />
              <Tile v={flood.sum.t_arrive_far_s >= 0 ? flood.sum.t_arrive_far_s / 3600 : "—"} u="soat" t="Quyi chegaraga yetib kelish" />
            </div>
            <div className="row small wrap" style={{ gap: 8, margin: "4px 0" }}>
              {["Past (h·v<0.3)", "O'rtacha (<0.6, odam)", "Yuqori (<1.2, mashina)", "O'ta yuqori (bino)"].map((l, i) => <span key={l}><i style={{ display: "inline-block", width: 10, height: 10, background: ["#f2d94e", "#f0902e", "#d9392b", "#7a1010"][i], marginRight: 4, verticalAlign: "middle" }} />{l}: {(flood.sum.classes_m2[i] / 1e4).toFixed(1)} ga</span>)}
            </div>
            <div className="dim">Xavf sinfi — AIDR (2017) / NZ ko'rsatmalari: h·v (chuqurlik × tezlik) bo'yicha.</div>
            {flood.elements.length > 0 ? (
              <table style={{ marginTop: 4 }}><thead><tr><th>Suv bosgan inshoot</th><th>Chuqurlik</th><th>Kelish</th><th>Xavf</th></tr></thead><tbody>
                {flood.elements.slice(0, 30).map((e) => (
                  <tr key={e.localId} style={{ cursor: "pointer" }} onClick={() => void viewer?.selectLocalIds([e.localId], true)} title={e.category}>
                    <td>{e.name || e.category}</td><td className="mono">{e.depth.toFixed(1)} m</td><td className="mono">{e.t_arrive >= 0 ? `${(e.t_arrive / 3600).toFixed(1)} soat` : "—"}</td><td>{hazardLabel(e.hv)}</td>
                  </tr>
                ))}
              </tbody></table>
            ) : <div className="dim">Inshootlar suv bosmagan (ombor tashqarisida, ≥ 0.3 m).</div>}
          </div>
        )}
        {sedSeries && (
          <div className="sim-player" title="Yil kursori — 3D da ombor tubidagi loyqa qatlami (jigarrang) shu yilgacha yig'ilgan cho'kindi">
            <input type="range" min={0} max={sedSeries.length - 1} value={cursor ?? sedSeries.length - 1} onChange={(e) => setCursor(Number(e.target.value))} className="grow" aria-label="Yil" />
            <span className="mono small" style={{ minWidth: 150 }}>{String(x[cursor ?? sedSeries.length - 1])}-yil · sig'im {sedSeries[cursor ?? sedSeries.length - 1]?.toFixed(0)} mln m³</span>
          </div>
        )}
        {levelSeries && (
          <div className="sim-player">
            <input type="range" min={0} max={levelSeries.length - 1} value={i} onChange={(e) => setCursor(Number(e.target.value))} className="grow" aria-label="Vaqt" />
            <span className="mono small" style={{ minWidth: 120 }}>{String(x[i]).slice(0, 10)} · {levelSeries[i]?.toFixed(2)} m</span>
          </div>
        )}
        {ySeries.map((k, n) => {
          const [t, u] = lbl(k);
          const other = cmp && Array.isArray(cmp.result.series[k]) ? resample(cmp.result.series[xKey] as number[], cmp.result.series[k] as number[], x as number[]) : null;
          return <LineChart key={k} title={`${t}${xKey !== "t" ? ` (${X_LABEL[xKey] ?? xKey})` : ""}`} unit={u} x={x} series={[{ name: t, values: result.series[k] as number[], color: CHART_COLORS[n % CHART_COLORS.length] }, ...(other ? [{ name: `${t} · #${cmp!.job.id}`, values: other, color: "#9aa3ad", dashed: true }] : [])]} cursor={levelSeries ? cursor : undefined} onCursor={levelSeries ? setCursor : undefined} />;
        })}
        {result.profile && "x" in result.profile && (
          <LineChart title="Napor epyurasi quvur bo'ylab (max/min)" unit="m" x={result.profile.x as number[]} series={[{ name: "Maksimal", values: result.profile.h_max_x as number[], color: CHART_COLORS[4] }, { name: "Minimal", values: result.profile.h_min_x as number[], color: CHART_COLORS[0] }]} />
        )}
        {result.profile && "y" in result.profile && (
          <LineChart title="Westergaard gidrodinamik bosim (chuqurlik bo'yicha)" unit="kPa" x={result.profile.y as number[]} series={[{ name: "p", values: result.profile.p_kpa as number[] }]} />
        )}
        {result.profile && "points" in result.profile && <DamProfile profile={result.profile as { points: [number, number][]; h1: number; h2: number }} />}
        {result.downstream && (
          <>
            <LineChart title="Quyi byef: sarf (Muskingum)" unit="m³/s" x={result.downstream.t} series={[{ name: "Q", values: result.downstream.q, color: CHART_COLORS[1] }]} />
            <LineChart title="Quyi byef: suv chuqurligi (Manning)" unit="m" x={result.downstream.t} series={[{ name: "h", values: result.downstream.depth, color: CHART_COLORS[0] }]} refLines={typeof active.params?.ch_bank_depth_m === "number" ? [{ value: active.params.ch_bank_depth_m as number, label: "Qirg'oq" }] : []} />
          </>
        )}
        {result.seismic_scan && (
          <LineChart title="Seysmik koeffitsient bo'yicha zaxira" unit="" x={result.seismic_scan.kh} series={[{ name: "Sirpanish", values: result.seismic_scan.fs_sliding, color: CHART_COLORS[4] }, { name: "Ag'darilish", values: result.seismic_scan.fs_overturning, color: CHART_COLORS[0] }]} refLines={[{ value: 1, label: "1.0" }]} />
        )}
        {result.breach && (
          <div className="section-box small"><b>Yorilish (Froehlich)</b>: kenglik {String(result.breach.width_m)} m · balandlik {String(result.breach.height_m)} m · hajm {String(result.breach.volume_mcm)} mln m³ · shakllanish {String(result.breach.formation_h)} soat · Q_p {String(result.breach.peak_m3s)} m³/s</div>
        )}
        {result.thermal && (
          <div className="section-box small">
            <b>Issiqlik yorilishi</b>: ΔT_ad {String(result.thermal.dT_adiabatic)} °C · T_max {String(result.thermal.t_max)} °C · ΔT {String(result.thermal.dT)} °C · σ_T {String(result.thermal.sigma_t_mpa)} MPa · indeks <b>{String(result.thermal.index)}</b> ({String(result.thermal.risk)}, ~{String(result.thermal.probability_pct)} %) · ruxsat ΔT {String(result.thermal.dT_allow)} °C · sement ≤ {String(result.thermal.cement_allow_kg_m3)} kg/m³
          </div>
        )}
        {result.prone && result.prone.length > 0 && (
          <div className="section-box">
            <b>Yorilishga moyil joylar</b>
            <table className="grid small" style={{ marginTop: 4 }}>
              <tbody>{result.prone.map((x, i) => (
                <tr key={i} className={x.severity === "kritik" ? "alarm-active" : undefined}>
                  <td style={{ width: 22 }}><Icon name={x.severity === "kritik" || x.severity === "yuqori" ? "alert-triangle" : x.severity === "o'rtacha" ? "alert-circle" : "info"} size={13} style={{ color: x.severity === "kritik" ? "var(--danger)" : x.severity === "yuqori" ? "var(--danger)" : x.severity === "o'rtacha" ? "var(--warn)" : "var(--text-dim)" }} /></td>
                  <td><b>{x.where}</b><div className="dim">{x.why}</div></td>
                  <td className="dim" style={{ whiteSpace: "nowrap" }}>{x.severity}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
        {result.ranking && (
          <div className="ranking">
            {result.ranking.map((r, i) => (
              <details key={r.type} className="section-box" open={i === 0}>
                <summary className="row" style={{ alignItems: "center" }}>
                  <b>{i + 1}. {r.name}</b><span className="grow" />
                  <span className={`badge ${r.verdict === "mos" ? "published" : r.verdict === "shartli" ? "shared" : "rejected"}`}>{r.verdict}</span>
                  <span className="mono">{r.score} ball</span>
                </summary>
                <div className="small" style={{ marginTop: 6 }}>
                  <div><b className="ok-text">Yaxshi:</b> {r.good.join(" · ")}</div>
                  <div><b className="bad-text">Yomon:</b> {r.bad.join(" · ")}</div>
                  <div><b>Yorilishga moyil:</b> {r.cracks.join(" · ")}</div>
                  <div className="dim" style={{ marginTop: 4 }}>{r.reasons.join("; ")}</div>
                </div>
              </details>
            ))}
          </div>
        )}
        {result.units && <KVTable rows={result.units} cols={[["name", "Agregat"], ["power_mw", "MW"], ["load_pct", "yuk, %"], ["flow_m3s", "sarf, m³/s"], ["efficiency", "FIK"], ["head_net_m", "netto napor, m"]]} />}
        {result.forces && <KVTable rows={result.forces} cols={[["name", "Kuch"], ["v_kn", "V, kN/m"], ["h_kn", "H, kN/m"], ["arm_v_m", "yelka V, m"], ["arm_h_m", "yelka H, m"]]} />}
        {result.structures && <KVTable rows={result.structures} cols={[["name", "Inshoot"], ["period_s", "T, s"], ["sa_g", "S_a, g"], ["mass_t", "massa, t"], ["force_kn", "kuch, kN"]]} />}
        <details style={{ marginTop: 8 }}>
          <summary className="muted small">Barcha natijalar</summary>
          <table className="grid small"><tbody>{Object.entries(s).filter(([k]) => k !== "verdict").map(([k, v]) => <tr key={k}><td className="dim">{k}</td><td className="mono">{typeof v === "number" ? v.toLocaleString("uz-UZ", { maximumFractionDigits: 4 }) : String(v)}</td></tr>)}</tbody></table>
        </details>
      </div>
    );
  }

  return (
    <div className="sim">
      {head}
      {formulas}
      {!showFormulas && <p className="dim small" style={{ marginTop: 0 }}>{kind.description}</p>}
      {error && <p className="error small">{error}</p>}
      {info && <p className="muted small"><Icon name="info" size={12} /> {info}</p>}
      {myJobs.length > 0 && (
        <details open={myJobs.length <= 3} className="section-box">
          <summary>Oldingi hisoblar ({myJobs.length})</summary>
          {myJobs.map((j) => (
            <div key={j.id} className="list-item" onClick={() => j.status === "done" && openResult(j)}>
              <div className="title"><b>#{j.id}</b><span className="grow">{j.name}</span>{j.status === "done" && <Icon name={j.summary.ok === false ? "alert-triangle" : "check-circle"} size={13} style={{ color: j.summary.ok === false ? "var(--danger)" : "var(--ok)" }} />}<span className={`badge ${j.status === "done" ? "published" : j.status === "failed" ? "rejected" : "shared"}`}>{j.status === "done" ? "Tayyor" : j.status === "failed" ? "Xato" : "Hisoblanmoqda"}</span></div>
              <div className="meta">{j.author_username} · {fmtDate(j.created_at)}{j.status === "done" && j.summary.verdict ? ` · ${String(j.summary.verdict).slice(0, 80)}` : ""}{j.error && <span className="error"> · {j.error}</span>}</div>
            </div>
          ))}
        </details>
      )}
      <form onSubmit={run}>
        <div className="row" style={{ marginBottom: 8 }}>
          <input className="input grow" placeholder="Hisob nomi (ixtiyoriy)" value={name} onChange={(e) => setName(e.target.value)} />
          <button className="btn primary" type="submit" disabled={busy || prefilling || active?.status === "running" || active?.status === "queued"} title={prefilling ? "Maydon pasporti yuklanmoqda…" : undefined}>{busy ? "…" : prefilling ? "Pasport…" : "Hisoblash"}</button>
        </div>
        <div className="row" style={{ marginBottom: 8 }}>
          {current && <button type="button" className="btn sm" title="IFC dagi Pset_GES_* va 3D da yaratilgan qoralama obyektlardan (to'g'on o'lchamlari, beton klassi…)" onClick={() => applyPrefill("model")}><Icon name="box" size={12} /> Modeldan (v{current.number} + qoralamalar)</button>}
          {projectId && <button type="button" className="btn sm" title="Raqamli egizak: joriy sath/sarf SCADA dan" onClick={() => applyPrefill("live")}><Icon name="activity" size={12} /> Jonli holatdan</button>}
          <button type="button" className="btn sm" onClick={() => { setValues(fieldDefaults(kind.fields)); setSources({}); }}>Standart qiymatlar</button>
        </div>
        {active && (active.status === "queued" || active.status === "running") && <p className="muted small">Hisoblanmoqda…</p>}
        <SimForm fields={kind.fields} values={values} onChange={(k, v) => setValues((p) => ({ ...p, [k]: v }))} sources={sources} />
        <p className="dim small">Natija versiyaga bog'lanadi: {current ? `v${current.number}` : "—"}.</p>
      </form>
      <Sweep kind={kind} values={values} />
    </div>
  );
}

/** Sezgirlik tahlili: bitta parametrni oraliqda o'zgartirib, xulosa ko'rsatkichlari grafigi (saqlanmaydi, sinxron). */
function Sweep({ kind, values }: { kind: SimKind; values: GenericParams }) {
  const numeric = kind.fields.filter((f) => f.type === "number" || f.type === "int");
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState(numeric[0]?.key ?? "");
  const [range, setRange] = useState<{ min: string; max: string; n: number }>({ min: "", max: "", n: 9 });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [res, setRes] = useState<Awaited<ReturnType<typeof api.simSweep>> | null>(null);
  const field = numeric.find((f) => f.key === key);
  useEffect(() => {
    // oraliq: joriy qiymatning 0.5×…1.5× (chegaralar ichida)
    if (!field) return;
    const cur = Number(values[field.key] ?? field.default) || 0;
    // katta mutlaq qiymatlar (belgilar, m) uchun ±10 %, qolganlari 0.5×…1.5×
    let lo = Math.abs(cur) > 200 ? cur * 0.9 : cur * 0.5, hi = Math.abs(cur) > 200 ? cur * 1.1 : cur * 1.5;
    if (cur === 0) { lo = 0; hi = field.max ?? 1; }
    if (field.min != null) lo = Math.max(lo, field.min);
    if (field.max != null) hi = Math.min(hi, field.max);
    setRange((r) => ({ ...r, min: String(+lo.toPrecision(4)), max: String(+hi.toPrecision(4)) }));
    setRes(null);
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  async function run() {
    if (!field) return;
    const lo = Number(range.min), hi = Number(range.max), n = Math.max(2, Math.min(60, range.n));
    if (!Number.isFinite(lo) || !Number.isFinite(hi) || hi <= lo) { setErr("Oraliq noto'g'ri"); return; }
    setBusy(true); setErr("");
    try {
      const vals = Array.from({ length: n }, (_, i) => +(lo + (hi - lo) * i / (n - 1)).toPrecision(6));
      setRes(await api.simSweep({ kind: kind.id, params: values, key, values: vals }));
    } catch (e) { setErr(e instanceof Error ? e.message : "Xatolik"); } finally { setBusy(false); }
  }
  if (!numeric.length) return null;
  return (
    <details className="section-box small" open={open} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)} style={{ marginTop: 8 }}>
      <summary title="Bitta parametrni oraliqda o'zgartirib, natijalar qanday o'zgarishini ko'rish (masalan sath → zaxira koeffitsienti)"><b>Sezgirlik tahlili</b> <span className="dim">— parametr → ko'rsatkichlar</span></summary>
      <div className="row wrap" style={{ alignItems: "flex-end", gap: 6, marginTop: 6 }}>
        <label className="field" style={{ minWidth: 200 }}><span>Parametr</span>
          <select className="select" value={key} onChange={(e) => setKey(e.target.value)}>{numeric.map((f) => <option key={f.key} value={f.key}>{f.label}{f.unit ? ` (${f.unit})` : ""}</option>)}</select></label>
        <label className="field" style={{ width: 90 }}><span>dan</span><input className="input" type="number" step="any" value={range.min} onChange={(e) => setRange({ ...range, min: e.target.value })} /></label>
        <label className="field" style={{ width: 90 }}><span>gacha</span><input className="input" type="number" step="any" value={range.max} onChange={(e) => setRange({ ...range, max: e.target.value })} /></label>
        <label className="field" style={{ width: 70 }}><span>nuqta</span><input className="input" type="number" min={2} max={60} value={range.n} onChange={(e) => setRange({ ...range, n: Number(e.target.value) || 9 })} /></label>
        <button type="button" className="btn sm primary" disabled={busy} onClick={() => void run()}>{busy ? "…" : "Hisoblash"}</button>
      </div>
      {err && <div className="error small">{err}</div>}
      {res && (
        <>
          {res.outputs.filter((o) => res.rows.some((r) => typeof r.summary[o.key] === "number")).map((o, i) => (
            <LineChart key={o.key} title={`${o.label} (${res.label}${res.unit ? `, ${res.unit}` : ""})`} unit={o.unit} x={res.rows.map((r) => r.value)} series={[{ name: o.label, values: res.rows.map((r) => (typeof r.summary[o.key] === "number" ? (r.summary[o.key] as number) : NaN)), color: CHART_COLORS[i % CHART_COLORS.length] }]} height={120} />
          ))}
          {res.rows.some((r) => r.error) && <div className="dim">Xato bo'lgan nuqtalar: {res.rows.filter((r) => r.error).map((r) => r.value).join(", ")}</div>}
          {(() => { const bad = res.rows.filter((r) => r.summary.ok === false); const good = res.rows.filter((r) => r.summary.ok !== false && !r.error); return bad.length && good.length ? <div className="small"><b>Chegara:</b> {res.label} {bad[0].value > good[0].value ? `> ${good[good.length - 1].value}` : `< ${good[0].value}`} {res.unit} da mezon bajarilmaydi.</div> : null; })()}
        </>
      )}
    </details>
  );
}

function Tile({ v, u, t }: { v: unknown; u: string; t: string }) {
  let s: string;
  if (typeof v === "number") s = Math.abs(v) >= 1000 ? v.toLocaleString("uz-UZ", { maximumFractionDigits: 0 }) : v.toFixed(Math.abs(v) >= 100 ? 0 : 2);
  else if (v === null || v === undefined) s = "—";
  else s = String(v);
  return <div className="tile"><div className="tile-v">{s} <span className="tile-u">{u}</span></div><div className="tile-t">{t}</div></div>;
}

function KVTable({ rows, cols }: { rows: Record<string, unknown>[]; cols: [string, string][] }) {
  return (
    <table className="grid small" style={{ marginTop: 8 }}>
      <thead><tr>{cols.map(([k, t]) => <th key={k}>{t}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}>{cols.map(([k]) => <td key={k} className={typeof r[k] === "number" ? "mono" : ""}>{typeof r[k] === "number" ? (r[k] as number).toLocaleString("uz-UZ", { maximumFractionDigits: 2 }) : String(r[k] ?? "")}</td>)}</tr>)}</tbody>
    </table>
  );
}

/** To'g'on ko'ndalang kesimi: profil ko'pburchak, yuqori/quyi byef sathlari (SVG). */
function DamProfile({ profile }: { profile: { points: [number, number][]; h1: number; h2: number } }) {
  const pts = profile.points;
  const W = Math.max(...pts.map((p) => p[0])), H = Math.max(...pts.map((p) => p[1]), profile.h1);
  const sc = 260 / Math.max(W, H * 1.2);
  const X = (x: number) => 40 + x * sc, Y = (y: number) => 20 + (H - y) * sc;
  const h1y = Y(Math.min(profile.h1, H)), h2y = Y(Math.min(profile.h2, H));
  return (
    <svg className="dam-profile" viewBox={`0 0 340 ${40 + H * sc}`} width="100%" style={{ maxHeight: 220, marginTop: 8 }}>
      <rect x={0} y={h1y} width={X(0)} height={Y(0) - h1y} fill="#3d8ee6" opacity={0.35} />
      <rect x={X(W)} y={h2y} width={340 - X(W)} height={Y(0) - h2y} fill="#3d8ee6" opacity={0.35} />
      <polygon points={pts.map((p) => `${X(p[0])},${Y(p[1])}`).join(" ")} fill="#8a8f98" stroke="#d0d3d8" strokeWidth={1} />
      <line x1={0} y1={Y(0)} x2={340} y2={Y(0)} stroke="#6a6e76" />
      <text x={4} y={h1y - 3} fontSize={10} fill="#9ab">h₁ = {profile.h1.toFixed(1)} m</text>
      <text x={X(W) + 4} y={h2y - 3} fontSize={10} fill="#9ab">h₂ = {profile.h2.toFixed(1)} m</text>
    </svg>
  );
}
