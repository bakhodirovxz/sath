import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Icon from "../../ui/Icon";
import { useNavigate } from "react-router-dom";
import { api, type SimCatalog as Catalog, type SimJob, type SimKind, type SimParams, type SimResult, type SimUnit, type Version } from "../../api/client";
import SimCatalog from "./sim/SimCatalog";
import SafetyCheck from "./sim/SafetyCheck";
import GenericSim from "./sim/GenericSim";
import CustomSim from "./sim/CustomSim";
import type { SelectedItem, Viewer } from "../../viewer/Viewer";
import CfdPanel from "./CfdPanel";
import LineChart, { CHART_COLORS } from "../../ui/LineChart";
import { fmtDate } from "../../ui/format";

interface Props {
  modelId: number;
  projectId?: number;
  current: Version | null;
  viewer: Viewer | null;
  selection: SelectedItem[];
  canEdit?: boolean;
  initialKind?: string | null;
}

const MODES: { id: SimParams["operation"]["mode"]; title: string; hint: string }[] = [
  { id: "target_level", title: "Sathni ushlab turish", hint: "Turbinalar sathni maqsadli belgida saqlaydi" },
  { id: "max_power", title: "Maksimal quvvat", hint: "Suv yetguncha to'liq yuklama (o'lik sathgacha)" },
  { id: "run_of_river", title: "Oqim bo'yicha", hint: "Kiruvchi sarf qancha — shuncha turbinalanadi" },
  { id: "constant_flow", title: "Doimiy sarf", hint: "Berilgan sarf bilan ishlash" },
  { id: "target_power", title: "Berilgan quvvat", hint: "Dispetcher topshirig'i bo'yicha quvvat" },
];

const num = (v: string, d = 0) => (v === "" || Number.isNaN(Number(v)) ? d : Number(v));

