"""Ish buyruqlari (CMMS): yaratish (qo'lda, sog'liq muammosidan, alarmdan, profilaktik rejadan),
tayinlash, holat, yopish (natija, to'xtab turish soati, ISO 14224 nosozlik kodlari), mehnat yozuvi,
ehtiyot qism bandlash/sarflash, ruxsatnoma (PTW) va LOTO, aktiv tarixi, KPI (ochiq, MTTR, MTBF).

Rollar: ko'rish — ko'ruvchi; yaratish/holat — dispetcher (operator) va yuqori; tayinlash/o'chirish — muhandis.
Tayinlangan foydalanuvchiga bildirishnoma; hodisalar audit jurnalida va jonli oqimda ({"type": "workorder"}).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from .. import audit, notifications
from ..auth.deps import DB, CurrentUser, get_project_role, has_role, require_project_role
from ..orm import (
    Asset,
    LaborEntry,
    MaintenancePlan,
    PartReservation,
    Project,
    Role,
    SparePart,
    User,
    WorkOrder,
    WorkOrderStatus,
    utcnow,
)
from . import cmms, live

router = APIRouter(prefix="/api", tags=["workorders"])

ViewerProject = Annotated[Project, Depends(require_project_role(Role.viewer))]
OperatorProject = Annotated[Project, Depends(require_project_role(Role.operator))]
EngineerProject = Annotated[Project, Depends(require_project_role(Role.engineer))]

Priority = Literal["low", "medium", "high", "critical"]
Source = Literal["manual", "health", "alarm", "maintenance", "plan"]


class WorkOrderIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    asset_id: int | None = None
    assignee_id: int | None = None
    priority: Priority = "medium"
    source: Source = "manual"
    due_at: datetime | None = None
    tasks: list[dict] = Field(default_factory=list, description="[{title, done}] ish rejasi")
    permit_required: bool = False
    labor_rate: float = Field(default=0, ge=0)


class WorkOrderPatch(BaseModel):
    title: str | None = Field(None, max_length=200)
    description: str | None = None
    assignee_id: int | None = None
    priority: Priority | None = None
    status: WorkOrderStatus | None = None
    due_at: datetime | None = None
    downtime_hours: float | None = None
    cost: float | None = None
    resolution: str | None = None
    # H2
    tasks: list[dict] | None = None
    failure_mode: str | None = None
    failure_cause: str | None = None
    detection_method: str | None = None
    labor_rate: float | None = Field(None, ge=0)
    extra_cost: float | None = Field(None, ge=0)
    permit_required: bool | None = None


class WorkOrderOut(BaseModel):
    id: int
    project_id: int
    asset_id: int | None
    asset_name: str | None
    title: str
    description: str
    priority: str
    source: str
    status: WorkOrderStatus
    author_username: str
    assignee_id: int | None
    assignee_username: str | None
    due_at: datetime | None
    started_at: datetime | None
    closed_at: datetime | None
    downtime_hours: float
    cost: float
    resolution: str
    created_at: datetime
    updated_at: datetime
    overdue: bool
    # H2
    plan_id: int | None
    tasks: list[dict]
    failure_mode: str | None
    failure_cause: str | None
    detection_method: str | None
    labor_rate: float
    labor_hours: float
    labor_cost: float
    parts_cost: float
    extra_cost: float
    permit_required: bool
    permit_status: str
    permit_note: str
    loto_active: bool
    loto_points: list[dict]


class LaborIn(BaseModel):
    hours: float = Field(gt=0, le=1000)
    note: str = Field(default="", max_length=300)
    user_id: int | None = Field(default=None, description="boshqa xodim (muhandis huquqi)")
    rate: float | None = Field(default=None, ge=0)
    work_date: datetime | None = None


class LaborOut(BaseModel):
    id: int
    work_order_id: int
    user_id: int
    username: str
    hours: float
    rate: float | None
    note: str
    work_date: datetime


class ReserveIn(BaseModel):
    part_id: int
    qty: float = Field(ge=0, description="0 — bandlikni bekor qilish")


class ConsumeIn(BaseModel):
    part_id: int
    qty: float = Field(gt=0)
    note: str = Field(default="", max_length=200)


class PartLineOut(BaseModel):
    part_id: int
    part_name: str
    unit: str
    reserved: float
    consumed: float
    free: float
    stock: float


class PermitIn(BaseModel):
    status: Literal["none", "requested", "issued", "closed"]
    note: str = Field(default="", max_length=1000)


class LotoIn(BaseModel):
    active: bool
    points: list[dict] | None = Field(default=None, description="[{label, sensor_id?}] izolyatsiya nuqtalari")
    note: str = Field(default="", max_length=300)


def _aware(d: datetime | None) -> datetime | None:
    return live._aware(d) if d else None


def _out(w: WorkOrder, db=None) -> WorkOrderOut:
    due = _aware(w.due_at)
    return WorkOrderOut(
        id=w.id,
        project_id=w.project_id,
        asset_id=w.asset_id,
        asset_name=w.asset.name if w.asset else None,
        title=w.title,
        description=w.description,
        priority=w.priority,
        source=w.source,
        status=w.status,
        author_username=w.author.username,
        assignee_id=w.assignee_id,
        assignee_username=w.assignee.username if w.assignee else None,
        due_at=due,
        started_at=_aware(w.started_at),
        closed_at=_aware(w.closed_at),
        downtime_hours=w.downtime_hours,
        cost=w.cost,
        resolution=w.resolution,
        created_at=_aware(w.created_at),
        updated_at=_aware(w.updated_at),
        overdue=bool(
            due
            and w.status in (WorkOrderStatus.open, WorkOrderStatus.in_progress)
            and due < datetime.now(timezone.utc)
        ),
        plan_id=w.plan_id,
        tasks=list(w.tasks or []),
        failure_mode=w.failure_mode,
        failure_cause=w.failure_cause,
        detection_method=w.detection_method,
        labor_rate=w.labor_rate or 0.0,
        labor_hours=cmms.labor_hours(db, w) if db is not None else 0.0,
        labor_cost=w.labor_cost or 0.0,
        parts_cost=w.parts_cost or 0.0,
        extra_cost=w.extra_cost or 0.0,
        permit_required=bool(w.permit_required),
        permit_status=w.permit_status or "none",
        permit_note=w.permit_note or "",
        loto_active=bool(w.loto_active),
        loto_points=list(w.loto_points or []),
    )


def _check_refs(db, project_id: int, asset_id: int | None, assignee_id: int | None) -> None:
    if asset_id is not None:
        a = db.get(Asset, asset_id)
        if a is None or a.project_id != project_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aktiv loyihada yo'q")
    if assignee_id is not None:
        if db.get(User, assignee_id) is None or assignee_id not in notifications.member_ids(
            db, project_id, with_admins=True
        ):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ijrochi loyiha a'zosi emas")


@router.get("/projects/{project_id}/work-orders", response_model=list[WorkOrderOut])
def list_work_orders(
    project: ViewerProject,
    db: DB,
    status_: Annotated[str | None, Query(alias="status")] = None,
    asset_id: int | None = None,
    limit: int = 200,
):
    q = db.query(WorkOrder).filter_by(project_id=project.id)
    if status_:
        q = q.filter(WorkOrder.status == WorkOrderStatus(status_))
    if asset_id:
        q = q.filter(WorkOrder.asset_id == asset_id)
    rows = q.order_by(WorkOrder.status, WorkOrder.created_at.desc()).limit(min(limit, 1000)).all()
    return [_out(w, db) for w in rows]


@router.post("/projects/{project_id}/work-orders", response_model=WorkOrderOut, status_code=201)
def create_work_order(project: OperatorProject, body: WorkOrderIn, user: CurrentUser, db: DB):
    _check_refs(db, project.id, body.asset_id, body.assignee_id)
    w = WorkOrder(project_id=project.id, created_by=user.id, **body.model_dump())
    db.add(w)
    db.flush()
    audit.log(
        db,
        user_id=user.id,
        action="workorder.create",
        target_type="workorder",
        target_id=w.id,
        project_id=project.id,
        detail={"title": w.title, "priority": w.priority, "source": w.source},
    )
    if w.assignee_id and w.assignee_id != user.id:
        notifications.push(
            db,
            [w.assignee_id],
            "workorder",
            f"Ish buyrug'i: {w.title}",
            f"{project.name} · {w.priority} · {w.asset.name if w.asset else ''}",
            f"/projects/{project.id}/dashboard",
        )
    db.commit()
    db.refresh(w)
    out = _out(w, db)
    live.hub.publish(project.id, {"type": "workorder", "order": out.model_dump(mode="json")})
    return out


def _get(db, wo_id: int, user, role: Role) -> WorkOrder:
    w = db.get(WorkOrder, wo_id)
    if w is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ish buyrug'i topilmadi")
    if not has_role(get_project_role(db, w.project_id, user), role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ruxsat yo'q")
    return w


@router.patch("/work-orders/{wo_id}", response_model=WorkOrderOut)
def update_work_order(wo_id: int, body: WorkOrderPatch, user: CurrentUser, db: DB):
    w = _get(db, wo_id, user, Role.operator)
    changes = body.model_dump(exclude_none=True)
    if "assignee_id" in changes and not has_role(
        get_project_role(db, w.project_id, user), Role.engineer
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tayinlash — muhandis huquqi")
    _check_refs(db, w.project_id, None, changes.get("assignee_id"))
    try:
        cmms.check_codes(
            changes.get("failure_mode"), changes.get("failure_cause"), changes.get("detection_method")
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    old_status = w.status
    new_status = changes.get("status", w.status)
    if new_status in (WorkOrderStatus.done, WorkOrderStatus.cancelled) and w.loto_active:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "LOTO faol — avval izolyatsiyani olib tashlang (energiya qaytarilishi xavfli)",
        )
    for k in WorkOrderPatch.model_fields:
        if k in changes:
            setattr(w, k, changes[k])
    if {"labor_rate", "extra_cost"} & set(changes) and "cost" not in changes:
        cmms.recompute_cost(db, w)
    now = utcnow()
    if w.status == WorkOrderStatus.in_progress and w.started_at is None:
        w.started_at = now
    if w.status in (WorkOrderStatus.done, WorkOrderStatus.cancelled) and w.closed_at is None:
        w.closed_at = now
    if w.status in (WorkOrderStatus.open, WorkOrderStatus.in_progress):
        w.closed_at = None
    w.updated_at = now
    audit.log(
        db,
        user_id=user.id,
        action="workorder.update",
        target_type="workorder",
        target_id=w.id,
        project_id=w.project_id,
        detail={
            k: (v.value if hasattr(v, "value") else v)
            for k, v in changes.items()
            if k != "description"
        },
    )
    if "assignee_id" in changes and w.assignee_id and w.assignee_id != user.id:
        notifications.push(
            db,
            [w.assignee_id],
            "workorder",
            f"Ish buyrug'i tayinlandi: {w.title}",
            "",
            f"/projects/{w.project_id}/dashboard",
        )
    if old_status != w.status and w.created_by != user.id:
        notifications.push(
            db,
            [w.created_by],
            "workorder",
            f"Ish buyrug'i {w.status.value}: {w.title}",
            w.resolution or "",
            f"/projects/{w.project_id}/dashboard",
        )
    db.commit()
    db.refresh(w)
    out = _out(w, db)
    live.hub.publish(w.project_id, {"type": "workorder", "order": out.model_dump(mode="json")})
    return out


@router.delete("/work-orders/{wo_id}", status_code=204)
def delete_work_order(wo_id: int, user: CurrentUser, db: DB):
    w = _get(db, wo_id, user, Role.engineer)
    audit.log(
        db,
        user_id=user.id,
        action="workorder.delete",
        target_type="workorder",
        target_id=w.id,
        project_id=w.project_id,
        detail={"title": w.title},
    )
    db.delete(w)
    db.commit()


@router.get("/projects/{project_id}/work-orders/kpi")
def work_order_kpi(project: ViewerProject, db: DB):
    """KPI: ochiq/bajarilayotgan/muddati o'tgan; oxirgi 90 kun — bajarilgan soni, MTTR (o'rtacha
    boshlash→yopish, soat), MTBF (aktiv bo'yicha ikki nosozlik orasidagi o'rtacha vaqt, soat), to'xtab turish."""
    now = datetime.now(timezone.utc)
    rows = db.query(WorkOrder).filter_by(project_id=project.id).all()
    open_ = [w for w in rows if w.status == WorkOrderStatus.open]
    prog = [w for w in rows if w.status == WorkOrderStatus.in_progress]
    overdue = [w for w in open_ + prog if w.due_at and live._aware(w.due_at) < now]
    done90 = [
        w
        for w in rows
        if w.status == WorkOrderStatus.done
        and w.closed_at
        and live._aware(w.closed_at) >= now - timedelta(days=90)
    ]
    ttr = [
        (live._aware(w.closed_at) - live._aware(w.started_at or w.created_at)).total_seconds()
        / 3600
        for w in done90
        if w.closed_at
    ]
    mttr = round(sum(ttr) / len(ttr), 1) if ttr else None
    # MTBF: aktivlar bo'yicha nosozlik (source alarm/health) buyruqlari orasidagi o'rtacha vaqt
    gaps: list[float] = []
    by_asset: dict[int, list[datetime]] = {}
    for w in rows:
        if w.asset_id and w.source in ("alarm", "health"):
            by_asset.setdefault(w.asset_id, []).append(live._aware(w.created_at))
    for ts in by_asset.values():
        ts.sort()
        gaps += [(b - a).total_seconds() / 3600 for a, b in zip(ts, ts[1:], strict=False)]
    mtbf = round(sum(gaps) / len(gaps), 1) if gaps else None
    return {
        "open": len(open_),
        "in_progress": len(prog),
        "overdue": len(overdue),
        "done_90d": len(done90),
        "mttr_hours": mttr,
        "mtbf_hours": mtbf,
        "downtime_90d_hours": round(sum(w.downtime_hours for w in done90), 1),
        "cost_90d": round(sum(w.cost for w in done90), 2),
        "by_priority": {
            p: sum(1 for w in open_ + prog if w.priority == p)
            for p in ("critical", "high", "medium", "low")
        },
    }


