import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";
import { api, type AlarmEvent, type Command, type LiveMessage, type Sensor } from "../api/client";
import { openLiveConnection, type LiveState } from "../hooks/liveConnection";
import { annunciator, type Priority } from "../ui/annunciator";

/** Umumiy jonli store (UX-11): loyiha uchun BITTA WebSocket (sahifalar/panellar soni qancha bo'lishidan
 * qat'i nazar), ma'lumot bir joyda. Komponentlar faqat o'z sensorlariga obuna bo'ladi (`useSensor`,
 * `useSensorsByIds`, `useLiveSelector`) — bitta o'qish butun sahifani qayta chizmaydi. O'zgarmagan sensor
 * obyektlari o'z identifikatorini saqlaydi (React.memo ishlaydi); bildirishnomalar 50 ms da bir marta
 * to'planib yuboriladi (yuqori chastotali oqimda ham ≤ 20 Hz qayta chizish).
 *
 * Alarm hodisalari (faol ro'yxat) ham shu yerda: kvitlanmagan yangi alarm — annunciator (bir marta), kvitlash/
 * yopilish — ovoz to'xtaydi. Qayta ulanganda (OFFLINE → LIVE) faol alarmlar qayta so'raladi (uzilish paytida
 * o'tkazib yuborilganlari). */

type Fn = () => void;

interface ProjectLive {
  pid: number;
  refs: number;
  closeTimer: number | undefined;
  stop: (() => void) | null;
  sensors: Map<number, Sensor>;
  list: Sensor[];
  version: number;
  state: LiveState;
  /** Oxirgi LIVE holat vaqti (ALOQA YO'Q bannerida "N s oldin") */
  lastLiveAt: number | null;
  everLive: boolean;
  events: AlarmEvent[];
  eventsLoaded: boolean;
  lastCommand: Command | null;
  // obunachilar
  listSubs: Set<Fn>;
  sensorSubs: Map<number, Set<Fn>>;
  stateSubs: Set<Fn>;
  eventSubs: Set<Fn>;
  msgSubs: Set<(m: LiveMessage) => void>;
  // to'plangan o'zgarishlar
  dirty: Set<number>;
  flushTimer: number | undefined;
}

const FLUSH_MS = 50;
const CLOSE_GRACE_MS = 3000; // sahifalar orasida o'tishda soket qayta ochilmasin
const projects = new Map<number, ProjectLive>();
const announced = new Set<number>();

/** Test/injeksiya: soket fabrikasi. */
let socketFactory: ((pid: number) => WebSocket | Promise<WebSocket>) | undefined;
let tickMs = 1000;
export function configureLive(o: { socket?: (pid: number) => WebSocket | Promise<WebSocket>; tickMs?: number }): void {
  socketFactory = o.socket;
  tickMs = o.tickMs ?? 1000;
}
/** Test: barcha holatni tozalash. */
export function resetLive(): void {
  for (const p of projects.values()) { p.stop?.(); window.clearTimeout(p.closeTimer); window.clearTimeout(p.flushTimer); }
  projects.clear();
  announced.clear();
}

function get(pid: number): ProjectLive {
  let p = projects.get(pid);
  if (!p) {
    p = {
      pid, refs: 0, closeTimer: undefined, stop: null, sensors: new Map(), list: [], version: 0, state: "OFFLINE", lastLiveAt: null, everLive: false,
      events: [], eventsLoaded: false, lastCommand: null,
      listSubs: new Set(), sensorSubs: new Map(), stateSubs: new Set(), eventSubs: new Set(), msgSubs: new Set(), dirty: new Set(), flushTimer: undefined,
    };
    projects.set(pid, p);
  }
  return p;
}