/** Simulyatsiya: parametrlar → ishga tushirish → natijalar (grafiklar, xulosa, 3D suv sathi vaqt slayderi bilan). */
export default function SimPanel({ modelId, projectId, current, viewer, selection, canEdit = false, initialKind = null }: Props) {
  const [kind, setKind] = useState<string | null>(initialKind);
  const [openJobId, setOpenJobId] = useState<number | null>(null); // xavfsizlik tekshiruvidan natijani ochish
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [siteFilled, setSiteFilled] = useState<boolean | null>(null);
  const nav = useNavigate();
  useEffect(() => { setKind(initialKind); }, [initialKind]);
  useEffect(() => {
    api.simCatalog().then(setCatalog).catch((e) => setError(e.message));
    if (projectId) api.site(projectId).then((st) => setSiteFilled(st.filled)).catch(() => setSiteFilled(null));
  }, [projectId]);
  const [params, setParams] = useState<SimParams | null>(null);
  const [name, setName] = useState("");
  const [jobs, setJobs] = useState<SimJob[]>([]);
  const [active, setActive] = useState<SimJob | null>(null);
  const [result, setResult] = useState<SimResult | null>(null);
  const [cursor, setCursor] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState<"form" | "results">("form");
  const [inflowText, setInflowText] = useState("");
  const [curveText, setCurveText] = useState("");
  const pollRef = useRef<number | null>(null);

  const loadJobs = useCallback(() => api.simJobs(modelId).then(setJobs).catch((e) => setError(e.message)), [modelId]);

  useEffect(() => {
    api.simExample().then((p) => {
      setParams(p);
      setCurveText(p.reservoir.curve.elevations_m.map((e, i) => `${e} ${p.reservoir.curve.volumes_mcm[i]}`).join("\n"));
    });
    void loadJobs();
  }, [loadJobs]);

  // Ish tugaguncha so'rab turish
  useEffect(() => {
    if (!active || (active.status !== "queued" && active.status !== "running")) return;
    pollRef.current = window.setInterval(async () => {
      const j = await api.simJob(active.id);
      if (j.status === "done" || j.status === "failed") {
        setActive(j);
        void loadJobs();
        if (j.status === "done") openResult(j);
      }
    }, 700);
    return () => { if (pollRef.current) window.clearInterval(pollRef.current); };
  }, [active?.id, active?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  // Slayder → 3D suv sathi + agregat ranglari
  useEffect(() => {
    if (!viewer || !result) return;
    const i = cursor ?? result.series.level.length - 1;
    const zero = active?.params?.model_zero_elevation_m ?? params?.model_zero_elevation_m ?? 0;
    viewer.setWaterLevel(result.series.level[i] - zero);
    const colors: Record<string, string> = {};
    const units = active?.params?.units ?? [];
    units.forEach((u, k) => {
      if (u.guid) colors[u.guid] = (result.units[k]?.power_mw[i] ?? 0) > 0 ? "#3aa864" : "#6a6e76";
    });
    void viewer.colorByGuids(colors);
  }, [cursor, result, viewer]); // eslint-disable-line react-hooks/exhaustive-deps

  // Panel yopilganda suv sathini olib tashlash
  useEffect(() => () => { viewer?.setWaterLevel(null); void viewer?.colorByGuids({}); }, [viewer]);

  // Animatsiya
  useEffect(() => {
    if (!playing || !result) return;
    const n = result.series.level.length;
    const id = window.setInterval(() => setCursor((c) => ((c ?? -1) + 1) % n), 80);
    return () => window.clearInterval(id);
  }, [playing, result]);

  async function openResult(j: SimJob) {
    try {
      const full = await api.simJob(j.id);
      setActive(full);
      setResult(await api.simResult(j.id));
      setCursor(null);
      setView("results");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Xatolik");
    }
  }

  async function run(e: React.FormEvent) {
    e.preventDefault();
    if (!params) return;
    setBusy(true);
    setError("");
    try {
      const p: SimParams = { ...params };
      if (inflowText.trim()) {
        const vals = inflowText.split(/[\s,;]+/).map(Number).filter((v) => Number.isFinite(v));
        if (vals.length < 2) throw new Error("Gidrograf: kamida 2 ta qiymat kiriting");
        p.inflow_m3s = vals;
      }
      const rows = curveText.trim().split(/\n+/).map((r) => r.trim().split(/[\s,;]+/).map(Number));
      if (rows.some((r) => r.length < 2 || r.some((v) => !Number.isFinite(v)))) throw new Error("Sath–hajm jadvali: har qatorda 'sath hajm'");
      p.reservoir = { ...p.reservoir, curve: { elevations_m: rows.map((r) => r[0]), volumes_mcm: rows.map((r) => r[1]) } };
      const job = await api.createSim(modelId, { name, version_id: current?.id ?? null, params: p });
      setActive(job);
      await loadJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Xatolik");
    } finally {
      setBusy(false);
    }
  }

  /** Raqamli egizak: jonli SCADA holatidan boshlash (sath, kiruvchi sarf) — "nima bo'lsa" ssenariysi */
  async function fromLive() {
    if (!projectId || !params) return;
    try {
      const d = await api.dashboard(projectId);
      const by = new Map(d.sensors.map((s) => [s.id, s]));
      const up = by.get(d.mimic.upstream_level ?? -1);
      const inflow = by.get(d.mimic.inflow ?? -1);
      const tail = by.get(d.mimic.downstream_level ?? -1);
      if (!up || up.last_value == null) { setError("Sxemada yuqori byef sathi sensori bog'lanmagan yoki ma'lumot yo'q"); return; }
      setParams({
        ...params,
        reservoir: { ...params.reservoir, initial_level_m: up.last_value, ...(tail?.last_value != null ? { tailwater_m: tail.last_value } : {}) },
        inflow_m3s: inflow?.last_value != null ? { constant: inflow.last_value, steps: (params.inflow_m3s as { steps?: number }).steps ?? 365 } : params.inflow_m3s,
      });
      setName(`Jonli holatdan (${up.last_value.toFixed(2)} m)`);
    } catch (e) { setError(e instanceof Error ? e.message : "Xatolik"); }
  }

  async function fromModel() {
    if (!current || !params) return;
    try {
      const g = await api.gesParams(current.id);
      const units: SimUnit[] = g.units.map((u) => ({ guid: u.guid, name: u.name, type: u.type, rated_power_mw: u.rated_power_mw, rated_head_m: u.rated_head_m, rated_flow_m3s: u.rated_flow_m3s, max_efficiency: u.max_efficiency }));
      const next: SimParams = { ...params };
      if (units.length) next.units = units;
      if (g.penstocks.length) next.penstock = { ...(params.penstock ?? { minor_loss_k: 0.5, per_unit: true }), length_m: g.penstocks[0].length_m, diameter_m: g.penstocks[0].diameter_m, roughness_mm: g.penstocks[0].roughness_mm, per_unit: true, minor_loss_k: params.penstock?.minor_loss_k ?? 0.5 };
      if (g.spillways.length) next.reservoir = { ...next.reservoir, spillway: { crest_m: g.spillways[0].crest_m || next.reservoir.normal_level_m, width_m: g.spillways[0].width_m, coefficient: g.spillways[0].coefficient, gate_opening: 1 } };
      setParams(next);
      setError(units.length ? "" : "Modelda Pset_GES_Turbine topilmadi — agregatlarni qo'lda kiriting");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Xatolik");
    }
  }

  const upd = (patch: Partial<SimParams>) => setParams((p) => (p ? { ...p, ...patch } : p));
  const updRes = (patch: Partial<SimParams["reservoir"]>) => setParams((p) => (p ? { ...p, reservoir: { ...p.reservoir, ...patch } } : p));
  const updUnit = (i: number, patch: Partial<SimUnit>) => setParams((p) => (p ? { ...p, units: p.units.map((u, k) => (k === i ? { ...u, ...patch } : u)) } : p));

  const x = useMemo(() => result?.series.t ?? [], [result]);

  const hydroJobs = jobs.filter((j) => j.kind === "hydro");
  const kindMeta = catalog?.kinds.find((k) => k.id === kind) ?? null;
  const modeBar = (
    <div className="bhead">
      <button className="btn sm" onClick={() => setKind(null)} title="Katalogga qaytish"><Icon name="chevron-left" size={13} /></button>
      {kindMeta && <Icon name={kindMeta.icon} size={14} />}
      <b className="grow">{kindMeta?.title ?? (kind === "cfd" ? "CFD oqim (OpenFOAM)" : "Suv ombori rejimi va energiya")}</b>
    </div>
  );
  if (kind === null) {
    if (!catalog) return <p className="muted">{error || "Katalog yuklanmoqda…"}</p>;
    return (
      <div className="sim">
        {siteFilled && <SafetyCheck modelId={modelId} current={current} viewer={viewer} onOpenJob={(k, id) => { setOpenJobId(id); setKind(k); }} onDone={() => void loadJobs()} />}
        <SimCatalog catalog={catalog} jobs={jobs} onPick={(k: SimKind) => setKind(k.id)} siteFilled={siteFilled} onSite={projectId ? () => nav(`/projects/${projectId}/site`) : undefined} />
      </div>
    );
  }
  if (kind === "cfd") return <div className="sim">{modeBar}<CfdPanel modelId={modelId} current={current} viewer={viewer} selection={selection} jobs={jobs} onJobsChanged={() => void loadJobs()} /></div>;
  if (kind === "custom") return <CustomSim modelId={modelId} projectId={projectId} current={current} canEdit={canEdit} jobs={jobs} onJobsChanged={() => void loadJobs()} onBack={() => setKind(null)} />;
  if (kind !== "hydro") {
    if (!kindMeta) return <p className="muted">Noma'lum simulyatsiya turi: {kind}</p>;
    return <GenericSim key={kind} kind={kindMeta} modelId={modelId} projectId={projectId} current={current} viewer={viewer} jobs={jobs} onJobsChanged={() => void loadJobs()} onBack={() => { setOpenJobId(null); setKind(null); }} initialJobId={openJobId} />;
  }

  if (!params) return <p className="muted">Yuklanmoqda…</p>;

  if (view === "results" && result && active) {
    const s = result.series;
    const sm = active.summary;
    const i = cursor ?? s.level.length - 1;
    return (
      <div className="sim">
        {modeBar}
        <div className="row" style={{ marginBottom: 8 }}>
          <button className="btn sm" onClick={() => setView("form")}><Icon name="arrow-left" size={13} /> Parametrlar</button>
          <b className="grow">{active.name || `#${active.id}`}</b>
          <span className="dim small">{fmtDate(active.created_at)}</span>
        </div>
        <div className="tiles">
          <Tile v={sm.energy_mwh} u="MWh" t="Ishlab chiqarish" />
          <Tile v={sm.mean_power_mw} u="MW" t="O'rtacha quvvat" />
          <Tile v={sm.capacity_factor * 100} u="%" t="O'rnatilgan quvvatdan foydalanish" />
          <Tile v={sm.spill_volume_mcm} u="mln m³" t="Tashlama" />
          <Tile v={sm.min_level_m} u="m" t="Min sath" />
          <Tile v={sm.max_level_m} u="m" t="Max sath" />
        </div>
        <div className="sim-player">
          <button className="btn sm" onClick={() => setPlaying(!playing)} aria-label={playing ? "Pauza" : "Ijro"}><Icon name={playing ? "pause" : "play"} size={13} /></button>
          <input type="range" min={0} max={s.level.length - 1} value={i} onChange={(e) => { setPlaying(false); setCursor(Number(e.target.value)); }} className="grow" aria-label="Vaqt" />
          <span className="mono small" style={{ minWidth: 150 }}>{String(s.t[i]).slice(0, 10)} · {s.level[i].toFixed(2)} m · {s.power_mw[i].toFixed(1)} MW</span>
        </div>
        <LineChart title="Suv sathi" unit="m" x={x} series={[{ name: "Sath", values: s.level }]} cursor={cursor} onCursor={setCursor}
          refLines={[{ value: active.params!.reservoir.normal_level_m, label: "NPU" }, { value: active.params!.reservoir.dead_level_m, label: "O'lik sath" }]} />
        <LineChart title="Sarflar" unit="m³/s" x={x} cursor={cursor} onCursor={setCursor}
          series={[{ name: "Kiruvchi", values: s.inflow, color: CHART_COLORS[0] }, { name: "Turbina", values: s.turbine_flow, color: CHART_COLORS[2] }, { name: "Tashlama", values: s.spill, color: CHART_COLORS[1] }]} />
        <LineChart title="Quvvat" unit="MW" x={x} cursor={cursor} onCursor={setCursor}
          series={[{ name: "Jami", values: s.power_mw, color: CHART_COLORS[0] }, ...result.units.slice(0, 4).map((u, k) => ({ name: u.name, values: u.power_mw, color: CHART_COLORS[(k + 1) % CHART_COLORS.length], dashed: true }))]} />
        <LineChart title="Sof napor" unit="m" x={x} series={[{ name: "Napor", values: s.head_net }]} cursor={cursor} onCursor={setCursor} />
        <details style={{ marginTop: 8 }}>
          <summary className="muted small">Jadval ko'rinishi</summary>
          <div style={{ maxHeight: 220, overflow: "auto" }}>
            <table className="grid small"><thead><tr><th>t</th><th>Sath</th><th>Kir.</th><th>Turb.</th><th>Tash.</th><th>MW</th></tr></thead>
              <tbody>{s.t.map((t, k) => <tr key={k}><td>{String(t).slice(0, 10)}</td><td>{s.level[k]}</td><td>{s.inflow[k]}</td><td>{s.turbine_flow[k]}</td><td>{s.spill[k]}</td><td>{s.power_mw[k]}</td></tr>)}</tbody>
            </table>
          </div>
        </details>
      </div>
    );
  }

  return (
    <div className="sim">
      {modeBar}
      {error && <p className="error small">{error}</p>}
      {hydroJobs.length > 0 && (
        <details open={hydroJobs.length <= 3} className="section-box">
          <summary>Oldingi hisoblar ({hydroJobs.length})</summary>
          {hydroJobs.map((j) => (
            <div key={j.id} className="list-item" onClick={() => j.status === "done" && openResult(j)}>
              <div className="title"><b>#{j.id}</b><span className="grow">{j.name}</span><span className={`badge ${j.status === "done" ? "published" : j.status === "failed" ? "rejected" : "shared"}`}>{j.status === "done" ? "Tayyor" : j.status === "failed" ? "Xato" : "Hisoblanmoqda"}</span></div>
              <div className="meta">{j.author_username} · {fmtDate(j.created_at)}{j.status === "done" && <> · {j.summary.energy_mwh} MWh · CF {(j.summary.capacity_factor * 100).toFixed(0)}%</>}{j.error && <span className="error"> · {j.error}</span>}</div>
            </div>
          ))}
        </details>
      )}
      <form onSubmit={run}>
        <div className="row" style={{ marginBottom: 8 }}>
          <input className="input grow" placeholder="Hisob nomi (masalan: 2026 o'rtacha suvli yil)" value={name} onChange={(e) => setName(e.target.value)} />
          <button className="btn primary" type="submit" disabled={busy || (active?.status === "running")}>{busy ? "…" : "Hisoblash"}</button>
        </div>
        {active && (active.status === "queued" || active.status === "running") && <p className="muted small">Hisoblanmoqda…</p>}

        <h3>Kiruvchi suv (gidrograf)</h3>
        <div className="row">
          <label className="field grow"><span>Doimiy sarf, m³/s</span><input className="input" type="number" value={Array.isArray(params.inflow_m3s) ? "" : params.inflow_m3s.constant} onChange={(e) => upd({ inflow_m3s: { constant: num(e.target.value), steps: Array.isArray(params.inflow_m3s) ? 365 : params.inflow_m3s.steps } })} disabled={!!inflowText.trim()} /></label>
          <label className="field"><span>Qadamlar</span><input className="input" type="number" style={{ width: 80 }} value={Array.isArray(params.inflow_m3s) ? params.inflow_m3s.length : params.inflow_m3s.steps} onChange={(e) => upd({ inflow_m3s: { constant: Array.isArray(params.inflow_m3s) ? 100 : params.inflow_m3s.constant, steps: num(e.target.value, 365) } })} disabled={!!inflowText.trim()} /></label>
          <label className="field"><span>Qadam, soat</span><input className="input" type="number" style={{ width: 80 }} value={params.dt_hours} onChange={(e) => upd({ dt_hours: num(e.target.value, 24) })} /></label>
        </div>
        <label className="field"><span>yoki qadamma-qadam qiymatlar (CSV/bo'shliq bilan; bo'sh — doimiy)</span><textarea className="textarea" style={{ minHeight: 44 }} value={inflowText} onChange={(e) => setInflowText(e.target.value)} placeholder="120 130 150 210 300 280 …" /></label>
        <div className="row">
          <label className="field grow"><span>Boshlanish sanasi</span><input className="input" type="date" value={params.start_date ?? ""} onChange={(e) => upd({ start_date: e.target.value || undefined })} /></label>
        </div>

        <h3>Suv ombori</h3>
        <label className="field"><span>Sath–hajm jadvali (m, mln m³ — har qatorda)</span><textarea className="textarea mono" style={{ minHeight: 70 }} value={curveText} onChange={(e) => setCurveText(e.target.value)} /></label>
        <div className="row wrap">
          <Num label="O'lik sath, m" v={params.reservoir.dead_level_m} set={(v) => updRes({ dead_level_m: v })} />
          <Num label="NPU, m" v={params.reservoir.normal_level_m} set={(v) => updRes({ normal_level_m: v })} />
          <Num label="FPU, m" v={params.reservoir.max_level_m ?? ""} set={(v) => updRes({ max_level_m: v })} />
          <Num label="Boshlang'ich sath, m" v={params.reservoir.initial_level_m ?? ""} set={(v) => updRes({ initial_level_m: v })} />
          <Num label="Quyi byef, m" v={params.reservoir.tailwater_m ?? 0} set={(v) => updRes({ tailwater_m: v })} />
          <Num label="Boshqa chiqim, m³/s" v={params.reservoir.other_outflow_m3s ?? 0} set={(v) => updRes({ other_outflow_m3s: v })} />
          <Num label="Bug'lanish, mm/kun" v={params.reservoir.evaporation_mm_day ?? 0} set={(v) => updRes({ evaporation_mm_day: v })} />
          <Num label="Model 0 belgisi, m (IFC z=0)" v={params.model_zero_elevation_m ?? 0} set={(v) => upd({ model_zero_elevation_m: v })} />
        </div>

        <h3>Suv tashlagich</h3>
        <label className="row small" style={{ marginBottom: 6 }}><input type="checkbox" checked={!!params.reservoir.spillway} onChange={(e) => updRes({ spillway: e.target.checked ? { crest_m: params.reservoir.normal_level_m, width_m: 20, coefficient: 0.49, gate_opening: 1 } : null })} /> bor</label>
        {params.reservoir.spillway && (
          <div className="row wrap">
            <Num label="Ostona, m" v={params.reservoir.spillway.crest_m} set={(v) => updRes({ spillway: { ...params.reservoir.spillway!, crest_m: v } })} />
            <Num label="Kenglik, m" v={params.reservoir.spillway.width_m} set={(v) => updRes({ spillway: { ...params.reservoir.spillway!, width_m: v } })} />
            <Num label="Sarf koeff. m" v={params.reservoir.spillway.coefficient} set={(v) => updRes({ spillway: { ...params.reservoir.spillway!, coefficient: v } })} step={0.01} />
            <Num label="Darvoza ochiqligi 0–1" v={params.reservoir.spillway.gate_opening} set={(v) => updRes({ spillway: { ...params.reservoir.spillway!, gate_opening: v } })} step={0.1} />
          </div>
        )}

        <h3>Bosimli quvur</h3>
        <label className="row small" style={{ marginBottom: 6 }}><input type="checkbox" checked={!!params.penstock} onChange={(e) => upd({ penstock: e.target.checked ? { length_m: 150, diameter_m: 3.5, roughness_mm: 0.1, minor_loss_k: 0.5, per_unit: true } : null })} /> yo'qotishlarni hisobga olish</label>
        {params.penstock && (
          <div className="row wrap">
            <Num label="Uzunlik, m" v={params.penstock.length_m} set={(v) => upd({ penstock: { ...params.penstock!, length_m: v } })} />
            <Num label="Diametr, m" v={params.penstock.diameter_m} set={(v) => upd({ penstock: { ...params.penstock!, diameter_m: v } })} step={0.1} />
            <Num label="G'adir-budirlik, mm" v={params.penstock.roughness_mm} set={(v) => upd({ penstock: { ...params.penstock!, roughness_mm: v } })} step={0.01} />
            <Num label="Mahalliy yo'qotish K" v={params.penstock.minor_loss_k} set={(v) => upd({ penstock: { ...params.penstock!, minor_loss_k: v } })} step={0.1} />
            <label className="row small"><input type="checkbox" checked={params.penstock.per_unit} onChange={(e) => upd({ penstock: { ...params.penstock!, per_unit: e.target.checked } })} /> har agregatga alohida quvur</label>
          </div>
        )}

        <h3 className="row">Agregatlar <span className="grow" />{current && <button type="button" className="btn sm" onClick={fromModel}>Modeldan olish (v{current.number})</button>}{projectId && <button type="button" className="btn sm" title="Raqamli egizak: joriy sath/sarf SCADA dan" onClick={fromLive}>Jonli holatdan</button>}<button type="button" className="btn sm" onClick={() => upd({ units: [...params.units, { name: `Agregat ${params.units.length + 1}`, type: "Francis", rated_power_mw: 25, rated_head_m: 45, rated_flow_m3s: 62, max_efficiency: 0.92 }] })}>+</button></h3>
        <table className="grid small">
          <thead><tr><th>Nomi</th><th>Turi</th><th>MW</th><th>Napor m</th><th>Sarf m³/s</th><th>FIK</th><th /></tr></thead>
          <tbody>
            {params.units.map((u, i) => (
              <tr key={i}>
                <td><input className="input" value={u.name} onChange={(e) => updUnit(i, { name: e.target.value })} /></td>
                <td><select className="select" value={u.type} onChange={(e) => updUnit(i, { type: e.target.value })}>{["Francis", "Kaplan", "Pelton", "Bulb"].map((t) => <option key={t}>{t}</option>)}</select></td>
                <td><input className="input" type="number" value={u.rated_power_mw} onChange={(e) => updUnit(i, { rated_power_mw: num(e.target.value) })} /></td>
                <td><input className="input" type="number" value={u.rated_head_m} onChange={(e) => updUnit(i, { rated_head_m: num(e.target.value) })} /></td>
                <td><input className="input" type="number" value={u.rated_flow_m3s} onChange={(e) => updUnit(i, { rated_flow_m3s: num(e.target.value) })} /></td>
                <td><input className="input" type="number" step={0.01} value={u.max_efficiency} onChange={(e) => updUnit(i, { max_efficiency: num(e.target.value, 0.9) })} /></td>
                <td><button type="button" className="btn sm" onClick={() => upd({ units: params.units.filter((_, k) => k !== i) })} aria-label="O'chirish"><Icon name="x" size={13} /></button></td>
              </tr>
            ))}
          </tbody>
        </table>

        <h3>Ish rejimi</h3>
        <select className="select" value={params.operation.mode} onChange={(e) => upd({ operation: { ...params.operation, mode: e.target.value as SimParams["operation"]["mode"] } })}>
          {MODES.map((m) => <option key={m.id} value={m.id}>{m.title}</option>)}
        </select>
        <p className="dim small" style={{ margin: "4px 0 6px" }}>{MODES.find((m) => m.id === params.operation.mode)?.hint}</p>
        <div className="row wrap">
          {params.operation.mode === "target_level" && <Num label="Maqsadli sath, m" v={params.operation.target_level_m ?? params.reservoir.normal_level_m} set={(v) => upd({ operation: { ...params.operation, target_level_m: v } })} />}
          {params.operation.mode === "constant_flow" && <Num label="Sarf, m³/s" v={params.operation.flow_m3s ?? 100} set={(v) => upd({ operation: { ...params.operation, flow_m3s: v } })} />}
          {params.operation.mode === "target_power" && <Num label="Quvvat, MW" v={params.operation.power_mw ?? 50} set={(v) => upd({ operation: { ...params.operation, power_mw: v } })} />}
        </div>
        <p className="dim small">Natija versiyaga bog'lanadi: {current ? `v${current.number}` : "—"}.</p>
      </form>
    </div>
  );
}

function Num({ label, v, set, step }: { label: string; v: number | string; set: (v: number) => void; step?: number }) {
  return (
    <label className="field" style={{ width: 150 }}>
      <span>{label}</span>
      <input className="input" type="number" step={step ?? "any"} value={v} onChange={(e) => set(num(e.target.value))} />
    </label>
  );
}

function Tile({ v, u, t }: { v: number; u: string; t: string }) {
  const s = Math.abs(v) >= 1000 ? v.toLocaleString("uz-UZ", { maximumFractionDigits: 0 }) : v.toFixed(Math.abs(v) >= 100 ? 0 : 1);
  return (
    <div className="tile">
      <div className="tile-v">{s} <span className="tile-u">{u}</span></div>
      <div className="tile-t">{t}</div>
    </div>
  );
}