# =============================================================== H2 — profilaktik xizmat rejalari


class PlanIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    asset_id: int | None = None
    tasks: list[str] = Field(default_factory=list)
    interval_days: int | None = Field(default=None, ge=1, le=3650)
    interval_hours: float | None = Field(default=None, gt=0, le=200000)
    priority: Priority = "medium"
    lead_days: int = Field(default=7, ge=0, le=365)
    permit_required: bool = False
    active: bool = True
    last_generated_at: datetime | None = Field(
        default=None, description="oxirgi bajarilgan xizmat sanasi (mavjud uskunani ro'yxatga olishda)"
    )
    last_run_hours: float = Field(default=0, ge=0, description="oxirgi xizmatdagi ish soati hisoblagichi")


class PlanPatch(BaseModel):
    name: str | None = Field(None, max_length=200)
    description: str | None = None
    asset_id: int | None = None
    tasks: list[str] | None = None
    interval_days: int | None = Field(None, ge=1, le=3650)
    interval_hours: float | None = Field(None, gt=0, le=200000)
    priority: Priority | None = None
    lead_days: int | None = Field(None, ge=0, le=365)
    permit_required: bool | None = None
    active: bool | None = None
    last_generated_at: datetime | None = None
    last_run_hours: float | None = Field(None, ge=0)


