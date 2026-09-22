"""Monitoring API: sensorlar, o'lchov qabul qilish (HTTP/CSV), tarix, jonli WebSocket, alarmlar."""

from __future__ import annotations

import asyncio
import csv
import io
import math
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, Field, field_serializer, field_validator
from sqlalchemy import func

from .. import audit, ratelimit
from ..auth.deps import DB, CurrentUser, get_project_role, has_role, require_project_role
from ..auth.security import decode_access_token
from ..config import get_settings
from ..db import SessionLocal
from ..orm import AlarmEvent, AlarmState, Project, Reading, Role, Sensor, User, utcnow
from . import alarm_kpi, historian, interlock, keys, live, mqtt_bridge, soe

router = APIRouter(prefix="/api", tags=["monitoring"])
WS_PING_S = 10.0  # WebSocket heartbeat davri (klient 3× davrda xabar kelmasa OFFLINE deb hisoblaydi)

ViewerProject = Annotated[Project, Depends(require_project_role(Role.viewer))]
EngineerProject = Annotated[Project, Depends(require_project_role(Role.engineer))]
ApproverProject = Annotated[Project, Depends(require_project_role(Role.approver))]

Kind = Literal[
    "level", "flow", "power", "pressure", "temperature", "vibration", "status", "position", "value",
    "deviation",  # egizak/model bilan og'ish (%): alarm turi `deviation`
]
Protocol = Literal["http", "csv", "mqtt", "opcua", "modbus", "twin", "ml"]
Priority = Literal["low", "medium", "high", "critical"]
OperatorProject = Annotated[Project, Depends(require_project_role(Role.operator))]


class SensorIn(BaseModel):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.\-/:]+$")
    name: str = Field(min_length=1, max_length=128)
    kind: Kind = "value"
    unit: str = ""
    model_id: int | None = None
    element_guid: str | None = None
    protocol: Protocol = "http"
    address: dict[str, Any] = Field(default_factory=dict)
    low_alarm: float | None = None  # L
    high_alarm: float | None = None  # H
    ll_alarm: float | None = None  # LL
    hh_alarm: float | None = None  # HH
    deadband: float = Field(0.0, ge=0)
    on_delay_s: int = Field(0, ge=0, le=86400)
    off_delay_s: int = Field(0, ge=0, le=86400)
    roc_limit_per_min: float | None = Field(None, gt=0)
    # Suppression-by-design (ISA-18.2): ifoda rost bo'lsa alarm bostiriladi (masalan `AGG1_RUN == 0`)
    suppress_condition: str = ""
    # Arxiv siqishi (D2): o'lik zona (sensor birligida) va majburiy yozuv oralig'i
    archive_deadband: float | None = Field(None, gt=0)
    archive_max_interval_s: int = Field(3600, ge=10, le=86400)
    # Ratsionalizatsiya (ISA-18.2 §10): matnlar; tasdiqlash — POST /sensors/{id}/rationalize
    cause: str = Field("", max_length=2000)
    consequence: str = Field("", max_length=2000)
    corrective_action: str = Field("", max_length=2000)
    response_time_s: int | None = Field(None, gt=0, le=7 * 86400)
    priority_basis: str = Field("", max_length=2000)
    # fizik diapazon: tashqarida quality=bad
    min_raw: float | None = None
    max_raw: float | None = None
    stale_after_s: int = 600

    @field_validator("suppress_condition")
    @classmethod
    def _cond(cls, v: str) -> str:
        v = (v or "").strip()
        if v:
            try:
                interlock.validate(v)
            except ValueError as e:
                raise ValueError(f"suppress_condition: {e}") from e
        return v
    enabled: bool = True
    priority: Priority = "medium"
    writable: bool = False
    # buyruq konverti (writable uchun)
    min_setpoint: float | None = None
    max_setpoint: float | None = None
    max_rate_per_min: float | None = None
    requires_dual_approval: bool = False
    command_ttl_s: int = Field(300, ge=10, le=86400)
    readback_tolerance: float = Field(0.01, ge=0, le=1)