function flush(p: ProjectLive) {
  p.flushTimer = undefined;
  if (!p.dirty.size) return;
  const ids = [...p.dirty];
  p.dirty.clear();
  p.version++;
  p.list = [...p.sensors.values()];
  for (const id of ids) p.sensorSubs.get(id)?.forEach((f) => f());
  p.listSubs.forEach((f) => f());
}
function markDirty(p: ProjectLive, id: number, now = false) {
  p.dirty.add(id);
  if (now) { window.clearTimeout(p.flushTimer); flush(p); return; }
  if (p.flushTimer === undefined) p.flushTimer = window.setTimeout(() => flush(p), FLUSH_MS);
}

function patchSensor(p: ProjectLive, id: number, patch: Partial<Sensor>) {
  const cur = p.sensors.get(id);
  if (!cur) return;
  let changed = false;
  for (const k of Object.keys(patch) as (keyof Sensor)[]) if (cur[k] !== patch[k]) { changed = true; break; }
  if (!changed) return;
  p.sensors.set(id, { ...cur, ...patch });
  markDirty(p, id);
}

function announce(e: AlarmEvent) {
  if (e.acked_at || e.ended_at) { annunciator.ack(e.id); announced.delete(e.id); return; }
  if (announced.has(e.id)) return;
  announced.add(e.id);
  annunciator.alarm(e.id, (e.priority ?? "medium") as Priority);
}

function setEventsInternal(p: ProjectLive, events: AlarmEvent[]) {
  p.events = events;
  p.eventsLoaded = true;
  for (const e of events) announce(e);
  p.eventSubs.forEach((f) => f());
}

function onMessage(p: ProjectLive, m: LiveMessage) {
  if (m.type === "snapshot" && m.sensors) {
    for (const u of m.sensors) patchSensor(p, u.sensor_id, { last_value: u.value, last_ts: u.ts, alarm: u.alarm, ...(u.stale != null ? { stale: u.stale } : {}), ...(u.quality ? { last_quality: u.quality } : {}) });
  } else if (m.type === "reading" && m.sensor_id != null) {
    patchSensor(p, m.sensor_id, { last_value: m.value ?? null, last_ts: m.ts ?? null, ...(m.alarm ? { alarm: m.alarm } : {}), stale: m.stale ?? false, ...(m.quality ? { last_quality: m.quality } : {}) });
  } else if (m.type === "alarm" && m.event) {
    const ev = m.event;
    const prev = p.events.find((x) => x.id === ev.id);
    const s = p.sensors.get(ev.sensor_id);
    const merged: AlarmEvent = { ...(prev ?? { sensor_key: s?.key ?? "", unit: s?.unit ?? "", acked_at: null, comment: "" }), ...ev } as AlarmEvent;
    const rest = p.events.filter((x) => x.id !== ev.id);
    setEventsInternal(p, merged.ended_at && merged.acked_at ? rest : [merged, ...rest]);
  } else if (m.type === "command" && m.command) {
    p.lastCommand = m.command;
  }
  p.msgSubs.forEach((f) => f(m));
}

function setState(p: ProjectLive, s: LiveState) {
  const wasDown = p.state === "OFFLINE";
  p.state = s;
  if (s === "LIVE") {
    p.lastLiveAt = Date.now();
    if (wasDown && p.everLive) void loadEvents(p.pid); // uzilish paytidagi alarmlar
    p.everLive = true;
  }
  p.stateSubs.forEach((f) => f());
}

function connect(p: ProjectLive) {
  if (p.stop) return;
  p.stop = openLiveConnection({ projectId: p.pid, socket: socketFactory, tickMs, onMessage: (m) => onMessage(p, m), onState: (s) => setState(p, s) });
}

/** Soketdan foydalanishni boshlash (hisoblagich); qaytaradi — bo'shatish. Oxirgi foydalanuvchi ketgach
 * soket biroz kutib yopiladi (sahifalar orasida o'tish uzilishsiz). */
