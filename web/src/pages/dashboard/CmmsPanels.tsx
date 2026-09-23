import { useCallback, useEffect, useState } from "react";
import { api, type AssetHistory, type CmmsCodes, type LaborEntry, type MaintenancePlan, type Member, type SparePart, type WorkOrder, type WorkOrderPart } from "../../api/client";
import Dialog from "../../ui/Dialog";
import Icon from "../../ui/Icon";
import { dialogs } from "../../ui/dialogs";
import { fmtDate } from "../../ui/format";
import { notify } from "../../ui/notice";

/* H2 — CMMS chuqurligi: profilaktik xizmat rejalari, ish buyrug'i tafsiloti (vazifalar, mehnat,
   ehtiyot qism bandlash/sarflash, ruxsatnoma va LOTO), aktiv bo'yicha xizmat tarixi. */

/** Profilaktik xizmat rejalari: davriylik (kun yoki ish soati), vazifalar, avtomatik ish buyrug'i. */
export function PlansPanel({ projectId, assets, canEdit }: { projectId: number; assets: { id: number; name: string }[]; canEdit: boolean }) {
  const [items, setItems] = useState<MaintenancePlan[]>([]);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", asset_id: "", tasks: "", interval_days: "180", interval_hours: "", priority: "medium", lead_days: "7", permit_required: false, last_service: "" });
  const load = useCallback(() => api.maintenancePlans(projectId).then(setItems).catch((e) => setErr(e.message)), [projectId]);
  useEffect(() => { void load(); }, [load]);
  const due = items.filter((p) => p.due_reason).length;
  return (
    <div className="dash-block">
      <div className="row items-center">
        <b>Profilaktik xizmat rejalari</b>
        <span className="muted small">davriylik: kun yoki ish soati (agregat hisoblagichi) — muddati kelganda ish buyrug'i avtomatik yaratiladi</span>
        {due > 0 && <span className="badge high" data-testid="plans-due">{due} ta muddati keldi</span>}
        <span className="grow" />
        {canEdit && <button className="btn sm" data-testid="plans-run" onClick={() => api.runPlans(projectId).then((w) => { setMsg(w.length ? `${w.length} ta ish buyrug'i yaratildi` : "Muddati kelgan reja yo'q"); notify(w.length ? `${w.length} ta ish buyrug'i yaratildi` : "Muddati kelgan reja yo'q", w.length ? "success" : "info"); void load(); }).catch((e) => setErr(e.message))}>Hozir tekshirish</button>}
        {canEdit && <button className="btn sm primary" data-testid="plan-add" onClick={() => setAdding(true)}>+ Reja</button>}
      </div>
      {err && <p className="error small">{err}</p>}
      {msg && <p className="small muted" data-testid="plans-msg">{msg}</p>}
      {items.length === 0 ? <p className="muted">Rejalar yo'q — davriy ko'rik/moylash rejasini qo'shing.</p> : (
        <table className="grid small" data-testid="plans-table">
          <thead><tr><th>Reja</th><th>Aktiv</th><th>Davriylik</th><th>Oxirgi buyruq</th><th>Holat</th><th /></tr></thead>
          <tbody>{items.map((p) => (
            <tr key={p.id} className={p.due_reason ? "row-attention" : undefined}>
              <td><b>{p.name}</b>{p.description && <div className="dim">{p.description}</div>}{p.tasks.length > 0 && <div className="dim">{p.tasks.length} vazifa: {p.tasks.slice(0, 3).join("; ")}{p.tasks.length > 3 ? "…" : ""}</div>}</td>
              <td className="dim">{p.asset_name ?? "—"}</td>
              <td className="mono">{p.interval_days ? `${p.interval_days} kun` : ""}{p.interval_days && p.interval_hours ? " / " : ""}{p.interval_hours ? `${p.interval_hours} soat` : ""}</td>
              <td className="dim">{p.last_generated_at ? fmtDate(p.last_generated_at) : "—"}</td>
              <td>{p.due_reason ? <span className="badge high" title={p.due_reason}>muddati keldi</span> : <span className={`badge ${p.active ? "published" : "archived"}`}>{p.active ? "faol" : "o'chirilgan"}</span>}{p.permit_required && <span className="badge shared" title="Ruxsatnoma talab qilinadi">PTW</span>}</td>
              <td className="row gap-4">
                {canEdit && <button className="btn sm" title={p.active ? "O'chirish (faolsizlantirish)" : "Faollashtirish"} onClick={() => api.updatePlan(p.id, { active: !p.active }).then(load).catch((e) => setErr(e.message))}><Icon name={p.active ? "pause" : "play"} size={12} /></button>}
                {canEdit && <button className="btn sm" title="Rejani o'chirish" onClick={() => void dialogs.confirm("Reja o'chirilsinmi?", { text: p.name, danger: true, ok: "O'chirish" }).then((ok) => { if (ok) api.deletePlan(p.id).then(load).catch((e) => setErr(e.message)); })}><Icon name="trash" size={12} /></button>}
              </td>
            </tr>
          ))}</tbody>
        </table>
      )}
      {adding && (
        <Dialog title="Yangi profilaktik reja" onClose={() => setAdding(false)}>
          <label className="field"><span>Nomi</span><input className="input" value={form.name} data-autofocus data-testid="plan-name" onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label className="field"><span>Tavsif</span><textarea className="textarea" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
          <label className="field"><span>Vazifalar (har qatorda bittadan)</span><textarea className="textarea" value={form.tasks} onChange={(e) => setForm({ ...form, tasks: e.target.value })} /></label>
          <div className="row">
            <label className="field grow"><span>Aktiv</span><select className="select" value={form.asset_id} data-testid="plan-asset" onChange={(e) => setForm({ ...form, asset_id: e.target.value })}><option value="">—</option>{assets.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
            <label className="field grow"><span>Davriylik, kun</span><input className="input" type="number" min="1" value={form.interval_days} data-testid="plan-days" onChange={(e) => setForm({ ...form, interval_days: e.target.value })} /></label>
            <label className="field grow"><span>yoki ish soati</span><input className="input" type="number" min="1" value={form.interval_hours} onChange={(e) => setForm({ ...form, interval_hours: e.target.value })} /></label>
          </div>
          <div className="row">
            <label className="field grow"><span>Ustuvorlik</span><select className="select" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>{["low", "medium", "high", "critical"].map((x) => <option key={x}>{x}</option>)}</select></label>
            <label className="field grow"><span>Muddat, kun</span><input className="input" type="number" min="0" value={form.lead_days} onChange={(e) => setForm({ ...form, lead_days: e.target.value })} /></label>
            <label className="field grow"><span>Ruxsatnoma (PTW)</span><input type="checkbox" checked={form.permit_required} onChange={(e) => setForm({ ...form, permit_required: e.target.checked })} /></label>
          </div>
          <label className="field"><span>Oxirgi bajarilgan xizmat sanasi (mavjud uskunani ro'yxatga olishda)</span><input className="input" type="date" value={form.last_service} data-testid="plan-last" onChange={(e) => setForm({ ...form, last_service: e.target.value })} /></label>
          <div className="actions">
            <button className="btn" onClick={() => setAdding(false)}>Bekor</button>
            <button className="btn primary" data-testid="plan-save" disabled={!form.name} onClick={() => api.createPlan(projectId, {
              name: form.name,
              description: form.description,
              asset_id: form.asset_id ? Number(form.asset_id) : null,
              tasks: form.tasks.split("\n").map((t) => t.trim()).filter(Boolean),
              interval_days: form.interval_days ? Number(form.interval_days) : null,
              interval_hours: form.interval_hours ? Number(form.interval_hours) : null,
              priority: form.priority,
              lead_days: Number(form.lead_days) || 0,
              permit_required: form.permit_required,
              last_generated_at: form.last_service ? new Date(form.last_service).toISOString() : null,
            }).then(() => { setAdding(false); void load(); }).catch((e) => setErr(e.message))}>Saqlash</button>
          </div>
        </Dialog>
      )}
    </div>
  );
}

/** Ish buyrug'i tafsiloti: vazifalar ro'yxati, mehnat yozuvi, ehtiyot qism bandlash/sarflash,
    ruxsatnoma (PTW) va LOTO (izolyatsiya — boshqaruv buyruqlarini taqiqlaydi). */
export function WorkOrderDetail({ wo, parts, members, canApprove, onClose, onChange }: { wo: WorkOrder; parts: SparePart[]; members: Member[]; canApprove: boolean; onClose: () => void; onChange: (w: WorkOrder) => void }) {
  const [labor, setLabor] = useState<LaborEntry[]>([]);
  const [lines, setLines] = useState<WorkOrderPart[]>([]);
  const [err, setErr] = useState("");
  const [lf, setLf] = useState({ hours: "1", note: "", user_id: "" });
  const [pf, setPf] = useState({ part_id: "", qty: "1" });
  const open = wo.status === "open" || wo.status === "in_progress";
  const load = useCallback(() => Promise.all([api.workOrderLabor(wo.id), api.workOrderParts(wo.id)]).then(([l, p]) => { setLabor(l); setLines(p); }).catch((e) => setErr(e.message)), [wo.id]);
  useEffect(() => { void load(); }, [load]);
  const toggleTask = (i: number) => {
    const tasks = wo.tasks.map((t, k) => (k === i ? { ...t, done: !t.done } : t));
    api.updateWorkOrder(wo.id, { tasks }).then(onChange).catch((e) => setErr(e.message));
  };
  return (
    <Dialog title={`#${wo.id} ${wo.title}`} onClose={onClose}>
      {err && <p className="error small">{err}</p>}
      <div className="tiles cols-4">
        <div className="tile"><div className="tile-v">{wo.labor_hours}<span className="tile-u"> soat</span></div><div className="tile-t">mehnat · {wo.labor_cost}</div></div>
        <div className="tile"><div className="tile-v">{wo.parts_cost}</div><div className="tile-t">ehtiyot qism</div></div>
        <div className="tile"><div className="tile-v">{wo.extra_cost}</div><div className="tile-t">qo'shimcha</div></div>
        <div className="tile"><div className="tile-v">{wo.cost}</div><div className="tile-t">jami xarajat</div></div>
      </div>

      <h4>Ruxsatnoma va izolyatsiya</h4>
      <div className="row gap-6 items-center flex-wrap">
        <span className={`badge ${wo.permit_status === "issued" ? "published" : wo.permit_status === "requested" ? "high" : "archived"}`}>PTW: {wo.permit_status}</span>
        {open && wo.permit_status === "none" && <button className="btn sm" onClick={() => api.setPermit(wo.id, { status: "requested", note: wo.title }).then(onChange).catch((e) => setErr(e.message))}>Ruxsatnoma so'rash</button>}
        {open && canApprove && wo.permit_status === "requested" && <button className="btn sm primary" onClick={() => api.setPermit(wo.id, { status: "issued" }).then(onChange).catch((e) => setErr(e.message))}>Ruxsatnoma berish</button>}
        <span className={`badge ${wo.loto_active ? "rejected" : "archived"}`} data-testid="loto-badge">LOTO: {wo.loto_active ? "faol" : "yo'q"}</span>
        {open && !wo.loto_active && <button className="btn sm" data-testid="loto-on" onClick={() => void dialogs.prompt("Izolyatsiya nuqtalari (vergul bilan)", "", { text: "LOTO qo'yilganda shu aktivga boshqaruv buyruqlari taqiqlanadi" }).then((v) => { if (v == null) return; api.setLoto(wo.id, { active: true, points: v.split(",").map((s) => s.trim()).filter(Boolean).map((label) => ({ label })) }).then(onChange).catch((e) => setErr(e.message)); })}>LOTO qo'yish</button>}
        {open && wo.loto_active && <button className="btn sm primary" data-testid="loto-off" onClick={() => api.setLoto(wo.id, { active: false }).then(onChange).catch((e) => setErr(e.message))}>LOTO ni olib tashlash</button>}
      </div>
      {wo.loto_points.length > 0 && <p className="small dim">Nuqtalar: {wo.loto_points.map((p) => p.label ?? `sensor #${p.sensor_id}`).join(", ")}</p>}

      {wo.tasks.length > 0 && (
        <>
          <h4>Vazifalar</h4>
          <ul className="plain small" data-testid="wo-tasks">{wo.tasks.map((t, i) => (
            <li key={i}><label><input type="checkbox" checked={t.done} disabled={!open} onChange={() => toggleTask(i)} /> {t.title}</label></li>
          ))}</ul>
        </>
      )}

      <h4>Mehnat</h4>
      {labor.length > 0 && (
        <table className="grid small"><thead><tr><th>Sana</th><th>Xodim</th><th>Soat</th><th>Izoh</th><th /></tr></thead>
          <tbody>{labor.map((e) => (
            <tr key={e.id}><td className="dim">{fmtDate(e.work_date)}</td><td>{e.username}</td><td className="mono">{e.hours}</td><td className="dim">{e.note}</td>
              <td>{open && <button className="btn sm" title="O'chirish" onClick={() => api.deleteLabor(wo.id, e.id).then((w) => { onChange(w); void load(); }).catch((er) => setErr(er.message))}><Icon name="trash" size={12} /></button>}</td></tr>
          ))}</tbody></table>
      )}
      {open && (
        <div className="row gap-6">
          <label className="field"><span>Soat</span><input className="input" type="number" step="any" min="0" value={lf.hours} data-testid="labor-hours" onChange={(e) => setLf({ ...lf, hours: e.target.value })} /></label>
          <label className="field grow"><span>Izoh</span><input className="input" value={lf.note} onChange={(e) => setLf({ ...lf, note: e.target.value })} /></label>
          <label className="field"><span>Xodim</span><select className="select" value={lf.user_id} onChange={(e) => setLf({ ...lf, user_id: e.target.value })}><option value="">o'zim</option>{members.map((m) => <option key={m.user_id} value={m.user_id}>{m.username}</option>)}</select></label>
          <button className="btn sm primary" data-testid="labor-add" onClick={() => api.addLabor(wo.id, { hours: Number(lf.hours) || 0, note: lf.note, user_id: lf.user_id ? Number(lf.user_id) : null }).then((w) => { onChange(w); setLf({ ...lf, note: "" }); void load(); }).catch((e) => setErr(e.message))}>Qo'shish</button>
        </div>
      )}

      <h4>Ehtiyot qismlar</h4>
      {lines.length > 0 && (
        <table className="grid small" data-testid="wo-parts"><thead><tr><th>Qism</th><th>Band</th><th>Sarflandi</th><th>Ombor</th><th>Bo'sh</th></tr></thead>
          <tbody>{lines.map((l) => <tr key={l.part_id}><td>{l.part_name}</td><td className="mono">{l.reserved} {l.unit}</td><td className="mono">{l.consumed}</td><td className="mono dim">{l.stock}</td><td className="mono dim">{l.free}</td></tr>)}</tbody></table>
      )}
      {open && (
        <div className="row gap-6">
          <label className="field grow"><span>Qism</span><select className="select" value={pf.part_id} data-testid="wo-part-select" onChange={(e) => setPf({ ...pf, part_id: e.target.value })}><option value="">—</option>{parts.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.qty} {p.unit})</option>)}</select></label>
          <label className="field"><span>Miqdor</span><input className="input" type="number" step="any" min="0" value={pf.qty} data-testid="wo-part-qty" onChange={(e) => setPf({ ...pf, qty: e.target.value })} /></label>
          <button className="btn sm" data-testid="wo-part-reserve" disabled={!pf.part_id} onClick={() => api.reserveWorkOrderPart(wo.id, { part_id: Number(pf.part_id), qty: Number(pf.qty) || 0 }).then(setLines).catch((e) => setErr(e.message))}>Bandlash</button>
          <button className="btn sm primary" data-testid="wo-part-consume" disabled={!pf.part_id} onClick={() => api.consumeWorkOrderPart(wo.id, { part_id: Number(pf.part_id), qty: Number(pf.qty) || 0 }).then((l) => { setLines(l); api.workOrders(wo.project_id).then((ws) => { const w = ws.find((x) => x.id === wo.id); if (w) onChange(w); }).catch(() => undefined); }).catch((e) => setErr(e.message))}>Sarflash</button>
        </div>
      )}
      <div className="actions"><button className="btn" onClick={onClose}>Yopish</button></div>
    </Dialog>
  );
}

