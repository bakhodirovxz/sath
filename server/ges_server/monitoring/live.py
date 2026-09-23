"""Jonli o'lchovlar oqimi: WebSocket obunachilar (loyiha bo'yicha) va ingest → alarm → broadcast."""

from __future__ import annotations

import asyncio
import logging
import math
import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi import WebSocket
from sqlalchemy import insert
from sqlalchemy.orm import Session

from .. import notifications, notify
from ..config import get_settings
from ..orm import QUALITIES, AlarmEvent, AlarmState, ProjectMember, Reading, Role, Sensor, utcnow

log = logging.getLogger("ges_server.monitoring")

STATE_LABEL = {
    "low": "past",
    "high": "yuqori",
    "stale": "aloqa yo'q",
    "ok": "normal",
    "lowlow": "juda past (LL)",
    "highhigh": "juda yuqori (HH)",
    "roc": "tez o'zgarish",
    "deviation": "model bilan og'ish",
}
PRIORITY_LABEL = {"low": "", "medium": "", "high": "MUHIM: ", "critical": "KRITIK: "}


WS_QUEUE_MAX = 200  # har klient uchun chegaralangan navbat (L4): to'lsa eng eski xabar tashlanadi
WS_SEND_TIMEOUT_S = 10.0  # bitta send shuncha vaqtda tugamasa — qotgan klient, yopiladi


class Client:
    """Bitta WebSocket obunachi: o'z navbati va yuboruvchi vazifasi — sekin/qotgan klient boshqalarni to'xtatmaydi."""

    __slots__ = ("ws", "user_id", "project_id", "queue", "task", "dropped", "sent", "opened_at", "closed")

    def __init__(self, ws: WebSocket, project_id: int, user_id: int | None):
        self.ws = ws
        self.project_id = project_id
        self.user_id = user_id
        self.queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=WS_QUEUE_MAX)
        self.task: asyncio.Task | None = None
        self.dropped = 0
        self.sent = 0
        self.opened_at = time.monotonic()
        self.closed = False

    def put(self, message: dict) -> None:
        """Navbatga (bloklamaydi); to'lgan bo'lsa eng eski xabar tashlanadi (jonli oqim — eng yangisi muhim)."""
        if self.queue.full():
            try:
                self.queue.get_nowait()
                self.dropped += 1
            except asyncio.QueueEmpty:
                pass
        self.queue.put_nowait(message)

    async def sender(self) -> None:
        try:
            while True:
                m = await self.queue.get()
                await asyncio.wait_for(self.ws.send_json(m), timeout=WS_SEND_TIMEOUT_S)
                self.sent += 1
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — uzilgan/qotgan ulanish: yopamiz, qabul sikli WebSocketDisconnect oladi
            self.closed = True
            log.info("ws klient (user=%s, loyiha=%s) yuborishda uzildi: %s", self.user_id, self.project_id, type(e).__name__)
            try:
                await self.ws.close(code=1011)
            except Exception:  # noqa: BLE001
                pass