class PlanOut(BaseModel):
    id: int
    project_id: int
    asset_id: int | None
    asset_name: str | None
    name: str
    description: str
    tasks: list[str]
    interval_days: int | None
    interval_hours: float | None
    priority: str
    lead_days: int
    permit_required: bool
    active: bool
    last_generated_at: datetime | None
    last_run_hours: float
    due_reason: str | None
    created_at: datetime


def _plan_out(p: MaintenancePlan, due_reason: str | None = None) -> PlanOut:
    return PlanOut(
        id=p.id,
        project_id=p.project_id,
        asset_id=p.asset_id,
        asset_name=p.asset.name if p.asset else None,
        name=p.name,
        description=p.description,
        tasks=list(p.tasks or []),
        interval_days=p.interval_days,
        interval_hours=p.interval_hours,
        priority=p.priority,
        lead_days=p.lead_days,
        permit_required=bool(p.permit_required),
        active=bool(p.active),
        last_generated_at=_aware(p.last_generated_at),
        last_run_hours=p.last_run_hours or 0.0,
        due_reason=due_reason,
        created_at=_aware(p.created_at),
    )


def _check_intervals(
    interval_days: int | None, interval_hours: float | None, asset_id: int | None
) -> None:
    if not interval_days and not interval_hours:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Davriylik kerak: kun (interval_days) yoki ish soati (interval_hours)",
        )
    if interval_hours and asset_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Ish soati bo'yicha davriylik uchun aktiv (hisoblagich) kerak",
        )


