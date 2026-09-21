"""Supervisory control va smena jurnali.

Buyruqlar: dispetcher (operator+) yozish mumkin bo'lgan sensorga (setpoint/rele) qiymat yuboradi →
pending; gateway X-Ingest-Key bilan navbatni oladi (sent), SCADA ga yozadi va natijani qaytaradi
(acked/failed). Har qadam audit va jonli oqimda. Smena jurnali: dispetcher yozuvlari.
"""

from __future__ import annotations

import math
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError

from .. import audit, notifications
from ..auth.deps import DB, CurrentUser, get_project_role, has_role, require_project_role
from ..config import get_settings
from ..orm import Command, CommandStatus, JournalEntry, Project, Role, Sensor, utcnow
from . import live

router = APIRouter(prefix="/api", tags=["control"])

ViewerProject = Annotated[Project, Depends(require_project_role(Role.viewer))]
OperatorProject = Annotated[Project, Depends(require_project_role(Role.operator))]


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------- Buyruqlar ----------


class CommandIn(BaseModel):
    sensor_id: int
    value: float
    note: str = Field("", max_length=200)

    @field_validator("value")
    @classmethod
    def _finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("qiymat chekli son bo'lishi kerak (NaN/inf emas)")
        return v


class CommandOut(BaseModel):
    id: int
    sensor_id: int
    sensor_key: str
    sensor_name: str
    unit: str
    value: float
    note: str
    status: CommandStatus
    result: str
    author_username: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
    sent_at: datetime | None = None


class CommandAck(BaseModel):
    status: Literal["sent", "acked", "failed"]
    result: str = Field("", max_length=400)


def _out(c: Command) -> CommandOut:
    return CommandOut(
        id=c.id,
        sensor_id=c.sensor_id,
        sensor_key=c.sensor.key,
        sensor_name=c.sensor.name,
        unit=c.sensor.unit,
        value=c.value,
        note=c.note,
        status=c.status,
        result=c.result,
        author_username=c.author.username,
        created_at=_aware(c.created_at),
        updated_at=_aware(c.updated_at),
        expires_at=_aware(c.expires_at),
        sent_at=_aware(c.sent_at),
    )


def check_envelope(db, s: Sensor, value: float) -> None:
    """B1: diapazon va o'zgarish tezligi — sensor konverti. Buzilsa HTTPException 400."""
    if s.min_setpoint is not None and value < s.min_setpoint:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Qiymat {value:g} ruxsat etilgan minimum {s.min_setpoint:g} {s.unit} dan kichik",
        )
    if s.max_setpoint is not None and value > s.max_setpoint:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Qiymat {value:g} ruxsat etilgan maksimum {s.max_setpoint:g} {s.unit} dan katta",
        )
    if s.max_rate_per_min is not None and s.max_rate_per_min > 0:
        # Oxirgi bajarilgan/yuborilgan buyruq (yoki o'lchov) ga nisbatan tezlik
        last = (
            db.query(Command)
            .filter(
                Command.sensor_id == s.id,
                Command.status.in_([CommandStatus.acked, CommandStatus.sent, CommandStatus.pending]),
            )
            .order_by(Command.id.desc())
            .first()
        )
        ref_value, ref_ts = (last.value, last.created_at) if last else (s.last_value, s.last_ts)
        if ref_value is not None and ref_ts is not None:
            minutes = max((utcnow() - _aware(ref_ts)).total_seconds() / 60, 1.0)
            rate = abs(value - ref_value) / minutes
            if rate > s.max_rate_per_min:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"O'zgarish tezligi {rate:.3g} {s.unit}/min > ruxsat {s.max_rate_per_min:g} "
                    f"(oxirgi qiymat {ref_value:g}) — bosqichma-bosqich o'zgartiring",
                )


def expire_pending(db, project_id: int | None = None) -> list[Command]:
    """TTL o'tgan pending buyruqlar → expired (gateway ga berilmaydi)."""
    now = utcnow()
    q = db.query(Command).filter(
        Command.status == CommandStatus.pending, Command.expires_at.isnot(None)
    )
    if project_id is not None:
        q = q.filter(Command.project_id == project_id)
    out = []
    for c in q.all():
        if _aware(c.expires_at) <= now:
            c.status, c.updated_at = CommandStatus.expired, now
            c.result = "TTL o'tdi — gateway olmadi"
            audit.log(
                db,
                user_id=None,
                action="command.expired",
                target_type="command",
                target_id=c.id,
                project_id=c.project_id,
            )
            out.append(c)
    if out:
        db.flush()  # autoflush=False: keyingi so'rovlar (pending filtri) yangilangan holatni ko'rsin
    return out