class Hub:
    """Loyiha → ochiq WebSocket klientlar (har biri o'z navbati bilan). Sync (ingest) kontekstdan ham
    xabar yuborish mumkin; backplane (L4) ulangan bo'lsa boshqa replikalarga ham uzatiladi."""

    def __init__(self) -> None:
        self._subs: dict[int, set[Client]] = {}
        self.loop: asyncio.AbstractEventLoop | None = None
        self.backplane = None  # backplane.Backplane | None

    async def connect(self, project_id: int, ws: WebSocket, user_id: int | None = None) -> Client:
        await ws.accept()
        self.loop = asyncio.get_running_loop()
        c = Client(ws, project_id, user_id)
        c.task = asyncio.create_task(c.sender())
        self._subs.setdefault(project_id, set()).add(c)
        return c

    def disconnect(self, project_id: int, client: Client | WebSocket) -> None:
        subs = self._subs.get(project_id, set())
        c = client if isinstance(client, Client) else next((x for x in subs if x.ws is client), None)
        if c is None:
            return
        subs.discard(c)
        if c.task is not None:
            c.task.cancel()

    def user_connections(self, user_id: int) -> int:
        return sum(1 for subs in self._subs.values() for c in subs if c.user_id == user_id)

    def deliver(self, project_id: int, message: dict) -> None:
        """Mahalliy obunachilarga (backplane dan kelgan yoki o'zimizniki). Loop threadidan chaqiriladi."""
        for c in list(self._subs.get(project_id, ())):
            c.put(message)

    async def broadcast(self, project_id: int, message: dict) -> None:
        self.deliver(project_id, message)

    def publish(self, project_id: int, message: dict) -> None:
        """Sync koddan (HTTP handler, MQTT thread) chaqiriladi: mahalliy navbatlar + backplane."""
        if self.backplane is not None:
            self.backplane.publish(project_id, message)
        if self.loop is None or not self._subs.get(project_id):
            return
        self.loop.call_soon_threadsafe(self.deliver, project_id, message)

    def count(self, project_id: int) -> int:
        return len(self._subs.get(project_id, ()))

    def diagnostics(self, project_id: int) -> list[dict]:
        """Sekin klient diagnostikasi: navbat chuqurligi, tashlangan/yuborilgan xabarlar, davomiylik."""
        return [
            {
                "user_id": c.user_id,
                "queue": c.queue.qsize(),
                "dropped": c.dropped,
                "sent": c.sent,
                "age_s": round(time.monotonic() - c.opened_at, 1),
                "slow": c.dropped > 0 or c.queue.qsize() > WS_QUEUE_MAX // 2,
            }
            for c in self._subs.get(project_id, ())
        ]


hub = Hub()


def evaluate_alarm(sensor: Sensor, value: float, rate_per_min: float | None = None) -> AlarmState:
    """Chegaralar (LL < L < H < HH) + o'lik zona (ISA-18.2 §12.3): faol holatdan qaytish uchun qiymat
    chegaradan `deadband` qadar ichkariga kirishi kerak — chegarada tebranayotgan signal chatter qilmaydi.
    Daraja alarmlari ROC dan ustun; `kind="deviation"` (egizak og'ishi) — L/H o'rniga `deviation`.
    Kechikishlar (on/off_delay_s) bu yerda emas — `settle()` da."""
    cur = sensor.alarm
    d = float(sensor.deadband or 0.0)
    if d < 0:
        d = 0.0

    def above(thr, active: bool) -> bool:
        return thr is not None and value > (thr - d if active else thr)

    def below(thr, active: bool) -> bool:
        return thr is not None and value < (thr + d if active else thr)

    hh, h = sensor.hh_alarm, sensor.high_alarm
    ll, lo = sensor.ll_alarm, sensor.low_alarm
    dev = sensor.kind == "deviation"
    level: AlarmState | None = None
    if above(hh, cur == AlarmState.highhigh):
        level = AlarmState.highhigh
    elif above(h, cur in (AlarmState.high, AlarmState.highhigh, AlarmState.deviation)):
        level = AlarmState.high
    elif below(ll, cur == AlarmState.lowlow):
        level = AlarmState.lowlow
    elif below(lo, cur in (AlarmState.low, AlarmState.lowlow, AlarmState.deviation)):
        level = AlarmState.low
    if level is not None:
        return AlarmState.deviation if dev else level
    lim = sensor.roc_limit_per_min
    if lim is not None and lim > 0 and rate_per_min is not None:
        # qaytish uchun 10 % gisterezis (tezlik shovqinli)
        thr = lim * 0.9 if cur == AlarmState.roc else lim
        if abs(rate_per_min) > thr:
            return AlarmState.roc
    return AlarmState.ok