export function retainLive(pid: number): () => void {
  const p = get(pid);
  p.refs++;
  window.clearTimeout(p.closeTimer);
  p.closeTimer = undefined;
  connect(p);
  let released = false;
  return () => {
    if (released) return;
    released = true;
    p.refs--;
    if (p.refs <= 0) {
      p.closeTimer = window.setTimeout(() => {
        if (p.refs > 0) return;
        p.stop?.();
        p.stop = null;
        p.state = "OFFLINE";
        p.stateSubs.forEach((f) => f());
      }, CLOSE_GRACE_MS);
    }
  };
}

/** REST dan kelgan sensorlar (to'liq obyekt) — mavjudlari yangilanadi, yangilari qo'shiladi.
 * `replace` — to'liq loyiha ro'yxati: unda yo'q (o'chirilgan) sensorlar store dan olib tashlanadi. */
export function putSensors(pid: number, sensors: Sensor[], opts: { replace?: boolean } = {}): void {
  const p = get(pid);
  if (opts.replace) {
    const keep = new Set(sensors.map((s) => s.id));
    for (const id of [...p.sensors.keys()]) if (!keep.has(id)) { p.sensors.delete(id); p.dirty.add(id); }
  }
  for (const s of sensors) {
    const cur = p.sensors.get(s.id);
    // jonli qiymat REST javobidan yangiroq bo'lsa — saqlanadi (sahifa yuklanguncha kelgan o'qish)
    const keepLive = cur && cur.last_ts && s.last_ts && Date.parse(cur.last_ts) > Date.parse(s.last_ts);
    p.sensors.set(s.id, keepLive ? { ...s, last_value: cur.last_value, last_ts: cur.last_ts, alarm: cur.alarm, stale: cur.stale, last_quality: cur.last_quality } : s);
    p.dirty.add(s.id);
  }
  window.clearTimeout(p.flushTimer);
  flush(p);
}

/** Faol alarmlarni serverdan qayta o'qish (sahifa ochilganda, qayta ulanganda, kvitlagandan keyin). */
export async function loadEvents(pid: number): Promise<AlarmEvent[]> {
  const p = get(pid);
  try {
    const ev = await api.alarmEvents(pid, true);
    setEventsInternal(p, ev);
    return ev;
  } catch {
    return p.events;
  }
}
/** Kvitlash natijasini darhol qo'llash (server javobi). */
export function applyEvent(pid: number, e: AlarmEvent): void {
  const p = get(pid);
  const rest = p.events.filter((x) => x.id !== e.id);
  setEventsInternal(p, e.ended_at && e.acked_at ? rest : p.events.map((x) => (x.id === e.id ? { ...x, ...e } : x)));
  announce(e);
}

// --- React hook lari ---------------------------------------------------------------------------------

/** Sahifa/panel jonli oqimdan foydalanadi (soket ochiq turadi) — holatni qaytaradi. */
export function useProjectLive(pid: number): LiveState {
  useEffect(() => (Number.isFinite(pid) && pid > 0 ? retainLive(pid) : undefined), [pid]);
  return useLiveState(pid);
}

/** Obuna funksiyasi (barqaror — useSyncExternalStore har renderda qayta obuna bo'lmasin). */
function useSub(set: Set<Fn>): (f: Fn) => () => void {
  return useCallback((f: Fn) => { set.add(f); return () => { set.delete(f); }; }, [set]);
}

export function useLiveState(pid: number): LiveState {
  const p = get(pid);
  return useSyncExternalStore(useSub(p.stateSubs), () => p.state, () => p.state);
}
/** Oxirgi LIVE vaqti (ms) — aloqa yo'qligi yoshi uchun. */
export function useLastLiveAt(pid: number): number | null {
  const p = get(pid);
  return useSyncExternalStore(useSub(p.stateSubs), () => p.lastLiveAt, () => p.lastLiveAt);
}

/** Loyihaning barcha sensorlari (ro'yxat o'zgarganda yangi massiv, elementlar — barqaror obyektlar). */
export function useSensors(pid: number): Sensor[] {
  const p = get(pid);
  return useSyncExternalStore(useSub(p.listSubs), () => p.list, () => p.list);
}

