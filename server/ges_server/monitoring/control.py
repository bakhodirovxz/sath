"""Supervisory control va smena jurnali.

Buyruqlar — select-before-operate (IEC 60870-5-101/104 va ISA-101 amaliyoti, B2):
  1. `POST /commands/select` — sensor va qiymat tekshiriladi (konvert B1), qisqa muddatli (30 s)
     imzolangan `select_token` qaytadi; hech narsa yozilmaydi.
  2. `POST /commands/execute` — token bilan; qiymat/sensor/foydalanuvchi tokenga bog'langan.
     `requires_dual_approval` sensorlarda buyruq `pending_approval` — boshqa operator
     `POST /commands/{id}/approve` qilmaguncha gateway ga bermaydi; muallif o'zini tasdiqlay olmaydi.
  3. Gateway `POST /commands/claim` (X-Ingest-Key) bilan navbatni oladi (sent), SCADA ga yozadi,
     `ack` (acked/failed) va yozgandan keyin o'qigan qiymatni `readback` ga yuboradi — server
     kutilgan va haqiqiy qiymatni solishtiradi (`readback_tolerance`), farq bo'lsa `mismatch` +
     bildirishnoma. Har qadam audit va jonli oqimda. Smena jurnali: dispetcher yozuvlari.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError

from .. import audit, notifications
from ..auth.deps import DB, CurrentUser, get_project_role, has_role, require_project_role
from ..config import get_settings
from ..orm import (
    Command,
    CommandStatus,
    Interlock,
    JournalEntry,
    Project,
    Role,
    Sensor,
    ShiftHandover,
    utcnow,
)
from . import interlock, keys, live, shift

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
    approved_by_username: str | None = None
    approved_at: datetime | None = None
    readback_value: float | None = None
    readback_at: datetime | None = None


class CommandAck(BaseModel):
    status: Literal["sent", "acked", "failed"]
    result: str = Field("", max_length=400)


class InterlockResult(BaseModel):
    interlock_id: int
    name: str
    ok: bool
    message: str


class SelectOut(BaseModel):
    select_token: str
    sensor_id: int
    value: float
    expires_at: datetime
    requires_approval: bool
    interlocks: list[InterlockResult] = []
    override: bool = False


class ExecuteIn(BaseModel):
    select_token: str
    note: str = Field("", max_length=200)


class InterlockIn(BaseModel):
    sensor_id: int
    name: str = Field(min_length=1, max_length=128)
    condition: str = Field(min_length=1, max_length=1000)
    message: str = Field("", max_length=300)
    enabled: bool = True


class InterlockPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    condition: str | None = Field(None, min_length=1, max_length=1000)
    message: str | None = Field(None, max_length=300)
    enabled: bool | None = None


class InterlockOut(BaseModel):
    id: int
    project_id: int
    sensor_id: int
    sensor_key: str
    name: str
    condition: str
    message: str
    enabled: bool
    current_ok: bool | None = None  # hozirgi qiymatlar bilan (value siz) baholash
    current_message: str = ""


class ReadbackIn(BaseModel):
    value: float
    ts: datetime | None = None

    @field_validator("value")
    @classmethod
    def _finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("qiymat chekli son bo'lishi kerak")
        return v


SELECT_TTL_S = 30


def _sign(payload: bytes) -> str:
    key = get_settings().ensure_secret_key().encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()[:32]


def make_select_token(
    user_id: int, project_id: int, sensor_id: int, value: float, override: bool = False
) -> tuple[str, datetime]:
    """Imzolangan, holatsiz token: (user, project, sensor, value, exp, override) — 30 s."""
    exp = utcnow() + timedelta(seconds=SELECT_TTL_S)
    body = json.dumps(
        {
            "u": user_id,
            "p": project_id,
            "s": sensor_id,
            "v": value,
            "e": int(exp.timestamp()),
            "o": bool(override),
        },
        separators=(",", ":"),
    ).encode("utf-8")
    b = base64.urlsafe_b64encode(body).decode("ascii").rstrip("=")
    return f"{b}.{_sign(body)}", exp


def parse_select_token(token: str, user_id: int, project_id: int) -> dict:
    """Tekshiradi: imzo, muddat, foydalanuvchi va loyiha mosligi. Xato → HTTPException 400/403."""
    try:
        b, sig = token.split(".", 1)
        body = base64.urlsafe_b64decode(b + "=" * (-len(b) % 4))
    except (ValueError, TypeError) as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "select_token noto'g'ri") from e
    if not hmac.compare_digest(sig, _sign(body)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "select_token imzosi noto'g'ri")
    d = json.loads(body)
    if d["u"] != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "select_token boshqa foydalanuvchiniki")
    if d["p"] != project_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "select_token boshqa loyihaniki")
    if int(utcnow().timestamp()) > d["e"]:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"select muddati ({SELECT_TTL_S} s) o'tdi — qayta tanlang"
        )
    return d


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
        approved_by_username=c.approver.username if c.approver is not None else None,
        approved_at=_aware(c.approved_at),
        readback_value=c.readback_value,
        readback_at=_aware(c.readback_at),
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
    before_id: int | None = None,
):
    """Buyruqlar tarixi; kursor `before_id` (id kamayish tartibi) — izchil sahifalash (D4)."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    q = db.query(Command).filter(Command.project_id == project.id, Command.created_at >= since)
    if before_id is not None:
        q = q.filter(Command.id < before_id)
    return [_out(c) for c in q.order_by(Command.id.desc()).limit(limit).all()]