def settle(
    db: Session, sensor: Sensor, target: AlarmState, value: float | None, now: datetime | None = None
) -> AlarmEvent | None:
    """Kechikishli holat mashinasi (ISA-18.2 on/off delay): `target` hozirgi holatdan farq qilsa,
    alarmga kirish `on_delay_s`, qaytish (ok ga) `off_delay_s` davomida saqlanishi kerak; `stale` dan
    chiqish darhol. Kutish `alarm_pending`/`alarm_pending_since` da (fon tekshiruvi ham yakunlaydi).
    Qaytaradi: yangi ochilgan hodisa yoki None. Commit chaqiruvchida."""
    now = now or datetime.now(timezone.utc)
    if target == sensor.alarm:
        sensor.alarm_pending = None
        sensor.alarm_pending_since = None
        return None
    if target == AlarmState.ok:
        delay = int(sensor.off_delay_s or 0)
    else:
        delay = int(sensor.on_delay_s or 0)
    if delay > 0:
        if sensor.alarm_pending != target.value or sensor.alarm_pending_since is None:
            sensor.alarm_pending = target.value
            sensor.alarm_pending_since = now
            return None
        if (now - _aware(sensor.alarm_pending_since)).total_seconds() < delay:
            return None
    sensor.alarm_pending = None
    sensor.alarm_pending_since = None
    return transition(db, sensor, target, value)


def settle_pending(db: Session, project_id: int) -> list[Sensor]:
    """Kechikishi o'tgan kutilayotgan holatlarni yangi o'lchovsiz ham yakunlaydi (fon vazifasi):
    qiymat chegarada turib yangi xabar kelmasa ham alarm `on_delay_s` dan keyin ochiladi."""
    now = datetime.now(timezone.utc)
    changed, events = [], []
    q = db.query(Sensor).filter(Sensor.project_id == project_id, Sensor.alarm_pending.isnot(None))
    for s in q.all():
        try:
            target = AlarmState(s.alarm_pending)
        except ValueError:
            s.alarm_pending = None
            continue
        ev = settle(db, s, target, s.last_value, now)
        if s.alarm_pending is None:
            changed.append(s)
            if ev is not None:
                events.append((ev, s))
    if changed:
        db.commit()
        for s in changed:
            hub.publish(project_id, sensor_message(s))
        announce(db, project_id, events)
    return changed


def event_message(ev: AlarmEvent, sensor: Sensor) -> dict:
    return {
        "type": "alarm",
        "event": {
            "id": ev.id,
            "sensor_id": ev.sensor_id,
            "sensor_name": sensor.name,
            "state": ev.state.value,
            "value": ev.value,
            "started_at": _aware(ev.started_at).isoformat(),
            "ended_at": _aware(ev.ended_at).isoformat() if ev.ended_at else None,
            "acked_by": ev.acked_by,
            "acked_at": _aware(ev.acked_at).isoformat() if ev.acked_at else None,
            "priority": sensor.priority or "medium",
        },
    }


MODE_LABEL = {
    "shelved": "shelved (vaqtincha yashirilgan)",
    "out_of_service": "xizmatdan chiqarilgan",
    "suppressed_by_design": "shart bo'yicha bostirilgan",
}


def effective_mode(sensor: Sensor) -> str | None:
    """Hodisa uchun bostirish sababi: out_of_service > shelved > suppressed_by_design; None — normal."""
    if sensor.alarm_mode == "out_of_service":
        return "out_of_service"
    if sensor.alarm_mode == "shelved":
        return "shelved"
    if sensor.suppressed:
        return "suppressed_by_design"
    return None


