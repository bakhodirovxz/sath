import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type CfdParams, type CfdResult, type SimJob, type Version } from "../../api/client";
import type { SelectedItem, Viewer } from "../../viewer/Viewer";
import LineChart from "../../ui/LineChart";
import Heatmap, { gridFromPoints, seqColor } from "../../ui/Heatmap";
import { fmtDate } from "../../ui/format";

interface Props {
  modelId: number;
  current: Version | null;
  viewer: Viewer | null;
  selection: SelectedItem[];
  jobs: SimJob[];
  onJobsChanged: () => void;
}

type Kind = "penstock" | "spillway" | "geometry";
const DEFAULTS: Record<Kind, CfdParams> = {
  penstock: { kind: "penstock", length_m: 20, diameter_m: 2.4, flow_m3s: 20, roughness_mm: 0.1, resolution: 1, max_iterations: 400 },
  spillway: { kind: "spillway", crest_height_m: 3, head_m: 1, crest_length_m: 4, upstream_m: 10, downstream_m: 12, unit_discharge_m2s: null, resolution: 1, end_time_s: 15 },
  geometry: { kind: "geometry", velocity_ms: 2, flow_axis: "x", refinement: 2, resolution: 1, max_iterations: 300 },
};
const n1 = (v: unknown, d = 2) => (typeof v === "number" ? v.toFixed(d) : "—");
const num = (v: string, d = 0) => (v === "" || Number.isNaN(Number(v)) ? d : Number(v));