class SensorPatch(BaseModel):
    name: str | None = None
    kind: Kind | None = None
    unit: str | None = None
    model_id: int | None = None
    element_guid: str | None = None
    protocol: Protocol | None = None
    address: dict[str, Any] | None = None
    low_alarm: float | None = None
    high_alarm: float | None = None
    ll_alarm: float | None = None
    hh_alarm: float | None = None
    deadband: float | None = Field(None, ge=0)
    on_delay_s: int | None = Field(None, ge=0, le=86400)
    off_delay_s: int | None = Field(None, ge=0, le=86400)
    roc_limit_per_min: float | None = Field(None, gt=0)
    suppress_condition: str | None = None
    archive_deadband: float | None = Field(None, gt=0)
    archive_max_interval_s: int | None = Field(None, ge=10, le=86400)
    cause: str | None = Field(None, max_length=2000)
    consequence: str | None = Field(None, max_length=2000)
    corrective_action: str | None = Field(None, max_length=2000)
    response_time_s: int | None = Field(None, gt=0, le=7 * 86400)
    priority_basis: str | None = Field(None, max_length=2000)
    min_raw: float | None = None
    max_raw: float | None = None
    stale_after_s: int | None = None

    @field_validator("suppress_condition")
    @classmethod
    def _cond(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if v:
            try:
                interlock.validate(v)
            except ValueError as e:
                raise ValueError(f"suppress_condition: {e}") from e
        return v
    enabled: bool | None = None
    priority: Priority | None = None
    writable: bool | None = None
    min_setpoint: float | None = None
    max_setpoint: float | None = None
    max_rate_per_min: float | None = None
    requires_dual_approval: bool | None = None
    command_ttl_s: int | None = Field(None, ge=10, le=86400)
    readback_tolerance: float | None = Field(None, ge=0, le=1)
    clear_alarms: bool = False  # low/high/ll/hh ni null qilish uchun
    clear_roc: bool = False  # roc_limit_per_min ni null qilish uchun
    clear_archive_deadband: bool = False
    clear_raw_range: bool = False  # min_raw/max_raw ni null qilish uchun
    clear_setpoint_range: bool = False  # min/max_setpoint, max_rate_per_min ni null qilish uchun


class SensorOut(BaseModel):
    id: int
    project_id: int
    model_id: int | None
    key: str
    name: str
    kind: str
    unit: str
    element_guid: str | None
    protocol: str
    address: dict
    low_alarm: float | None
    high_alarm: float | None
    ll_alarm: float | None = None
    hh_alarm: float | None = None
    deadband: float = 0.0
    on_delay_s: int = 0
    off_delay_s: int = 0
    roc_limit_per_min: float | None = None
    suppress_condition: str = ""
    archive_deadband: float | None = None
    archive_max_interval_s: int = 3600
    suppressed: bool = False
    alarm_mode: str = "normal"
    alarm_mode_until: datetime | None = None
    alarm_mode_by: int | None = None
    alarm_mode_reason: str = ""
    alarm_mode_since: datetime | None = None
    cause: str = ""
    consequence: str = ""
    corrective_action: str = ""
    response_time_s: int | None = None
    priority_basis: str = ""
    rationalized_by: int | None = None
    rationalized_at: datetime | None = None
    min_raw: float | None = None
    max_raw: float | None = None
    stale_after_s: int
    enabled: bool
    last_value: float | None
    last_ts: datetime | None
    last_quality: str = "good"
    alarm: AlarmState
    stale: bool = True
    priority: str = "medium"
    writable: bool = False
    min_setpoint: float | None = None
    max_setpoint: float | None = None
    max_rate_per_min: float | None = None
    requires_dual_approval: bool = False
    command_ttl_s: int = 300
    readback_tolerance: float = 0.01

    model_config = {"from_attributes": True}

    @field_serializer("last_ts", "alarm_mode_until", "alarm_mode_since", "rationalized_at", when_used="json")
    def _tz(self, v: datetime | None) -> str | None:
        """SQLite naive UTC ni offset bilan beradi — brauzer lokal vaqt deb o'qimasin (F4: yosh/eskirish to'g'ri)."""
        return live._aware(v).isoformat() if v else None


class ReadingIn(BaseModel):
    """Gateway ma'lumotlari. `value` chekli son bo'lishi shart (NaN/inf/matn → 422 — gateway o'zi
    tozalashi kerak); `ts` tekshiruvi ingest da (yaroqsiz/kelajak/eski → `rejected`)."""

    key: str | None = None
    sensor_id: int | None = None
    value: float
    ts: datetime | float | str | None = None

    @field_validator("value")
    @classmethod
    def _finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("qiymat chekli son bo'lishi kerak (NaN/inf emas)")
        return v
    # QUALITIES (good|uncertain|bad|substituted|manual); yo'q bo'lsa good
    quality: str | None = None
    # manbadagi vaqt tamg'asi (OPC UA SourceTimestamp, gateway o'qish vaqti)
    src_ts: datetime | float | str | None = None


# ---------- Sensorlar ----------


@router.get("/projects/{project_id}/sensors", response_model=list[SensorOut])
def list_sensors(
    project: ViewerProject,
    db: DB,
    model_id: int | None = None,
    limit: int | None = Query(None, gt=0, le=20000),
    after_id: int | None = None,
):
    """Sensorlar: `limit` bo'lmasa hammasi (nom tartibi); kursor `after_id` bilan id tartibi (D4)."""
    q = db.query(Sensor).filter_by(project_id=project.id)
    if model_id is not None:
        q = q.filter((Sensor.model_id == model_id) | (Sensor.model_id.is_(None)))
    if after_id is not None:
        q = q.filter(Sensor.id > after_id).order_by(Sensor.id)
    else:
        q = q.order_by(Sensor.name, Sensor.id)
    if limit is not None:
        q = q.limit(limit)
    return q.all()


@router.post("/projects/{project_id}/sensors", response_model=SensorOut, status_code=201)
def create_sensor(body: SensorIn, project: EngineerProject, user: CurrentUser, db: DB):
    if db.query(Sensor).filter_by(project_id=project.id, key=body.key).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Bunday kalitli sensor mavjud")
    sensor = Sensor(project_id=project.id, **body.model_dump())
    db.add(sensor)
    db.flush()
    audit.log(
        db,
        user_id=user.id,
        action="sensor.create",
        target_type="sensor",
        target_id=sensor.id,
        project_id=project.id,
        detail={"key": sensor.key},
    )
    db.commit()
    mqtt_bridge.refresh()
    live.invalidate_sensors()
    return sensor


class SensorImportIn(BaseModel):
    """SCADA teglar ro'yxati (CSV matni): key;name;kind;unit;protocol;address;element;low;high
    — ustunlar sarlavha bilan, ajratuvchi `;` yoki `,`. address: JSON yoki oddiy matn (mqtt topic / OPC node id /
    modbus register). element: IFC element nomi (yoki GUID) — model oxirgi versiyasidan qidiriladi."""

    csv: str = Field(min_length=1, max_length=2_000_000)
    model_id: int | None = None
    update_existing: bool = True


def _element_names(db, model_id: int | None) -> dict[str, str]:
    """Model oxirgi versiyasi elementlari: nom (kichik harf) → GUID (bog'lash uchun)."""
    if model_id is None:
        return {}
    from ..models import storage
    from ..orm import Model as ModelRow

    m = db.get(ModelRow, model_id)
    if m is None or not m.versions:
        return {}
    try:
        import ifcopenshell

        f = ifcopenshell.open(str(storage.resolve(m.versions[-1].file_sha256)))
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, str] = {}
    for e in f.by_type("IfcProduct"):
        if e.Name:
            out.setdefault(e.Name.strip().lower(), e.GlobalId)
        out[e.GlobalId] = e.GlobalId
    return out


@router.post("/projects/{project_id}/sensors/import")
def import_sensors(body: SensorImportIn, project: EngineerProject, user: CurrentUser, db: DB):
    """Teglar ro'yxatini CSV dan yaratish/yangilash; element nomi bo'yicha 3D ga avtomatik bog'lash."""
    import csv
    import io
    import json as _json

    text = body.csv.lstrip("\ufeff")
    delim = ";" if text.splitlines()[0].count(";") >= text.splitlines()[0].count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    names = _element_names(db, body.model_id)
    kinds = {
        "level",
        "flow",
        "power",
        "pressure",
        "temperature",
        "vibration",
        "status",
        "position",
        "value",
    }
    protocols = {"http", "csv", "mqtt", "opcua", "modbus"}
    created, updated, bound, errors = 0, 0, 0, []
    for i, row in enumerate(reader, start=2):
        r = {
            str(k or "").strip().lower(): (v if isinstance(v, str) else "").strip()
            for k, v in row.items()
        }
        key = r.get("key") or r.get("teg") or r.get("tag")
        if not key:
            errors.append(f"{i}-qator: key yo'q")
            continue
        try:
            kind = r.get("kind", "value").lower() or "value"
            if kind not in kinds:
                kind = "value"
            proto = (r.get("protocol") or "http").lower()
            if proto not in protocols:
                proto = "http"
            addr_raw = r.get("address", "")
            if addr_raw.startswith("{"):
                address = _json.loads(addr_raw)
            elif addr_raw:
                address = {
                    "mqtt": {"topic": addr_raw},
                    "opcua": {"node_id": addr_raw},
                    "modbus": {"register": addr_raw},
                }.get(proto, {"value": addr_raw})
            else:
                address = {}
            elem = r.get("element") or r.get("element_guid") or ""
            guid = (
                names.get(elem.strip().lower())
                or names.get(elem)
                or (elem if len(elem) == 22 else None)
            )
            data = SensorIn(
                key=key,
                name=r.get("name") or key,
                kind=kind,  # type: ignore[arg-type]
                unit=r.get("unit", ""),
                model_id=body.model_id,
                element_guid=guid,
                protocol=proto,  # type: ignore[arg-type]
                address=address,
                low_alarm=float(r["low"]) if r.get("low") else None,
                high_alarm=float(r["high"]) if r.get("high") else None,
                stale_after_s=int(float(r.get("stale_s") or 600)),
            )
        except (ValueError, TypeError, _json.JSONDecodeError) as e:
            errors.append(f"{i}-qator ({key}): {e}")
            continue
        existing = db.query(Sensor).filter_by(project_id=project.id, key=key).first()
        if existing:
            if not body.update_existing:
                continue
            for k, v in data.model_dump().items():
                if k == "element_guid" and v is None:
                    continue
                setattr(existing, k, v)
            updated += 1
        else:
            db.add(Sensor(project_id=project.id, **data.model_dump()))
            created += 1
        if guid:
            bound += 1
    audit.log(
        db,
        user_id=user.id,
        action="sensor.import",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
        detail={"created": created, "updated": updated, "bound": bound, "errors": len(errors)},
    )
    db.commit()
    mqtt_bridge.refresh()
    live.invalidate_sensors()
    return {"created": created, "updated": updated, "bound": bound, "errors": errors[:50]}