def watchdog_sent(db, timeout_s: int) -> list[Command]:
    """`sent` da qotgan buyruqlar (gateway ack/failed qaytarmadi) → failed, sensor bloki ochiladi."""
    now = utcnow()
    out = []
    for c in db.query(Command).filter(Command.status == CommandStatus.sent).all():
        ref = _aware(c.sent_at) or _aware(c.updated_at)
        if ref is not None and (now - ref).total_seconds() > timeout_s:
            c.status, c.updated_at = CommandStatus.failed, now
            c.result = f"watchdog: gateway {timeout_s} s ichida javob bermadi"
            audit.log(
                db,
                user_id=None,
                action="command.failed",
                target_type="command",
                target_id=c.id,
                project_id=c.project_id,
                detail={"result": c.result, "watchdog": True},
            )
            notifications.push(
                db,
                [c.created_by],
                "system",
                f"Buyruq bajarilmadi: {c.sensor.name} → {c.value:g}",
                c.result,
                f"/projects/{c.project_id}/dashboard",
            )
            out.append(c)
    return out


def tick(db) -> int:
    """Fon vazifa: TTL va watchdog. Qaytaradi: o'zgargan buyruqlar soni."""
    changed = expire_pending(db) + watchdog_sent(db, get_settings().command_sent_timeout_s)
    if changed:
        db.commit()
        for c in changed:
            _publish(c)
    return len(changed)


def _publish(c: Command) -> None:
    live.hub.publish(
        c.project_id,
        {"type": "command", "command": _out(c).model_dump(mode="json")},
    )


@router.get("/projects/{project_id}/commands", response_model=list[CommandOut])
def list_commands(
    project: ViewerProject,
    db: DB,
    hours: float = Query(24 * 7, gt=0, le=24 * 366),
    limit: int = Query(200, gt=0, le=2000),
):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    q = (
        db.query(Command)
        .filter(Command.project_id == project.id, Command.created_at >= since)
        .order_by(Command.id.desc())
        .limit(limit)
    )
    return [_out(c) for c in q.all()]


@router.post("/projects/{project_id}/commands", response_model=CommandOut, status_code=201)
def create_command(body: CommandIn, project: OperatorProject, user: CurrentUser, db: DB):
    """Buyruq yuborish (operator+). Sensor `writable` bo'lishi kerak; bitta sensorga bir vaqtda
    faqat bitta bajarilmagan buyruq."""
    s = db.get(Sensor, body.sensor_id)
    if s is None or s.project_id != project.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sensor topilmadi")
    if not s.writable:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Bu nuqta boshqaruvga ochiq emas (writable)"
        )
    if not s.enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sensor o'chirilgan")
    check_envelope(db, s, body.value)
    for c in expire_pending(db, project.id):  # eskirgan pending sensorni band qilmasin
        _publish(c)
    open_ = (
        db.query(Command)
        .filter(
            Command.sensor_id == s.id,
            Command.status.in_([CommandStatus.pending, CommandStatus.sent]),
        )
        .first()
    )
    if open_ is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Buyruq #{open_.id} hali bajarilmagan (kuting yoki bekor qiling)",
        )
    c = Command(
        project_id=project.id,
        sensor_id=s.id,
        value=body.value,
        note=body.note,
        created_by=user.id,
        expires_at=utcnow() + timedelta(seconds=s.command_ttl_s or 300),
    )
    db.add(c)
    try:
        db.flush()
    except IntegrityError:
        # uq_commands_sensor_open: parallel so'rov yuqoridagi tekshiruvdan o'tib ulgurgan (TOCTOU)
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Bu sensorga parallel buyruq yuborildi — qayta tekshiring"
        ) from None
    audit.log(
        db,
        user_id=user.id,
        action="command.create",
        target_type="command",
        target_id=c.id,
        project_id=project.id,
        detail={"sensor": s.key, "value": body.value, "note": body.note},
    )
    notifications.push(
        db,
        [uid for uid in notifications.member_ids(db, project.id, Role.approver, exclude=user.id)],
        "system",
        f"Buyruq: {s.name} → {body.value:g} {s.unit}",
        f"{user.username}: {body.note}",
        f"/projects/{project.id}/dashboard",
    )
    db.commit()
    db.refresh(c)
    _publish(c)
    return _out(c)


@router.post("/commands/{command_id}/cancel", response_model=CommandOut)
def cancel_command(command_id: int, user: CurrentUser, db: DB):
    c = db.get(Command, command_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyruq topilmadi")
    if not has_role(get_project_role(db, c.project_id, user), Role.operator):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Operator huquqi kerak")
    if c.status != CommandStatus.pending:
        # sent — gateway allaqachon olgan, PLC ga yozilishi mumkin: bekor qilish yolg'on xavfsizlik beradi;
        # javob kelmasa watchdog (command_sent_timeout_s) failed ga o'tkazadi
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Faqat kutayotgan (pending) buyruq bekor qilinadi"
        )
    c.status, c.updated_at = CommandStatus.cancelled, utcnow()
    audit.log(
        db,
        user_id=user.id,
        action="command.cancel",
        target_type="command",
        target_id=c.id,
        project_id=c.project_id,
    )
    db.commit()
    _publish(c)
    return _out(c)


