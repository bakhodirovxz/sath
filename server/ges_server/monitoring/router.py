"""Monitoring API: sensorlar, o'lchov qabul qilish (HTTP/CSV), tarix, jonli WebSocket, alarmlar."""

from __future__ import annotations

import csv
import io
import secrets
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
from pydantic import BaseModel, Field

from .. import audit
from ..auth.deps import DB, CurrentUser, get_project_role, has_role, require_project_role
from ..auth.security import decode_access_token
from ..db import SessionLocal
from ..orm import AlarmEvent, AlarmState, Project, Reading, Role, Sensor, User, utcnow
from . import historian, live, mqtt_bridge

router = APIRouter(prefix="/api", tags=["monitoring"])

ViewerProject = Annotated[Project, Depends(require_project_role(Role.viewer))]
EngineerProject = Annotated[Project, Depends(require_project_role(Role.engineer))]
ApproverProject = Annotated[Project, Depends(require_project_role(Role.approver))]

Kind = Literal[
    "level", "flow", "power", "pressure", "temperature", "vibration", "status", "position", "value"
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
    low_alarm: float | None = None
    high_alarm: float | None = None
    stale_after_s: int = 600
    enabled: bool = True
    priority: Priority = "medium"
    writable: bool = False


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
    stale_after_s: int | None = None
    enabled: bool | None = None
    priority: Priority | None = None
    writable: bool | None = None
    clear_alarms: bool = False  # low/high ni null qilish uchun


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
    stale_after_s: int
    enabled: bool
    last_value: float | None
    last_ts: datetime | None
    alarm: AlarmState
    priority: str = "medium"
    writable: bool = False

    model_config = {"from_attributes": True}


class ReadingIn(BaseModel):
    """Gateway ma'lumotlari — bitta yaroqsiz qiymat butun paketni rad etmasin (value tekshiruvi ingest da)."""

    key: str | None = None
    sensor_id: int | None = None
    value: Any
    ts: datetime | float | str | None = None


# ---------- Sensorlar ----------


@router.get("/projects/{project_id}/sensors", response_model=list[SensorOut])
def list_sensors(project: ViewerProject, db: DB, model_id: int | None = None):
    q = db.query(Sensor).filter_by(project_id=project.id)
    if model_id is not None:
        q = q.filter((Sensor.model_id == model_id) | (Sensor.model_id.is_(None)))
    return q.order_by(Sensor.name).all()


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
    changes = body.model_dump(exclude_none=True, exclude={"clear_alarms"})
    for k, v in changes.items():
        setattr(s, k, v)
    if body.clear_alarms:
        s.low_alarm = s.high_alarm = None
    if s.last_value is not None and s.alarm != AlarmState.stale:
        s.alarm = live.evaluate_alarm(s, s.last_value)
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


@router.get("/projects/{project_id}/ingest-key")
def get_ingest_key(project: ApproverProject, db: DB):
    """SCADA/gateway uchun kalit; bo'lmasa yaratiladi. Sarlavha: X-Ingest-Key."""
    if not project.ingest_key:
        project.ingest_key = secrets.token_urlsafe(24)
        db.commit()
    return {"ingest_key": project.ingest_key, "url": f"/api/projects/{project.id}/readings"}


@router.post("/projects/{project_id}/ingest-key")
def rotate_ingest_key(project: ApproverProject, user: CurrentUser, db: DB):
    project.ingest_key = secrets.token_urlsafe(24)
    audit.log(
        db,
        user_id=user.id,
        action="project.ingest_key.rotate",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
    )
    db.commit()
    return {"ingest_key": project.ingest_key}


@router.post("/projects/{project_id}/readings")
def push_readings(
    project_id: int,
    body: list[ReadingIn],
    db: DB,
    x_ingest_key: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
):
    """O'lchovlarni yuborish: yoki X-Ingest-Key (gateway), yoki foydalanuvchi tokeni (muhandis+)."""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Loyiha topilmadi")
    ok = bool(project.ingest_key and x_ingest_key) and secrets.compare_digest(
        x_ingest_key, project.ingest_key
    )
    if not ok and authorization and authorization.lower().startswith("bearer "):
        uid = decode_access_token(authorization[7:])
        user = db.get(User, uid) if uid else None
        ok = (
            user is not None
            and user.is_active
            and has_role(get_project_role(db, project_id, user), Role.engineer)
        )
    if not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Ingest kaliti yoki token noto'g'ri")
    if len(body) > 10000:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Bir so'rovda 10000 tagacha o'lchov"
        )
    return live.ingest(db, project_id, [b.model_dump() for b in body])


