"""Foydalanuvchi vazifalari va loyiha vaqt chizig'i (UX-12).

- `GET /api/me/tasks` — "Mening vazifalarim": meni kutayotgan tasdiqlash so'rovlari (CR), menga biriktirilgan
  muammolar (issue) va ish buyruqlari, o'zgartirish so'ralgan o'z CR larim, ikki kishi qoidasida tasdiq kutayotgan
  boshqaruv buyruqlari (muallif o'zi emas).
- `GET /api/projects/{project_id}/history` — loyiha vaqt chizig'i (SOE `/timeline` dan farqli), bitta o'qda: versiyalar, CR lar, nashr (merge), muammolar,
  ish buyruqlari, alarmlar (eng yangisi birinchi).

Faqat o'qish; yangi jadval/migratsiya yo'q. Ruxsat: loyiha a'zosi (admin — hamma loyiha).
"""

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth.deps import DB, CurrentUser, get_project_role, has_role
from ..orm import (
    AlarmEvent,
    AlarmState,
    ChangeRequest,
    Command,
    CommandStatus,
    CRStatus,
    Issue,
    IssueStatus,
    Model,
    Project,
    ProjectMember,
    Review,
    Role,
    Sensor,
    User,
    Version,
    WorkOrder,
    WorkOrderStatus,
    utcnow,
)

try:  # SCADA-01 (asosiy tarmoq): ruxsatlar matritsasi — ikkinchi imzo faqat smena boshlig'ida
    from ..auth.deps import has_permission as _has_permission
except ImportError:  # pragma: no cover — eski tarmoq: operator+ tasdiqlaydi
    _has_permission = None

router = APIRouter(prefix="/api", tags=["me"])


# ---------- Sxemalar ----------


class TaskCR(BaseModel):
    id: int
    title: str
    status: str
    project_id: int
    project_name: str
    model_id: int
    model_name: str
    version_id: int
    version_number: int
    author: str
    created_at: datetime


class TaskIssue(BaseModel):
    id: int
    title: str
    status: str
    priority: str
    project_id: int
    project_name: str
    model_id: int
    model_name: str
    updated_at: datetime


class TaskWorkOrder(BaseModel):
    id: int
    title: str
    status: str
    priority: str
    project_id: int
    project_name: str
    due_at: datetime | None
    loto_active: bool


class TaskCommand(BaseModel):
    id: int
    project_id: int
    project_name: str
    sensor_id: int
    sensor_name: str
    sensor_key: str
    unit: str
    value: float
    author: str
    created_at: datetime


class MyTasks(BaseModel):
    reviews: list[TaskCR]
    my_change_requests: list[TaskCR]
    issues: list[TaskIssue]
    work_orders: list[TaskWorkOrder]
    command_approvals: list[TaskCommand]
    total: int


TimelineKind = Literal["version", "cr", "publish", "cr_rejected", "issue", "work_order", "alarm"]


class TimelineItem(BaseModel):
    ts: datetime
    kind: TimelineKind
    title: str
    detail: str = ""
    actor: str = ""
    severity: str | None = None  # alarm: ustuvorlik; issue/work_order: prioritet
    model_id: int | None = None
    version_id: int | None = None
    change_request_id: int | None = None
    issue_id: int | None = None
    work_order_id: int | None = None
    sensor_id: int | None = None


class Timeline(BaseModel):
    project_id: int
    since: datetime
    items: list[TimelineItem]
    truncated: bool


# ---------- Yordamchilar ----------


def _name(u: User | None) -> str:
    return (u.full_name or u.username) if u else ""


def _my_projects(db: Session, user: User) -> dict[int, tuple[Project, Role]]:
    """Foydalanuvchi a'zo loyihalar va roli (admin — hammasi, tasdiqlovchi sifatida)."""
    if user.is_admin:
        return {p.id: (p, Role.approver) for p in db.query(Project).all()}
    rows = db.query(ProjectMember).filter(ProjectMember.user_id == user.id).all()
    return {m.project_id: (m.project, m.role) for m in rows}


def _can_approve_command(db: Session, project_id: int, user: User, role: Role) -> bool:
    if _has_permission is not None:
        return _has_permission(db, project_id, user, "scada.command.approve")
    return has_role(role, Role.operator)


def _cr_out(cr: ChangeRequest, model: Model, project: Project) -> TaskCR:
    return TaskCR(
        id=cr.id,
        title=cr.title,
        status=cr.status.value,
        project_id=project.id,
        project_name=project.name,
        model_id=model.id,
        model_name=model.name,
        version_id=cr.version_id,
        version_number=cr.version.number if cr.version else 0,
        author=_name(cr.author),
        created_at=cr.created_at,
    )


