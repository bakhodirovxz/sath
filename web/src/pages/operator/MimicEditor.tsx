import { useState } from "react";
import type { Sensor } from "../../api/client";
import { MAX_UNITS, defaultScheme, setUnits, validateScheme, type ElementType, type Scheme, type SchemeElement } from "./scheme";

/** Mimika muharriri yon paneli (F3): agregatlar soni, tanlangan element (nom, sensor bog'lash, qo'shimcha
 * bog'lanishlar, o'chirish), yangi element qo'shish, standartga qaytarish. Surish — Mimic ichida. */
const ADDABLE: { type: ElementType; label: string }[] = [
  { type: "value", label: "Qiymat katakchasi" },
  { type: "breaker", label: "Uzgich" },
  { type: "gate", label: "Zatvor" },
  { type: "valve", label: "Ventil" },
  { type: "transformer", label: "Transformator" },
  { type: "bus", label: "Shina" },
];
const EXTRA: Partial<Record<ElementType, { key: string; label: string }[]>> = {
  unit: [{ key: "run", label: "RUN holati (0/1)" }, { key: "cb", label: "Generator uzgichi" }],
};

export default function MimicEditor({ scheme, sensors, selected, onSelect, onChange }: { scheme: Scheme; sensors: Sensor[]; selected: string | null; onSelect: (id: string | null) => void; onChange: (s: Scheme) => void }) {
  const [newType, setNewType] = useState<ElementType>("value");
  const el = scheme.elements.find((e) => e.id === selected) ?? null;
  const errs = validateScheme(scheme);
  const upd = (patch: Partial<SchemeElement>) => el && onChange({ ...scheme, elements: scheme.elements.map((e) => (e.id === el.id ? { ...e, ...patch } : e)) });
  const add = () => {
    const id = `${newType}_${Date.now().toString(36)}`;
    onChange({ ...scheme, elements: [...scheme.elements, { id, type: newType, x: 500, y: 60, label: ADDABLE.find((a) => a.type === newType)?.label ?? newType }] });
    onSelect(id);
  };
  const remove = () => el && !["hall"].includes(el.id) && el.type !== "unit" && (onChange({ ...scheme, elements: scheme.elements.filter((e) => e.id !== el.id) }), onSelect(null));
  const opt = (v: number | null | undefined, onPick: (id: number | null) => void, filter?: (s: Sensor) => boolean) => (
    <select className="select" value={v ?? ""} onChange={(e) => onPick(e.target.value ? Number(e.target.value) : null)}>
      <option value="">— bog'lanmagan —</option>
      {sensors.filter(filter ?? (() => true)).map((s) => <option key={s.id} value={s.id}>{s.key} — {s.name} ({s.unit || s.kind})</option>)}
    </select>
  );
  return (
    <div className="mimic-editor panel" data-testid="mimic-editor">
      <div className="row"><b>Sxema muharriri</b><span className="grow" /><button className="btn sm" title="Standart sxemaga qaytarish (bog'lanishlar saqlanmaydi)" onClick={() => onChange(defaultScheme(scheme.units))}>Standart</button></div>
      <label className="field"><span>Agregatlar soni (1–{MAX_UNITS})</span><input className="input" type="number" min={1} max={MAX_UNITS} value={scheme.units} onChange={(e) => onChange(setUnits(scheme, Number(e.target.value) || 1))} /></label>
      <div className="row"><select className="select" value={newType} onChange={(e) => setNewType(e.target.value as ElementType)}>{ADDABLE.map((a) => <option key={a.type} value={a.type}>{a.label}</option>)}</select><button className="btn sm" onClick={add}>+ Qo'shish</button></div>
      <p className="dim small">Elementni sxemada surish mumkin; bosib tanlang.</p>
      {el ? (
        <div className="mimic-el-props">
          <div className="row"><b>{el.id}</b><span className="dim">{el.type}</span><span className="grow" />{el.type !== "unit" && el.id !== "hall" && <button className="btn sm danger" onClick={remove}>O'chirish</button>}</div>
          <label className="field"><span>Nom</span><input className="input" value={el.label ?? ""} onChange={(e) => upd({ label: e.target.value })} /></label>
          <div className="row"><label className="field grow"><span>x</span><input className="input" type="number" value={el.x} onChange={(e) => upd({ x: Number(e.target.value) })} /></label><label className="field grow"><span>y</span><input className="input" type="number" value={el.y} onChange={(e) => upd({ y: Number(e.target.value) })} /></label></div>
          {["value", "unit", "breaker", "gate", "valve", "transformer"].includes(el.type) && (
            <label className="field"><span>{el.type === "unit" ? "Quvvat sensori" : el.type === "gate" ? "Ochilish sensori (%)" : el.type === "breaker" || el.type === "valve" ? "Holat sensori (0/1)" : "Sensor"}</span>{opt(el.sensor_id, (id) => upd({ sensor_id: id }))}</label>
          )}
          {(EXTRA[el.type] ?? []).map((x) => (
            <label key={x.key} className="field"><span>{x.label}</span>{opt(el.extra?.[x.key], (id) => upd({ extra: { ...(el.extra ?? {}), [x.key]: id } }))}</label>
          ))}
        </div>
      ) : <p className="muted small">Element tanlanmagan</p>}
      {errs.length > 0 && <p className="error small">{errs.join("; ")}</p>}
    </div>
  );
}