def _gateway_project(db, project_id: int, x_ingest_key: str | None) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Loyiha topilmadi")
    ok = bool(project.ingest_key and x_ingest_key) and secrets.compare_digest(
        x_ingest_key, project.ingest_key
    )
    if not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Ingest kaliti noto'g'ri")
    return project


@router.get("/projects/{project_id}/commands/pending")
def pending_commands(project_id: int, db: DB, x_ingest_key: Annotated[str | None, Header()] = None):
    """Gateway uchun: kutayotgan buyruqlar (X-Ingest-Key). Olingach `sent` ga o'tadi."""
    project = _gateway_project(db, project_id, x_ingest_key)
    expired = expire_pending(db, project.id)
    rows = (
        db.query(Command)
        .filter(Command.project_id == project.id, Command.status == CommandStatus.pending)
        .order_by(Command.id)
        .all()
    )
    out = []
    for c in rows:
        c.status, c.updated_at = CommandStatus.sent, utcnow()
        c.sent_at = c.updated_at
        out.append(
            {
                "id": c.id,
                "key": c.sensor.key,
                "value": c.value,
                "protocol": c.sensor.protocol,
                "address": c.sensor.address,
            }
        )
    if rows or expired:
        db.commit()
        for c in rows + expired:
            _publish(c)
    return out


@router.post("/commands/{command_id}/ack", response_model=CommandOut)
def ack_command(
    command_id: int,
    body: CommandAck,
    db: DB,
    x_ingest_key: Annotated[str | None, Header()] = None,
):
    """Gateway natijasi: acked (bajarildi) / failed (xato) — X-Ingest-Key bilan."""
    c = db.get(Command, command_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyruq topilmadi")
    _gateway_project(db, c.project_id, x_ingest_key)
    if c.status in (CommandStatus.cancelled, CommandStatus.acked, CommandStatus.expired):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Buyruq allaqachon {c.status.value}")
    if c.status == CommandStatus.failed and body.status != "failed":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Buyruq watchdog bilan failed — qayta yuboring"
        )
    c.status, c.result, c.updated_at = CommandStatus(body.status), body.result[:400], utcnow()
    audit.log(
        db,
        user_id=None,
        action=f"command.{body.status}",
        target_type="command",
        target_id=c.id,
        project_id=c.project_id,
        detail={"result": body.result[:200]},
    )
    if body.status == "failed":
        notifications.push(
            db,
            [c.created_by],
            "system",
            f"Buyruq bajarilmadi: {c.sensor.name} → {c.value:g}",
            body.result[:200],
            f"/projects/{c.project_id}/dashboard",
        )
    db.commit()
    _publish(c)
    return _out(c)


# ---------- Smena jurnali ----------

JournalKind = Literal["note", "shift_start", "shift_end", "event"]


class JournalIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    kind: JournalKind = "note"


class JournalOut(BaseModel):
    id: int
    kind: str
    text: str
    author_username: str
    created_at: datetime


@router.get("/projects/{project_id}/journal", response_model=list[JournalOut])
def list_journal(
    project: ViewerProject,
    db: DB,
    hours: float = Query(24 * 7, gt=0, le=24 * 366),
    limit: int = Query(200, gt=0, le=2000),
):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = (
        db.query(JournalEntry)
        .filter(JournalEntry.project_id == project.id, JournalEntry.created_at >= since)
        .order_by(JournalEntry.id.desc())
        .limit(limit)
        .all()
    )
    return [
        JournalOut(
            id=r.id,
            kind=r.kind,
            text=r.text,
            author_username=r.author.username,
            created_at=_aware(r.created_at),
        )
        for r in rows
    ]


@router.post("/projects/{project_id}/journal", response_model=JournalOut, status_code=201)
def add_journal(body: JournalIn, project: OperatorProject, user: CurrentUser, db: DB):
    r = JournalEntry(project_id=project.id, user_id=user.id, kind=body.kind, text=body.text)
    db.add(r)
    db.flush()
    audit.log(
        db,
        user_id=user.id,
        action=f"journal.{body.kind}",
        target_type="journal",
        target_id=r.id,
        project_id=project.id,
    )
    db.commit()
    db.refresh(r)
    out = JournalOut(
        id=r.id,
        kind=r.kind,
        text=r.text,
        author_username=user.username,
        created_at=_aware(r.created_at),
    )
    live.hub.publish(project.id, {"type": "journal", "entry": out.model_dump(mode="json")})
    return out