def transition(
    db: Session, sensor: Sensor, new_state: AlarmState, value: float | None
) -> AlarmEvent | None:
    """Sensor holati o'zgarganda alarm jurnalini yuritadi: faol hodisani yopadi, yangisini ochadi.
    Rejim normal bo'lmasa (shelved/OOS/bostirilgan) hodisa `suppressed` bilan yoziladi — chaqiruvchi
    (`announce`) uni bildirmaydi. Qaytaradi: yangi ochilgan hodisa yoki None. Commit chaqiruvchida."""
    old = sensor.alarm
    if new_state == old:
        return None
    sensor.alarm = new_state
    now = utcnow()
    if old != AlarmState.ok:
        for ev in db.query(AlarmEvent).filter_by(sensor_id=sensor.id, ended_at=None).all():
            ev.ended_at = now
    if new_state == AlarmState.ok:
        return None
    ev = AlarmEvent(
        project_id=sensor.project_id,
        sensor_id=sensor.id,
        state=new_state,
        value=value,
        started_at=now,
        suppressed=effective_mode(sensor),
    )
    db.add(ev)
    return ev


def announce(db: Session, project_id: int, events: list[tuple[AlarmEvent, Sensor]]) -> None:
    """Yangi alarm hodisalari: jonli oqim, ilova ichi bildirishnoma (a'zolar + adminlar), email (muhandis+).
    Bostirilgan (shelved/OOS/shart) hodisalar jurnalda qoladi, lekin bildirilmaydi."""
    events = [(ev, s) for ev, s in events if not ev.suppressed]
    if not events:
        return
    members = notifications.member_ids(db, project_id, with_admins=True)  # adminlar ham (taqriz kabi)
    emails = sorted(
        {
            m.user.email
            for m in db.query(ProjectMember).filter_by(project_id=project_id).all()
            if m.user.email and m.user.is_active and m.role in (Role.engineer, Role.approver)
        }
    )
    base = get_settings().public_url.rstrip("/")
    link = f"/projects/{project_id}/dashboard"
    lines = []
    for ev, s in events:
        hub.publish(project_id, event_message(ev, s))
        val = f" ({ev.value:g} {s.unit})" if ev.value is not None else ""
        lines.append(
            f"{PRIORITY_LABEL.get(s.priority or 'medium', '')}{s.name} — {STATE_LABEL[ev.state.value]}{val}"
        )
    if len(events) == 1:
        title, body = f"Alarm: {lines[0]}", events[0][1].key
    else:  # bir paketda ko'p hodisa — bitta jamlangan xabar (toshqin bo'lmasin)
        title = f"{len(events)} ta alarm"
        body = "; ".join(lines[:10]) + (" …" if len(lines) > 10 else "")
    notifications.push(db, members, "alarm", title, body, link)
    notify.send_async(emails, title, "\n".join(lines) + f"\n{base}{link}", group=f"alarm:{project_id}")
    db.commit()


def sensor_message(sensor: Sensor) -> dict:
    return {
        "type": "reading",
        "sensor_id": sensor.id,
        "key": sensor.key,
        "value": sensor.last_value,
        "ts": _aware(sensor.last_ts).isoformat() if sensor.last_ts else None,
        "alarm": sensor.alarm.value,
        "stale": bool(sensor.stale),
        "age_s": round((datetime.now(timezone.utc) - _aware(sensor.last_ts)).total_seconds(), 1) if sensor.last_ts else None,
        "alarm_mode": effective_mode(sensor) or "normal",
        "quality": sensor.last_quality or "good",
        "element_guid": sensor.element_guid,
        "unit": sensor.unit,
    }


SENSOR_CACHE_TTL_S = 30.0
_sensor_cache: dict[int, tuple[float, dict[str, int], dict[int, bool]]] = {}  # project → (muddat, key→id, id→enabled)
_sensor_cache_lock = threading.Lock()


def invalidate_sensors(project_id: int | None = None) -> None:
    """Sensor keshi (D1): sensor yaratilganda/o'zgarganda/o'chirilganda chaqiriladi (yo'qsa TTL 30 s)."""
    with _sensor_cache_lock:
        if project_id is None:
            _sensor_cache.clear()
        else:
            _sensor_cache.pop(project_id, None)