# ---------- Mening vazifalarim ----------


@router.get("/me/tasks", response_model=MyTasks)
def my_tasks(user: CurrentUser, db: DB):
    projects = _my_projects(db, user)
    pids = list(projects)
    reviews: list[TaskCR] = []
    mine: list[TaskCR] = []
    issues: list[TaskIssue] = []
    wos: list[TaskWorkOrder] = []
    cmds: list[TaskCommand] = []
    if pids:
        models = {m.id: m for m in db.query(Model).filter(Model.project_id.in_(pids)).all()}
        if models:
            # Tasdiqlovchi: ochiq CR (muallif o'zi emas), men hali qaror (approve/request_changes) bermaganman
            decided = {
                r.change_request_id
                for r in db.query(Review).filter(
                    Review.reviewer_id == user.id, Review.decision.in_(("approve", "request_changes"))
                )
            }
            crs = (
                db.query(ChangeRequest)
                .filter(ChangeRequest.model_id.in_(list(models)))
                .filter(ChangeRequest.status.in_((CRStatus.open, CRStatus.changes_requested, CRStatus.approved)))
                .order_by(ChangeRequest.created_at.desc())
                .all()
            )
            for cr in crs:
                m = models[cr.model_id]
                p, role = projects[m.project_id]
                if cr.author_id == user.id:
                    if cr.status == CRStatus.changes_requested:
                        mine.append(_cr_out(cr, m, p))
                elif cr.status == CRStatus.open and has_role(role, Role.approver) and cr.id not in decided:
                    reviews.append(_cr_out(cr, m, p))
            for i in (
                db.query(Issue)
                .filter(Issue.model_id.in_(list(models)), Issue.assignee_id == user.id)
                .filter(Issue.status.in_((IssueStatus.open, IssueStatus.in_progress)))
                .order_by(Issue.updated_at.desc())
                .limit(200)
            ):
                m = models[i.model_id]
                p = projects[m.project_id][0]
                issues.append(
                    TaskIssue(
                        id=i.id,
                        title=i.title,
                        status=i.status.value,
                        priority=i.priority,
                        project_id=p.id,
                        project_name=p.name,
                        model_id=m.id,
                        model_name=m.name,
                        updated_at=i.updated_at,
                    )
                )
        for w in (
            db.query(WorkOrder)
            .filter(WorkOrder.project_id.in_(pids), WorkOrder.assignee_id == user.id)
            .filter(WorkOrder.status.in_((WorkOrderStatus.open, WorkOrderStatus.in_progress)))
            .order_by(WorkOrder.due_at.is_(None), WorkOrder.due_at, WorkOrder.created_at.desc())
            .limit(200)
        ):
            p = projects[w.project_id][0]
            wos.append(
                TaskWorkOrder(
                    id=w.id,
                    title=w.title,
                    status=w.status.value,
                    priority=w.priority,
                    project_id=p.id,
                    project_name=p.name,
                    due_at=w.due_at,
                    loto_active=bool(w.loto_active),
                )
            )
        for c in (
            db.query(Command)
            .filter(Command.project_id.in_(pids), Command.status == CommandStatus.pending_approval)
            .filter(Command.created_by != user.id)
            .order_by(Command.created_at)
        ):
            p, role = projects[c.project_id]
            if not _can_approve_command(db, c.project_id, user, role):
                continue
            cmds.append(
                TaskCommand(
                    id=c.id,
                    project_id=p.id,
                    project_name=p.name,
                    sensor_id=c.sensor_id,
                    sensor_name=c.sensor.name,
                    sensor_key=c.sensor.key,
                    unit=c.sensor.unit or "",
                    value=c.value,
                    author=_name(c.author),
                    created_at=c.created_at,
                )
            )
    return MyTasks(
        reviews=reviews,
        my_change_requests=mine,
        issues=issues,
        work_orders=wos,
        command_approvals=cmds,
        total=len(reviews) + len(mine) + len(issues) + len(wos) + len(cmds),
    )


# ---------- Loyiha vaqt chizig'i ----------