def _get_sensor(db, sensor_id: int, user: User, required: Role) -> Sensor:
    s = db.get(Sensor, sensor_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sensor topilmadi")
    if not has_role(get_project_role(db, s.project_id, user), required):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu loyihada ruxsat yo'q")
    return s


@router.patch("/sensors/{sensor_id}", response_model=SensorOut)
def update_sensor(sensor_id: int, body: SensorPatch, user: CurrentUser, db: DB):
    s = _get_sensor(db, sensor_id, user, Role.engineer)
    changes = body.model_dump(
        exclude_none=True,
        exclude={"clear_alarms", "clear_roc", "clear_raw_range", "clear_setpoint_range", "clear_archive_deadband"},
    )
    for k, v in changes.items():
        setattr(s, k, v)
    if body.clear_alarms:
        s.low_alarm = s.high_alarm = s.ll_alarm = s.hh_alarm = None
    if body.clear_roc:
        s.roc_limit_per_min = None
    if body.clear_archive_deadband:
        s.archive_deadband = None
    if body.clear_raw_range:
        s.min_raw = s.max_raw = None
    if body.clear_setpoint_range:
        s.min_setpoint = s.max_setpoint = s.max_rate_per_min = None
    if s.last_value is not None and not s.stale:
        s.alarm = live.evaluate_alarm(s, s.last_value)
        s.alarm_pending = s.alarm_pending_since = None
    if "suppress_condition" in changes:
        live.evaluate_suppression(db, s.project_id, [s])
    if s.rationalized_at is not None and (
        body.clear_alarms
        or body.clear_roc
        or any(k in changes for k in ("low_alarm", "high_alarm", "ll_alarm", "hh_alarm", "roc_limit_per_min", "priority"))
    ):
        s.rationalized_at = s.rationalized_by = None  # chegara/ustuvorlik o'zgardi — qayta ratsionalizatsiya
    audit.log(
        db,
        user_id=user.id,
        action="sensor.update",
        target_type="sensor",
        target_id=s.id,
        project_id=s.project_id,
        detail=changes,
    )
    db.commit()
    mqtt_bridge.refresh()
    live.invalidate_sensors()
    return s


@router.delete("/sensors/{sensor_id}", status_code=204)
def delete_sensor(sensor_id: int, user: CurrentUser, db: DB):
    s = _get_sensor(db, sensor_id, user, Role.approver)
    audit.log(
        db,
        user_id=user.id,
        action="sensor.delete",
        target_type="sensor",
        target_id=s.id,
        project_id=s.project_id,
        detail={"key": s.key},
    )
    db.delete(s)
    db.commit()


# ---------- Ingest ----------


def _key_response(project: Project, kind: str) -> dict:
    inf = keys.info(project, kind)
    out = {
        **inf,
        "url": f"/api/projects/{project.id}/readings"
        if kind == "ingest"
        else f"/api/projects/{project.id}/commands/claim",
        "header": "X-Ingest-Key" if kind == "ingest" else "X-Command-Key",
    }
    out["ingest_key" if kind == "ingest" else "command_key"] = inf["key"]  # eski nom (moslik)
    return out


@router.get("/projects/{project_id}/keys/{kind}")
def get_project_key(
    kind: Literal["ingest", "command"], project: ApproverProject, user: CurrentUser, db: DB
):
    """Gateway kaliti (ingest — X-Ingest-Key, faqat o'lchov; command — X-Command-Key, buyruq kanali).
    Bo'lmasa yaratiladi (365 kun). Har o'qish auditda."""
    keys.ensure(db, project, kind, user.id)
    audit.log(
        db,
        user_id=user.id,
        action=f"project.{kind}_key.read",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
    )
    db.commit()
    return _key_response(project, kind)


@router.post("/projects/{project_id}/keys/{kind}")
def rotate_project_key(
    kind: Literal["ingest", "command"],
    project: ApproverProject,
    user: CurrentUser,
    db: DB,
    ttl_days: int = Query(keys.DEFAULT_TTL_DAYS, ge=0, le=3650, description="0 — muddatsiz"),
):
    keys.rotate(db, project, kind, user.id, ttl_days)
    db.commit()
    return _key_response(project, kind)


@router.get("/projects/{project_id}/ingest-key")
def get_ingest_key(project: ApproverProject, user: CurrentUser, db: DB):
    """Eski manzil — `GET .../keys/ingest` bilan bir xil."""
    return get_project_key("ingest", project, user, db)


@router.post("/projects/{project_id}/ingest-key")
def rotate_ingest_key(project: ApproverProject, user: CurrentUser, db: DB):
    """Eski manzil — `POST .../keys/ingest` bilan bir xil."""
    return rotate_project_key("ingest", project, user, db, keys.DEFAULT_TTL_DAYS)


@router.post("/projects/{project_id}/readings")
def push_readings(
    project_id: int,
    body: list[ReadingIn],
    db: DB,
    x_ingest_key: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
):
    """O'lchovlarni yuborish: yoki X-Ingest-Key (gateway), yoki foydalanuvchi tokeni (muhandis+).
    Loyiha bo'yicha tezlik cheklovi (`rate_ingest_per_min` so'rov/daqiqa) — 429."""
    ratelimit.check("ingest", str(project_id), get_settings().rate_ingest_per_min)
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Loyiha topilmadi")
    ok = False
    if x_ingest_key:
        keys.verify(db, project, "ingest", x_ingest_key)  # 401/403 tashlaydi
        ok = True
    auth_kind, actor_id = ("key", None) if ok else (None, None)
    if not ok and authorization and authorization.lower().startswith("bearer "):
        uid = decode_access_token(authorization[7:])
        user = db.get(User, uid) if uid else None
        ok = (
            user is not None
            and user.is_active
            and has_role(get_project_role(db, project_id, user), Role.engineer)
        )
        if ok:
            auth_kind, actor_id = "token", user.id
    if not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Ingest kaliti yoki token noto'g'ri")
    if len(body) > 10000:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Bir so'rovda 10000 tagacha o'lchov"
        )
    out = live.ingest(
        db,
        project_id,
        [b.model_dump() for b in body],
        max_age=timedelta(days=get_settings().ingest_max_age_days),
    )
    # Partiya bo'yicha bitta jamlangan yozuv (har o'lchov emas)
    audit.log(
        db,
        user_id=actor_id,
        action="readings.ingest",
        target_type="project",
        target_id=project_id,
        project_id=project_id,
        detail={
            "count": len(body),
            "accepted": out["accepted"],
            "bad": out["bad"],
            "unknown": len(out["unknown"]),
            "rejected": len(out["rejected"]),
            "auth": auth_kind,
            "key_prefix": (x_ingest_key or "")[:6] if auth_kind == "key" else None,
        },
    )
    db.commit()
    return out