def _sensor_index(db: Session, project_id: int, force: bool = False) -> tuple[dict[str, int], dict[int, bool]]:
    """Loyiha sensorlari indeksi (kalit → id, id → enabled), TTL bilan keshlangan — har partiyada butun
    sensor jadvalini yuklamaslik uchun; faqat paketda kelgan sensorlar ORM orqali o'qiladi."""
    now = time.monotonic()
    with _sensor_cache_lock:
        hit = _sensor_cache.get(project_id)
        if hit and hit[0] > now and not force:
            return hit[1], hit[2]
    rows = db.query(Sensor.id, Sensor.key, Sensor.enabled).filter(Sensor.project_id == project_id).all()
    by_key = {k: i for i, k, _ in rows}
    enabled = {i: bool(e) for i, _, e in rows}
    with _sensor_cache_lock:
        _sensor_cache[project_id] = (now + SENSOR_CACHE_TTL_S, by_key, enabled)
    return by_key, enabled


def _archive(sensor: Sensor, value: float, ts: datetime, quality: str) -> bool:
    """Arxiv siqishi (D2, o'lik zona): `archive_deadband` berilgan sensorda oxirgi yozilgan qiymatdan
    o'zgarish shundan kichik va `archive_max_interval_s` o'tmagan bo'lsa xom qator yozilmaydi.
    Bad sifat va sifat o'zgarishi har doim yoziladi. Qaytaradi: yozish kerakmi."""
    d = sensor.archive_deadband
    if d is None or d <= 0 or quality == "bad":
        sensor.last_archived_value, sensor.last_archived_ts = value, ts
        return True
    lv, lt = sensor.last_archived_value, sensor.last_archived_ts
    if lv is None or lt is None or abs(value - lv) >= d:
        sensor.last_archived_value, sensor.last_archived_ts = value, ts
        return True
    if (ts - _aware(lt)).total_seconds() >= int(sensor.archive_max_interval_s or 3600):
        sensor.last_archived_value, sensor.last_archived_ts = value, ts
        return True
    return False


def _bulk_insert_readings(db: Session, rows: list[dict]) -> None:
    """Xom o'lchovlarni partiyalab yozadi: Postgres — COPY (psycopg 3), boshqalar — executemany INSERT."""
    if not rows:
        return
    if db.bind.dialect.name == "postgresql":
        raw = db.connection().connection.dbapi_connection
        with raw.cursor() as cur, cur.copy("COPY readings (sensor_id, ts, value, quality, src_ts) FROM STDIN") as cp:
            for r in rows:
                cp.write_row((r["sensor_id"], r["ts"], r["value"], r["quality"], r["src_ts"]))
        return
    db.execute(insert(Reading), rows)