@router.get("/projects/{project_id}/history", response_model=Timeline)
def project_timeline(
    project_id: int,
    user: CurrentUser,
    db: DB,
    days: int = Query(90, ge=1, le=3650),
    limit: int = Query(300, ge=1, le=2000),
    alarms: Literal["all", "high", "none"] = "high",
):
    """Versiyalar, CR (ochildi / nashr / rad), muammolar, ish buyruqlari, alarmlar — bitta o'qda. `alarms=high` —
    faqat kritik va yuqori ustuvorlik (stale siz) (toshqin vaqt chizig'ini bosib ketmasin), `all` — hammasi."""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Loyiha topilmadi")
    if get_project_role(db, project_id, user) is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu loyihada ruxsat yo'q")
    since = utcnow() - timedelta(days=days)
    items: list[TimelineItem] = []
    models = {m.id: m for m in db.query(Model).filter(Model.project_id == project_id).all()}
    mids = list(models)
    if mids:
        for v in (
            db.query(Version)
            .filter(Version.model_id.in_(mids), Version.created_at >= since)
            .order_by(Version.created_at.desc())
            .limit(limit)
        ):
            m = models[v.model_id]
            items.append(
                TimelineItem(
                    ts=v.created_at,
                    kind="version",
                    title=f"{m.name}: v{v.number}",
                    detail=v.message or v.file_name,
                    actor=_name(v.author),
                    model_id=m.id,
                    version_id=v.id,
                )
            )
        for cr in (
            db.query(ChangeRequest)
            .filter(ChangeRequest.model_id.in_(mids))
            .filter((ChangeRequest.created_at >= since) | (ChangeRequest.closed_at >= since))
            .order_by(ChangeRequest.created_at.desc())
            .limit(limit)
        ):
            m = models[cr.model_id]
            vnum = cr.version.number if cr.version else 0
            if _aware(cr.created_at) >= since:
                items.append(
                    TimelineItem(
                        ts=cr.created_at,
                        kind="cr",
                        title=f"Tasdiqlash so'rovi #{cr.id}: {cr.title}",
                        detail=f"{m.name} v{vnum}",
                        actor=_name(cr.author),
                        model_id=m.id,
                        version_id=cr.version_id,
                        change_request_id=cr.id,
                    )
                )
            if cr.closed_at is not None and _aware(cr.closed_at) >= since and cr.status in (CRStatus.merged, CRStatus.rejected):
                items.append(
                    TimelineItem(
                        ts=cr.closed_at,
                        kind="publish" if cr.status == CRStatus.merged else "cr_rejected",
                        title=f"{m.name} v{vnum} nashr qilindi" if cr.status == CRStatus.merged else f"#{cr.id} rad etildi: {cr.title}",
                        detail=cr.title,
                        model_id=m.id,
                        version_id=cr.version_id,
                        change_request_id=cr.id,
                    )
                )
        for i in (
            db.query(Issue)
            .filter(Issue.model_id.in_(mids), Issue.created_at >= since)
            .order_by(Issue.created_at.desc())
            .limit(limit)
        ):
            items.append(
                TimelineItem(
                    ts=i.created_at,
                    kind="issue",
                    title=f"Muammo #{i.id}: {i.title}",
                    detail=models[i.model_id].name,
                    actor=_name(i.author),
                    severity=i.priority,
                    model_id=i.model_id,
                    version_id=i.version_id,
                    issue_id=i.id,
                )
            )
    for w in (
        db.query(WorkOrder)
        .filter(WorkOrder.project_id == project_id, WorkOrder.created_at >= since)
        .order_by(WorkOrder.created_at.desc())
        .limit(limit)
    ):
        items.append(
            TimelineItem(
                ts=w.created_at,
                kind="work_order",
                title=f"Ish buyrug'i #{w.id}: {w.title}",
                detail=w.status.value,
                actor=_name(w.author),
                severity=w.priority,
                work_order_id=w.id,
            )
        )
    if alarms != "none":
        q = (
            db.query(AlarmEvent, Sensor)
            .join(Sensor, Sensor.id == AlarmEvent.sensor_id)
            .filter(AlarmEvent.project_id == project_id, AlarmEvent.started_at >= since)
            .filter(AlarmEvent.suppressed.is_(None))
        )
        if alarms == "high":  # muhim: kritik/yuqori, aloqa yo'qligi (stale) emas — vaqt chizig'ini bosib ketmasin
            q = q.filter(Sensor.priority.in_(("critical", "high")), AlarmEvent.state != AlarmState.stale)
        for e, s in q.order_by(AlarmEvent.started_at.desc()).limit(limit):
            items.append(
                TimelineItem(
                    ts=e.started_at,
                    kind="alarm",
                    title=f"{s.name}: {e.state.value}",
                    detail=f"{e.value:g} {s.unit}".strip() if e.value is not None else "",
                    severity=s.priority,
                    sensor_id=s.id,
                )
            )
    items.sort(key=lambda x: _aware(x.ts), reverse=True)
    return Timeline(project_id=project_id, since=since, items=items[:limit], truncated=len(items) > limit)


def _aware(ts: datetime) -> datetime:
    """SQLite naive datetime qaytaradi — solishtirish/saralashda aware bilan aralashmasin (UTC)."""
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