def _target_sensor(db, project: Project, sensor_id: int, value: float) -> Sensor:
    s = db.get(Sensor, sensor_id)
    if s is None or s.project_id != project.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sensor topilmadi")
    if not s.writable:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Bu nuqta boshqaruvga ochiq emas (writable)"
        )
    if not s.enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sensor o'chirilgan")
    check_envelope(db, s, value)
    return s


@router.post("/projects/{project_id}/commands", status_code=410)
def create_command_legacy(project: OperatorProject):
    """Bir bosqichli buyruq olib tashlandi (B2): `POST .../commands/select` → `.../commands/execute`."""
    raise HTTPException(
        status.HTTP_410_GONE,
        "Buyruq ikki bosqichli: /commands/select (token) → /commands/execute (select-before-operate)",
    )


def _interlock_results(db, s: Sensor, value: float) -> list[InterlockResult]:
    return [
        InterlockResult(interlock_id=r.interlock_id, name=r.name, ok=r.ok, message=r.message)
        for r in interlock.evaluate(db, s, value)
    ]


@router.post("/projects/{project_id}/commands/select", response_model=SelectOut)
def select_command(
    body: CommandIn,
    project: OperatorProject,
    user: CurrentUser,
    db: DB,
    override: bool = Query(False, description="Blokirovkani chetlab o'tish (faqat tasdiqlovchi)"),
    override_reason: str = Query("", max_length=300),
):
    """1-bosqich: tanlash — sensor/qiymat tekshiriladi, blokirovkalar baholanadi (natija javobda),
    30 s li imzolangan token qaytadi, yozilmaydi. Blokirovka bajarilmasa 409 (sabablar bilan);
    `override=true` — faqat tasdiqlovchi, sabab majburiy, audit + dispetcherlarga alarm."""
    s = _target_sensor(db, project, body.sensor_id, body.value)
    results = _interlock_results(db, s, body.value)
    blocked = [r for r in results if not r.ok]
    if blocked and override:
        if not has_role(get_project_role(db, project.id, user), Role.approver):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Blokirovkani chetlab o'tish — faqat tasdiqlovchi"
            )
        if len(override_reason.strip()) < 5:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Chetlab o'tish sababi majburiy (kamida 5 belgi)"
            )
        audit.log(
            db,
            user_id=user.id,
            action="command.interlock_override",
            target_type="sensor",
            target_id=s.id,
            project_id=project.id,
            detail={
                "sensor": s.key,
                "value": body.value,
                "reason": override_reason.strip(),
                "blocked": [f"{r.name}: {r.message}" for r in blocked],
            },
        )
        notifications.push(
            db,
            notifications.member_ids(db, project.id, Role.operator, exclude=user.id, at_least=True),
            "alarm",
            f"Blokirovka chetlab o'tildi: {s.name} → {body.value:g} {s.unit}",
            f"{user.username}: {override_reason.strip()} — {'; '.join(r.name for r in blocked)}",
            f"/projects/{project.id}/dashboard",
        )
        db.commit()
    elif blocked:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Blokirovka: " + "; ".join(f"{r.name} — {r.message}" for r in blocked),
        )
    token, exp = make_select_token(user.id, project.id, s.id, body.value, bool(blocked and override))
    audit.log(
        db,
        user_id=user.id,
        action="command.select",
        target_type="sensor",
        target_id=s.id,
        project_id=project.id,
        detail={"sensor": s.key, "value": body.value, "override": bool(blocked and override)},
    )
    db.commit()
    return SelectOut(
        select_token=token,
        sensor_id=s.id,
        value=body.value,
        expires_at=exp,
        requires_approval=bool(s.requires_dual_approval),
        interlocks=results,
        override=bool(blocked and override),
    )


