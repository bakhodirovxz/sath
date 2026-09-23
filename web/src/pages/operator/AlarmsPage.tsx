import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { api, type AlarmEvent } from "../../api/client";
import Dialog from "../../ui/Dialog";
import { alarmStyle } from "../../ui/tokens";
import AlarmTable from "./AlarmTable";
import OperatorShell, { opsPath, useOps } from "./OperatorShell";
import { AREAS, type AreaId } from "./model";
import { EMPTY_FILTER, FLOOD_PRIORITIES, counters, filterAlarms, groupAlarms, sortAlarms, toRows, type AlarmFilter, type ViewMode } from "./alarms";
import { priorityLabel } from "../../i18n/labels";
import { areaTitle } from "./model";
import { can } from "../../api/permissions";

/** Alarm sahifasi (F5, ISA-18.2): saralash ustuvorlik → vaqt, filtr (ustuvorlik, uchastka, holat), guruhlash,
 * qidiruv; kvitlash Dialog bilan; «Hammasini kvitlash» — tasdiqlash, faqat filtrlangan to'plam; toshqin rejimida
 * ustuvorlik filtri taklifi (C4); shelving/OOS (C2); ratsionalizatsiya (C3) qator ochilganda.
 * Faol hisoblagichlar tarix ko'rinishidan mustaqil (OperatorShell faol hodisalari). */
const VIEW_LABEL: Record<ViewMode, string> = { active: "Faol", unack: "Kvitlanmagan", acked: "Kvitlangan", suppressed: "Shelved/OOS", history: "Tarix" };

export default function AlarmsPage() {
  const { projectId } = useParams();
  const pid = Number(projectId);
  return (
    <OperatorShell level={2} crumbs={[{ label: "L1 Umumiy", to: opsPath(pid) }, { label: "Alarmlar" }]}>
      <Body />
    </OperatorShell>
  );
}

