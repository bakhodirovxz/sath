"""Smena topshirish (F9): tuzilgan topshirish varaqasi — faol alarmlar, ochiq ish buyruqlari, blokirovka chetlab
o'tishlari, shelved/OOS nuqtalar, kutilayotgan buyruqlar, aloqasiz sensorlar — avtomatik to'ldiriladi; topshiruvchi va
qabul qiluvchining imzosi (audit yozuvi bilan); smena hodisalari tasmasi (alarm, buyruq, izoh, SOE) bitta xronologiyada.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..orm import (
    AlarmEvent,
    AuditLog,
    Command,
    CommandStatus,
    JournalEntry,
    Sensor,
    ShiftHandover,
    WorkOrder,
    WorkOrderStatus,
)
from . import soe
from .live import STATE_LABEL, _aware


def snapshot(db: Session, project_id: int, since: datetime, now: datetime | None = None) -> dict:
    """Topshirish varaqasi mazmuni (avtomatik). `since` — smena boshi (chetlab o'tishlar shu oynadan)."""
    now = now or datetime.now(timezone.utc)
    sensors = {s.id: s for s in db.query(Sensor).filter_by(project_id=project_id).all()}
    active = (
        db.query(AlarmEvent)
        .filter(AlarmEvent.project_id == project_id, AlarmEvent.ended_at.is_(None), AlarmEvent.suppressed.is_(None))
        .order_by(AlarmEvent.started_at.desc())
        .all()
    )
    alarms = [
        {
            "event_id": e.id,
            "sensor_id": e.sensor_id,
            "key": sensors[e.sensor_id].key if e.sensor_id in sensors else "",
            "name": sensors[e.sensor_id].name if e.sensor_id in sensors else "",
            "state": e.state.value,
            "label": STATE_LABEL.get(e.state.value, e.state.value),
            "priority": sensors[e.sensor_id].priority if e.sensor_id in sensors else "medium",
            "value": e.value,
            "started_at": _aware(e.started_at).isoformat(),
            "acked": e.acked_at is not None,
        }
        for e in active
    ]
    wos = (
        db.query(WorkOrder)
        .filter(WorkOrder.project_id == project_id, WorkOrder.status.in_([WorkOrderStatus.open, WorkOrderStatus.in_progress]))
        .order_by(WorkOrder.id.desc())
        .all()
    )
    work_orders = [
        {"id": w.id, "title": w.title, "status": w.status.value, "priority": w.priority, "due_at": _aware(w.due_at).isoformat() if w.due_at else None, "overdue": bool(w.due_at and _aware(w.due_at) < now)}
        for w in wos
    ]
    overrides = [
        {"at": _aware(a.created_at).isoformat(), "user_id": a.user_id, "detail": a.detail}
        for a in db.query(AuditLog)
        .filter(AuditLog.project_id == project_id, AuditLog.action == "command.interlock_override", AuditLog.created_at >= since)
        .order_by(AuditLog.id.desc())
        .all()
    ]
    modes = [
        {"sensor_id": s.id, "key": s.key, "name": s.name, "mode": s.alarm_mode, "reason": s.alarm_mode_reason, "until": _aware(s.alarm_mode_until).isoformat() if s.alarm_mode_until else None}
        for s in sensors.values()
        if s.alarm_mode and s.alarm_mode != "normal"
    ] + [
        {"sensor_id": s.id, "key": s.key, "name": s.name, "mode": "disabled", "reason": "", "until": None}
        for s in sensors.values()
        if not s.enabled
    ]
    pending = [
        {"id": c.id, "sensor_key": sensors[c.sensor_id].key if c.sensor_id in sensors else "", "value": c.value, "status": c.status.value, "author_id": c.created_by, "created_at": _aware(c.created_at).isoformat()}
        for c in db.query(Command)
        .filter(Command.project_id == project_id, Command.status.in_([CommandStatus.pending, CommandStatus.sent, CommandStatus.pending_approval, CommandStatus.mismatch, CommandStatus.unknown]))
        .order_by(Command.id.desc())
        .all()
    ]
    stale = [{"sensor_id": s.id, "key": s.key, "name": s.name} for s in sensors.values() if s.enabled and s.stale]
    warnings: list[str] = []
    unacked = sum(1 for a in alarms if not a["acked"])
    if unacked:
        warnings.append(f"{unacked} ta kvitlanmagan alarm")
    if any(w["overdue"] for w in work_orders):
        warnings.append(f"{sum(1 for w in work_orders if w['overdue'])} ta muddati o'tgan ish buyrug'i")
    if pending:
        warnings.append(f"{len(pending)} ta yakunlanmagan buyruq (pending/sent/tasdiq/mismatch)")
    if overrides:
        warnings.append(f"{len(overrides)} ta blokirovka chetlab o'tish — qabul qiluvchi bilishi shart")
    if modes:
        warnings.append(f"{len(modes)} ta shelved/OOS/o'chirilgan nuqta")
    if stale:
        warnings.append(f"{len(stale)} ta aloqasiz sensor")
    return {
        "since": since.isoformat(),
        "at": now.isoformat(),
        "alarms": alarms,
        "unacked": unacked,
        "work_orders": work_orders,
        "interlock_overrides": overrides,
        "alarm_modes": modes,
        "pending_commands": pending,
        "stale_sensors": stale,
        "warnings": warnings,
    }


def shift_start(db: Session, project_id: int, now: datetime | None = None) -> datetime:
    """Joriy smena boshi: oxirgi qabul qilingan topshirish vaqti, bo'lmasa 12 soat oldin."""
    now = now or datetime.now(timezone.utc)
    last = (
        db.query(ShiftHandover)
        .filter(ShiftHandover.project_id == project_id, ShiftHandover.received_at.isnot(None))
        .order_by(ShiftHandover.id.desc())
        .first()
    )
    return _aware(last.received_at) if last else now - timedelta(hours=12)


def handover_out(h: ShiftHandover) -> dict:
    return {
        "id": h.id,
        "project_id": h.project_id,
        "status": h.status,
        "since": _aware(h.since).isoformat(),
        "summary": h.summary,
        "notes": h.notes,
        "handed_by": h.handed_by,
        "handed_by_username": h.hander.username if h.hander else None,
        "handed_at": _aware(h.handed_at).isoformat() if h.handed_at else None,
        "received_by": h.received_by,
        "received_by_username": h.receiver.username if h.receiver else None,
        "received_at": _aware(h.received_at).isoformat() if h.received_at else None,
        "receive_notes": h.receive_notes,
        "warnings": (h.summary or {}).get("warnings", []),
    }


def feed(db: Session, project_id: int, since: datetime, until: datetime, limit: int = 500) -> list[dict]:
    """Smena hodisalari tasmasi: alarm + SOE (soe.timeline) + buyruqlar + jurnal yozuvlari, eng yangisi birinchi."""
    out = soe.timeline(db, project_id, since, until, limit)
    sensors = {s.id: s for s in db.query(Sensor).filter_by(project_id=project_id).all()}
    for c in db.query(Command).filter(Command.project_id == project_id, Command.created_at >= since, Command.created_at < until).order_by(Command.id.desc()).limit(limit).all():
        t = _aware(c.created_at)
        s = sensors.get(c.sensor_id)
        out.append({"type": "command", "id": c.id, "source": "command", "point": s.key if s else str(c.sensor_id), "state": f"{c.value:g} {s.unit if s else ''} → {c.status.value}", "ts": t.isoformat(timespec="milliseconds"), "ts_ms": int(t.timestamp() * 1000), "quality": "good", "raw": {"note": c.note, "result": c.result, "author": c.author.username if c.author else None}})
    for j in db.query(JournalEntry).filter(JournalEntry.project_id == project_id, JournalEntry.created_at >= since, JournalEntry.created_at < until).order_by(JournalEntry.id.desc()).limit(limit).all():
        t = _aware(j.created_at)
        out.append({"type": "journal", "id": j.id, "source": j.kind, "point": j.author.username if j.author else "", "state": j.text, "ts": t.isoformat(timespec="milliseconds"), "ts_ms": int(t.timestamp() * 1000), "quality": "good", "raw": None})
    out.sort(key=lambda r: (r["ts_ms"], r["id"]), reverse=True)
    return out[:limit]