@router.post("/sensors/{sensor_id}/import")
async def import_csv(sensor_id: int, file: UploadFile, user: CurrentUser, db: DB):
    """CSV: 'ts,value[,quality]' (sarlavha ixtiyoriy). ts — ISO yoki Unix soniya; quality — QUALITIES."""
    s = _get_sensor(db, sensor_id, user, Role.engineer)
    text = (await file.read()).decode("utf-8-sig", errors="replace")
    items = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 2:
            continue
        try:
            float(row[1])
        except ValueError:
            continue  # sarlavha
        it = {"sensor_id": s.id, "ts": row[0].strip(), "value": row[1].strip()}
        if len(row) > 2 and row[2].strip():
            it["quality"] = row[2].strip().lower()
        items.append(it)
    if not items:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CSV da 'ts,value' qatorlar topilmadi")
    out = live.ingest(db, s.project_id, items, source="csv")
    audit.log(
        db,
        user_id=user.id,
        action="readings.ingest",
        target_type="sensor",
        target_id=s.id,
        project_id=s.project_id,
        detail={"count": len(items), "accepted": out["accepted"], "bad": out["bad"], "auth": "csv"},
    )
    db.commit()
    return out


# ---------- SOE — hodisalar ketma-ketligi (D3) ----------


class SoeIn(BaseModel):
    point: str = Field("", max_length=64)  # bo'sh — element rad etiladi (butun partiya emas)
    state: str | bool | int = ""
    ts: str | float | int
    source: str | None = Field(None, max_length=32)
    quality: str | None = Field(None, max_length=16)
    raw: dict | list | str | None = None


def _ingest_auth(db, project_id: int, x_ingest_key: str | None, authorization: str | None) -> tuple[str, int | None]:
    """Ingest kaliti yoki muhandis+ tokeni → (auth turi, foydalanuvchi id)."""
    ratelimit.check("ingest", str(project_id), get_settings().rate_ingest_per_min)
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Loyiha topilmadi")
    if x_ingest_key:
        keys.verify(db, project, "ingest", x_ingest_key)
        return "key", None
    if authorization and authorization.lower().startswith("bearer "):
        uid = decode_access_token(authorization[7:])
        user = db.get(User, uid) if uid else None
        if user is not None and user.is_active and has_role(get_project_role(db, project_id, user), Role.engineer):
            return "token", user.id
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Ingest kaliti yoki token noto'g'ri")


@router.post("/projects/{project_id}/soe")
def push_soe(
    project_id: int,
    body: list[SoeIn],
    db: DB,
    x_ingest_key: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
):
    """SOE hodisalarini yuborish (ingest kaliti yoki muhandis+): partiyali, ms aniqlik, takror tashlanadi."""
    auth_kind, actor_id = _ingest_auth(db, project_id, x_ingest_key, authorization)
    if len(body) > 10000:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Bir so'rovda 10000 tagacha hodisa")
    out = soe.ingest(db, project_id, [b.model_dump() for b in body], max_age=timedelta(days=get_settings().ingest_max_age_days))
    audit.log(
        db,
        user_id=actor_id,
        action="soe.ingest",
        target_type="project",
        target_id=project_id,
        project_id=project_id,
        detail={"count": len(body), "accepted": out["accepted"], "duplicates": out["duplicates"], "rejected": len(out["rejected"]), "auth": auth_kind},
    )
    db.commit()
    return out


@router.get("/projects/{project_id}/soe")
def list_soe(
    project: ViewerProject,
    db: DB,
    hours: float = Query(24, gt=0, le=24 * 366),
    point: str | None = None,
    source: str | None = None,
    limit: int = Query(500, gt=0, le=5000),
    before_id: int | None = None,
):
    """SOE ro'yxati: vaqt bo'yicha (ms), eng yangisi birinchi; `point` filtri `*` bilan (AGG1.*)."""
    now = datetime.now(timezone.utc)
    rows = soe.query(db, project.id, now - timedelta(hours=hours), now, point, source, limit, before_id)
    return [soe.event_out(e) for e in rows]


@router.get("/projects/{project_id}/timeline")
def timeline(project: ViewerProject, db: DB, hours: float = Query(24, gt=0, le=24 * 366), limit: int = Query(500, gt=0, le=5000)):
    """SOE + alarm jurnali birlashtirilgan vaqt chizig'i (avariya tahlili: sabab → oqibat)."""
    now = datetime.now(timezone.utc)
    return soe.timeline(db, project.id, now - timedelta(hours=hours), now, limit)


# ---------- Tarix / holat ----------