def ingest(
    db: Session,
    project_id: int,
    items: list[dict],
    source: str = "http",
    max_age: timedelta | None = None,
) -> dict:
    """O'lchovlarni saqlaydi, alarm holatini yangilaydi, jonli oqimga yuboradi.

    items: [{"key": "AGG1.P", "value": 24.3, "ts": "2026-...Z"?, "quality": "good"?, "src_ts": ...?}]
    (yoki "sensor_id"). Sifat: QUALITIES; noma'lum/yo'q → good. `bad` qiymat tarixga yoziladi, lekin
    sensor holatini (last_value, alarm) o'zgartirmaydi va jonli oqimga chiqmaydi.

    Validatsiya (A3): qiymat chekli son bo'lishi shart (NaN/inf → rejected); `ts` yaroqsiz, kelajakda
    (> ingest_future_s) yoki `max_age` dan eski bo'lsa element rad etiladi (`rejected`, sabab bilan) —
    kelajakdagi tamg'a `last_ts` ni qotirmasin. `max_age=None` — chegarasiz (tarixiy CSV import).
    Sensor `min_raw`/`max_raw` dan tashqaridagi qiymat `quality=bad` bilan saqlanadi.
    Qaytaradi: {"accepted": n, "unknown": [key...], "bad": n, "rejected": [{"key", "reason"}]}
    """
    settings = get_settings()
    # Sensor indeksi keshdan; paketda noma'lum kalit bo'lsa bir marta yangilanadi (yangi yaratilgan sensor)
    by_key, enabled_map = _sensor_index(db, project_id)

    def _resolve(it: dict) -> int | None:
        if it.get("key") is not None:
            return by_key.get(str(it["key"]))
        sid = it.get("sensor_id")
        return sid if sid in enabled_map else None

    wanted = [_resolve(it) for it in items]
    if any(w is None for w in wanted):  # noma'lum kalit — kesh eskirgan bo'lishi mumkin, bir marta yangilash
        by_key, enabled_map = _sensor_index(db, project_id, force=True)
        wanted = [_resolve(it) for it in items]
    wanted = [w for w in wanted if w is not None]
    loaded = db.query(Sensor).filter(Sensor.id.in_(set(wanted))).all() if wanted else []
    by_id = {s.id: s for s in loaded}
    sensors = {s.key: s for s in loaded}
    accepted, bad, unknown, rejected, events = 0, 0, [], [], []
    changed_map: dict[int, Sensor] = {}
    rows: list[dict] = []
    prev: dict[int, tuple[float | None, datetime | None]] = {}  # ROC uchun paketdan oldingi qiymat
    now = datetime.now(timezone.utc)
    latest = now + timedelta(seconds=settings.ingest_future_s)
    earliest = now - max_age if max_age is not None else None
    for it in items:
        sensor = sensors.get(str(it.get("key", ""))) or by_id.get(it.get("sensor_id"))
        if sensor is None or not sensor.enabled:
            unknown.append(it.get("key") or it.get("sensor_id"))
            continue
        ident = it.get("key") or it.get("sensor_id")
        try:
            value = float(it["value"])
        except (KeyError, TypeError, ValueError):
            rejected.append({"key": ident, "reason": "value_invalid"})
            continue
        if not math.isfinite(value):
            rejected.append({"key": ident, "reason": "value_not_finite"})
            continue
        raw_ts = it.get("ts")
        ts = _parse_ts(raw_ts) if raw_ts is not None else now
        if ts is None:
            rejected.append({"key": ident, "reason": "ts_invalid"})
            continue
        if ts > latest:
            rejected.append({"key": ident, "reason": "ts_future"})
            continue
        if earliest is not None and ts < earliest:
            rejected.append({"key": ident, "reason": "ts_too_old"})
            continue
        quality = str(it.get("quality") or "good")
        if quality not in QUALITIES:
            quality = "good"
        if (sensor.min_raw is not None and value < sensor.min_raw) or (
            sensor.max_raw is not None and value > sensor.max_raw
        ):
            quality = "bad"  # fizik diapazondan tashqarida — o'lchov yaroqsiz
        if _archive(sensor, value, ts, quality):
            rows.append(
                {"sensor_id": sensor.id, "ts": ts, "value": value, "quality": quality, "src_ts": _parse_ts(it.get("src_ts"))}
            )
        accepted += 1
        if quality == "bad":
            bad += 1
            continue
        if sensor.last_ts is None or ts >= _aware(sensor.last_ts):
            if sensor.id not in prev:
                prev[sensor.id] = (sensor.last_value, sensor.last_ts)
            sensor.last_value = value
            sensor.last_ts = ts
            sensor.last_quality = quality
            changed_map.setdefault(sensor.id, sensor)
    changed = list(changed_map.values())
    for sensor in changed:
        if sensor.stale:  # aloqa qaytdi: ochiq "stale" hodisasi yopiladi, jarayon alarmi o'z holida
            sensor.stale = False
            for ev in db.query(AlarmEvent).filter_by(sensor_id=sensor.id, state=AlarmState.stale, ended_at=None).all():
                ev.ended_at = utcnow()
    _bulk_insert_readings(db, rows)
    # Alarm holati — har sensor uchun paketdagi eng so'nggi qiymat bo'yicha bir marta
    # (tarixiy import/CSV da har nuqta uchun hodisa ochilib "alarm toshqini" bo'lmasin)
    if any(s.suppress_condition for s in changed):
        evaluate_suppression(db, project_id, [s for s in changed if s.suppress_condition], fresh=changed)
    for sensor in changed:
        p_val, p_ts = prev.get(sensor.id, (None, None))
        rate = None
        if sensor.roc_limit_per_min is not None and p_val is not None and p_ts is not None:
            dt_min = (_aware(sensor.last_ts) - _aware(p_ts)).total_seconds() / 60.0
            if dt_min > 0:
                rate = (sensor.last_value - p_val) / dt_min
        target = evaluate_alarm(sensor, sensor.last_value, rate)
        ev = settle(db, sensor, target, sensor.last_value, now)
        if ev is not None:
            events.append((ev, sensor))
    db.commit()
    for s in changed:
        hub.publish(project_id, {**sensor_message(s), "source": source})
    announce(db, project_id, events)
    return {"accepted": accepted, "unknown": unknown, "bad": bad, "rejected": rejected}