@router.post("/projects/{project_id}/commands/execute", response_model=CommandOut, status_code=201)
def execute_command(body: ExecuteIn, project: OperatorProject, user: CurrentUser, db: DB):
    """2-bosqich: bajarish — faqat amaldagi select_token bilan (sensor va qiymat tokenda). Sensor
    `requires_dual_approval` bo'lsa buyruq `pending_approval` — boshqa operator tasdiqlaydi."""
    tok = parse_select_token(body.select_token, user.id, project.id)
    s = _target_sensor(db, project, int(tok["s"]), float(tok["v"]))
    value = float(tok["v"])
    # Blokirovkalar select dan keyin o'zgargan bo'lishi mumkin — execute da qayta baholanadi
    blocked = [r for r in _interlock_results(db, s, value) if not r.ok]
    if blocked and not tok.get("o"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Blokirovka: " + "; ".join(f"{r.name} — {r.message}" for r in blocked),
        )
    for c in expire_pending(db, project.id):  # eskirgan pending sensorni band qilmasin
        _publish(c)
    open_ = (
        db.query(Command)
        .filter(
            Command.sensor_id == s.id,
            Command.status.in_(
                [CommandStatus.pending, CommandStatus.sent, CommandStatus.pending_approval]
            ),
        )
        .first()
    )
    if open_ is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Buyruq #{open_.id} hali bajarilmagan (kuting yoki bekor qiling)",
        )
    needs_approval = bool(s.requires_dual_approval)
    c = Command(
        project_id=project.id,
        sensor_id=s.id,
        value=value,
        note=body.note,
        created_by=user.id,
        status=CommandStatus.pending_approval if needs_approval else CommandStatus.pending,
        # TTL tasdiqdan keyin boshlanadi (approve da qayta qo'yiladi)
        expires_at=None if needs_approval else utcnow() + timedelta(seconds=s.command_ttl_s or 300),
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
        detail={
            "sensor": s.key,
            "value": value,
            "note": body.note,
            "approval": needs_approval,
            "interlock_override": bool(tok.get("o")),
        },
    )
    if needs_approval:
        # Tasdiqlashi mumkin bo'lganlar (operator+, muallifdan tashqari)
        notifications.push(
            db,
            notifications.member_ids(db, project.id, Role.operator, exclude=user.id, at_least=True),
            "system",
            f"Tasdiq kutilmoqda: {s.name} → {value:g} {s.unit}",
            f"{user.username}: {body.note} — ikkinchi kishi tasdig'i kerak",
            f"/projects/{project.id}/dashboard",
        )
    else:
        notifications.push(
            db,
            [uid for uid in notifications.member_ids(db, project.id, Role.approver, exclude=user.id)],
            "system",
            f"Buyruq: {s.name} → {value:g} {s.unit}",
            f"{user.username}: {body.note}",
            f"/projects/{project.id}/dashboard",
        )
    db.commit()
    db.refresh(c)
    _publish(c)
    return _out(c)