@router.get("/sensors/{sensor_id}/readings")
def readings(
    sensor_id: int,
    user: CurrentUser,
    db: DB,
    hours: float = Query(24, gt=0, le=24 * 366),
    limit: int = Query(2000, gt=0, le=20000),
):
    """Oxirgi `hours` soat. Nuqtalar limit dan ko'p bo'lsa vaqt bo'yicha teng bo'laklarga
    yig'iladi (o'rtacha, min, max) — grafik uchun yetarli, tarmoq yuki kichik."""
    s = _get_sensor(db, sensor_id, user, Role.viewer)
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)
    tier = historian.tier_for_span(hours)
    if tier != "raw":
        # Uzoq davr: historian qatlami (1m/10m/1h) + hali yig'ilmagan dum xomdan (D2)
        points = historian.tier_points(db, s.id, tier, since, now)
        return {
            "sensor_id": s.id,
            "unit": s.unit,
            "total": len(points),
            "points": points[-limit:],
            "hourly": tier == "1h",
            "tier": tier,
        }
    base = db.query(Reading).filter(Reading.sensor_id == s.id, Reading.ts >= since, Reading.quality != "bad")
    total = base.count()
    points: list[dict] = []
    if total <= limit:
        points = [
            {"ts": live._aware(t).isoformat(), "v": round(v, 4), "min": round(v, 4), "max": round(v, 4)}
            for t, v in base.with_entities(Reading.ts, Reading.value).order_by(Reading.ts).all()
        ]
    else:
        # Siyraklashtirish DB tomonda (D4): vaqt bo'laklari bo'yicha avg/min/max — xom qatorlar RAM ga yuklanmaydi
        first = base.with_entities(func.min(Reading.ts)).scalar()
        span_s = max(1.0, (now - live._aware(first)).total_seconds()) if first else hours * 3600
        sec = max(1, -(-int(span_s) // limit))
        points = historian.bucketed(db, s.id, since, now, sec)
    return {"sensor_id": s.id, "unit": s.unit, "total": total, "points": points, "hourly": False, "tier": "raw"}


@router.get("/sensors/{sensor_id}/export.csv")
def export_csv(
    sensor_id: int, user: CurrentUser, db: DB, hours: float = Query(24, gt=0, le=24 * 366)
):
    """Xom o'lchovlar CSV (ts,value,quality,src_ts) — tahlil/Excel uchun; bad qatorlar ham kiradi."""
    s = _get_sensor(db, sensor_id, user, Role.viewer)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ts", f"value_{s.unit or 'raw'}", "quality", "src_ts"])
    for t, v, q, st in (
        db.query(Reading.ts, Reading.value, Reading.quality, Reading.src_ts)
        .filter(Reading.sensor_id == s.id, Reading.ts >= since)
        .order_by(Reading.ts)
        .yield_per(1000)
    ):
        w.writerow([live._aware(t).isoformat(), v, q, live._aware(st).isoformat() if st else ""])
    audit.log(
        db,
        user_id=user.id,
        action="export.csv",
        target_type="sensor",
        target_id=s.id,
        project_id=s.project_id,
        detail={"hours": hours},
    )
    db.commit()
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{s.key}.csv"'},
    )


@router.get("/projects/{project_id}/alarms", response_model=list[SensorOut])
def alarms(project: ViewerProject, db: DB):
    return (
        db.query(Sensor)
        .filter(
            Sensor.project_id == project.id,
            Sensor.enabled.is_(True),
            (Sensor.alarm != AlarmState.ok) | Sensor.stale.is_(True),
        )
        .order_by(Sensor.name)
        .all()
    )


# ---------- Alarm jurnali ----------


class AlarmEventOut(BaseModel):
    id: int
    sensor_id: int
    sensor_name: str
    sensor_key: str
    unit: str
    priority: str
    state: AlarmState
    value: float | None
    started_at: datetime
    ended_at: datetime | None
    acked_by: int | None
    acked_at: datetime | None
    comment: str
    suppressed: str | None = None  # shelved | out_of_service | suppressed_by_design
    alarm_state: str = "unack"  # ISA-18.2: unack | acked | rtn_unack | normal | (bostirilgan rejim)
    cause: str = ""
    consequence: str = ""
    corrective_action: str = ""
    response_time_s: int | None = None


class AckIn(BaseModel):
    comment: str = ""


class ShelveIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    hours: float | None = Field(None, gt=0)


class ModeReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


def _event_out(e: AlarmEvent) -> AlarmEventOut:
    return AlarmEventOut(
        id=e.id,
        sensor_id=e.sensor_id,
        sensor_name=e.sensor.name,
        sensor_key=e.sensor.key,
        unit=e.sensor.unit,
        priority=e.sensor.priority or "medium",
        state=e.state,
        value=e.value,
        started_at=live._aware(e.started_at),
        ended_at=live._aware(e.ended_at) if e.ended_at else None,
        acked_by=e.acked_by,
        acked_at=live._aware(e.acked_at) if e.acked_at else None,
        comment=e.comment,
        suppressed=e.suppressed,
        alarm_state=e.alarm_state,
        cause=e.sensor.cause or "",
        consequence=e.sensor.consequence or "",
        corrective_action=e.sensor.corrective_action or "",
        response_time_s=e.sensor.response_time_s,
    )


@router.get("/projects/{project_id}/alarm-events", response_model=list[AlarmEventOut])
def alarm_events(
    project: ViewerProject,
    db: DB,
    active: bool = False,
    hours: float = Query(24 * 7, gt=0, le=24 * 366),
    limit: int = Query(500, gt=0, le=5000),
    include_suppressed: bool = False,
    before_id: int | None = None,
):
    """Alarm jurnali: active=true — davom etayotgan yoki kvitlanmaganlar; aks holda tarix.
    Bostirilgan (shelved/OOS/shart) hodisalar faqat include_suppressed=true bilan (KPI/audit uchun).
    Kursor: `before_id` (id kamayish tartibi) — keyingi sahifa."""
    q = db.query(AlarmEvent).filter(AlarmEvent.project_id == project.id)
    if before_id is not None:
        q = q.filter(AlarmEvent.id < before_id)
    if not include_suppressed:
        q = q.filter(AlarmEvent.suppressed.is_(None))
    if active:
        q = q.filter((AlarmEvent.ended_at.is_(None)) | (AlarmEvent.acked_at.is_(None)))
    else:
        q = q.filter(AlarmEvent.started_at >= datetime.now(timezone.utc) - timedelta(hours=hours))
    return [_event_out(e) for e in q.order_by(AlarmEvent.id.desc()).limit(limit).all()]


@router.post("/alarm-events/{event_id}/ack", response_model=AlarmEventOut)
def ack_alarm(event_id: int, body: AckIn, user: CurrentUser, db: DB):
    """Kvitlash (dispetcher ko'rdi) — operator, muhandis yoki tasdiqlovchi."""
    e = db.get(AlarmEvent, event_id)
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hodisa topilmadi")
    if not has_role(get_project_role(db, e.project_id, user), Role.operator):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Operator huquqi kerak")
    if e.acked_at is None:
        e.acked_by, e.acked_at, e.comment = user.id, utcnow(), body.comment
        audit.log(
            db,
            user_id=user.id,
            action="alarm.ack",
            target_type="alarm_event",
            target_id=e.id,
            project_id=e.project_id,
            detail={"sensor": e.sensor.key, "state": e.state.value},
        )
        db.commit()
        live.hub.publish(e.project_id, live.event_message(e, e.sensor))
    return _event_out(e)


class AckBatchIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=5000)
    comment: str = ""


@router.post("/projects/{project_id}/alarm-events/ack-batch")
def ack_batch(body: AckBatchIn, project: OperatorProject, user: CurrentUser, db: DB):
    """Tanlangan (filtrlangan) hodisalarni kvitlash (F5) — «hammasini» emas, aynan ko'rsatilganlar."""
    n = 0
    now = utcnow()
    rows = db.query(AlarmEvent).filter(AlarmEvent.project_id == project.id, AlarmEvent.id.in_(body.ids), AlarmEvent.acked_at.is_(None), AlarmEvent.suppressed.is_(None)).all()
    for e in rows:
        e.acked_by, e.acked_at, e.comment = user.id, now, body.comment
        n += 1
    audit.log(
        db,
        user_id=user.id,
        action="alarm.ack_batch",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
        detail={"count": n, "requested": len(body.ids)},
    )
    db.commit()
    for e in rows:
        live.hub.publish(project.id, live.event_message(e, e.sensor))
    return {"acked": n}


@router.post("/projects/{project_id}/alarm-events/ack-all")
def ack_all(project: OperatorProject, user: CurrentUser, db: DB):
    n = 0
    for e in db.query(AlarmEvent).filter_by(project_id=project.id, acked_at=None, suppressed=None).all():
        e.acked_by, e.acked_at = user.id, utcnow()
        n += 1
    audit.log(
        db,
        user_id=user.id,
        action="alarm.ack_all",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
        detail={"count": n},
    )
    db.commit()
    return {"acked": n}


# ---------- KPI (EEMUA-191, C4) ----------