function Body() {
  const { projectId: pid, sensors, events, dash, project, reload } = useOps();
  const [filter, setFilter] = useState<AlarmFilter>(EMPTY_FILTER);
  const [group, setGroup] = useState<"none" | "sensor" | "area">("none");
  const [history, setHistory] = useState<AlarmEvent[]>([]);
  const [hours, setHours] = useState(24 * 7);
  const [ackAll, setAckAll] = useState(false);
  const [comment, setComment] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const canOperate = can(project?.my_role, "scada.ack");
  const canEngineer = can(project?.my_role, "sensor.oos");
  const flood = !!dash?.alarm_flood;
  const loadHistory = useCallback(() => api.alarmEvents(pid, false, hours).then(setHistory).catch((e) => setErr(e instanceof Error ? e.message : "Xato")), [pid, hours]);
  useEffect(() => { if (filter.view === "history" || filter.view === "suppressed") void loadHistory(); }, [filter.view, loadHistory]);
  // Bostirilganlar (shelved/OOS) tarixdan (include_suppressed) — alohida so'rov
  const [suppressed, setSuppressed] = useState<AlarmEvent[]>([]);
  useEffect(() => {
    if (filter.view !== "suppressed") return;
    api.alarmEvents(pid, true, 168, undefined, true).then((rows) => setSuppressed(rows.filter((r) => r.suppressed))).catch(() => setSuppressed([]));
  }, [filter.view, pid, events]);
  const source = filter.view === "history" ? history : filter.view === "suppressed" ? suppressed : events;
  const rows = useMemo(() => sortAlarms(filterAlarms(toRows(source, sensors), filter)), [source, sensors, filter]);
  const groups = useMemo(() => groupAlarms(rows, group), [rows, group]);
  const c = counters(events);
  const unackedFiltered = rows.filter((r) => !r.acked_at);
  const togglePrio = (p: string) => setFilter((f) => { const s = new Set(f.priorities); if (s.has(p)) s.delete(p); else s.add(p); return { ...f, priorities: s }; });
  const onChanged = () => { void reload(); if (filter.view === "history") void loadHistory(); };
  return (
    <div className="alarms-page">
      {flood && (
        <div className="verdict warn" data-testid="flood-banner">
          Alarm toshqini (EEMUA-191: 10 daqiqada 10 dan ko'p). Tavsiya — ustuvorlik bo'yicha filtr.
          <button className="btn sm ml-8" onClick={() => setFilter((f) => ({ ...f, priorities: new Set(FLOOD_PRIORITIES) }))}>Faqat kritik/yuqori</button>
        </div>
      )}
      <div className="dash-kpi l1-kpi cols-4">
        <div className={`tile ${c.active ? "tile-alarm" : ""}`} data-testid="cnt-active"><div className="tile-t">Faol</div><div className="tile-v">{c.active}</div></div>
        <div className={`tile ${c.unacked ? "tile-alarm" : ""}`} data-testid="cnt-unacked"><div className="tile-t">Kvitlanmagan</div><div className="tile-v">{c.unacked}</div></div>
        <div className={`tile ${c.critical ? "tile-alarm" : ""}`}><div className="tile-t">Kritik</div><div className="tile-v">{c.critical}</div></div>
        <div className="tile"><div className="tile-t">Ko'rinishda</div><div className="tile-v">{rows.length} <span className="tile-u">{VIEW_LABEL[filter.view]}</span></div></div>
      </div>
      <div className="row wrap panel gap-6 my-8 mx-0">
        {(["active", "unack", "acked", "suppressed", "history"] as ViewMode[]).map((v) => <button key={v} className={`btn sm ${filter.view === v ? "active" : ""}`} onClick={() => setFilter((f) => ({ ...f, view: v }))}>{VIEW_LABEL[v]}</button>)}
        {filter.view === "history" && <select className="select w-110" value={hours} onChange={(e) => setHours(Number(e.target.value))}>{[24, 72, 168, 720].map((h) => <option key={h} value={h}>{h / 24} kun</option>)}</select>}
        <span className="sep" />
        {(["critical", "high", "medium", "low"] as const).map((p) => { const st = alarmStyle("high", p); return <button key={p} className={`btn sm ${filter.priorities.has(p) ? "active" : ""}`} style={{ color: filter.priorities.has(p) ? undefined : st.color }} onClick={() => togglePrio(p)} title={priorityLabel(p)}>{st.glyph} {priorityLabel(p)}</button>; })}
        <select className="select w-160" value={filter.area} onChange={(e) => setFilter((f) => ({ ...f, area: e.target.value as AreaId | "" }))}>
          <option value="">barcha uchastkalar</option>{AREAS.map((a) => <option key={a.id} value={a.id}>{a.title}</option>)}
        </select>
        <select className="select w-130" value={group} onChange={(e) => setGroup(e.target.value as "none" | "sensor" | "area")}>
          <option value="none">guruhsiz</option><option value="sensor">sensor bo'yicha</option><option value="area">uchastka bo'yicha</option>
        </select>
        <input className="input w-180" placeholder="qidiruv (nom, kalit)" value={filter.q} onChange={(e) => setFilter((f) => ({ ...f, q: e.target.value }))} data-testid="alarm-search" />
        <span className="grow" />
        {canOperate && unackedFiltered.length > 0 && <button className="btn sm" onClick={() => setAckAll(true)} data-testid="ack-all">Hammasini kvitlash ({unackedFiltered.length})</button>}
      </div>
      {err && <p className="error">{err}</p>}
      {groups.map((g) => (
        <section key={g.key} className="panel mb-8">
          {g.title && <div className="row"><b>{g.title}</b></div>}
          <AlarmTable rows={g.rows} pid={pid} canOperate={canOperate} canEngineer={canEngineer} onChanged={onChanged} onError={setErr} />
        </section>
      ))}
      {ackAll && (
        <Dialog title="Hammasini kvitlash" onClose={() => setAckAll(false)}>
          <p><b>{unackedFiltered.length}</b> ta alarm kvitlanadi — faqat hozirgi filtrdagi kvitlanmagan hodisalar{filter.priorities.size ? ` (${[...filter.priorities].map(priorityLabel).join(", ")})` : ""}{filter.area ? `, uchastka ${areaTitle(filter.area)}` : ""}.</p>
          <label className="field"><span>Izoh (ixtiyoriy)</span><input className="input" value={comment} onChange={(e) => setComment(e.target.value)} data-autofocus /></label>
          <div className="actions">
            <button className="btn" onClick={() => setAckAll(false)}>Bekor</button>
            <button className="btn primary" data-testid="ack-all-ok" disabled={busy} onClick={async () => { setBusy(true); try { await api.ackAlarmsBatch(pid, unackedFiltered.map((r) => r.id), comment); setAckAll(false); setComment(""); onChanged(); } catch (e) { setErr(e instanceof Error ? e.message : "Xato"); } finally { setBusy(false); } }}>Kvitlash</button>
          </div>
        </Dialog>
      )}
    </div>
  );
}
