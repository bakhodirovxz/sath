"""Jonli o'lchovlar oqimi: WebSocket obunachilar (loyiha bo'yicha) va ingest → alarm → broadcast."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import WebSocket
from sqlalchemy.orm import Session

from .. import notifications, notify
from ..config import get_settings
from ..orm import AlarmEvent, AlarmState, ProjectMember, Reading, Role, Sensor, utcnow

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
        "element_guid": sensor.element_guid,
        "unit": sensor.unit,
    }


def ingest(db: Session, project_id: int, items: list[dict], source: str = "http") -> dict:
    """O'lchovlarni saqlaydi, alarm holatini yangilaydi, jonli oqimga yuboradi.

    items: [{"key": "AGG1.P", "value": 24.3, "ts": "2026-...Z"?}]  (yoki "sensor_id")
    Qaytaradi: {"accepted": n, "unknown": [key...]}
    """
    sensors = {s.key: s for s in db.query(Sensor).filter_by(project_id=project_id).all()}
    by_id = {s.id: s for s in sensors.values()}
    accepted, unknown, changed, events = 0, [], [], []
    now = datetime.now(timezone.utc)
    for it in items:
        sensor = sensors.get(str(it.get("key", ""))) or by_id.get(it.get("sensor_id"))
        if sensor is None or not sensor.enabled:
            unknown.append(it.get("key") or it.get("sensor_id"))
            continue
        try:
            value = float(it["value"])
        except (KeyError, TypeError, ValueError):
            unknown.append(it.get("key"))
            continue
        ts = _parse_ts(it.get("ts")) or now
        db.add(Reading(sensor_id=sensor.id, ts=ts, value=value))
        if sensor.last_ts is None or ts >= _aware(sensor.last_ts):
            sensor.last_value = value
            sensor.last_ts = ts
            if sensor not in changed:
                changed.append(sensor)
        accepted += 1
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
    return {"accepted": accepted, "unknown": unknown}


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
    if v is None:
        return None
    if isinstance(v, int | float):
        return datetime.fromtimestamp(v, tz=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