@router.get("/projects/{project_id}/alarms/kpi")
def alarms_kpi(project: ViewerProject, db: DB, hours: float = Query(24, gt=0, le=24 * 92)):
    """Alarm tizimi KPI (EEMUA-191 / ISA-18.2 §16): yuk, cho'qqi, toshqin, turg'un, chattering,
    ustuvorlik taqsimoti, eng yomon 10 ta, kvitlash vaqti; EEMUA mezonlariga nisbatan baho va tavsiyalar."""
    now = datetime.now(timezone.utc)
    return alarm_kpi.kpi(db, project.id, now - timedelta(hours=hours), now, now)


# ---------- Ratsionalizatsiya (ISA-18.2 §10, C3) ----------

RATIONALIZATION_FIELDS = ("cause", "consequence", "corrective_action", "response_time_s", "priority_basis")


class RationalizeIn(BaseModel):
    cause: str = Field(min_length=3, max_length=2000)
    consequence: str = Field(min_length=3, max_length=2000)
    corrective_action: str = Field(min_length=3, max_length=2000)
    response_time_s: int = Field(gt=0, le=7 * 86400)
    priority_basis: str = Field(min_length=3, max_length=2000)


def rationalization_missing(s: Sensor) -> list[str]:
    """Alarm ta'rifi bor sensor uchun to'ldirilmagan ratsionalizatsiya maydonlari (bo'sh — to'liq)."""
    missing = [f for f in RATIONALIZATION_FIELDS if not getattr(s, f)]
    if s.rationalized_at is None:
        missing.append("rationalized")
    return missing


@router.post("/sensors/{sensor_id}/rationalize", response_model=SensorOut)
def rationalize_sensor(sensor_id: int, body: RationalizeIn, user: CurrentUser, db: DB):
    """Ratsionalizatsiyani tasdiqlash (muhandis+): barcha maydonlar majburiy; kim/qachon yoziladi.
    Keyin chegara yoki ustuvorlik o'zgarsa tasdiq bekor bo'ladi (qayta ko'rib chiqish)."""
    s = _get_sensor(db, sensor_id, user, Role.engineer)
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    s.rationalized_by, s.rationalized_at = user.id, utcnow()
    audit.log(
        db,
        user_id=user.id,
        action="alarm.rationalize",
        target_type="sensor",
        target_id=s.id,
        project_id=s.project_id,
        detail={"key": s.key, "priority": s.priority, "response_time_s": body.response_time_s},
    )
    db.commit()
    return s


class RationalizationRow(BaseModel):
    id: int
    project_id: int
    key: str
    name: str
    priority: str
    alarm_mode: str
    missing: list[str]


class RationalizationReport(BaseModel):
    total: int  # alarm ta'rifi bor sensorlar
    rationalized: int
    unrationalized: list[RationalizationRow]


def _rationalization_report(sensors: list[Sensor]) -> RationalizationReport:
    with_limits = [s for s in sensors if s.enabled and s.has_alarm_limits]
    rows = []
    for s in with_limits:
        miss = rationalization_missing(s)
        if miss:
            rows.append(
                RationalizationRow(
                    id=s.id, project_id=s.project_id, key=s.key, name=s.name,
                    priority=s.priority or "medium", alarm_mode=s.alarm_mode or "normal", missing=miss,
                )
            )
    rows.sort(key=lambda r: ({"critical": 0, "high": 1, "medium": 2, "low": 3}.get(r.priority, 9), r.key))
    return RationalizationReport(total=len(with_limits), rationalized=len(with_limits) - len(rows), unrationalized=rows)


@router.get("/projects/{project_id}/alarms/rationalization", response_model=RationalizationReport)
def project_rationalization(project: ViewerProject, db: DB):
    """Loyihada ratsionalizatsiya qilinmagan alarmlar (ISA-18.2 §10 hisoboti)."""
    return _rationalization_report(db.query(Sensor).filter_by(project_id=project.id).all())


@router.get("/admin/alarms/rationalization", response_model=RationalizationReport)
def admin_rationalization(user: CurrentUser, db: DB):
    """Barcha loyihalar bo'yicha ratsionalizatsiya qilinmagan alarmlar (admin)."""
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Faqat admin")
    return _rationalization_report(db.query(Sensor).all())


# ---------- Annunciator (F6): silence auditi ----------


class SilenceIn(BaseModel):
    minutes: int = Field(ge=0, le=24 * 60)  # 0 — bekor qilish
    reason: str = Field("", max_length=200)


@router.post("/projects/{project_id}/annunciator/silence")
def annunciator_silence(body: SilenceIn, project: OperatorProject, user: CurrentUser, db: DB):
    """Ovozli signalni vaqtincha o'chirish (klientda) — kim, qancha vaqtga: audit yozuvi (ISA-18.2 §12)."""
    audit.log(
        db,
        user_id=user.id,
        action="annunciator.silence" if body.minutes > 0 else "annunciator.unsilence",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
        detail={"minutes": body.minutes, "reason": body.reason},
    )
    db.commit()
    return {"ok": True, "minutes": body.minutes}


# ---------- Alarm rejimi: shelving / out-of-service (ISA-18.2, C2) ----------


def _mode_response(db, s: Sensor, user: User, action: str, detail: dict, reactivated: AlarmEvent | None) -> Sensor:
    audit.log(
        db,
        user_id=user.id,
        action=action,
        target_type="sensor",
        target_id=s.id,
        project_id=s.project_id,
        detail={"key": s.key, **detail},
    )
    db.commit()
    live.hub.publish(s.project_id, live.sensor_message(s))
    if reactivated is not None:
        live.announce(db, s.project_id, [(reactivated, s)])
    return s


@router.post("/sensors/{sensor_id}/shelve", response_model=SensorOut)
def shelve_sensor(sensor_id: int, body: ShelveIn, user: CurrentUser, db: DB):
    """Shelving (operator+): alarm muddatga yashiriladi, sabab majburiy; muddat tugagach avtomatik qaytadi.
    Default va maksimal muddat — GES_ALARM_SHELVE_DEFAULT_H / _MAX_H."""
    s = _get_sensor(db, sensor_id, user, Role.operator)
    st = get_settings()
    hours = body.hours if body.hours is not None else st.alarm_shelve_default_h
    if hours > st.alarm_shelve_max_h:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Shelving muddati ko'pi bilan {st.alarm_shelve_max_h:g} soat")
    if s.alarm_mode == "out_of_service":
        raise HTTPException(status.HTTP_409_CONFLICT, "Sensor xizmatdan chiqarilgan — avval xizmatga qaytaring")
    until = datetime.now(timezone.utc) + timedelta(hours=hours)
    live.set_alarm_mode(db, s, "shelved", user.id, body.reason, until)
    return _mode_response(db, s, user, "alarm.shelve", {"hours": hours, "reason": body.reason, "alarm": s.alarm.value}, None)


@router.post("/sensors/{sensor_id}/unshelve", response_model=SensorOut)
def unshelve_sensor(sensor_id: int, user: CurrentUser, db: DB):
    s = _get_sensor(db, sensor_id, user, Role.operator)
    if s.alarm_mode != "shelved":
        raise HTTPException(status.HTTP_409_CONFLICT, "Sensor shelved emas")
    ev = live.set_alarm_mode(db, s, "normal", user.id, "")
    return _mode_response(db, s, user, "alarm.unshelve", {"alarm": s.alarm.value}, ev)


