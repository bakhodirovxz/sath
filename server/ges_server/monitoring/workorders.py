"""Ish buyruqlari (CMMS-lite): yaratish (qo'lda, sog'liq muammosidan, alarmdan), tayinlash, holat,
yopish (natija, to'xtab turish soati, xarajat), KPI (ochiq, MTTR, MTBF, 30 kun).

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
from ..orm import Asset, Project, Role, User, WorkOrder, WorkOrderStatus, utcnow
from . import live

router = APIRouter(prefix="/api", tags=["workorders"])

ViewerProject = Annotated[Project, Depends(require_project_role(Role.viewer))]
OperatorProject = Annotated[Project, Depends(require_project_role(Role.operator))]

Priority = Literal["low", "medium", "high", "critical"]
Source = Literal["manual", "health", "alarm", "maintenance"]


class WorkOrderIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    asset_id: int | None = None
    assignee_id: int | None = None
    priority: Priority = "medium"
    source: Source = "manual"
    due_at: datetime | None = None


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


def _aware(d: datetime | None) -> datetime | None:
    return live._aware(d) if d else None


def _out(w: WorkOrder) -> WorkOrderOut:
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
    return [_out(w) for w in rows]


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
    out = _out(w)
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
    old_status = w.status
    for k in WorkOrderPatch.model_fields:
        if k in changes:
            setattr(w, k, changes[k])
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
    out = _out(w)
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
