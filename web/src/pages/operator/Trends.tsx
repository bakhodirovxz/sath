import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { api, type PenGroup } from "../../api/client";
import Dialog from "../../ui/Dialog";
import Trend from "../../ui/Trend";
import type { TrendSeries } from "../../ui/trendMath";
import OperatorShell, { opsPath, useOps } from "./OperatorShell";

/** Trend server sahifasi (F7): qalamlar (sensorlar) tanlash, saqlanadigan qalam guruhlari (nom bilan, serverda),
 * davr, ko'p o'qli / normallashtirilgan rejim; ma'lumot serverdan siyraklashtirilgan (D4: limit), klientda qayta
 * hisoblanmaydi; 30 s da yangilanadi. */
export default function Trends() {
  const { projectId } = useParams();
  const pid = Number(projectId);
  return (
    <OperatorShell level={2} crumbs={[{ label: "L1 Umumiy", to: opsPath(pid) }, { label: "Trendlar" }]}>
      <Body />
    </OperatorShell>
  );
}

const PERIODS = [{ label: "1 soat", h: 1 }, { label: "6 soat", h: 6 }, { label: "24 soat", h: 24 }, { label: "3 kun", h: 72 }, { label: "7 kun", h: 168 }, { label: "30 kun", h: 720 }];

function Body() {
  const { projectId: pid, sensors, dash, project, reload } = useOps();
  const [pens, setPens] = useState<number[]>([]);
  const [hours, setHours] = useState(24);
  const [mode, setMode] = useState<"multi" | "normalized">("multi");
  const [data, setData] = useState<Record<number, TrendSeries>>({});
  const [err, setErr] = useState("");
  const [saveDlg, setSaveDlg] = useState(false);
  const [name, setName] = useState("");
  const groups = useMemo<PenGroup[]>(() => dash?.pen_groups ?? [], [dash?.pen_groups]);
  const canEdit = ["engineer", "approver"].includes(project?.my_role ?? "");
  useEffect(() => {
    if (pens.length || !sensors.length) return;
    const g = groups[0];
    setPens(g ? g.sensor_ids.filter((id) => sensors.some((s) => s.id === id)) : sensors.filter((s) => s.kind === "power" || s.kind === "level").slice(0, 3).map((s) => s.id));
  }, [sensors, groups, pens.length]);
  const load = useCallback(async () => {
    const out: Record<number, TrendSeries> = {};
    await Promise.all(pens.map(async (id) => {
      const s = sensors.find((x) => x.id === id);
      if (!s) return;
      try {
        const r = await api.readings(id, hours, 2000);
        out[id] = { id, name: s.name, unit: s.unit, points: r.points.map((p) => ({ t: Date.parse(p.ts), v: p.v, min: p.min, max: p.max })) };
      } catch (e) { setErr(e instanceof Error ? e.message : "Xato"); }
    }));
    setData(out);
  }, [pens, hours, sensors]);
  useEffect(() => { void load(); const t = setInterval(load, 30_000); return () => clearInterval(t); }, [load]);
  const series = useMemo(() => pens.map((id) => data[id]).filter((s): s is TrendSeries => !!s), [pens, data]);
  const toggle = (id: number) => setPens((p) => (p.includes(id) ? p.filter((x) => x !== id) : p.length >= 6 ? p : [...p, id]));
  const saveGroup = async () => {
    const next = [...groups.filter((g) => g.name !== name.trim()), { name: name.trim(), sensor_ids: pens }];
    try { await api.saveDashboard(pid, { mimic: dash?.mimic ?? {}, tiles: dash?.tiles ?? [], pen_groups: next }); setSaveDlg(false); setName(""); await reload(); } catch (e) { setErr(e instanceof Error ? e.message : "Xato"); }
  };
  const removeGroup = async (g: PenGroup) => {
    try { await api.saveDashboard(pid, { mimic: dash?.mimic ?? {}, tiles: dash?.tiles ?? [], pen_groups: groups.filter((x) => x.name !== g.name) }); await reload(); } catch (e) { setErr(e instanceof Error ? e.message : "Xato"); }
  };
  return (
    <div className="trends-page">
      <div className="row wrap panel" style={{ gap: 6, marginBottom: 8 }}>
        {PERIODS.map((p) => <button key={p.h} className={`btn sm ${hours === p.h ? "active" : ""}`} onClick={() => setHours(p.h)}>{p.label}</button>)}
        <span className="sep" />
        <button className={`btn sm ${mode === "multi" ? "active" : ""}`} onClick={() => setMode("multi")} title="Har birlik uchun alohida Y o'qi">Ko'p o'qli</button>
        <button className={`btn sm ${mode === "normalized" ? "active" : ""}`} onClick={() => setMode("normalized")} title="Har seriya 0…100 % (o'z diapazonida)">Normallashtirilgan</button>
        <span className="sep" />
        <span className="dim small">Guruhlar:</span>
        {groups.map((g) => <span key={g.name} className="row" style={{ gap: 2 }}><button className="btn sm" onClick={() => setPens(g.sensor_ids.filter((id) => sensors.some((s) => s.id === id)))} data-testid="pen-group">{g.name}</button>{canEdit && <button className="btn sm danger" title="Guruhni o'chirish" onClick={() => removeGroup(g)}>×</button>}</span>)}
        {canEdit && pens.length > 0 && <button className="btn sm" onClick={() => setSaveDlg(true)}>+ Guruhni saqlash</button>}
        <span className="grow" />
        <span className="dim small">{series.reduce((a, s) => a + s.points.length, 0)} nuqta (serverdan siyraklashtirilgan)</span>
      </div>
      {err && <p className="error">{err}</p>}
      <div className="panel">
        {series.length ? <Trend series={series} height={340} mode={mode} /> : <p className="muted">Qalam tanlang (≤ 6)</p>}
      </div>
      <div className="panel" style={{ marginTop: 8 }}>
        <div className="row"><b>Qalamlar</b><span className="dim small">{pens.length}/6</span></div>
        <div className="vgrid">
          {sensors.filter((s) => s.enabled).map((s) => (
            <label key={s.id} className={`vcard compact ${pens.includes(s.id) ? "alarm" : ""}`} style={{ cursor: "pointer" }}>
              <input type="checkbox" checked={pens.includes(s.id)} onChange={() => toggle(s.id)} disabled={!pens.includes(s.id) && pens.length >= 6} /> {s.name} <span className="dim mono">{s.key} {s.unit}</span>
            </label>
          ))}
        </div>
      </div>
      {saveDlg && (
        <Dialog title="Qalam guruhini saqlash" onClose={() => setSaveDlg(false)}>
          <label className="field"><span>Nom</span><input className="input" value={name} onChange={(e) => setName(e.target.value)} autoFocus /></label>
          <p className="small dim">{pens.map((id) => sensors.find((s) => s.id === id)?.name).join(", ")}</p>
          <div className="actions"><button className="btn" onClick={() => setSaveDlg(false)}>Bekor</button><button className="btn primary" disabled={name.trim().length < 2} onClick={saveGroup}>Saqlash</button></div>
        </Dialog>
      )}
    </div>
  );
}