@router.get("/projects/{project_id}/maintenance-plans", response_model=list[PlanOut])
def list_plans(project: ViewerProject, db: DB):
    rows = (
        db.query(MaintenancePlan)
        .filter_by(project_id=project.id)
        .order_by(MaintenancePlan.active.desc(), MaintenancePlan.name)
        .all()
    )
    now = datetime.now(timezone.utc)
    hours = (
        cmms.run_hours_map(db, project) if any(p.interval_hours and p.asset_id for p in rows) else {}
    )
    return [_plan_out(p, cmms.plan_due(p, hours, now)) for p in rows]


@router.post("/projects/{project_id}/maintenance-plans", response_model=PlanOut, status_code=201)
def create_plan(project: EngineerProject, body: PlanIn, user: CurrentUser, db: DB):
    _check_refs(db, project.id, body.asset_id, None)
    _check_intervals(body.interval_days, body.interval_hours, body.asset_id)
    p = MaintenancePlan(project_id=project.id, created_by=user.id, **body.model_dump())
    db.add(p)
    db.flush()
    audit.log(
        db,
        user_id=user.id,
        action="plan.create",
        target_type="plan",
        target_id=p.id,
        project_id=project.id,
        detail={"name": p.name, "days": p.interval_days, "hours": p.interval_hours},
    )
    db.commit()
    db.refresh(p)
    return _plan_out(p)