@router.post("/sensors/{sensor_id}/import")
async def import_csv(sensor_id: int, file: UploadFile, user: CurrentUser, db: DB):
    """CSV: 'ts,value' (sarlavha ixtiyoriy). ts — ISO yoki Unix soniya."""
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
        items.append({"sensor_id": s.id, "ts": row[0].strip(), "value": row[1].strip()})
    if not items:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CSV da 'ts,value' qatorlar topilmadi")
    return live.ingest(db, s.project_id, items, source="csv")


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
    if hours > 72:
        # Uzoq davr: historian (soatlik agregat) + hali yig'ilmagan soatlar xomdan
        points = historian.hourly_points(db, s.id, since, now)
        tail_since = (
            datetime.fromisoformat(points[-1]["ts"]) + timedelta(hours=1) if points else since
        )
        rows = (
            db.query(Reading.ts, Reading.value)
            .filter(Reading.sensor_id == s.id, Reading.ts >= tail_since)
            .order_by(Reading.ts)
            .all()
        )
        buckets: dict[datetime, list[float]] = {}
        for t, v in rows:
            buckets.setdefault(historian.floor_hour(t), []).append(v)
        for h, vals in sorted(buckets.items()):
            points.append(
                {
                    "ts": h.isoformat(),
                    "v": round(sum(vals) / len(vals), 4),
                    "min": round(min(vals), 4),
                    "max": round(max(vals), 4),
                }
            )
        return {
            "sensor_id": s.id,
            "unit": s.unit,
            "total": len(points),
            "points": points[-limit:],
            "hourly": True,
        }
    rows = (
        db.query(Reading.ts, Reading.value)
        .filter(Reading.sensor_id == s.id, Reading.ts >= since)
        .order_by(Reading.ts)
        .all()
    )
    total = len(rows)
    points: list[dict] = []
    if total <= limit:
        points = [
            {
                "ts": live._aware(t).isoformat(),
                "v": round(v, 4),
                "min": round(v, 4),
                "max": round(v, 4),
            }
            for t, v in rows
        ]
    else:
        per = -(-total // limit)  # har bo'lakda nechta nuqta (yuqoriga yaxlitlash)
        for i in range(0, total, per):
            chunk = rows[i : i + per]
            vals = [v for _, v in chunk]
            points.append(
                {
                    "ts": live._aware(chunk[0][0]).isoformat(),
                    "v": round(sum(vals) / len(vals), 4),
                    "min": round(min(vals), 4),
                    "max": round(max(vals), 4),
                }
            )
    return {"sensor_id": s.id, "unit": s.unit, "total": total, "points": points, "hourly": False}


@router.get("/sensors/{sensor_id}/export.csv")
def export_csv(
    sensor_id: int, user: CurrentUser, db: DB, hours: float = Query(24, gt=0, le=24 * 366)
):
    """Xom o'lchovlar CSV (ts,value) — tahlil/Excel uchun."""
    s = _get_sensor(db, sensor_id, user, Role.viewer)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ts", f"value_{s.unit or 'raw'}"])
    for t, v in (
        db.query(Reading.ts, Reading.value)
        .filter(Reading.sensor_id == s.id, Reading.ts >= since)
        .order_by(Reading.ts)
        .yield_per(1000)
    ):
        w.writerow([live._aware(t).isoformat(), v])
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{s.key}.csv"'},
    )


@router.get("/projects/{project_id}/alarms", response_model=list[SensorOut])
def alarms(project: ViewerProject, db: DB):
    live.mark_stale(db, project.id)
    return (
        db.query(Sensor)
        .filter(
            Sensor.project_id == project.id, Sensor.enabled.is_(True), Sensor.alarm != AlarmState.ok
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


class AckIn(BaseModel):
    comment: str = ""


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
    )


@router.get("/projects/{project_id}/alarm-events", response_model=list[AlarmEventOut])
def alarm_events(
    project: ViewerProject,
    db: DB,
    active: bool = False,
    hours: float = Query(24 * 7, gt=0, le=24 * 366),
    limit: int = Query(500, gt=0, le=5000),
):
    """Alarm jurnali: active=true — davom etayotgan yoki kvitlanmaganlar; aks holda tarix."""
    live.mark_stale(db, project.id)
    q = db.query(AlarmEvent).filter(AlarmEvent.project_id == project.id)
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


@router.post("/projects/{project_id}/alarm-events/ack-all")
def ack_all(project: OperatorProject, user: CurrentUser, db: DB):
    n = 0
    for e in db.query(AlarmEvent).filter_by(project_id=project.id, acked_at=None).all():
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


class DashboardIn(BaseModel):
    mimic: dict[str, int | None] = Field(default_factory=dict)
    tiles: list[int] = Field(default_factory=list)


@router.get("/projects/{project_id}/dashboard")
def dashboard(project: ViewerProject, db: DB):
    """Dispetcher paneli: sensorlar holati, mimik sxema bog'lanishi, faol alarmlar, 24 soatlik
    energiya (quvvat sensorlaridan)."""
    live.mark_stale(db, project.id)
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
                s.alarm != AlarmState.stale
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
        "active_alarms": active,
        "energy_24h_mwh": round(energy, 3) if has_power else None,
        "alarms_24h": historian.alarm_stats(db, project.id, since, now),
        "live_clients": live.hub.count(project.id),
    }


@router.put("/projects/{project_id}/dashboard")
def save_dashboard(body: DashboardIn, project: EngineerProject, user: CurrentUser, db: DB):
    ids = {s.id for s in db.query(Sensor).filter_by(project_id=project.id).all()}
    bad = [v for v in body.mimic.values() if v and v not in ids] + [
        t for t in body.tiles if t not in ids
    ]
    if bad:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Sensor loyihada yo'q: {bad}")
    project.dashboard = {"mimic": {k: v for k, v in body.mimic.items() if v}, "tiles": body.tiles}
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
        live.mark_stale(db, project_id)
        snapshot = [
            live.sensor_message(s) for s in db.query(Sensor).filter_by(project_id=project_id).all()
        ]
    await live.hub.connect(project_id, ws)
    try:
        await ws.send_json({"type": "snapshot", "sensors": snapshot})
        while True:
            await ws.receive_text()  # ping/pong yoki mijoz xabari — e'tiborsiz
    except WebSocketDisconnect:
        pass
    finally:
        live.hub.disconnect(project_id, ws)
