import { useState } from "react";
import { api, type Underlay } from "../../api/client";
import type { Draft, DraftManager, GizmoMode } from "../../viewer/drafts";
import { DRAFT_KINDS, DRAFT_KIND_BY_ID, type DraftKind } from "../../viewer/draftKinds";
import Icon from "../../ui/Icon";

/* Qoralama obyektlar (Blender "Add" bilan yaratilgan): tanlangan obyekt xususiyatlari (nom, o'lchamlar,
   joylashuv, Pset_GES_*), ro'yxat, IFC ga commit. */

const num = (v: string, d = 0) => (v === "" || Number.isNaN(Number(v)) ? d : Number(v));

export function DraftProps({ draft, dm, canEdit, onDelete, onDuplicate }: { draft: Draft; dm: DraftManager; canEdit: boolean; onDelete: (uid: string) => void; onDuplicate: (uid: string) => void }) {
  const kind = DRAFT_KIND_BY_ID[draft.kind];
  const t = draft.transform;
  const mode = dm.mode;
  const setT = (patch: Partial<typeof t>) => dm.update(draft.uid, { transform: patch });
  const pset = kind.pset ? draft.psets[kind.pset.name] ?? {} : {};
  const setPset = (k: string, v: unknown) => kind.pset && dm.update(draft.uid, { psets: { ...draft.psets, [kind.pset.name]: { ...pset, [k]: v } } });
  // Mavjud element Pset lari (erkin tahrir): mesh turi uchun barcha to'plamlar ko'rsatiladi
  const setFreePset = (ps: string, k: string, v: unknown) => dm.update(draft.uid, { psets: { ...draft.psets, [ps]: { ...(draft.psets[ps] ?? {}), [k]: v } } });
  if (draft.kind === "deleted") {
    return (
      <div className="draft-props">
        <div className="row" style={{ alignItems: "center", marginBottom: 6 }}><Icon name="trash" size={16} /><b className="grow">O'chirishga belgilangan</b></div>
        <div><b>{draft.name}</b> <span className="dim small">{draft.ifcClass}</span></div>
        <p className="dim small">«IFC ga qo'shish» bilan yangi versiyada olib tashlanadi. Bekor qilish — asl element qayta ko'rinadi.</p>
        {canEdit && <button className="btn sm" onClick={() => onDelete(draft.uid)}><Icon name="rotate" size={12} /> Bekor qilish (qaytarish)</button>}
      </div>
    );
  }
  return (
    <div className="draft-props">
      <div className="row" style={{ alignItems: "center", marginBottom: 6 }}>
        <Icon name={kind.icon} size={16} /><b className="grow">{draft.kind === "mesh" ? `${kind.title} · ${draft.ifcClass ?? ""}` : kind.title}</b>
        <span className="dim small">{draft.id ? `#${draft.id}` : "saqlanmagan"}</span>
      </div>
      {draft.sourceGuid && <div className="small dim" style={{ marginBottom: 6 }}>Asl element: <span className="mono">{draft.sourceGuid}</span> — commitda shu GUID bilan almashtiriladi. {canEdit && <button className="btn sm" title="Tahrirni bekor qilish — asl element qayta ko'rinadi" onClick={() => onDelete(draft.uid)}>Bekor qilish</button>}</div>}
      <label className="field"><span>Nomi</span><input className="input" value={draft.name} disabled={!canEdit} onChange={(e) => dm.update(draft.uid, { name: e.target.value })} /></label>
      <div className="row" style={{ marginBottom: 6 }}>
        <GizmoBtn m="translate" cur={mode} icon="move" title="Surish (G)" onClick={() => dm.setMode("translate")} />
        <GizmoBtn m="rotate" cur={mode} icon="rotate" title="Burish (R)" onClick={() => dm.setMode("rotate")} />
        <GizmoBtn m="scale" cur={mode} icon="scale" title="Masshtab (S)" onClick={() => dm.setMode("scale")} />
        <span className="grow" />
        <button className="btn sm" title="Kamerani moslash" onClick={() => dm.fit(draft.uid)}><Icon name="maximize" size={12} /></button>
        {canEdit && <button className="btn sm" title="Yerga o'tqazish — obyekt tubi relyef/inshoot yuzasiga (balandlik xaritasi bo'yicha, Blender shrinkwrap kabi)" onClick={() => { if (!dm.snapToGround(draft.uid)) alert("Balandlik xaritasi hali yuklanmagan"); }}><Icon name="arrow-down" size={12} /> Yerga</button>}
        {canEdit && <button className="btn sm" title="Nusxa (Shift+D)" onClick={() => onDuplicate(draft.uid)}><Icon name="copy" size={12} /></button>}
        {canEdit && <button className="btn sm" title="Massiv — n ta nusxa qadam bilan (masalan 4 agregat 20 m oralig'ida)" onClick={() => { const a = prompt("Massiv: soni, qadam (m), o'q (x/y)", "4, 20, x"); if (!a) return; const [n, st, ax] = a.split(/[,\s]+/); const cnt = Number(n), step = Number(st); if (!(cnt >= 2) || !Number.isFinite(step)) { alert("Masalan: 4, 20, x"); return; } dm.arrayCopies(draft.uid, cnt, step, (ax ?? "x").toLowerCase() === "y" ? "y" : "x"); }}><Icon name="grid" size={12} /> Massiv</button>}
        {canEdit && <button className="btn sm" title="O'chirish (X)" onClick={() => onDelete(draft.uid)}><Icon name="trash" size={12} /></button>}
      </div>
      {kind.params.length > 0 && <h3>O'lchamlar</h3>}
      <div className="row wrap">
        {kind.params.map((p) => p.options ? (
          <label key={p.key} className="field" style={{ width: 130 }}><span>{p.label}</span>
            <select className="select" value={String(draft.params[p.key] ?? p.default)} disabled={!canEdit} onChange={(e) => dm.update(draft.uid, { params: { [p.key]: e.target.value } })}>{p.options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
        ) : (
          <label key={p.key} className="field" style={{ width: 130 }}><span>{p.label}{p.unit && <em className="unit">{p.unit}</em>}</span>
            <input className="input" type="number" step={p.step ?? "any"} min={p.min} value={String(draft.params[p.key] ?? p.default)} disabled={!canEdit} onChange={(e) => dm.update(draft.uid, { params: { [p.key]: num(e.target.value, Number(p.default)) } })} /></label>
        ))}
      </div>
      <h3>Joylashuv (IFC, m)</h3>
      <div className="row wrap">
        {(["x", "y", "z"] as const).map((k) => <label key={k} className="field" style={{ width: 90 }}><span>{k.toUpperCase()}</span><input className="input" type="number" step="any" value={t[k]} disabled={!canEdit} onChange={(e) => setT({ [k]: num(e.target.value) })} /></label>)}
        <label className="field" style={{ width: 90 }}><span>Burilish Z°</span><input className="input" type="number" step="any" value={t.rz} disabled={!canEdit} onChange={(e) => setT({ rz: num(e.target.value) })} /></label>
        {(["sx", "sy", "sz"] as const).map((k) => <label key={k} className="field" style={{ width: 90 }}><span>Masshtab {k.slice(1).toUpperCase()}</span><input className="input" type="number" step="0.1" value={t[k]} disabled={!canEdit} onChange={(e) => setT({ [k]: num(e.target.value, 1) || 1 })} /></label>)}
      </div>
      {kind.pset && (
        <>
          <h3>{kind.pset.name}</h3>
          <div className="row wrap">
            {kind.pset.fields.map((f) => (
              <label key={f.key} className="field" style={{ width: f.type === "select" ? 200 : 130 }}><span>{f.label}{f.unit && <em className="unit">{f.unit}</em>}{f.from && <em className="unit" title="O'lchamlardan hisoblanadi">auto</em>}</span>
                {f.type === "select" && f.options ? (
                  <select className="select" value={String(pset[f.key] ?? f.default ?? "")} disabled={!canEdit} onChange={(e) => setPset(f.key, e.target.value)}>{f.options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
                ) : (
                  <input className="input" type={f.type === "text" ? "text" : "number"} step="any" value={String(pset[f.key] ?? f.default ?? "")} disabled={!canEdit || !!f.from} onChange={(e) => setPset(f.key, f.type === "text" ? e.target.value : num(e.target.value))} />
                )}</label>
            ))}
          </div>
        </>
      )}
      {draft.kind === "mesh" && Object.keys(draft.psets).length > 0 && (
        <>
          <h3>Xususiyatlar (Pset)</h3>
          {Object.entries(draft.psets).map(([ps, props]) => (
            <details key={ps} open><summary>{ps}</summary>
              <div className="row wrap">
                {Object.entries(props).map(([k, v]) => (
                  <label key={k} className="field" style={{ width: 150 }}><span>{k}</span>
                    <input className="input" type={typeof v === "number" ? "number" : "text"} step="any" value={String(v ?? "")} disabled={!canEdit} onChange={(e) => setFreePset(ps, k, typeof v === "number" ? num(e.target.value) : e.target.value)} /></label>
                ))}
              </div>
            </details>
          ))}
        </>
      )}
      <p className="dim small">IFC klassi: {draft.ifcClass || kind.ifcClass}. Qoralama modelga «IFC ga qo'shish» (Versiyalar / Qoralamalar) bilan yangi versiya sifatida kiradi.</p>
    </div>
  );
}

function GizmoBtn({ m, cur, icon, title, onClick }: { m: GizmoMode; cur: GizmoMode | null; icon: string; title: string; onClick: () => void }) {
  return <button className={`btn sm${cur === m ? " active" : ""}`} title={title} onClick={onClick}><Icon name={icon} size={12} /></button>;
}

/** Qoralamalar ro'yxati (Outliner bo'limi) + commit. */
export function DraftList({ drafts, selected, dm, canEdit, onCommit, onDelete, busy }: { drafts: Draft[]; selected: Draft | null; dm: DraftManager; canEdit: boolean; onCommit: () => void; onDelete: (uid: string) => void; busy: boolean }) {
  if (drafts.length === 0) return null;
  return (
    <div className="draft-list">
      <div className="row small" style={{ padding: "2px 6px", alignItems: "center" }}>
        <b className="muted">Qoralama ({drafts.length})</b><span className="grow" />
        {canEdit && drafts.some((d) => d.kind !== "deleted") && <button className="btn sm" title="Barcha qoralamalarni yerga o'tqazish (relyef/DEM almashganda)" onClick={() => { const n = dm.snapAllToGround(); if (!n) alert("Balandlik xaritasi hali yuklanmagan"); }}><Icon name="arrow-down" size={12} /></button>}
        {canEdit && <button className="btn sm primary" disabled={busy} title="Barcha qoralamalarni IFC ga qo'shib yangi versiya yaratish (commit)" onClick={onCommit}><Icon name="git-branch" size={12} /> IFC ga qo'shish</button>}
      </div>
      {drafts.map((d) => {
        const kind = DRAFT_KIND_BY_ID[d.kind];
        return (
          <div key={d.uid} className={`node${selected?.uid === d.uid || dm.multiSelected.includes(d.uid) ? " selected" : ""}`} style={{ paddingLeft: 10, opacity: d.kind === "deleted" ? 0.7 : 1 }} onClick={(e) => (e.shiftKey && selected && selected.uid !== d.uid ? dm.toggleMulti(d.uid) : dm.select(d.uid))} onDoubleClick={() => dm.fit(d.uid)} title="Shift+bosish — guruhga (birga surish/burish)">
            <Icon name={kind.icon} size={12} /> <span className="name" style={d.kind === "deleted" ? { textDecoration: "line-through" } : undefined}>{d.name}</span><span className="cat dim">{d.kind === "deleted" ? "o'chiriladi" : d.kind === "mesh" ? "tahrir" : kind.title.split(" (")[0]}</span>
            <span className="grow" />
            {d.kind !== "deleted" && <button className="eye" title={d.visible ? "Yashirish" : "Ko'rsatish"} onClick={(e) => { e.stopPropagation(); dm.update(d.uid, { visible: !d.visible }); }}><Icon name={d.visible ? "eye" : "eye-off"} size={13} /></button>}
            {canEdit && <button className="eye" title={d.sourceGuid ? "Bekor qilish (asl element qaytadi)" : "O'chirish"} onClick={(e) => { e.stopPropagation(); onDelete(d.uid); }}><Icon name={d.sourceGuid ? "rotate" : "x"} size={12} /></button>}
          </div>
        );
      })}
    </div>
  );
}

/** Rasm asoslari (foto / skanerlangan chizma / sun'iy yo'ldosh surati) — 3D da tekislik, ustidan chizish uchun.
   AutoCAD «Attach image» kabi: rasm, kengligi metrda, joylashuv, burish, shaffoflik; vertikal — fasad/kesim. */
export function UnderlayPanel({ modelId, list, canEdit, onChange, centerIfc }: { modelId: number; list: Underlay[]; canEdit: boolean; onChange: (list: Underlay[]) => void; centerIfc: () => [number, number, number] | null }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  async function add(file: File) {
    setBusy(true); setErr("");
    try {
      const c = centerIfc() ?? [0, 0, 0];
      const u = await api.createUnderlay(modelId, file, { name: file.name.replace(/\.[^.]+$/, ""), width_m: 100, x: c[0], y: c[1], z: c[2] });
      onChange([...list, u]); setOpen(u.id);
    } catch (e) { setErr(e instanceof Error ? e.message : "Xatolik"); } finally { setBusy(false); }
  }
  async function patch(u: Underlay, body: Parameters<typeof api.updateUnderlay>[1]) {
    const nu = { ...u, ...body, height_m: body.width_m ? u.height_m * (body.width_m / u.width_m) : u.height_m };
    onChange(list.map((x) => (x.id === u.id ? nu : x)));
    try { const saved = await api.updateUnderlay(u.id, body); onChange(list.map((x) => (x.id === u.id ? saved : x))); } catch (e) { setErr(e instanceof Error ? e.message : "Xatolik"); }
  }
  async function remove(u: Underlay) {
    if (!confirm(`«${u.name}» rasm asosini o'chirish?`)) return;
    try { await api.deleteUnderlay(u.id); onChange(list.filter((x) => x.id !== u.id)); } catch (e) { setErr(e instanceof Error ? e.message : "Xatolik"); }
  }
  const N = ({ u, k, step = 1, label }: { u: Underlay; k: "x" | "y" | "z" | "width_m" | "rotation_deg"; step?: number; label: string }) => (
    <label className="field" style={{ width: 86 }}><span>{label}</span><input className="input" type="number" step={step} value={u[k]} disabled={!canEdit} onChange={(e) => void patch(u, { [k]: Number(e.target.value) || 0 })} /></label>
  );
  return (
    <div className="draft-list underlay-list">
      <div className="row small" style={{ padding: "2px 6px", alignItems: "center" }}>
        <b className="muted">Rasm asosi ({list.length})</b><span className="grow" />
        {canEdit && <label className="btn sm" title="Foto, skanerlangan chizma yoki sun'iy yo'ldosh suratini 3D ga tekislik sifatida qo'yish — ustidan Shift+A bilan chiziladi"><Icon name="image" size={12} /> {busy ? "…" : "Rasm qo'shish"}<input type="file" accept="image/*" hidden disabled={busy} onChange={(e) => { const f = e.target.files?.[0]; if (f) void add(f); e.target.value = ""; }} /></label>}
      </div>
      {err && <div className="error small" style={{ padding: "0 6px" }}>{err}</div>}
      {list.map((u) => (
        <div key={u.id}>
          <div className={`node${open === u.id ? " selected" : ""}`} style={{ paddingLeft: 10 }} onClick={() => setOpen(open === u.id ? null : u.id)}>
            <Icon name="image" size={12} /> <span className="name">{u.name}</span><span className="cat dim">{u.width_m} m{u.vertical ? " · vertikal" : ""}</span>
            <span className="grow" />
            <button className="eye" title={u.visible ? "Yashirish" : "Ko'rsatish"} onClick={(e) => { e.stopPropagation(); void patch(u, { visible: !u.visible }); }}><Icon name={u.visible ? "eye" : "eye-off"} size={13} /></button>
            {canEdit && <button className="eye" title="O'chirish" onClick={(e) => { e.stopPropagation(); void remove(u); }}><Icon name="x" size={12} /></button>}
          </div>
          {open === u.id && (
            <div className="small" style={{ padding: "4px 10px 6px" }}>
              <div className="row wrap">
                <N u={u} k="width_m" step={1} label="Kengligi, m" />
                <N u={u} k="x" label="X, m" /><N u={u} k="y" label="Y, m" /><N u={u} k="z" step={0.1} label="Z, m" />
                <N u={u} k="rotation_deg" label="Burish, °" />
                <label className="field" style={{ width: 86 }}><span>Shaffoflik</span><input type="range" min={0.05} max={1} step={0.05} value={u.opacity} disabled={!canEdit} onChange={(e) => void patch(u, { opacity: Number(e.target.value) })} /></label>
              </div>
              <div className="row small" style={{ gap: 8 }}>
                <label className="row small field-check"><input type="checkbox" checked={u.vertical} disabled={!canEdit} onChange={(e) => void patch(u, { vertical: e.target.checked })} /> vertikal (fasad/kesim)</label>
                {canEdit && <button className="btn sm" title="Model markaziga" onClick={() => { const c = centerIfc(); if (c) void patch(u, { x: c[0], y: c[1], z: c[2] }); }}><Icon name="crosshair" size={11} /> markazga</button>}
              </div>
              <div className="dim">Rasm kengligini haqiqiy o'lchamga (masalan to'g'on uzunligi) moslang, so'ng ustidan Shift+A bilan elementlar qo'ying — rasmdan raqamli egizak.</div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/** Blender Shift+A: qo'shish menyusi (kursor yonida). */
export function AddMenu({ x, y, onPick, onClose }: { x: number; y: number; onPick: (k: DraftKind) => void; onClose: () => void }) {
  const [q, setQ] = useState("");
  const groups = ["Primitivlar", "GES inshootlari"] as const;
  const filt = (k: DraftKind) => !q || k.title.toLowerCase().includes(q.toLowerCase());
  return (
    <div className="add-menu" style={{ left: Math.min(x, window.innerWidth - 280), top: Math.min(y, window.innerHeight - 420) }} onMouseLeave={onClose}>
      <input className="input" autoFocus placeholder="Qidirish…" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Escape") onClose(); if (e.key === "Enter") { const first = DRAFT_KINDS.find(filt); if (first) onPick(first); } }} />
      {groups.map((g) => (
        <div key={g}>
          <div className="add-group">{g}</div>
          {DRAFT_KINDS.filter((k) => k.group === g && filt(k)).map((k) => <button key={k.id} className="menu-item" onClick={() => onPick(k)}><Icon name={k.icon} size={14} /> <span>{k.title}</span></button>)}
        </div>
      ))}
    </div>
  );
}
