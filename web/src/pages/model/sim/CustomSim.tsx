import { useEffect, useState } from "react";
import { api, type CustomTemplate, type GenericParams, type GenericResult, type SimJob, type SimTemplate, type Version } from "../../../api/client";
import Icon from "../../../ui/Icon";
import LineChart, { CHART_COLORS } from "../../../ui/LineChart";
import { fmtDate } from "../../../ui/format";

interface Props {
  modelId: number;
  projectId?: number;
  current: Version | null;
  canEdit: boolean;
  jobs: SimJob[];
  onJobsChanged: () => void;
  onBack: () => void;
}

const EMPTY: CustomTemplate = { name: "", description: "", inputs: [], steps: 100, dt: 1, init: {}, step: [], outputs: [], summary: {}, checks: [] };

/** Maxsus simulyatsiya: shablon muharriri (kirishlar, boshlang'ich holat, qadam tenglamalari, chiqishlar,
    xulosa, tekshiruvlar), sinov, saqlash, ishga tushirish. Formulalar — ges_sim.custom xavfsiz hisoblagichda. */
export default function CustomSim({ modelId, projectId, current, canEdit, jobs, onJobsChanged, onBack }: Props) {
  const [templates, setTemplates] = useState<SimTemplate[]>([]);
  const [sel, setSel] = useState<number | null>(null); // saqlangan shablon id
  const [t, setT] = useState<CustomTemplate>(EMPTY);
  const [inputs, setInputs] = useState<GenericParams>({});
  const [raw, setRaw] = useState(false);
  const [rawText, setRawText] = useState("");
  const [result, setResult] = useState<GenericResult | null>(null);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState<SimJob | null>(null);
  const [name, setName] = useState("");

  const loadTemplates = () => projectId ? api.simTemplates(projectId).then(setTemplates).catch((e) => setError(e.message)) : Promise.resolve();
  useEffect(() => { void loadTemplates(); }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!active || (active.status !== "queued" && active.status !== "running")) return;
    const id = window.setInterval(async () => {
      const j = await api.simJob(active.id);
      if (j.status === "done" || j.status === "failed") {
        setActive(j); onJobsChanged();
        if (j.status === "done") setResult(await api.genericResult(j.id)); else setError(j.error);
      }
    }, 600);
    return () => window.clearInterval(id);
  }, [active?.id, active?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const load = (tpl: CustomTemplate, id: number | null) => {
    setT({ ...EMPTY, ...tpl });
    setSel(id);
    setInputs(Object.fromEntries((tpl.inputs ?? []).map((i) => [i.key, i.default ?? 0])));
    setRawText(JSON.stringify(tpl, null, 2));
    setResult(null); setError(""); setInfo("");
  };
  const fromExample = () => api.customExample().then((ex) => load(ex, null)).catch((e) => setError(e.message));
  const applyRaw = () => { try { load(JSON.parse(rawText) as CustomTemplate, sel); setRaw(false); } catch (e) { setError(`JSON xatosi: ${e instanceof Error ? e.message : ""}`); } };

  async function preview() {
    setBusy(true); setError("");
    try { setResult(await api.customPreview(t, inputs)); setInfo("Sinov natijasi (saqlanmagan)"); }
    catch (e) { setError(e instanceof Error ? e.message : "Xatolik"); } finally { setBusy(false); }
  }
  async function save() {
    if (!projectId) return;
    setBusy(true); setError("");
    try {
      const body = { name: t.name || "Nomsiz shablon", description: t.description ?? "", template: t };
      const saved = sel ? await api.updateTemplate(sel, body) : await api.createTemplate(projectId, body);
      setSel(saved.id); await loadTemplates(); setInfo("Shablon saqlandi");
    } catch (e) { setError(e instanceof Error ? e.message : "Xatolik"); } finally { setBusy(false); }
  }
  async function run() {
    setBusy(true); setError("");
    try {
      const params = sel ? { template_id: sel, inputs } : { template: t, inputs };
      const job = await api.createSim(modelId, { name: name || t.name || "", version_id: current?.id ?? null, kind: "custom", params });
      setActive(job); onJobsChanged(); setInfo("Hisob navbatga qo'yildi");
    } catch (e) { setError(e instanceof Error ? e.message : "Xatolik"); } finally { setBusy(false); }
  }
  async function remove() {
    if (!sel || !confirm("Shablon o'chirilsinmi?")) return;
    try { await api.deleteTemplate(sel); setSel(null); await loadTemplates(); } catch (e) { setError(e instanceof Error ? e.message : "Xatolik"); }
  }

  // --- muharrir yordamchilari ---
  const setRows = <K extends "inputs" | "step" | "checks">(k: K, rows: CustomTemplate[K]) => setT((p) => ({ ...p, [k]: rows }));
  const setMap = (k: "init" | "summary", key: string, val: string, oldKey?: string) => setT((p) => {
    const m: Record<string, string> = {};
    for (const [kk, vv] of Object.entries(p[k])) { if (kk === oldKey) m[key] = val; else m[kk] = vv; }
    if (oldKey === undefined) m[key] = val;
    return { ...p, [k]: m };
  });
  const delMap = (k: "init" | "summary", key: string) => setT((p) => { const m = { ...p[k] }; delete m[key]; return { ...p, [k]: m }; });

  const myJobs = jobs.filter((j) => j.kind === "custom");
  const xs = result?.series.t ?? [];

  return (
    <div className="sim">
      <div className="row" style={{ marginBottom: 8, alignItems: "center" }}>
        <button className="btn sm" onClick={onBack}><Icon name="arrow-left" size={13} /> Katalog</button>
        <Icon name="code" size={16} /><b className="grow">Maxsus simulyatsiya (formulalar)</b>
      </div>
      <p className="dim small" style={{ marginTop: 0 }}>Kirishlar → boshlang'ich holat → har qadamda tenglamalar (tartib bilan) → chiqishlar (vaqt qatori) → xulosa va tekshiruvlar.
        Ifodalar: + − × / ** , taqqoslash, <span className="mono">a if shart else b</span>, funksiyalar <span className="mono">abs min max sqrt exp log sin cos clip interp mean sum last</span>; o'zgaruvchilar <span className="mono">t dt i g rho pi</span>.</p>
      {error && <p className="error small">{error}</p>}
      {info && <p className="muted small"><Icon name="info" size={12} /> {info}</p>}

      <div className="row wrap" style={{ marginBottom: 8 }}>
        <select className="select" value={sel ?? ""} onChange={(e) => { const id = Number(e.target.value); const tp = templates.find((x) => x.id === id); if (tp) load(tp.template, tp.id); }}>
          <option value="">Saqlangan shablon…</option>
          {templates.map((tp) => <option key={tp.id} value={tp.id}>{tp.name} — {tp.author_username}</option>)}
        </select>
        <button className="btn sm" onClick={fromExample}><Icon name="file-text" size={12} /> Namuna (ombor balansi)</button>
        <button className="btn sm" onClick={() => load(EMPTY, null)}><Icon name="plus" size={12} /> Bo'sh</button>
        <button className="btn sm" onClick={() => { setRawText(JSON.stringify(t, null, 2)); setRaw(!raw); }} title="JSON ko'rinishida tahrirlash"><Icon name="code" size={12} /> JSON</button>
      </div>

      {raw ? (
        <div>
          <textarea className="textarea mono" style={{ minHeight: 260 }} value={rawText} onChange={(e) => setRawText(e.target.value)} />
          <div className="row"><button className="btn sm primary" onClick={applyRaw}>Qo'llash</button><button className="btn sm" onClick={() => setRaw(false)}>Bekor</button></div>
        </div>
      ) : (
        <>
          <div className="row">
            <label className="field grow"><span>Nomi</span><input className="input" value={t.name ?? ""} onChange={(e) => setT({ ...t, name: e.target.value })} /></label>
            <label className="field" style={{ width: 90 }}><span>Qadamlar</span><input className="input" type="number" value={t.steps} onChange={(e) => setT({ ...t, steps: Number(e.target.value) })} /></label>
            <label className="field" style={{ width: 90 }}><span>dt</span><input className="input" type="number" step="any" value={t.dt} onChange={(e) => setT({ ...t, dt: Number(e.target.value) })} /></label>
          </div>
          <label className="field"><span>Tavsif</span><input className="input" value={t.description ?? ""} onChange={(e) => setT({ ...t, description: e.target.value })} /></label>

          <h3 className="row">Kirishlar <span className="grow" /><button className="btn sm" type="button" onClick={() => setRows("inputs", [...t.inputs, { key: `x${t.inputs.length + 1}`, label: "", unit: "", default: 0 }])}><Icon name="plus" size={12} /></button></h3>
          <table className="grid small"><thead><tr><th>kalit</th><th>sarlavha</th><th>birlik</th><th>default</th><th>min</th><th>max</th><th /></tr></thead>
            <tbody>{t.inputs.map((inp, i) => (
              <tr key={i}>
                <td><input className="input mono" value={inp.key} onChange={(e) => setRows("inputs", t.inputs.map((x, k) => (k === i ? { ...x, key: e.target.value } : x)))} /></td>
                <td><input className="input" value={inp.label ?? ""} onChange={(e) => setRows("inputs", t.inputs.map((x, k) => (k === i ? { ...x, label: e.target.value } : x)))} /></td>
                <td><input className="input" style={{ width: 60 }} value={inp.unit ?? ""} onChange={(e) => setRows("inputs", t.inputs.map((x, k) => (k === i ? { ...x, unit: e.target.value } : x)))} /></td>
                <td><input className="input" type="number" step="any" style={{ width: 80 }} value={inp.default ?? ""} onChange={(e) => setRows("inputs", t.inputs.map((x, k) => (k === i ? { ...x, default: Number(e.target.value) } : x)))} /></td>
                <td><input className="input" type="number" step="any" style={{ width: 70 }} value={inp.min ?? ""} onChange={(e) => setRows("inputs", t.inputs.map((x, k) => (k === i ? { ...x, min: e.target.value === "" ? undefined : Number(e.target.value) } : x)))} /></td>
                <td><input className="input" type="number" step="any" style={{ width: 70 }} value={inp.max ?? ""} onChange={(e) => setRows("inputs", t.inputs.map((x, k) => (k === i ? { ...x, max: e.target.value === "" ? undefined : Number(e.target.value) } : x)))} /></td>
                <td><button className="btn sm" type="button" onClick={() => setRows("inputs", t.inputs.filter((_, k) => k !== i))} aria-label="O'chirish"><Icon name="x" size={12} /></button></td>
              </tr>))}</tbody></table>

          <h3 className="row">Boshlang'ich holat <span className="grow" /><button className="btn sm" type="button" onClick={() => setMap("init", `v${Object.keys(t.init).length + 1}`, "0")}><Icon name="plus" size={12} /></button></h3>
          {Object.entries(t.init).map(([k, v]) => <ExprRow key={k} k={k} v={v} onChange={(nk, nv) => setMap("init", nk, nv, k)} onDel={() => delMap("init", k)} />)}

          <h3 className="row">Har qadamda (tartib bilan) <span className="grow" /><button className="btn sm" type="button" onClick={() => setRows("step", [...t.step, { target: "", expr: "" }])}><Icon name="plus" size={12} /></button></h3>
          {t.step.map((s, i) => <ExprRow key={i} k={s.target} v={s.expr} onChange={(nk, nv) => setRows("step", t.step.map((x, j) => (j === i ? { target: nk, expr: nv } : x)))} onDel={() => setRows("step", t.step.filter((_, j) => j !== i))} />)}

          <label className="field"><span>Chiqishlar (vaqt qatori, vergul bilan)</span><input className="input mono" value={t.outputs.join(", ")} onChange={(e) => setT({ ...t, outputs: e.target.value.split(/[\s,]+/).filter(Boolean) })} /></label>

          <h3 className="row">Xulosa <span className="grow" /><button className="btn sm" type="button" onClick={() => setMap("summary", `s${Object.keys(t.summary).length + 1}`, "max(series.x)")}><Icon name="plus" size={12} /></button></h3>
          {Object.entries(t.summary).map(([k, v]) => <ExprRow key={k} k={k} v={v} onChange={(nk, nv) => setMap("summary", nk, nv, k)} onDel={() => delMap("summary", k)} />)}

          <h3 className="row">Tekshiruvlar (shart rost — ogohlantirish) <span className="grow" /><button className="btn sm" type="button" onClick={() => setRows("checks", [...t.checks, { expr: "", message: "" }])}><Icon name="plus" size={12} /></button></h3>
          {t.checks.map((c, i) => <ExprRow key={i} k={c.message} v={c.expr} kLabel="xabar" vLabel="shart" onChange={(nk, nv) => setRows("checks", t.checks.map((x, j) => (j === i ? { message: nk, expr: nv } : x)))} onDel={() => setRows("checks", t.checks.filter((_, j) => j !== i))} />)}
        </>
      )}

      {t.inputs.length > 0 && (
        <>
          <h3>Kirish qiymatlari</h3>
          <div className="row wrap">
            {t.inputs.map((inp) => (
              <label key={inp.key} className="field" style={{ width: 150 }}><span>{inp.label || inp.key}{inp.unit && <em className="unit">{inp.unit}</em>}</span>
                <input className="input" type="number" step="any" value={String(inputs[inp.key] ?? inp.default ?? 0)} onChange={(e) => setInputs({ ...inputs, [inp.key]: Number(e.target.value) })} /></label>
            ))}
          </div>
        </>
      )}

      <div className="row wrap" style={{ margin: "8px 0" }}>
        <button className="btn sm" onClick={preview} disabled={busy}><Icon name="play" size={12} /> Sinov</button>
        {canEdit && <button className="btn sm" onClick={save} disabled={busy}><Icon name="save" size={12} /> {sel ? "Shablonni yangilash" : "Shablonni saqlash"}</button>}
        {canEdit && sel && <button className="btn sm" onClick={remove}><Icon name="trash" size={12} /></button>}
        <span className="grow" />
        <input className="input" style={{ width: 160 }} placeholder="Hisob nomi" value={name} onChange={(e) => setName(e.target.value)} />
        <button className="btn sm primary" onClick={run} disabled={busy}>Hisoblash (saqlanadi)</button>
      </div>

      {result && (
        <div>
          <div className={`verdict ${result.summary.ok === false ? "bad" : "ok"}`}><Icon name={result.summary.ok === false ? "alert-triangle" : "check-circle"} size={16} /> <span>{String(result.summary.verdict ?? "")}</span></div>
          <div className="tiles">{Object.entries(result.summary).filter(([k]) => k !== "verdict" && k !== "ok").map(([k, v]) => <div key={k} className="tile"><div className="tile-v">{typeof v === "number" ? v.toLocaleString("uz-UZ", { maximumFractionDigits: 3 }) : String(v)}</div><div className="tile-t">{k}</div></div>)}</div>
          {Object.keys(result.series).filter((k) => k !== "t").map((k, n) => <LineChart key={k} title={k} unit="" x={xs} series={[{ name: k, values: result.series[k] as number[], color: CHART_COLORS[n % CHART_COLORS.length] }]} />)}
        </div>
      )}

      {myJobs.length > 0 && (
        <details className="section-box" style={{ marginTop: 8 }}>
          <summary>Oldingi hisoblar ({myJobs.length})</summary>
          {myJobs.map((j) => (
            <div key={j.id} className="list-item" onClick={async () => { if (j.status !== "done") return; const full = await api.simJob(j.id); if (full.params?.template) load(full.params.template as CustomTemplate, (full.params.template_id as number) ?? null); setInputs((full.params?.inputs as GenericParams) ?? {}); setResult(await api.genericResult(j.id)); }}>
              <div className="title"><b>#{j.id}</b><span className="grow">{j.name}</span><span className={`badge ${j.status === "done" ? "published" : j.status === "failed" ? "rejected" : "shared"}`}>{j.status === "done" ? "Tayyor" : j.status === "failed" ? "Xato" : "Hisoblanmoqda"}</span></div>
              <div className="meta">{j.author_username} · {fmtDate(j.created_at)}{j.error && <span className="error"> · {j.error}</span>}</div>
            </div>
          ))}
        </details>
      )}
    </div>
  );
}

function ExprRow({ k, v, kLabel = "o'zgaruvchi", vLabel = "ifoda", onChange, onDel }: { k: string; v: string; kLabel?: string; vLabel?: string; onChange: (k: string, v: string) => void; onDel: () => void }) {
  return (
    <div className="row" style={{ marginBottom: 4 }}>
      <input className="input mono" style={{ width: 130 }} placeholder={kLabel} value={k} onChange={(e) => onChange(e.target.value, v)} />
      <span className="dim">=</span>
      <input className="input mono grow" placeholder={vLabel} value={v} onChange={(e) => onChange(k, e.target.value)} />
      <button className="btn sm" type="button" onClick={onDel} aria-label="O'chirish"><Icon name="x" size={12} /></button>
    </div>
  );
}
