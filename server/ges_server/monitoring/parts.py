"""Ehtiyot qismlar ombori (CMMS): ro'yxat, kirim/sarf (ish buyrug'iga bog'lab), minimal zaxira ogohlantirishi,
va tashqi ML modeli uchun integratsiya nuqtasi (bashoratlar → ML.* virtual sensorlar).

Rollar: ko'rish — ko'ruvchi; sarf — dispetcher; qism qo'shish/tahrirlash/kirim — muhandis.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .. import audit, notifications
from ..auth.deps import DB, CurrentUser, get_project_role, has_role, require_project_role
from ..orm import Asset, PartMovement, Project, Role, Sensor, SparePart, WorkOrder, utcnow
from . import live, twin

router = APIRouter(prefix="/api", tags=["parts"])

ViewerProject = Annotated[Project, Depends(require_project_role(Role.viewer))]
OperatorProject = Annotated[Project, Depends(require_project_role(Role.operator))]
EngineerProject = Annotated[Project, Depends(require_project_role(Role.engineer))]


class PartIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    code: str = Field(default="", max_length=64)
    unit: str = Field(default="dona", max_length=16)
    qty: float = Field(default=0, ge=0)
    min_qty: float = Field(default=0, ge=0)
    location: str = Field(default="", max_length=120)
    unit_cost: float = Field(default=0, ge=0)
    asset_id: int | None = None
    notes: str = ""


class PartPatch(BaseModel):
    name: str | None = Field(None, max_length=160)
    code: str | None = None
    unit: str | None = None
    min_qty: float | None = Field(None, ge=0)
    location: str | None = None
    unit_cost: float | None = Field(None, ge=0)
    asset_id: int | None = None
    notes: str | None = None


class PartOut(BaseModel):
    id: int
    project_id: int
    name: str
    code: str
    unit: str
    qty: float
    min_qty: float
    location: str
    unit_cost: float
    asset_id: int | None
    asset_name: str | None
    notes: str
    low: bool
    updated_at: datetime


class MovementIn(BaseModel):
    qty: float = Field(description="+ kirim, − sarf")
    work_order_id: int | None = None
    note: str = Field(default="", max_length=200)


class MovementOut(BaseModel):
    id: int
    part_id: int
    part_name: str
    work_order_id: int | None
    qty: float
    note: str
    author_username: str
    created_at: datetime


def _out(db, p: SparePart) -> PartOut:
    a = db.get(Asset, p.asset_id) if p.asset_id else None
    return PartOut(
        id=p.id,
        project_id=p.project_id,
        name=p.name,
        code=p.code,
        unit=p.unit,
        qty=p.qty,
        min_qty=p.min_qty,
        location=p.location,
        unit_cost=p.unit_cost,
        asset_id=p.asset_id,
        asset_name=a.name if a else None,
        notes=p.notes,
        low=p.qty < p.min_qty,
        updated_at=live._aware(p.updated_at),
    )


def _check_asset(db, project_id: int, asset_id: int | None) -> None:
    if asset_id is not None:
        a = db.get(Asset, asset_id)
        if a is None or a.project_id != project_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aktiv loyihada yo'q")


@router.get("/projects/{project_id}/parts", response_model=list[PartOut])
def list_parts(project: ViewerProject, db: DB):
    rows = db.query(SparePart).filter_by(project_id=project.id).order_by(SparePart.name).all()
    return [_out(db, p) for p in rows]


@router.post("/projects/{project_id}/parts", response_model=PartOut, status_code=201)
def create_part(project: EngineerProject, body: PartIn, user: CurrentUser, db: DB):
    _check_asset(db, project.id, body.asset_id)
    p = SparePart(project_id=project.id, **body.model_dump())
    db.add(p)
    db.flush()
    if body.qty > 0:
        db.add(
            PartMovement(part_id=p.id, user_id=user.id, qty=body.qty, note="boshlang'ich qoldiq")
        )
    audit.log(
        db,
        user_id=user.id,
        action="part.create",
        target_type="part",
        target_id=p.id,
        project_id=project.id,
        detail={"name": p.name, "qty": p.qty},
    )
    db.commit()
    db.refresh(p)
    return _out(db, p)


def _get_part(db, part_id: int, user, role: Role) -> SparePart:
    p = db.get(SparePart, part_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Qism topilmadi")
    if not has_role(get_project_role(db, p.project_id, user), role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ruxsat yo'q")
    return p


@router.patch("/parts/{part_id}", response_model=PartOut)
def update_part(part_id: int, body: PartPatch, user: CurrentUser, db: DB):
    p = _get_part(db, part_id, user, Role.engineer)
    changes = body.model_dump(exclude_none=True)
    _check_asset(db, p.project_id, changes.get("asset_id"))
    for k in PartPatch.model_fields:
        if k in changes:
            setattr(p, k, changes[k])
    p.updated_at = utcnow()
    db.commit()
    db.refresh(p)
    return _out(db, p)


@router.delete("/parts/{part_id}", status_code=204)
def delete_part(part_id: int, user: CurrentUser, db: DB):
    p = _get_part(db, part_id, user, Role.engineer)
    audit.log(
        db,
        user_id=user.id,
        action="part.delete",
        target_type="part",
        target_id=p.id,
        project_id=p.project_id,
        detail={"name": p.name},
    )
    db.delete(p)
    db.commit()


@router.post("/parts/{part_id}/move", response_model=PartOut)
def move_part(part_id: int, body: MovementIn, user: CurrentUser, db: DB):
    """Kirim (+, muhandis) yoki sarf (−, dispetcher va yuqori). Sarf ish buyrug'iga bog'lanishi mumkin;
    qoldiq minimal zaxiradan tushsa muhandislarga bildirishnoma."""
    role_needed = Role.engineer if body.qty > 0 else Role.operator
    p = _get_part(db, part_id, user, role_needed)
    if body.qty == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Miqdor nol bo'lmasin")
    if p.qty + body.qty < 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Omborda yetarli emas: {p.qty} {p.unit}")
    if body.work_order_id is not None:
        w = db.get(WorkOrder, body.work_order_id)
        if w is None or w.project_id != p.project_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ish buyrug'i loyihada yo'q")
        if body.qty < 0:
            w.cost = (w.cost or 0) + (-body.qty) * p.unit_cost
    was_ok = p.qty >= p.min_qty
    p.qty += body.qty
    p.updated_at = utcnow()
    db.add(
        PartMovement(
            part_id=p.id,
            work_order_id=body.work_order_id,
            user_id=user.id,
            qty=body.qty,
            note=body.note,
        )
    )
    audit.log(
        db,
        user_id=user.id,
        action="part.move",
        target_type="part",
        target_id=p.id,
        project_id=p.project_id,
        detail={"qty": body.qty, "work_order_id": body.work_order_id},
    )
    if was_ok and p.qty < p.min_qty:
        notifications.push(
            db,
            notifications.member_ids(db, p.project_id, Role.engineer),
            "parts",
            f"Ehtiyot qism kam: {p.name}",
            f"qoldiq {p.qty} {p.unit} < minimal {p.min_qty}",
            f"/projects/{p.project_id}/dashboard",
        )
    db.commit()
    db.refresh(p)
    return _out(db, p)


@router.get("/parts/{part_id}/movements", response_model=list[MovementOut])
def part_movements(part_id: int, user: CurrentUser, db: DB, limit: int = 100):
    p = _get_part(db, part_id, user, Role.viewer)
    rows = (
        db.query(PartMovement)
        .filter_by(part_id=p.id)
        .order_by(PartMovement.id.desc())
        .limit(min(limit, 1000))
        .all()
    )
    return [
        MovementOut(
            id=m.id,
            part_id=m.part_id,
            part_name=p.name,
            work_order_id=m.work_order_id,
            qty=m.qty,
            note=m.note,
            author_username=m.author.username,
            created_at=live._aware(m.created_at),
        )
        for m in rows
    ]


# --- Tashqi ML modeli integratsiya nuqtasi ---
class Prediction(BaseModel):
    key: str = Field(
        min_length=1, max_length=48, description="ML.<nom> (prefiks avtomatik qo'shiladi)"
    )
    name: str = Field(default="", max_length=128)
    value: float
    unit: str = Field(default="", max_length=16)
    ts: datetime | None = None
    low_alarm: float | None = None
    high_alarm: float | None = None
    element_guid: str | None = None


class PredictionsIn(BaseModel):
    predictions: list[Prediction] = Field(min_length=1, max_length=500)
    model: str = Field(default="", max_length=64)


@router.post("/projects/{project_id}/ml/predictions")
def ml_predictions(project: EngineerProject, body: PredictionsIn, user: CurrentUser, db: DB):
    """Tashqi ML modeli bashoratlari: ML.<key> virtual sensorlar (protocol="ml") yaratiladi/yangilanadi va
    qiymatlar historian/alarm/jonli oqimga kiradi (oddiy sensor kabi: trend, chegara, dashboard, egizak)."""
    items = []
    for pr in body.predictions:
        key = pr.key if pr.key.startswith("ML.") else f"ML.{pr.key}"
        s = db.query(Sensor).filter_by(project_id=project.id, key=key).first()
        if s is None:
            s = twin.twin_sensor(
                db,
                project.id,
                key,
                pr.name or key,
                pr.unit,
                kind="value",
                low=pr.low_alarm,
                high=pr.high_alarm,
            )
            s.protocol = "ml"
        if pr.name:
            s.name = pr.name
        if pr.unit:
            s.unit = pr.unit
        if pr.low_alarm is not None:
            s.low_alarm = pr.low_alarm
        if pr.high_alarm is not None:
            s.high_alarm = pr.high_alarm
        if pr.element_guid:
            s.element_guid = pr.element_guid
        s.address = {**(s.address or {}), "model": body.model} if body.model else s.address
        item = {"key": key, "value": pr.value}
        if pr.ts:
            item["ts"] = pr.ts.isoformat()
        items.append(item)
    db.commit()
    res = live.ingest(db, project.id, items, source="ml")
    audit.log(
        db,
        user_id=user.id,
        action="ml.predictions",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
        detail={"model": body.model, "n": len(items)},
    )
    db.commit()
    return res