def _get_plan(db, plan_id: int, user, role: Role) -> MaintenancePlan:
    p = db.get(MaintenancePlan, plan_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reja topilmadi")
    if not has_role(get_project_role(db, p.project_id, user), role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ruxsat yo'q")
    return p


@router.patch("/maintenance-plans/{plan_id}", response_model=PlanOut)
def update_plan(plan_id: int, body: PlanPatch, user: CurrentUser, db: DB):
    p = _get_plan(db, plan_id, user, Role.engineer)
    changes = body.model_dump(exclude_unset=True)
    if "asset_id" in changes:
        _check_refs(db, p.project_id, changes["asset_id"], None)
    _check_intervals(
        changes.get("interval_days", p.interval_days),
        changes.get("interval_hours", p.interval_hours),
        changes.get("asset_id", p.asset_id),
    )
    for k, v in changes.items():
        setattr(p, k, v)
    audit.log(
        db,
        user_id=user.id,
        action="plan.update",
        target_type="plan",
        target_id=p.id,
        project_id=p.project_id,
        detail={k: v for k, v in changes.items() if k != "description"},
    )
    db.commit()
    db.refresh(p)
    return _plan_out(p)


@router.delete("/maintenance-plans/{plan_id}", status_code=204)
def delete_plan(plan_id: int, user: CurrentUser, db: DB):
    p = _get_plan(db, plan_id, user, Role.engineer)
    audit.log(
        db,
        user_id=user.id,
        action="plan.delete",
        target_type="plan",
        target_id=p.id,
        project_id=p.project_id,
        detail={"name": p.name},
    )
    db.delete(p)
    db.commit()


@router.post("/projects/{project_id}/maintenance-plans/run", response_model=list[WorkOrderOut])
def run_plans(project: EngineerProject, user: CurrentUser, db: DB):
    """Rejalarni darhol tekshirish (fon vazifasi soatiga bir marta o'zi bajaradi)."""
    created = cmms.generate_work_orders(db, project)
    for w in created:
        audit.log(
            db,
            user_id=user.id,
            action="workorder.create",
            target_type="workorder",
            target_id=w.id,
            project_id=project.id,
            detail={"title": w.title, "source": "plan", "plan_id": w.plan_id},
        )
    db.commit()
    out = [_out(w, db) for w in created]
    for o in out:
        live.hub.publish(project.id, {"type": "workorder", "order": o.model_dump(mode="json")})
    return out


# =============================================================== H2 — mehnat yozuvi


@router.get("/work-orders/{wo_id}/labor", response_model=list[LaborOut])
def list_labor(wo_id: int, user: CurrentUser, db: DB):
    w = _get(db, wo_id, user, Role.viewer)
    rows = db.query(LaborEntry).filter_by(work_order_id=w.id).order_by(LaborEntry.id).all()
    return [
        LaborOut(
            id=e.id,
            work_order_id=e.work_order_id,
            user_id=e.user_id,
            username=e.user.username,
            hours=e.hours,
            rate=e.rate,
            note=e.note,
            work_date=_aware(e.work_date),
        )
        for e in rows
    ]


@router.post("/work-orders/{wo_id}/labor", response_model=WorkOrderOut, status_code=201)
def add_labor(wo_id: int, body: LaborIn, user: CurrentUser, db: DB):
    """Mehnat yozuvi: o'z vaqtini dispetcher yozadi; boshqa xodim nomidan — muhandis."""
    w = _get(db, wo_id, user, Role.operator)
    uid = body.user_id or user.id
    if uid != user.id and not has_role(get_project_role(db, w.project_id, user), Role.engineer):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Boshqa xodim nomidan yozish — muhandis huquqi"
        )
    if uid != user.id:
        _check_refs(db, w.project_id, None, uid)
    e = LaborEntry(
        work_order_id=w.id,
        user_id=uid,
        hours=body.hours,
        rate=body.rate,
        note=body.note,
        work_date=body.work_date or utcnow(),
    )
    db.add(e)
    db.flush()
    cmms.recompute_cost(db, w)
    w.updated_at = utcnow()
    audit.log(
        db,
        user_id=user.id,
        action="workorder.labor",
        target_type="workorder",
        target_id=w.id,
        project_id=w.project_id,
        detail={"hours": body.hours, "for": uid},
    )
    db.commit()
    db.refresh(w)
    return _out(w, db)


@router.delete("/work-orders/{wo_id}/labor/{entry_id}", response_model=WorkOrderOut)
def delete_labor(wo_id: int, entry_id: int, user: CurrentUser, db: DB):
    w = _get(db, wo_id, user, Role.operator)
    e = db.get(LaborEntry, entry_id)
    if e is None or e.work_order_id != w.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Yozuv topilmadi")
    if e.user_id != user.id and not has_role(
        get_project_role(db, w.project_id, user), Role.engineer
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Begona yozuvni o'chirish — muhandis huquqi")
    db.delete(e)
    db.flush()
    cmms.recompute_cost(db, w)
    db.commit()
    db.refresh(w)
    return _out(w, db)


# =============================================================== H2 — ehtiyot qism bandlash/sarflash


def _part_lines(db, w: WorkOrder) -> list[PartLineOut]:
    lines: dict[int, PartLineOut] = {}

    def line_for(p: SparePart) -> PartLineOut:
        row = lines.get(p.id)
        if row is None:
            row = lines[p.id] = PartLineOut(
                part_id=p.id,
                part_name=p.name,
                unit=p.unit,
                reserved=0.0,
                consumed=0.0,
                free=cmms.free_qty(db, p),
                stock=p.qty,
            )
        return row

    for r in db.query(PartReservation).filter_by(work_order_id=w.id).all():
        line_for(r.part).reserved = r.qty
    for m in cmms.consumed_movements(db, w):
        if m.part is not None:
            line = line_for(m.part)
            line.consumed = round(line.consumed + -m.qty, 3)
    return sorted(lines.values(), key=lambda x: x.part_name)


def _get_part_for(db, w: WorkOrder, part_id: int) -> SparePart:
    p = db.get(SparePart, part_id)
    if p is None or p.project_id != w.project_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ehtiyot qism loyihada yo'q")
    return p


@router.get("/work-orders/{wo_id}/parts", response_model=list[PartLineOut])
def list_wo_parts(wo_id: int, user: CurrentUser, db: DB):
    w = _get(db, wo_id, user, Role.viewer)
    return _part_lines(db, w)


@router.post("/work-orders/{wo_id}/parts/reserve", response_model=list[PartLineOut])
def reserve_part(wo_id: int, body: ReserveIn, user: CurrentUser, db: DB):
    """Bandlash: ombor qoldig'i kamaymaydi, bo'sh qoldiq kamayadi (qty=0 — bekor qilish)."""
    w = _get(db, wo_id, user, Role.operator)
    p = _get_part_for(db, w, body.part_id)
    try:
        cmms.reserve(db, w, p, body.qty)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    audit.log(
        db,
        user_id=user.id,
        action="workorder.part_reserve",
        target_type="workorder",
        target_id=w.id,
        project_id=w.project_id,
        detail={"part_id": p.id, "qty": body.qty},
    )
    db.commit()
    return _part_lines(db, w)


@router.post("/work-orders/{wo_id}/parts/consume", response_model=list[PartLineOut])
def consume_part(wo_id: int, body: ConsumeIn, user: CurrentUser, db: DB):
    """Sarflash: ombordan chiqim, avval shu buyruqdagi bandlikdan yechiladi; xarajat qayta hisoblanadi."""
    w = _get(db, wo_id, user, Role.operator)
    p = _get_part_for(db, w, body.part_id)
    was_ok = p.qty >= p.min_qty
    try:
        cmms.consume(db, w, p, body.qty, user.id, body.note)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    p.updated_at = utcnow()
    w.updated_at = utcnow()
    audit.log(
        db,
        user_id=user.id,
        action="workorder.part_consume",
        target_type="workorder",
        target_id=w.id,
        project_id=w.project_id,
        detail={"part_id": p.id, "qty": body.qty},
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
    return _part_lines(db, w)


# =============================================================== H2 — ruxsatnoma (PTW) va LOTO


@router.post("/work-orders/{wo_id}/permit", response_model=WorkOrderOut)
def set_permit(wo_id: int, body: PermitIn, user: CurrentUser, db: DB):
    """Ruxsatnoma (permit-to-work): so'rash — dispetcher; berish/yopish — tasdiqlovchi (approver)."""
    w = _get(db, wo_id, user, Role.operator)
    if body.status in ("issued", "closed") and not has_role(
        get_project_role(db, w.project_id, user), Role.approver
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Ruxsatnoma berish/yopish — tasdiqlovchi huquqi"
        )
    if body.status == "closed" and w.loto_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "LOTO faol — avval izolyatsiyani olib tashlang")
    w.permit_status = body.status
    w.permit_note = body.note or w.permit_note
    if body.status == "issued":
        w.permit_issued_by = user.id
        w.permit_issued_at = utcnow()
    w.updated_at = utcnow()
    audit.log(
        db,
        user_id=user.id,
        action="workorder.permit",
        target_type="workorder",
        target_id=w.id,
        project_id=w.project_id,
        detail={"status": body.status},
    )
    if body.status == "requested":
        notifications.push(
            db,
            notifications.member_ids(db, w.project_id, Role.approver),
            "workorder",
            f"Ruxsatnoma so'raldi: {w.title}",
            body.note[:200],
            f"/projects/{w.project_id}/dashboard",
        )
    db.commit()
    db.refresh(w)
    out = _out(w, db)
    live.hub.publish(w.project_id, {"type": "workorder", "order": out.model_dump(mode="json")})
    return out


@router.post("/work-orders/{wo_id}/loto", response_model=WorkOrderOut)
def set_loto(wo_id: int, body: LotoIn, user: CurrentUser, db: DB):
    """LOTO (Lockout/Tagout, IEC 60204-1 §5.3): izolyatsiya qo'yilganda shu aktivga tegishli sensorlarga
    boshqaruv buyrug'i taqiqlanadi (chetlab o'tib bo'lmaydi). Ruxsatnoma talab qilinsa — berilgan
    bo'lishi kerak. Olib tashlash — qo'ygan xodim yoki tasdiqlovchi."""
    w = _get(db, wo_id, user, Role.operator)
    if body.active:
        if w.status not in cmms.OPEN_STATES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Yopilgan buyruqqa LOTO qo'yilmaydi")
        if w.permit_required and w.permit_status != "issued":
            raise HTTPException(status.HTTP_409_CONFLICT, "Avval ruxsatnoma berilishi kerak")
        w.loto_active = True
        w.loto_points = body.points if body.points is not None else list(w.loto_points or [])
        w.loto_applied_by = user.id
        w.loto_applied_at = utcnow()
        w.loto_removed_at = None
    else:
        if (
            w.loto_applied_by
            and w.loto_applied_by != user.id
            and not has_role(get_project_role(db, w.project_id, user), Role.approver)
        ):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "LOTO ni qo'ygan xodim yoki tasdiqlovchi olib tashlaydi"
            )
        w.loto_active = False
        w.loto_removed_at = utcnow()
    w.updated_at = utcnow()
    audit.log(
        db,
        user_id=user.id,
        action="workorder.loto",
        target_type="workorder",
        target_id=w.id,
        project_id=w.project_id,
        detail={"active": body.active, "points": len(w.loto_points or []), "note": body.note},
    )
    notifications.push(
        db,
        notifications.member_ids(db, w.project_id, Role.operator, at_least=True),
        "workorder",
        ("LOTO qo'yildi: " if body.active else "LOTO olib tashlandi: ") + w.title,
        body.note[:200] or (w.asset.name if w.asset else ""),
        f"/projects/{w.project_id}/dashboard",
    )
    db.commit()
    db.refresh(w)
    out = _out(w, db)
    live.hub.publish(w.project_id, {"type": "workorder", "order": out.model_dump(mode="json")})
    return out


@router.get("/projects/{project_id}/loto")
def active_loto(project: ViewerProject, db: DB):
    """Faol LOTO ro'yxati (boshqaruv ekranida ogohlantirish uchun)."""
    rows = (
        db.query(WorkOrder)
        .filter(
            WorkOrder.project_id == project.id,
            WorkOrder.loto_active.is_(True),
            WorkOrder.status.in_(cmms.OPEN_STATES),
        )
        .order_by(WorkOrder.id)
        .all()
    )
    return {
        "items": [
            {
                "work_order_id": w.id,
                "title": w.title,
                "asset_id": w.asset_id,
                "asset_name": w.asset.name if w.asset else None,
                "points": list(w.loto_points or []),
                "applied_at": _aware(w.loto_applied_at),
            }
            for w in rows
        ]
    }


# =============================================================== H2 — tarix va kodlar


@router.get("/cmms/codes")
def cmms_codes():
    """ISO 14224 nosozlik rejimi / sabab / aniqlash usuli kodlari (interfeys ro'yxatlari uchun)."""
    return {
        "failure_modes": cmms.FAILURE_MODES,
        "failure_causes": cmms.FAILURE_CAUSES,
        "detection_methods": cmms.DETECTION_METHODS,
    }


@router.get("/assets/{asset_id}/history")
def asset_history(asset_id: int, user: CurrentUser, db: DB):
    """Aktiv bo'yicha xizmat tarixi va xarajat hisoboti (ISO 55001 aktiv yozuvi)."""
    a = db.get(Asset, asset_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aktiv topilmadi")
    if not has_role(get_project_role(db, a.project_id, user), Role.viewer):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ruxsat yo'q")
    return cmms.asset_history(db, a)
