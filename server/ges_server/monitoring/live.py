"""Jonli o'lchovlar oqimi: WebSocket obunachilar (loyiha bo'yicha) va ingest → alarm → broadcast."""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timedelta, timezone

from fastapi import WebSocket
from sqlalchemy.orm import Session

from .. import notifications, notify
from ..config import get_settings
from ..orm import QUALITIES, AlarmEvent, AlarmState, ProjectMember, Reading, Role, Sensor, utcnow

log = logging.getLogger("ges_server.monitoring")

STATE_LABEL = {"low": "past", "high": "yuqori", "stale": "aloqa yo'q", "ok": "normal"}
PRIORITY_LABEL = {"low": "", "medium": "", "high": "MUHIM: ", "critical": "KRITIK: "}


class Hub:
    """Loyiha → ochiq WebSocket lar. Sync (ingest) kontekstdan ham xabar yuborish mumkin."""

    def __init__(self) -> None:
        self._subs: dict[int, set[WebSocket]] = {}
        self.loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, project_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self.loop = asyncio.get_running_loop()
        self._subs.setdefault(project_id, set()).add(ws)

    def disconnect(self, project_id: int, ws: WebSocket) -> None:
        self._subs.get(project_id, set()).discard(ws)

    async def broadcast(self, project_id: int, message: dict) -> None:
        dead = []
        for ws in list(self._subs.get(project_id, ())):
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001 — uzilgan ulanish
                dead.append(ws)
        for ws in dead:
            self.disconnect(project_id, ws)

    def publish(self, project_id: int, message: dict) -> None:
        """Sync koddan (HTTP handler, MQTT thread) chaqiriladi."""
        if self.loop is None or not self._subs.get(project_id):
            return
        asyncio.run_coroutine_threadsafe(self.broadcast(project_id, message), self.loop)

    def count(self, project_id: int) -> int:
        return len(self._subs.get(project_id, ()))


hub = Hub()


def evaluate_alarm(sensor: Sensor, value: float) -> AlarmState:
    if sensor.high_alarm is not None and value > sensor.high_alarm:
        return AlarmState.high
    if sensor.low_alarm is not None and value < sensor.low_alarm:
        return AlarmState.low
    return AlarmState.ok


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
            "priority": sensor.priority or "medium",
        },
    }


def transition(
    db: Session, sensor: Sensor, new_state: AlarmState, value: float | None
) -> AlarmEvent | None:
    """Sensor holati o'zgarganda alarm jurnalini yuritadi: faol hodisani yopadi, yangisini ochadi.
    Qaytaradi: yangi ochilgan hodisa (bildirishnoma uchun) yoki None. Commit chaqiruvchida."""
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
    )
    db.add(ev)
    return ev


def announce(db: Session, project_id: int, events: list[tuple[AlarmEvent, Sensor]]) -> None:
    """Yangi alarm hodisalari: jonli oqim, ilova ichi bildirishnoma (a'zolar + adminlar), email (muhandis+)."""
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
    notify.send_async(emails, title, "\n".join(lines) + f"\n{base}{link}")
    db.commit()


def sensor_message(sensor: Sensor) -> dict:
    return {
        "type": "reading",
        "sensor_id": sensor.id,
        "key": sensor.key,
        "value": sensor.last_value,
        "ts": _aware(sensor.last_ts).isoformat() if sensor.last_ts else None,
        "alarm": sensor.alarm.value,
        "quality": sensor.last_quality or "good",
        "element_guid": sensor.element_guid,
        "unit": sensor.unit,
    }


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
    sensors = {s.key: s for s in db.query(Sensor).filter_by(project_id=project_id).all()}
    by_id = {s.id: s for s in sensors.values()}
    accepted, bad, unknown, rejected, changed, events = 0, 0, [], [], [], []
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
            unknown.append(it.get("key"))
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
        db.add(
            Reading(
                sensor_id=sensor.id,
                ts=ts,
                value=value,
                quality=quality,
                src_ts=_parse_ts(it.get("src_ts")),
            )
        )
        accepted += 1
        if quality == "bad":
            bad += 1
            continue
        if sensor.last_ts is None or ts >= _aware(sensor.last_ts):
            sensor.last_value = value
            sensor.last_ts = ts
            sensor.last_quality = quality
            if sensor not in changed:
                changed.append(sensor)
    # Alarm holati — har sensor uchun paketdagi eng so'nggi qiymat bo'yicha bir marta
    # (tarixiy import/CSV da har nuqta uchun hodisa ochilib "alarm toshqini" bo'lmasin)
    for sensor in changed:
        ev = transition(db, sensor, evaluate_alarm(sensor, sensor.last_value), sensor.last_value)
        if ev is not None:
            events.append((ev, sensor))
    db.commit()
    for s in changed:
        hub.publish(project_id, {**sensor_message(s), "source": source})
    announce(db, project_id, events)
    return {"accepted": accepted, "unknown": unknown, "bad": bad, "rejected": rejected}


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
    """stale_after_s dan beri ma'lumot kelmagan sensorlarni 'stale' qiladi."""
    now = datetime.now(timezone.utc)
    changed, events = [], []
    for s in db.query(Sensor).filter_by(project_id=project_id, enabled=True).all():
        if s.alarm != AlarmState.stale and (
            s.last_ts is None or (now - _aware(s.last_ts)).total_seconds() > s.stale_after_s
        ):
            ev = transition(db, s, AlarmState.stale, s.last_value)
            if ev is not None:
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