@router.post("/sensors/{sensor_id}/out-of-service", response_model=SensorOut)
def out_of_service(sensor_id: int, body: ModeReasonIn, user: CurrentUser, db: DB):
    """Out-of-service (muhandis+): texnik xizmat — alarm muddatsiz bostiriladi, sabab majburiy."""
    s = _get_sensor(db, sensor_id, user, Role.engineer)
    live.set_alarm_mode(db, s, "out_of_service", user.id, body.reason)
    return _mode_response(db, s, user, "alarm.out_of_service", {"reason": body.reason, "alarm": s.alarm.value}, None)


@router.post("/sensors/{sensor_id}/in-service", response_model=SensorOut)
def in_service(sensor_id: int, user: CurrentUser, db: DB):
    s = _get_sensor(db, sensor_id, user, Role.engineer)
    if s.alarm_mode != "out_of_service":
        raise HTTPException(status.HTTP_409_CONFLICT, "Sensor xizmatdan chiqarilmagan")
    ev = live.set_alarm_mode(db, s, "normal", user.id, "")
    return _mode_response(db, s, user, "alarm.in_service", {"alarm": s.alarm.value}, ev)


# ---------- Dispetcher paneli / hisobot ----------

# Mimik sxema slotlari (GES texnologik zanjiri) — sensor bog'lanadi; kind bo'yicha avto-taklif
MIMIC_SLOTS = [
    ("upstream_level", "Yuqori byef sathi", "level"),
    ("inflow", "Kiruvchi sarf", "flow"),
    ("spillway_flow", "Suv tashlagich sarfi", "flow"),
    ("penstock_flow", "Quvur sarfi", "flow"),
    ("penstock_pressure", "Quvur bosimi", "pressure"),
    ("unit1_power", "Agregat 1 quvvati", "power"),
    ("unit2_power", "Agregat 2 quvvati", "power"),
    ("unit3_power", "Agregat 3 quvvati", "power"),
    ("total_power", "Umumiy quvvat", "power"),
    ("downstream_level", "Quyi byef sathi", "level"),
    ("bearing_temp", "Podshipnik harorati", "temperature"),
    ("vibration", "Tebranish", "vibration"),
]


# Avto-bog'lash uchun nom/kalit belgilari (kichik harfda qidiriladi)
MIMIC_HINTS: dict[str, tuple[str, ...]] = {
    "upstream_level": ("yuqori", "upstream", "res.", "res_", "ombor", "forebay", "vb"),
    "downstream_level": ("quyi", "tail", "tw", "downstream", "nb"),
    "inflow": ("kiruv", "inflow", "qin", "q_in", "in."),
    "spillway_flow": ("tashlag", "spill", "sbros"),
    "penstock_flow": ("quvur", "pen", "penstock", "turbin"),
    "penstock_pressure": ("quvur", "pen", "penstock", "bosim", "press"),
    "total_power": ("umumiy", "total", "sum", "ges.p", "station"),
    "unit1_power": ("agg1", "agregat 1", "unit1", "g1", "u1", "ag1"),
    "unit2_power": ("agg2", "agregat 2", "unit2", "g2", "u2", "ag2"),
    "unit3_power": ("agg3", "agregat 3", "unit3", "g3", "u3", "ag3"),
    "bearing_temp": ("podship", "bearing", "temp", "harorat"),
    "vibration": ("tebran", "vib"),
}


def _auto_mimic(mimic: dict[str, int], sensors: list[Sensor]) -> None:
    """Bo'sh slotlarga sensor taklif qiladi: avval nom/kalit belgilari, keyin tur (kind) bo'yicha.
    Bir sensor bir slotga; umumiy quvvat uchun sensor topilmasa slot bo'sh qoladi (web agregatlar
    yig'indisini ko'rsatadi)."""
    used = set(mimic.values())

    def take(s: Sensor, slot: str) -> None:
        mimic[slot] = s.id
        used.add(s.id)

    for slot, _label, kind in MIMIC_SLOTS:
        if slot in mimic:
            continue
        hints = MIMIC_HINTS.get(slot, ())
        for s in sensors:
            text = f"{s.key} {s.name}".lower()
            if s.kind == kind and s.id not in used and any(h in text for h in hints):
                take(s, slot)
                break
    for slot, _label, kind in MIMIC_SLOTS:
        if slot in mimic or slot.startswith("unit") or slot == "total_power":
            continue
        cand = next((s for s in sensors if s.kind == kind and s.id not in used), None)
        if cand:
            take(cand, slot)


class SchemeElementIn(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    type: Literal["reservoir", "dam", "spillway", "penstock", "unit", "breaker", "bus", "transformer", "line", "gate", "valve", "tailwater", "value"]
    x: float = Field(ge=0, le=2000)
    y: float = Field(ge=0, le=2000)
    w: float | None = Field(None, ge=0, le=2000)
    h: float | None = Field(None, ge=0, le=2000)
    label: str | None = Field(None, max_length=64)
    sensor_id: int | None = None
    unit: int | None = Field(None, ge=1, le=12)
    extra: dict[str, int | None] | None = None


class SchemeIn(BaseModel):
    """Mimika sxemasi (F3): elementlar, koordinatalar, sensor bog'lanishi; agregatlar soni."""

    version: Literal[1] = 1
    units: int = Field(ge=1, le=12)
    elements: list[SchemeElementIn] = Field(max_length=200)

    @field_validator("elements")
    @classmethod
    def _unique_ids(cls, v: list[SchemeElementIn]) -> list[SchemeElementIn]:
        ids = [e.id for e in v]
        if len(ids) != len(set(ids)):
            raise ValueError("element id lari takror")
        return v


class PenGroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    sensor_ids: list[int] = Field(min_length=1, max_length=6)


class DashboardIn(BaseModel):
    mimic: dict[str, int | None] = Field(default_factory=dict)
    tiles: list[int] = Field(default_factory=list)
    scheme: SchemeIn | None = None
    # Trend qalam guruhlari (F7): nom → sensorlar; None — o'zgarmaydi
    pen_groups: list[PenGroupIn] | None = Field(None, max_length=50)


@router.get("/projects/{project_id}/dashboard")
def dashboard(project: ViewerProject, db: DB):
    """Dispetcher paneli: sensorlar holati, mimik sxema bog'lanishi, faol alarmlar, 24 soatlik
    energiya (quvvat sensorlaridan)."""
    sensors = (
        db.query(Sensor).filter_by(project_id=project.id, enabled=True).order_by(Sensor.name).all()
    )
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)
    energy, has_power = 0.0, False
    for s in sensors:
        if s.kind == "power":
            st = historian.sensor_stats(db, s, since, now)
            if st["energy_mwh"] is not None:
                energy += st["energy_mwh"]
                has_power = True
    cfg = project.dashboard or {}
    mimic = {k: v for k, v in (cfg.get("mimic") or {}).items() if v}
    _auto_mimic(mimic, sensors)
    active = (
        db.query(AlarmEvent)
        .filter(AlarmEvent.project_id == project.id)
        .filter((AlarmEvent.ended_at.is_(None)) | (AlarmEvent.acked_at.is_(None)))
        .count()
    )
    units = [
        {
            "sensor_id": s.id,
            "name": s.name,
            "running": bool(
                not s.stale
                and s.last_value is not None
                and s.last_value > max(0.5, 0.01 * (s.high_alarm or 0))
            ),
            "power": s.last_value,
        }
        for s in sensors
        if s.kind == "power"
        and any(
            h in f"{s.key} {s.name}".lower()
            for h in ("agg", "agregat", "unit", "g1", "g2", "g3", "g4")
        )
    ]
    return {
        "sensors": [SensorOut.model_validate(s).model_dump(mode="json") for s in sensors],
        "units": units,
        "mimic": mimic,
        "slots": [{"slot": s, "label": lb, "kind": k} for s, lb, k in MIMIC_SLOTS],
        "tiles": cfg.get("tiles") or [],
        "scheme": cfg.get("scheme"),  # F3: konfiguratsiyalanadigan mimika (None → klient standart sxema)
        "pen_groups": cfg.get("pen_groups") or [],  # F7: trend qalam guruhlari
        "active_alarms": active,
        "energy_24h_mwh": round(energy, 3) if has_power else None,
        "alarms_24h": historian.alarm_stats(db, project.id, since, now),
        "alarm_flood": alarm_kpi.flood_now(db, project.id, now)[0],
        "live_clients": live.hub.count(project.id),
    }