/** CFD (OpenFOAM): shablon → parametrlar → hisob (progress) → natija: grafiklar, 2D maydon, 3D tekislik. */
export default function CfdPanel({ modelId, current, viewer, selection, jobs, onJobsChanged }: Props) {
  const [status, setStatus] = useState<{ mode: string; available: boolean } | null>(null);
  const [params, setParams] = useState<CfdParams>(DEFAULTS.penstock);
  const [name, setName] = useState("");
  const [active, setActive] = useState<SimJob | null>(null);
  const [result, setResult] = useState<CfdResult | null>(null);
  const [field, setField] = useState<"u" | "p" | "alpha">("u");
  const [logs, setLogs] = useState<Record<string, string> | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.cfdStatus().then(setStatus).catch(() => setStatus({ mode: "?", available: false })); }, []);

  // Progress so'rovi
  useEffect(() => {
    if (!active || (active.status !== "queued" && active.status !== "running")) return;
    const id = window.setInterval(async () => {
      const j = await api.simJob(active.id);
      setActive(j);
      if (j.status === "done" || j.status === "failed") { onJobsChanged(); if (j.status === "done") void openResult(j); }
    }, 1500);
    return () => window.clearInterval(id);
  }, [active?.id, active?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const openResult = useCallback(async (j: SimJob) => {
    try {
      const full = await api.simJob(j.id);
      setActive(full);
      setResult(await api.cfdResult(j.id));
      setLogs(null);
    } catch (e) { setError(e instanceof Error ? e.message : "Xatolik"); }
  }, []);

  const grid = useMemo(() => {
    if (!result) return null;
    const pick = field === "u" ? (p: { u: number }) => p.u : field === "p" ? (p: { p?: number }) => p.p : (p: { alpha?: number }) => p.alpha;
    return gridFromPoints(result.plane, pick as (p: { x: number; y: number }) => number | undefined);
  }, [result, field]);

  // 3D: maydon tekisligi elementga
  useEffect(() => {
    if (!viewer) return;
    const guid = active?.params?.element_guid as string | null | undefined;
    void viewer.showFieldPlane(guid ?? null, grid ? { nx: grid.nx, ny: grid.ny, values: grid.values } : null, seqColor);
  }, [grid, viewer, active?.params?.element_guid]);
  useEffect(() => () => { void viewer?.showFieldPlane(null, null, seqColor); }, [viewer]);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      const geomExtra = params.kind === "geometry" ? { element_guids: selection.map((s) => s.guid).filter((g): g is string => !!g) } : {};
      if (params.kind === "geometry" && !current) throw new Error("Geometriya uchun versiya kerak");
      const job = await api.createSim(modelId, { name, version_id: current?.id ?? null, kind: "cfd", params: { ...params, ...geomExtra, element_guid: selection[0]?.guid ?? params.element_guid ?? null } });
      setActive(job); setResult(null); onJobsChanged();
    } catch (err) { setError(err instanceof Error ? err.message : "Xatolik"); } finally { setBusy(false); }
  }

  async function fromModel() {
    if (!current) return;
    try {
      const g = await api.gesParams(current.id);
      const sel = selection[0]?.guid;
      const pen = g.penstocks.find((p) => p.guid === sel) ?? g.penstocks[0];
      const sp = g.spillways.find((p) => p.guid === sel) ?? g.spillways[0];
      if (params.kind === "penstock" && pen) setParams({ ...params, length_m: pen.length_m, diameter_m: pen.diameter_m, roughness_mm: pen.roughness_mm, element_guid: pen.guid });
      else if (params.kind === "spillway" && sp) setParams({ ...params, crest_length_m: params.crest_length_m, element_guid: sp.guid });
      else setError("Modelda mos Pset_GES_* element topilmadi");
    } catch (e) { setError(e instanceof Error ? e.message : "Xatolik"); }
  }

  const upd = (patch: Partial<CfdParams>) => setParams((p) => ({ ...p, ...patch }));
  const cfdJobs = jobs.filter((j) => j.kind === "cfd");
  const running = active && (active.status === "queued" || active.status === "running");

  return (
    <div className="cfd">
      {status && !status.available && <p className="error small">CFD bu serverda mavjud emas (rejim: {status.mode}). Administrator: docker yoki `--profile cfd`.</p>}
      {error && <p className="error small">{error} <a onClick={() => setError("")}>yopish</a></p>}

      {cfdJobs.length > 0 && (
        <details open={cfdJobs.length <= 3} className="section-box">
          <summary>CFD hisoblari ({cfdJobs.length})</summary>
          {cfdJobs.map((j) => (
            <div key={j.id} className={`list-item${active?.id === j.id ? " selected" : ""}`} onClick={() => (j.status === "done" ? openResult(j) : setActive(j))}>
              <div className="title"><b>#{j.id}</b><span className="grow">{j.name}</span><span className={`badge ${j.status === "done" ? "published" : j.status === "failed" ? "rejected" : "shared"}`}>{j.status === "done" ? "Tayyor" : j.status === "failed" ? "Xato" : `${Math.round(j.progress * 100)}%`}</span></div>
              <div className="meta">{j.author_username} · {fmtDate(j.created_at)}{j.status === "failed" && <span className="error"> · {j.error.slice(0, 120)}</span>}</div>
            </div>
          ))}
        </details>
      )}

      {running && (
        <div className="section-box">
          <b>Hisoblanmoqda…</b> <span className="muted small">{active.error || (active.status === "queued" ? "navbatda (worker kutilmoqda)" : "")}</span>
          <div className="progress" style={{ marginTop: 6 }}><i style={{ width: `${active.progress * 100}%` }} /></div>
        </div>
      )}

      {result && active && (
        <div className="section-box">
          <div className="row"><b className="grow">#{active.id} {active.name}</b><button className="btn sm" onClick={() => api.simLog(active.id).then(setLogs)}>Log</button><button className="btn sm" onClick={() => { setResult(null); setLogs(null); }}>Yopish</button></div>
          {result.kind === "geometry" ? (
            <>
              <div className="tiles">
                <Tile v={result.summary.drag_n as number | null} u="N" t="Oqim kuchi (drag)" d={0} />
                <Tile v={result.summary.max_velocity as number | null} u="m/s" t="Maks. tezlik" d={2} />
                <Tile v={result.summary.body_p_max_pa as number | null} u="Pa" t="Sirtdagi maks. bosim" d={0} />
                <Tile v={result.summary.body_p_min_pa as number | null} u="Pa" t="Sirtdagi min. bosim" d={0} />
                <Tile v={result.summary.inlet_velocity as number | null} u="m/s" t="Kirish tezligi" d={2} />
                <Tile v={result.summary.cells as number | null} u="" t="Yacheykalar" d={0} />
              </div>
              <p className="dim small">Kuch (x, y, z): {Array.isArray(result.summary.force_n) ? result.summary.force_n.map((v) => n1(v, 0)).join(", ") : "—"} N · elementlar: {(active.params?.stl_elements as { name: string }[] | undefined)?.map((e) => e.name).join(", ")}</p>
            </>
          ) : result.kind === "penstock" ? (
            <>
              <div className="tiles">
                <Tile v={result.summary.head_loss_m} u="m" t="Napor yo'qotishi" d={3} />
                <Tile v={result.summary.pressure_drop_pa} u="Pa" t="Bosim tushishi" d={0} />
                <Tile v={result.summary.max_velocity} u="m/s" t="Maks. tezlik" d={2} />
                <Tile v={result.summary.head_loss_per_100m} u="m/100m" t="Solishtirma yo'qotish" d={3} />
                <Tile v={result.summary.inlet_velocity} u="m/s" t="Kirish tezligi" d={2} />
                <Tile v={result.summary.cells} u="" t="Yacheykalar" d={0} />
              </div>
              {result.axis && <LineChart title="Bosim napori o'q bo'ylab" unit="m" x={result.axis.x.map((v) => v.toFixed(1))} series={[{ name: "Napor", values: result.axis.head_m }]} />}
              {result.radial && <LineChart title="Tezlik profili (radius bo'yicha)" unit="m/s" x={result.radial.r.map((v) => v.toFixed(2))} series={[{ name: "U", values: result.radial.u }]} />}
            </>
          ) : (
            <>
              <div className="tiles">
                <Tile v={result.summary.depth_over_crest_m} u="m" t="Ostona ustida chuqurlik" d={2} />
                <Tile v={result.summary.critical_depth_m} u="m" t="Kritik chuqurlik" d={2} />
                <Tile v={result.summary.max_velocity} u="m/s" t="Maks. tezlik (suv)" d={2} />
                <Tile v={result.summary.unit_discharge_in} u="m²/s" t="Solishtirma sarf (kirish)" d={3} />
                <Tile v={result.summary.unit_discharge_out} u="m²/s" t="Solishtirma sarf (chiqish)" d={3} />
                <Tile v={result.summary.cells} u="" t="Yacheykalar" d={0} />
              </div>
              {result.profile && <LineChart title="Suv sirti profili" unit="m" x={result.profile.map((p) => p.x.toFixed(1))} series={[{ name: "Sath", values: result.profile.map((p) => p.y) }]} refLines={[{ value: result.inputs.crest_height_m as number, label: "ostona" }]} />}
            </>
          )}
          <div className="row" style={{ margin: "6px 0" }}>
            <span className="small muted">Maydon:</span>
            <button className={`btn sm${field === "u" ? " active" : ""}`} onClick={() => setField("u")}>Tezlik</button>
            {(result.kind === "penstock" || result.kind === "geometry") && <button className={`btn sm${field === "p" ? " active" : ""}`} onClick={() => setField("p")}>Bosim</button>}
            {result.kind === "spillway" && <button className={`btn sm${field === "alpha" ? " active" : ""}`} onClick={() => setField("alpha")}>Suv ulushi</button>}
            {active.params?.element_guid ? <span className="dim small">· 3D da elementga qo'yilgan</span> : <span className="dim small">· 3D uchun elementni tanlab hisoblang</span>}
          </div>
          {grid ? <Heatmap grid={grid} title={field === "u" ? "Tezlik maydoni" : field === "p" ? "Bosim maydoni" : "Suv ulushi (alpha)"} unit={field === "u" ? "m/s" : field === "p" ? "Pa" : ""} /> : <p className="dim small">Maydon nuqtalari yo'q.</p>}
          {logs && <pre className="mono small" style={{ maxHeight: 200, overflow: "auto", background: "var(--canvas)", padding: 6 }}>{Object.entries(logs).map(([k, v]) => `--- ${k}\n${v}`).join("\n\n")}</pre>}
        </div>
      )}

      <form onSubmit={run}>
        <div className="row" style={{ marginBottom: 8 }}>
          <select className="select" style={{ width: 170 }} value={params.kind} onChange={(e) => setParams(DEFAULTS[e.target.value as Kind])}>
            <option value="penstock">Bosimli quvur (oqim)</option>
            <option value="spillway">Suv tashlagich (erkin sirt)</option>
            <option value="geometry">Model geometriyasi (3D)</option>
          </select>
          <input className="input grow" placeholder="Hisob nomi" value={name} onChange={(e) => setName(e.target.value)} />
          <button className="btn primary" type="submit" disabled={busy || !!running || (status ? !status.available : false)}>Hisoblash</button>
        </div>
        <div className="row" style={{ marginBottom: 6 }}>
          {current && <button type="button" className="btn sm" onClick={fromModel}>Modeldan olish{selection[0]?.name ? ` (${selection[0].name})` : ""}</button>}
          <span className="dim small">{selection[0]?.guid ? `3D: ${selection[0].name || selection[0].category}` : "3D da element tanlansa natija unga qo'yiladi"}</span>
        </div>
        {params.kind === "geometry" ? (
          <div className="row wrap">
            <span className="small" style={{ width: "100%" }}>{selection.length ? `${selection.length} ta element tanlangan: ${selection.map((s) => s.name || s.category).join(", ")}` : "3D da element(lar)ni tanlang — ular atrofida suv oqimi hisoblanadi (snappyHexMesh + simpleFoam)"}</span>
            <Num label="Oqim tezligi, m/s" v={params.velocity_ms!} set={(v) => upd({ velocity_ms: v })} step={0.1} />
            <label className="field" style={{ width: 120 }}><span>Oqim o'qi</span><select className="select" value={params.flow_axis} onChange={(e) => upd({ flow_axis: e.target.value as "x" | "y" })}><option value="x">X</option><option value="y">Y</option></select></label>
            <Num label="Sirt aniqligi (1–3)" v={params.refinement!} set={(v) => upd({ refinement: Math.round(v) })} />
            <Num label="Iteratsiyalar" v={params.max_iterations!} set={(v) => upd({ max_iterations: Math.round(v) })} />
            <Num label="Aniqlik (0.5–2)" v={params.resolution!} set={(v) => upd({ resolution: v })} step={0.1} />
          </div>
        ) : params.kind === "penstock" ? (
          <div className="row wrap">
            <Num label="Uzunlik, m" v={params.length_m!} set={(v) => upd({ length_m: v })} />
            <Num label="Diametr, m" v={params.diameter_m!} set={(v) => upd({ diameter_m: v })} step={0.1} />
            <Num label="Sarf, m³/s" v={params.flow_m3s!} set={(v) => upd({ flow_m3s: v })} />
            <Num label="G'adir-budirlik, mm" v={params.roughness_mm!} set={(v) => upd({ roughness_mm: v })} step={0.01} />
            <Num label="Iteratsiyalar" v={params.max_iterations!} set={(v) => upd({ max_iterations: Math.round(v) })} />
            <Num label="Aniqlik (0.5–2)" v={params.resolution!} set={(v) => upd({ resolution: v })} step={0.1} />
          </div>
        ) : (
          <div className="row wrap">
            <Num label="Ostona balandligi, m" v={params.crest_height_m!} set={(v) => upd({ crest_height_m: v })} step={0.1} />
            <Num label="Napor, m" v={params.head_m!} set={(v) => upd({ head_m: v })} step={0.1} />
            <Num label="Ostona uzunligi, m" v={params.crest_length_m!} set={(v) => upd({ crest_length_m: v })} step={0.5} />
            <Num label="Yuqori byef, m" v={params.upstream_m!} set={(v) => upd({ upstream_m: v })} />
            <Num label="Quyi byef, m" v={params.downstream_m!} set={(v) => upd({ downstream_m: v })} />
            <Num label="Solishtirma sarf, m²/s (bo'sh — napordan)" v={params.unit_discharge_m2s ?? ""} set={(v) => upd({ unit_discharge_m2s: v || null })} step={0.1} />
            <Num label="Vaqt, s" v={params.end_time_s!} set={(v) => upd({ end_time_s: v })} />
            <Num label="Aniqlik (0.5–2)" v={params.resolution!} set={(v) => upd({ resolution: v })} step={0.1} />
          </div>
        )}
        <p className="dim small">{params.kind === "penstock" ? "O'q-simmetrik model (simpleFoam, k-ε). Odatiy aniqlikda 10–60 s." : params.kind === "spillway" ? "2D erkin sirt (interFoam VOF). Odatiy aniqlikda 1–5 daqiqa; aniqlik 2 — 10+ daqiqa." : "3D, tanlangan IFC elementlari STL sifatida (snappyHexMesh, simpleFoam k-ε, suv ostida). Odatiy aniqlikda 5–20 daqiqa."}</p>
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

function Tile({ v, u, t, d }: { v: number | number[] | null | undefined; u: string; t: string; d: number }) {
  return (
    <div className="tile">
      <div className="tile-v">{typeof v !== "number" ? "—" : v.toFixed(d)} <span className="tile-u">{u}</span></div>
      <div className="tile-t">{t}</div>
    </div>
  );
}