def evaluate_suppression(
    db: Session, project_id: int, sensors: list[Sensor], fresh: list[Sensor] | None = None
) -> list[Sensor]:
    """Suppression-by-design: `suppress_condition` (interlock ifodasi, loyiha sensorlari muhitida) rost →
    `suppressed=True`. Baholab bo'lmasa (sensor ma'lumoti yo'q/ifoda xatosi) — bostirilMAYDI (alarm
    ko'rinadi, xavfsiz tomon). O'zgargan sensorlar qaytariladi; hodisa `suppressed` belgisi hozirgi
    natijaga qarab yoziladi. Commit chaqiruvchida."""
    from ges_sim import custom

    from . import interlock

    env = interlock.env_for(db, project_id)
    for f in fresh or []:  # shu paketda kelgan qiymatlar (alarm holati hali yangilanmagan bo'lishi mumkin)
        if f.last_value is not None and (f.last_quality or "good") != "bad":
            env[interlock.var_name(f.key)] = float(f.last_value)
    changed = []
    for s in sensors:
        cond = (s.suppress_condition or "").strip()
        if not cond:
            new = False
        else:
            try:
                new = bool(custom.evaluate(custom.compile_expr(cond), env))
            except (NameError, ValueError, TypeError, ZeroDivisionError, ArithmeticError) as e:
                log.warning("sensor %s suppress_condition baholanmadi (%s) — bostirilmaydi", s.key, e)
                new = False
        if new != bool(s.suppressed):
            s.suppressed = new
            changed.append(s)
    return changed


def set_alarm_mode(
    db: Session,
    sensor: Sensor,
    mode: str,
    user_id: int | None,
    reason: str = "",
    until: datetime | None = None,
) -> AlarmEvent | None:
    """Rejimni o'zgartiradi (normal | shelved | out_of_service). Normal ga qaytganda sensor alarm holatida
    bo'lsa ochiq bostirilgan hodisa faollashtiriladi (bildirish uchun qaytariladi) — alarm "qaytadi".
    Commit chaqiruvchida."""
    sensor.alarm_mode = mode
    sensor.alarm_mode_reason = reason
    sensor.alarm_mode_by = user_id
    sensor.alarm_mode_since = datetime.now(timezone.utc)
    sensor.alarm_mode_until = until
    reactivated = None
    for ev in db.query(AlarmEvent).filter_by(sensor_id=sensor.id, ended_at=None).all():
        want = effective_mode(sensor)
        if ev.suppressed and not want:
            ev.suppressed = None  # bostirish tugadi — hodisa faol, kvitlanmagan
            reactivated = ev
        elif want and not ev.suppressed:
            ev.suppressed = want
    return reactivated


