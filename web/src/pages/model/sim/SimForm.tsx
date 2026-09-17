import { useMemo, useState } from "react";
import type { GenericParams, SimField } from "../../../api/client";
import Icon from "../../../ui/Icon";

/** Sxema bo'yicha avtomatik forma (server: ges_sim.schema.Field). Guruhlar bo'limlarga, "advanced" — yig'iladigan.
    `sources` — qaysi maydon qayerdan to'ldirilgani (pasport / model / jonli) — yonida belgi. */
export const SOURCE_LABEL: Record<string, string> = { site: "pasport", model: "model", live: "jonli" };

interface Props {
  fields: SimField[];
  values: GenericParams;
  onChange: (key: string, v: unknown) => void;
  sources?: Record<string, string>;
  compact?: boolean;
}

export function fieldDefaults(fields: SimField[]): GenericParams {
  const out: GenericParams = {};
  for (const f of fields) out[f.key] = f.default;
  return out;
}

export default function SimForm({ fields, values, onChange, sources = {}, compact }: Props) {
  const [showAdv, setShowAdv] = useState(false);
  const groups = useMemo(() => {
    const g: { name: string; fields: SimField[] }[] = [];
    for (const f of fields) {
      let grp = g.find((x) => x.name === f.group);
      if (!grp) { grp = { name: f.group, fields: [] }; g.push(grp); }
      grp.fields.push(f);
    }
    return g;
  }, [fields]);
  const hasAdv = fields.some((f) => f.advanced);
  return (
    <div className="simform">
      {groups.map((g) => {
        const vis = g.fields.filter((f) => showAdv || !f.advanced);
        if (!vis.length) return null;
        return (
          <div key={g.name || "_"} className="simform-group">
            {g.name && <h3>{g.name}</h3>}
            <div className="row wrap">
              {vis.map((f) => <FieldInput key={f.key} f={f} v={values[f.key]} set={(v) => onChange(f.key, v)} source={sources[f.key]} compact={compact} />)}
            </div>
          </div>
        );
      })}
      {hasAdv && <button type="button" className="btn sm" onClick={() => setShowAdv(!showAdv)}><Icon name={showAdv ? "chevron-up" : "chevron-down"} size={12} /> {showAdv ? "Qo'shimcha parametrlarni yashirish" : "Qo'shimcha parametrlar"}</button>}
    </div>
  );
}

function FieldInput({ f, v, set, source, compact }: { f: SimField; v: unknown; set: (v: unknown) => void; source?: string; compact?: boolean }) {
  const tag = source ? <span className={`src src-${source}`} title={`${SOURCE_LABEL[source] ?? source}dan to'ldirilgan`}>{SOURCE_LABEL[source] ?? source}</span> : null;
  const label = <span>{f.label}{f.unit && <em className="unit">{f.unit}</em>}{tag}</span>;
  const width = compact ? 150 : f.type === "series" || f.type === "text" ? "100%" : 170;
  if (f.type === "bool") {
    return <label className="row small field-check" style={{ width }}><input type="checkbox" checked={!!v} onChange={(e) => set(e.target.checked)} /> {f.label}{tag}</label>;
  }
  if (f.type === "select") {
    return (
      <label className="field" style={{ width }} title={f.hint}>
        {label}
        <select className="select" value={String(v ?? f.default ?? "")} onChange={(e) => set(e.target.value)}>
          {f.options.map(([val, title]) => <option key={val} value={val}>{title}</option>)}
        </select>
      </label>
    );
  }
  if (f.type === "series") {
    return <label className="field" style={{ width }} title={f.hint}>{label}<SeriesInput v={v} set={set} /></label>;
  }
  if (f.type === "text") {
    return <label className="field" style={{ width }} title={f.hint}>{label}<input className="input" value={String(v ?? "")} onChange={(e) => set(e.target.value)} /></label>;
  }
  return (
    <label className="field" style={{ width }} title={f.hint}>
      {label}
      <input className="input" type="number" step="any" min={f.min ?? undefined} max={f.max ?? undefined} value={v === undefined || v === null ? "" : String(v)}
        onChange={(e) => set(e.target.value === "" ? "" : Number(e.target.value))} />
      {f.hint && !compact && <small className="dim">{f.hint}</small>}
    </label>
  );
}

/** Raqamlar ro'yxati: yozish paytida matn saqlanadi, fokus ketganda (yoki Enter) massivga aylanadi. */
function SeriesInput({ v, set }: { v: unknown; set: (v: unknown) => void }) {
  const fromValue = Array.isArray(v) ? (v as unknown[]).join(" ") : String(v ?? "");
  const [text, setText] = useState(fromValue);
  const [last, setLast] = useState(fromValue);
  if (fromValue !== last) { setLast(fromValue); setText(fromValue); }
  const commit = () => set(text.split(/[\s,;]+/).filter(Boolean).map(Number).filter((n) => Number.isFinite(n)));
  return <input className="input mono" value={text} placeholder="qiymatlar bo'shliq bilan" onChange={(e) => setText(e.target.value)} onBlur={commit} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); commit(); } }} />;
}