@router.post("/commands/{command_id}/approve", response_model=CommandOut)
def approve_command(command_id: int, user: CurrentUser, db: DB):
    """Ikki kishi tasdig'i: boshqa operator+ tasdiqlaydi; muallif o'zini tasdiqlay olmaydi.
    Tasdiqdan keyin buyruq `pending` (TTL boshlanadi) va gateway ga beriladi."""
    c = db.get(Command, command_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyruq topilmadi")
    if not has_role(get_project_role(db, c.project_id, user), Role.operator):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Operator huquqi kerak")
    if c.status != CommandStatus.pending_approval:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Buyruq holati {c.status.value} — tasdiq kutilmayapti")
    if c.created_by == user.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Muallif o'z buyrug'ini tasdiqlay olmaydi (ikki kishi qoidasi)"
        )
    now = utcnow()
    c.status, c.updated_at = CommandStatus.pending, now
    c.approved_by, c.approved_at = user.id, now
    c.expires_at = now + timedelta(seconds=c.sensor.command_ttl_s or 300)
    audit.log(
        db,
        user_id=user.id,
        action="command.approve",
        target_type="command",
        target_id=c.id,
        project_id=c.project_id,
        detail={"sensor": c.sensor.key, "value": c.value, "author": c.created_by},
    )
    db.commit()
    _publish(c)
    return _out(c)


