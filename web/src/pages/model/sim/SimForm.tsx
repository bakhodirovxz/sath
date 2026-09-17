import { useMemo, useState } from "react";
import type { GenericParams, SimField } from "../../../api/client";
import Icon from "../../../ui/Icon";
import { BPanel } from "../../../ui/BlenderUI";

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
      {groups.map((g, gi) => {
        const vis = g.fields.filter((f) => showAdv || !f.advanced);
        if (!vis.length) return null;
        const body = vis.map((f) => <FieldInput key={f.key} f={f} v={values[f.key]} set={(v) => onChange(f.key, v)} source={sources[f.key]} compact={compact} />);
        // Blender: har guruh — yopiladigan panel; nomsiz guruh — panelsiz
        return g.name ? <BPanel key={g.name} id={`simform:${g.name}`} title={g.name} count={vis.length} defaultOpen={gi < 4}>{body}</BPanel> : <div key="_">{body}</div>;
      })}
      {hasAdv && <button type="button" className="btn sm" onClick={() => setShowAdv(!showAdv)}><Icon name={showAdv ? "chevron-up" : "chevron-down"} size={12} /> {showAdv ? "Qo'shimcha parametrlarni yashirish" : "Qo'shimcha parametrlar"}</button>}
    </div>
  );
}

/** Bitta maydon — Blender qatori: chapda label (birlik, manba belgisi), o'ngda maydon. */
function FieldInput({ f, v, set, source }: { f: SimField; v: unknown; set: (v: unknown) => void; source?: string; compact?: boolean }) {
  const tag = source ? <span className={`src src-${source}`} title={`${SOURCE_LABEL[source] ?? source}dan to'ldirilgan`}>{SOURCE_LABEL[source] ?? source}</span> : null;
  const label = <span className="blabel" title={f.hint || f.label}>{f.label}{f.unit && <em className="unit">{f.unit}</em>}{tag}</span>;
  let input: React.ReactNode;
  if (f.type === "bool") input = <input type="checkbox" checked={!!v} onChange={(e) => set(e.target.checked)} />;
  else if (f.type === "select") {
    input = (
      <select className="select" value={String(v ?? f.default ?? "")} onChange={(e) => set(e.target.value)}>
        {f.options.map(([val, title]) => <option key={val} value={val}>{title}</option>)}
      </select>
    );
  } else if (f.type === "series") input = <SeriesInput v={v} set={set} />;
  else if (f.type === "text") input = <input className="input" value={String(v ?? "")} onChange={(e) => set(e.target.value)} />;
  else {
    input = (
      <input className="input" type="number" step="any" min={f.min ?? undefined} max={f.max ?? undefined} value={v === undefined || v === null ? "" : String(v)}
        onChange={(e) => set(e.target.value === "" ? "" : Number(e.target.value))} title={f.hint} />
    );
  }
  return <label className="brow">{label}<span className="bfield">{input}</span></label>;
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