/** Bitta sensor — faqat u o'zgarganda qayta chizadi. */
export function useSensor(pid: number, id: number | null | undefined): Sensor | undefined {
  const p = get(pid);
  const subscribe = useCallback((f: Fn) => {
    if (id == null) return () => undefined;
    let s = p.sensorSubs.get(id);
    if (!s) { s = new Set(); p.sensorSubs.set(id, s); }
    s.add(f);
    return () => { s!.delete(f); };
  }, [p, id]);
  const snap = () => (id == null ? undefined : p.sensors.get(id));
  return useSyncExternalStore(subscribe, snap, snap);
}

/** Tanlangan sensorlar (tartib saqlanadi) — faqat shular o'zgarganda qayta chizadi. */
export function useSensorsByIds(pid: number, ids: readonly number[]): Sensor[] {
  const p = get(pid);
  const key = ids.join(",");
  const cache = useRef<{ key: string; version: number; value: Sensor[] } | null>(null);
  const snapshot = () => {
    const c = cache.current;
    const value = ids.map((id) => p.sensors.get(id)).filter((s): s is Sensor => !!s);
    if (c && c.key === key && c.value.length === value.length && c.value.every((s, i) => s === value[i])) return c.value;
    cache.current = { key, version: p.version, value };
    return value;
  };
  const subscribe = useCallback((f: Fn) => {
    const subs = key ? key.split(",").map((x) => { const id = Number(x); let s = p.sensorSubs.get(id); if (!s) { s = new Set(); p.sensorSubs.set(id, s); } s.add(f); return s; }) : [];
    p.listSubs.add(f); // sensor keyinroq REST dan kelishi mumkin
    return () => { subs.forEach((s) => s.delete(f)); p.listSubs.delete(f); };
  }, [p, key]);
  return useSyncExternalStore(subscribe, snapshot, snapshot);
}

/** Sensorlardan hosil qilingan qiymat — faqat natija o'zgarganda (isEqual) qayta chizadi (KPI, jamlanmalar). */
export function useLiveSelector<T>(pid: number, select: (sensors: Sensor[]) => T, isEqual: (a: T, b: T) => boolean = Object.is): T {
  const p = get(pid);
  const cache = useRef<{ version: number; list: Sensor[]; value: T } | null>(null);
  const sel = useRef(select);
  sel.current = select;
  const snapshot = () => {
    const c = cache.current;
    if (c && c.list === p.list) return c.value;
    const value = sel.current(p.list);
    if (c && isEqual(c.value, value)) { cache.current = { version: p.version, list: p.list, value: c.value }; return c.value; }
    cache.current = { version: p.version, list: p.list, value };
    return value;
  };
  return useSyncExternalStore(useSub(p.listSubs), snapshot, snapshot);
}

/** Faol alarm hodisalari (umumiy ro'yxat). */
export function useAlarmEvents(pid: number): AlarmEvent[] {
  const p = get(pid);
  useEffect(() => { if (!p.eventsLoaded && Number.isFinite(pid) && pid > 0) void loadEvents(pid); }, [p, pid]);
  return useSyncExternalStore(useSub(p.eventSubs), () => p.events, () => p.events);
}

/** Xom jonli xabarlar (buyruq, jurnal, o'qishlar — trend chizig'i uchun). */
export function useLiveMessages(pid: number, cb: (m: LiveMessage) => void): void {
  const ref = useRef(cb);
  ref.current = cb;
  useEffect(() => {
    const p = get(pid);
    const f = (m: LiveMessage) => ref.current(m);
    p.msgSubs.add(f);
    return () => { p.msgSubs.delete(f); };
  }, [pid]);
}

/** Test/diagnostika: ichki holat. */
export function liveDebug(pid: number): { refs: number; open: boolean; sensors: number; events: number } {
  const p = get(pid);
  return { refs: p.refs, open: !!p.stop, sensors: p.sensors.size, events: p.events.length };
}