def unshelve_expired(db: Session, project_id: int) -> list[Sensor]:
    """Shelving muddati tugagan sensorlarni normal ga qaytaradi (fon vazifasi); alarm davom etayotgan
    bo'lsa bildirishnoma. Audit yozuvi tizim nomidan."""
    from .. import audit

    now = datetime.now(timezone.utc)
    changed, events = [], []
    q = db.query(Sensor).filter(Sensor.project_id == project_id, Sensor.alarm_mode == "shelved")
    for s in q.all():
        if s.alarm_mode_until is None or _aware(s.alarm_mode_until) > now:
            continue
        ev = set_alarm_mode(db, s, "normal", None, "")
        audit.log(
            db,
            user_id=None,
            action="alarm.unshelve_auto",
            target_type="sensor",
            target_id=s.id,
            project_id=project_id,
            detail={"key": s.key, "alarm": s.alarm.value},
        )
        changed.append(s)
        if ev is not None:
            events.append((ev, s))
    if changed:
        db.commit()
        for s in changed:
            hub.publish(project_id, sensor_message(s))
        announce(db, project_id, events)
    return changed


def mark_bad(db: Session, project_id: int, sensor_ids: list[int], source: str = "server") -> list[Sensor]:
    """Aloqa uzilganda (MQTT/gateway kanali) sensorlarga `quality=bad`: oxirgi qiymat bilan bitta bad
    Reading yoziladi (tarixda uzilish ko'rinsin), `last_quality=bad`, jonli oqimga chiqadi; `last_value`
    va alarm holati o'zgarmaydi (stale ni fon tekshiruvi beradi)."""
    now = datetime.now(timezone.utc)
    changed = []
    for s in db.query(Sensor).filter(Sensor.project_id == project_id, Sensor.id.in_(sensor_ids)).all():
        if s.last_quality == "bad":
            continue
        if s.last_value is not None:
            db.add(Reading(sensor_id=s.id, ts=now, value=float(s.last_value), quality="bad"))
        s.last_quality = "bad"
        changed.append(s)
    if changed:
        db.commit()
        for s in changed:
            hub.publish(project_id, {**sensor_message(s), "source": source})
    return changed


def mark_stale(db: Session, project_id: int) -> list[Sensor]:
    """stale_after_s dan beri ma'lumot kelmagan sensorlarga `stale` bayrog'i (F4): jarayon alarm holati
    o'zgarmaydi (yuqori alarm yashirinmaydi), jurnalga alohida `stale` hodisasi yoziladi."""
    now = datetime.now(timezone.utc)
    changed, events = [], []
    for s in db.query(Sensor).filter_by(project_id=project_id, enabled=True).all():
        if not s.stale and (s.last_ts is None or (now - _aware(s.last_ts)).total_seconds() > s.stale_after_s):
            s.stale = True
            s.alarm_pending = None
            s.alarm_pending_since = None
            ev = AlarmEvent(
                project_id=s.project_id,
                sensor_id=s.id,
                state=AlarmState.stale,
                value=s.last_value,
                started_at=utcnow(),
                suppressed=effective_mode(s),
            )
            db.add(ev)
            db.flush()
            events.append((ev, s))
            changed.append(s)
    if changed:
        db.commit()
        for s in changed:
            hub.publish(project_id, sensor_message(s))
        announce(db, project_id, events)
    return changed


def _aware(dt: datetime) -> datetime:
    """SQLite naive datetime qaytaradi — UTC deb hisoblaymiz."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _parse_ts(v) -> datetime | None:
    """ISO 8601 (Z yoki offset; naive → UTC), Unix soniya (int/float yoki raqamli satr) yoki datetime.
    Yaroqsiz/chegaradan tashqari → None (chaqiruvchi rad etadi)."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, bool):
        return None
    if isinstance(v, int | float):
        if not math.isfinite(v):
            return None
        try:
            return datetime.fromtimestamp(v, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    s = str(v).strip()
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    try:
        return _parse_ts(float(s))
    except ValueError:
        return None