@router.put("/projects/{project_id}/dashboard")
def save_dashboard(body: DashboardIn, project: EngineerProject, user: CurrentUser, db: DB):
    ids = {s.id for s in db.query(Sensor).filter_by(project_id=project.id).all()}
    bad = [v for v in body.mimic.values() if v and v not in ids] + [
        t for t in body.tiles if t not in ids
    ]
    if body.pen_groups is not None:
        for g in body.pen_groups:
            bad.extend(i for i in g.sensor_ids if i not in ids)
    if body.scheme is not None:
        for e in body.scheme.elements:
            if e.sensor_id and e.sensor_id not in ids:
                bad.append(e.sensor_id)
            for v in (e.extra or {}).values():
                if v and v not in ids:
                    bad.append(v)
        if sum(1 for e in body.scheme.elements if e.type == "unit") != body.scheme.units:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sxemadagi agregat elementlari soni `units` ga mos emas")
    if bad:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Sensor loyihada yo'q: {bad}")
    old = project.dashboard or {}
    project.dashboard = {
        "mimic": {k: v for k, v in body.mimic.items() if v},
        "tiles": body.tiles,
        "scheme": body.scheme.model_dump(exclude_none=True) if body.scheme is not None else old.get("scheme"),
        "pen_groups": [g.model_dump() for g in body.pen_groups] if body.pen_groups is not None else old.get("pen_groups") or [],
    }
    audit.log(
        db,
        user_id=user.id,
        action="dashboard.update",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
    )
    db.commit()
    return project.dashboard


@router.get("/projects/{project_id}/report")
def report(
    project: ViewerProject,
    user: CurrentUser,
    db: DB,
    period: Literal["day", "week", "month"] = "day",
    date: str | None = None,
    format: Literal["json", "csv"] = "json",
):
    """Davr hisoboti: har sensor bo'yicha o'rtacha/min/max, quvvat → energiya (MWh), alarmlar.
    date — davr boshi (YYYY-MM-DD, UTC); berilmasa joriy davr."""
    now = datetime.now(timezone.utc)
    start = None
    if date:
        try:
            start = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "date: YYYY-MM-DD") from e
    out = historian.build_report(db, project, period, start, now)
    audit.log(
        db,
        user_id=user.id,
        action="export.report",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
        detail={"period": period, "date": date, "format": format},
    )
    db.commit()
    start, end = datetime.fromisoformat(out["start"]), datetime.fromisoformat(out["end"])
    rows = out["sensors"]
    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(
            ["Sath hisobot", project.name, period, start.date().isoformat(), end.isoformat()]
        )
        w.writerow(["Energiya, MWh", out["energy_mwh"]])
        w.writerow(["Alarmlar", out["alarms"]["count"], "kvitlanmagan", out["alarms"]["unacked"]])
        w.writerow([])
        w.writerow(["key", "nom", "tur", "birlik", "n", "o'rtacha", "min", "max", "energiya MWh"])
        for r in rows:
            w.writerow(
                [
                    r["key"],
                    r["name"],
                    r["kind"],
                    r["unit"],
                    r["n"],
                    r["avg"],
                    r["min"],
                    r["max"],
                    r["energy_mwh"],
                ]
            )
        return Response(
            "\ufeff" + buf.getvalue(),  # BOM — Excel UTF-8 ni to'g'ri ochsin
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="hisobot-{period}-{start.date()}.csv"'
            },
        )
    return out


# ---------- WebSocket ----------


@router.websocket("/projects/{project_id}/live")
async def live_ws(ws: WebSocket, project_id: int, token: str = Query("")):
    """Jonli o'lchovlar. ?token=<JWT>. Birinchi xabar — hozirgi holat (snapshot)."""
    with SessionLocal() as db:
        uid = decode_access_token(token)
        user = db.get(User, uid) if uid else None
        if (
            user is None
            or not user.is_active
            or not has_role(get_project_role(db, project_id, user), Role.viewer)
        ):
            await ws.close(code=4401)
            return
        # stale tekshiruvi faqat fon vazifasida (C5): ulanish sikli alarm/email bo'roni bermasin
        snapshot = [
            live.sensor_message(s) for s in db.query(Sensor).filter_by(project_id=project_id).all()
        ]
        uid = user.id
    await live.hub.connect(project_id, ws)
    opened = datetime.now(timezone.utc)
    await asyncio.to_thread(
        audit.log_now,
        user_id=uid,
        action="ws.connect",
        target_type="project",
        target_id=project_id,
        project_id=project_id,
    )
    try:
        await ws.send_json({"type": "snapshot", "sensors": snapshot})
        # Heartbeat (F4): har WS_PING_S soniyada ping — klient xabar yoshi bo'yicha LIVE → STALE → OFFLINE ni aniqlaydi
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=WS_PING_S)  # ping/pong yoki mijoz xabari — e'tiborsiz
            except (TimeoutError, asyncio.TimeoutError):
                await ws.send_json({"type": "ping", "ts": datetime.now(timezone.utc).isoformat()})
    except WebSocketDisconnect:
        pass
    finally:
        live.hub.disconnect(project_id, ws)
        # Sinxron: ulanish bekor qilinayotganda (cancel) ham yozuv kafolatlanadi (qisqa DB yozuvi)
        audit.log_now(
            user_id=uid,
            action="ws.disconnect",
            target_type="project",
            target_id=project_id,
            project_id=project_id,
            detail={"duration_s": round((datetime.now(timezone.utc) - opened).total_seconds(), 1)},
        )