/** Aktiv bo'yicha xizmat tarixi va xarajat (ISO 14224 nosozlik kodlari taqsimoti bilan). */
export function AssetHistoryDialog({ assetId, onClose }: { assetId: number; onClose: () => void }) {
  const [hist, setHist] = useState<AssetHistory | null>(null);
  const [codes, setCodes] = useState<CmmsCodes | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { Promise.all([api.assetHistory(assetId), api.cmmsCodes()]).then(([h, c]) => { setHist(h); setCodes(c); }).catch((e) => setErr(e.message)); }, [assetId]);
  return (
    <Dialog title={hist ? `Xizmat tarixi: ${hist.asset.name}${hist.asset.kks_code ? ` (${hist.asset.kks_code})` : ""}` : "Xizmat tarixi"} onClose={onClose}>
      {err && <p className="error small">{err}</p>}
      {hist && (
        <>
          <div className="tiles cols-5">
            <div className="tile"><div className="tile-v">{hist.totals.work_orders}</div><div className="tile-t">ish buyrug'i</div></div>
            <div className="tile"><div className="tile-v">{hist.totals.failures}</div><div className="tile-t">nosozlik (kodlangan)</div></div>
            <div className="tile"><div className="tile-v">{hist.totals.labor_hours}<span className="tile-u"> soat</span></div><div className="tile-t">mehnat</div></div>
            <div className="tile"><div className="tile-v">{hist.totals.downtime_hours}<span className="tile-u"> soat</span></div><div className="tile-t">to'xtab turish</div></div>
            <div className="tile"><div className="tile-v">{hist.totals.cost}</div><div className="tile-t">jami xarajat</div></div>
          </div>
          {hist.failure_modes.length > 0 && <p className="small">Nosozlik rejimlari (ISO 14224): {hist.failure_modes.map((m) => `${m.code} ${m.label} — ${m.count}`).join("; ")}</p>}
          {hist.by_year.length > 0 && (
            <table className="grid small"><thead><tr><th>Yil</th><th>Buyruqlar</th><th>Mehnat, soat</th><th>To'xtash, soat</th><th>Xarajat</th></tr></thead>
              <tbody>{hist.by_year.map((y) => <tr key={y.year}><td>{y.year}</td><td className="mono">{y.work_orders}</td><td className="mono">{y.labor_hours}</td><td className="mono">{y.downtime_hours}</td><td className="mono">{y.cost}</td></tr>)}</tbody></table>
          )}
          <h4>Ish buyruqlari</h4>
          {hist.work_orders.length === 0 ? <p className="muted">Yozuv yo'q.</p> : (
            <table className="grid small" data-testid="asset-history"><thead><tr><th>#</th><th>Ish</th><th>Nosozlik (ISO 14224)</th><th>Mehnat</th><th>Qismlar</th><th>Xarajat</th></tr></thead>
              <tbody>{hist.work_orders.map((w) => (
                <tr key={w.id}>
                  <td className="dim">{w.id}</td>
                  <td><b>{w.title}</b><div className="dim">{fmtDate(w.created_at)} · {w.status}{w.plan_id ? " · reja" : ""}</div>{w.resolution && <div className="ok-text">✓ {w.resolution}</div>}</td>
                  <td className="small">{w.failure_mode ? <>{w.failure_mode_label}{w.failure_cause && codes ? <div className="dim">{codes.failure_causes[w.failure_cause] ?? w.failure_cause}</div> : null}{w.detection_method && codes ? <div className="dim">{codes.detection_methods[w.detection_method] ?? w.detection_method}</div> : null}</> : <span className="dim">—</span>}</td>
                  <td className="mono">{w.labor_hours} soat</td>
                  <td className="small dim">{w.parts.map((p) => `${p.part} ×${p.qty}`).join(", ") || "—"}</td>
                  <td className="mono">{w.cost}</td>
                </tr>
              ))}</tbody></table>
          )}
        </>
      )}
      <div className="actions"><button className="btn" onClick={onClose}>Yopish</button></div>
    </Dialog>
  );
}