@router.post("/commands/{command_id}/cancel", response_model=CommandOut)
def cancel_command(command_id: int, user: CurrentUser, db: DB):
    c = db.get(Command, command_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyruq topilmadi")
    if not has_role(get_project_role(db, c.project_id, user), Role.operator):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Operator huquqi kerak")
    if c.status not in (CommandStatus.pending, CommandStatus.pending_approval):
        # sent — gateway allaqachon olgan, PLC ga yozilishi mumkin: bekor qilish yolg'on xavfsizlik beradi;
        # javob kelmasa watchdog (command_sent_timeout_s) failed ga o'tkazadi
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Faqat kutayotgan (pending / tasdiq kutayotgan) buyruq bekor qilinadi"
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


def _gateway_project(db, project_id: int, x_command_key: str | None) -> Project:
    """Buyruq kanali faqat X-Command-Key bilan (B3); ingest kaliti → 403 (audit: gateway.key_misuse)."""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Loyiha topilmadi")
    keys.verify(db, project, "command", x_command_key)
    return project


@router.get("/projects/{project_id}/commands/pending", status_code=410)
def pending_commands_legacy(project_id: int):
    """Holatni o'zgartiradigan GET olib tashlandi (proksi qayta urinishi navbatni bo'shatardi) —
    gateway `POST .../commands/claim` ishlatadi."""
    raise HTTPException(status.HTTP_410_GONE, "POST /commands/claim ishlating")


@router.post("/projects/{project_id}/commands/claim")
def claim_commands(
    project_id: int, db: DB, x_command_key: Annotated[str | None, Header()] = None
):
    """Gateway uchun: kutayotgan buyruqlarni olish (X-Command-Key). Olingach `sent` ga o'tadi."""
    project = _gateway_project(db, project_id, x_command_key)
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
    db.commit()  # buyruqlar + kalitning last_used_at
    for c in rows + expired:
        _publish(c)
    return out


@router.post("/commands/{command_id}/ack", response_model=CommandOut)
def ack_command(
    command_id: int,
    body: CommandAck,
    db: DB,
    x_command_key: Annotated[str | None, Header()] = None,
):
    """Gateway natijasi: acked (bajarildi) / failed (xato) — X-Command-Key bilan."""
    c = db.get(Command, command_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyruq topilmadi")
    _gateway_project(db, c.project_id, x_command_key)
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


@router.post("/commands/{command_id}/readback", response_model=CommandOut)
def readback_command(
    command_id: int,
    body: ReadbackIn,
    db: DB,
    x_command_key: Annotated[str | None, Header()] = None,
):
    """Gateway yozgandan keyin PLC dan o'qigan haqiqiy qiymat. Kutilgan bilan solishtiriladi
    (`readback_tolerance`, nisbiy; ±1e-6 absolyut): mos → acked (readback bilan), farq → mismatch
    + operator/tasdiqlovchilarga bildirishnoma (alarm ta'rifi C1 da)."""
    c = db.get(Command, command_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyruq topilmadi")
    _gateway_project(db, c.project_id, x_command_key)
    if c.status not in (CommandStatus.sent, CommandStatus.acked):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Buyruq holati {c.status.value} — readback kutilmaydi")
    now = utcnow()
    c.readback_value, c.readback_at, c.updated_at = body.value, now, now
    tol = max(abs(c.value) * (c.sensor.readback_tolerance or 0.0), 1e-6)
    ok = abs(body.value - c.value) <= tol
    c.status = CommandStatus.acked if ok else CommandStatus.mismatch
    if not ok:
        c.result = f"readback {body.value:g} ≠ buyruq {c.value:g} (chegara ±{tol:g})"
    audit.log(
        db,
        user_id=None,
        action="command.readback" if ok else "command.mismatch",
        target_type="command",
        target_id=c.id,
        project_id=c.project_id,
        detail={"expected": c.value, "actual": body.value, "tolerance": tol},
    )
    if not ok:
        notifications.push(
            db,
            sorted(
                set(notifications.member_ids(db, c.project_id, Role.operator, at_least=True))
                | {c.created_by}
            ),
            "alarm",
            f"Buyruq mos kelmadi: {c.sensor.name}",
            c.result,
            f"/projects/{c.project_id}/dashboard",
        )
    db.commit()
    _publish(c)
    return _out(c)


# ---------- Blokirovkalar (interlock) ----------

EngineerProject = Annotated[Project, Depends(require_project_role(Role.engineer))]


def _il_out(db, il: Interlock) -> InterlockOut:
    cur_ok, cur_msg = None, ""
    try:
        env = interlock.env_for(db, il.project_id)
        from ges_sim import custom as _custom

        cur_ok = bool(_custom.evaluate(_custom.compile_expr(il.condition), env))
        cur_msg = "" if cur_ok else (il.message or "shart bajarilmayapti")
    except NameError as e:
        cur_ok, cur_msg = None, f"baholab bo'lmadi: {e}"
    except (ValueError, TypeError, ArithmeticError) as e:
        cur_ok, cur_msg = None, f"ifoda xatosi: {e}"
    return InterlockOut(
        id=il.id,
        project_id=il.project_id,
        sensor_id=il.sensor_id,
        sensor_key=il.sensor.key,
        name=il.name,
        condition=il.condition,
        message=il.message,
        enabled=il.enabled,
        current_ok=cur_ok,
        current_message=cur_msg,
    )


@router.get("/projects/{project_id}/interlocks", response_model=list[InterlockOut])
def list_interlocks(project: ViewerProject, db: DB):
    rows = db.query(Interlock).filter_by(project_id=project.id).order_by(Interlock.id).all()
    return [_il_out(db, il) for il in rows]


@router.get("/projects/{project_id}/interlocks/variables")
def interlock_variables(project: ViewerProject, db: DB):
    """Ifodada ishlatiladigan o'zgaruvchilar: sensor kaliti → identifikator, joriy qiymat (ishonchli bo'lsa)."""
    env = interlock.env_for(db, project.id)
    return [
        {"key": s.key, "var": interlock.var_name(s.key), "value": env.get(interlock.var_name(s.key))}
        for s in db.query(Sensor).filter_by(project_id=project.id, enabled=True).order_by(Sensor.key).all()
    ] + [{"key": "(buyruq qiymati)", "var": "value", "value": None}]


@router.post("/projects/{project_id}/interlocks", response_model=InterlockOut, status_code=201)
def create_interlock(body: InterlockIn, project: EngineerProject, user: CurrentUser, db: DB):
    s = db.get(Sensor, body.sensor_id)
    if s is None or s.project_id != project.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sensor topilmadi")
    if not s.writable:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Blokirovka faqat boshqariladigan (writable) sensorga")
    try:
        interlock.validate(body.condition)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Shart ifodasi: {e}") from e
    il = Interlock(
        project_id=project.id,
        sensor_id=s.id,
        name=body.name,
        condition=body.condition,
        message=body.message,
        enabled=body.enabled,
        created_by=user.id,
    )
    db.add(il)
    db.flush()
    audit.log(
        db,
        user_id=user.id,
        action="interlock.create",
        target_type="interlock",
        target_id=il.id,
        project_id=project.id,
        detail={"sensor": s.key, "name": body.name, "condition": body.condition},
    )
    db.commit()
    db.refresh(il)
    return _il_out(db, il)


@router.patch("/interlocks/{interlock_id}", response_model=InterlockOut)
def update_interlock(interlock_id: int, body: InterlockPatch, user: CurrentUser, db: DB):
    il = db.get(Interlock, interlock_id)
    if il is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Blokirovka topilmadi")
    if not has_role(get_project_role(db, il.project_id, user), Role.engineer):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Muhandis huquqi kerak")
    changes = body.model_dump(exclude_none=True)
    if "condition" in changes:
        try:
            interlock.validate(changes["condition"])
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Shart ifodasi: {e}") from e
    for k, v in changes.items():
        setattr(il, k, v)
    audit.log(
        db,
        user_id=user.id,
        action="interlock.update",
        target_type="interlock",
        target_id=il.id,
        project_id=il.project_id,
        detail=changes,
    )
    db.commit()
    return _il_out(db, il)


@router.delete("/interlocks/{interlock_id}", status_code=204)
def delete_interlock(interlock_id: int, user: CurrentUser, db: DB):
    il = db.get(Interlock, interlock_id)
    if il is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Blokirovka topilmadi")
    if not has_role(get_project_role(db, il.project_id, user), Role.engineer):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Muhandis huquqi kerak")
    audit.log(
        db,
        user_id=user.id,
        action="interlock.delete",
        target_type="interlock",
        target_id=il.id,
        project_id=il.project_id,
        detail={"name": il.name},
    )
    db.delete(il)
    db.commit()


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
    before_id: int | None = None,
):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    q = db.query(JournalEntry).filter(JournalEntry.project_id == project.id, JournalEntry.created_at >= since)
    if before_id is not None:
        q = q.filter(JournalEntry.id < before_id)
    rows = q.order_by(JournalEntry.id.desc()).limit(limit).all()
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


# ---------- Smena topshirish (F9) ----------


class HandoverIn(BaseModel):
    notes: str = Field("", max_length=4000)
    # Ogohlantirishlar bo'lsa (kvitlanmagan alarm, yakunlanmagan buyruq …) topshiruvchi ularni ko'rganini tasdiqlaydi
    acknowledge_warnings: bool = False


class ReceiveIn(BaseModel):
    notes: str = Field("", max_length=4000)


@router.get("/projects/{project_id}/shift/snapshot")
def shift_snapshot(project: ViewerProject, db: DB):
    """Joriy smena topshirish varaqasi mazmuni (avtomatik) — imzosiz ko'rish."""
    return shift.snapshot(db, project.id, shift.shift_start(db, project.id))


@router.get("/projects/{project_id}/shift/handovers")
def list_handovers(project: ViewerProject, db: DB, limit: int = Query(20, gt=0, le=200)):
    rows = db.query(ShiftHandover).filter_by(project_id=project.id).order_by(ShiftHandover.id.desc()).limit(limit).all()
    return [shift.handover_out(h) for h in rows]


@router.post("/projects/{project_id}/shift/handover", status_code=201)
def create_handover(body: HandoverIn, project: OperatorProject, user: CurrentUser, db: DB):
    """Smenani topshirish (operator+): varaqa avtomatik to'ldiriladi, topshiruvchi imzosi (audit). Ogohlantirish
    bo'lsa `acknowledge_warnings=true` bo'lmasa 409 — yakunlanmagan ishlar ko'rilmay topshirilmaydi."""
    open_h = db.query(ShiftHandover).filter_by(project_id=project.id, status="handed").first()
    if open_h is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Avvalgi topshirish (#{open_h.id}) hali qabul qilinmagan")
    since = shift.shift_start(db, project.id)
    summ = shift.snapshot(db, project.id, since)
    if summ["warnings"] and not body.acknowledge_warnings:
        raise HTTPException(status.HTTP_409_CONFLICT, "Topshirish yakunlanmagan: " + "; ".join(summ["warnings"]) + " — ko'rib chiqib, tasdiqlang (acknowledge_warnings)")
    h = ShiftHandover(project_id=project.id, status="handed", since=since, summary=summ, notes=body.notes, handed_by=user.id, handed_at=utcnow())
    db.add(h)
    db.flush()
    db.add(JournalEntry(project_id=project.id, user_id=user.id, kind="shift_end", text=f"Smenani topshirdim (varaqa #{h.id}): {body.notes}"))
    audit.log(
        db,
        user_id=user.id,
        action="shift.handover",
        target_type="shift_handover",
        target_id=h.id,
        project_id=project.id,
        detail={"warnings": summ["warnings"], "unacked": summ["unacked"], "pending_commands": len(summ["pending_commands"]), "acknowledged": body.acknowledge_warnings},
    )
    db.commit()
    return shift.handover_out(h)


@router.post("/shift/handovers/{handover_id}/receive")
def receive_handover(handover_id: int, body: ReceiveIn, user: CurrentUser, db: DB):
    """Smenani qabul qilish (operator+, topshiruvchidan boshqa shaxs) — ikkinchi imzo (audit)."""
    h = db.get(ShiftHandover, handover_id)
    if h is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topshirish topilmadi")
    if not has_role(get_project_role(db, h.project_id, user), Role.operator):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Operator huquqi kerak")
    if h.status != "handed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Allaqachon qabul qilingan")
    if h.handed_by == user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Topshiruvchi o'zi qabul qila olmaydi (ikki imzo)")
    h.status, h.received_by, h.received_at, h.receive_notes = "received", user.id, utcnow(), body.notes
    db.add(JournalEntry(project_id=h.project_id, user_id=user.id, kind="shift_start", text=f"Smenani qabul qildim (varaqa #{h.id}): {body.notes}"))
    audit.log(
        db,
        user_id=user.id,
        action="shift.receive",
        target_type="shift_handover",
        target_id=h.id,
        project_id=h.project_id,
        detail={"handed_by": h.handed_by, "warnings": (h.summary or {}).get("warnings", [])},
    )
    db.commit()
    return shift.handover_out(h)


@router.get("/projects/{project_id}/shift/feed")
def shift_feed(project: ViewerProject, db: DB, hours: float = Query(12, gt=0, le=24 * 31), limit: int = Query(500, gt=0, le=5000)):
    """Smena hodisalari tasmasi: alarm, buyruq, jurnal izohi, SOE — bitta xronologiya."""
    now = datetime.now(timezone.utc)
    return shift.feed(db, project.id, now - timedelta(hours=hours), now, limit)
