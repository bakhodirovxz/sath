"""Taqriz va tasdiqlash: change request (PR analogi), diff, BCF uslubidagi issue lar.

Holatlar:
  version: wip → shared (CR ochilganda) → published (merge) → archived (yangi published kelganda)
  CR:      open → changes_requested → open (yangi versiya) → approved → merged
                                                   └→ rejected
"""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import audit, notifications, notify
from ..auth.deps import DB, CurrentUser, get_project_role, has_role
from ..config import get_settings
from ..models import storage
from ..models.router import VersionOut, get_model_checked, get_version_checked, version_out
from ..orm import (
    ChangeRequest,
    CRStatus,
    Issue,
    IssueComment,
    IssueStatus,
    ProjectMember,
    Review,
    Role,
    SavedView,
    User,
    Version,
    VersionDiff,
    VersionState,
    utcnow,
)
from . import bcf
from . import diff as ifc_diff

router = APIRouter(prefix="/api", tags=["review"])


# ---------- Sxemalar ----------


class CRCreate(BaseModel):
    version_id: int
    title: str = Field(min_length=1, max_length=256)
    description: str = ""


class ReviewIn(BaseModel):
    decision: Literal["approve", "request_changes", "comment"]
    comment: str = ""


class ReviewOut(BaseModel):
    id: int
    reviewer_id: int
    reviewer_username: str
    decision: str
    comment: str
    created_at: datetime


class CROut(BaseModel):
    id: int
    model_id: int
    version_id: int
    version_number: int
    author_id: int
    author_username: str
    title: str
    description: str
    status: CRStatus
    created_at: datetime
    closed_at: datetime | None
    reviews: list[ReviewOut] = []


class CRSetVersion(BaseModel):
    version_id: int


class IssueCreate(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    description: str = ""
    version_id: int | None = None
    change_request_id: int | None = None
    assignee_id: int | None = None
    priority: Literal["low", "normal", "high", "critical"] = "normal"
    viewpoint: dict = Field(default_factory=dict)


class IssueUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: IssueStatus | None = None
    assignee_id: int | None = None
    priority: Literal["low", "normal", "high", "critical"] | None = None
    viewpoint: dict | None = None


class CommentIn(BaseModel):
    body: str = Field(min_length=1)
    viewpoint: dict | None = None


class CommentOut(BaseModel):
    id: int
    author_id: int
    author_username: str
    body: str
    viewpoint: dict | None
    created_at: datetime


class IssueOut(BaseModel):
    id: int
    model_id: int
    version_id: int | None
    change_request_id: int | None
    author_id: int
    author_username: str
    assignee_id: int | None
    assignee_username: str | None
    title: str
    description: str
    status: IssueStatus
    priority: str
    viewpoint: dict
    created_at: datetime
    updated_at: datetime
    comment_count: int = 0
    comments: list[CommentOut] = []


def _cr_out(cr: ChangeRequest) -> CROut:
    return CROut(
        id=cr.id,
        model_id=cr.model_id,
        version_id=cr.version_id,
        version_number=cr.version.number,
        author_id=cr.author_id,
        author_username=cr.author.username,
        title=cr.title,
        description=cr.description,
        status=cr.status,
        created_at=cr.created_at,
        closed_at=cr.closed_at,
        reviews=[
            ReviewOut(
                id=r.id,
                reviewer_id=r.reviewer_id,
                reviewer_username=r.reviewer.username,
                decision=r.decision,
                comment=r.comment,
                created_at=r.created_at,
            )
            for r in cr.reviews
        ],
    )


def _issue_out(i: Issue, with_comments: bool = False) -> IssueOut:
    return IssueOut(
        id=i.id,
        model_id=i.model_id,
        version_id=i.version_id,
        change_request_id=i.change_request_id,
        author_id=i.author_id,
        author_username=i.author.username,
        assignee_id=i.assignee_id,
        assignee_username=i.assignee.username if i.assignee else None,
        title=i.title,
        description=i.description,
        status=i.status,
        priority=i.priority,
        viewpoint=i.viewpoint,
        created_at=i.created_at,
        updated_at=i.updated_at,
        comment_count=len(i.comments),
        comments=[
            CommentOut(
                id=c.id,
                author_id=c.author_id,
                author_username=c.author.username,
                body=c.body,
                viewpoint=c.viewpoint,
                created_at=c.created_at,
            )
            for c in i.comments
        ]
        if with_comments
        else [],
    )


def _path(model_id: int, version_id: int | None = None) -> str:
    return f"/models/{model_id}" + (f"?v={version_id}" if version_id else "")


def _link(model_id: int, version_id: int | None = None) -> str:
    return get_settings().public_url.rstrip("/") + _path(model_id, version_id)


def _emails(db, project_id: int, role: Role | None = None, exclude: int | None = None) -> list[str]:
    q = db.query(ProjectMember).filter_by(project_id=project_id)
    if role is not None:
        q = q.filter_by(role=role)
    out = [
        m.user.email for m in q.all() if m.user.email and m.user.is_active and m.user_id != exclude
    ]
    admins = [
        u.email
        for u in db.query(User).filter_by(is_admin=True, is_active=True).all()
        if u.email and u.id != exclude
    ]
    return sorted(set(out + (admins if role == Role.approver else [])))


def _get_cr(db, cr_id: int, user: User, required: Role) -> ChangeRequest:
    cr = db.get(ChangeRequest, cr_id)
    if cr is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Change request topilmadi")
    get_model_checked(db, cr.model_id, user, required)
    return cr


def _require_approver_or_author(db, cr: ChangeRequest, user: User) -> None:
    role = get_project_role(db, cr.version.model.project_id, user)
    if cr.author_id != user.id and not has_role(role, Role.approver):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Faqat muallif yoki tasdiqlovchi")


# ---------- Diff ----------


@router.get("/versions/{version_id}/diff")
def version_diff(version_id: int, user: CurrentUser, db: DB, from_version_id: int | None = None):
    """Versiyani boshqa versiya (default: ota) bilan solishtirish. Natija keshlanadi."""
    new = get_version_checked(db, version_id, user, Role.viewer)
    if from_version_id is None:
        if new.parent_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu versiyaning ota versiyasi yo'q")
        from_version_id = new.parent_id
    old = get_version_checked(db, from_version_id, user, Role.viewer)
    if old.model_id != new.model_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Versiyalar bir modelga tegishli emas")

    cached = (
        db.query(VersionDiff).filter_by(from_version_id=old.id, to_version_id=new.id).one_or_none()
    )
    if cached is None:
        result = ifc_diff.compute(
            storage.resolve(old.file_sha256), storage.resolve(new.file_sha256)
        )
        cached = VersionDiff(from_version_id=old.id, to_version_id=new.id, result=result)
        db.add(cached)
        db.commit()
    return {"from_version_id": old.id, "to_version_id": new.id, **cached.result}


# ---------- Change requests ----------


@router.get("/models/{model_id}/change-requests", response_model=list[CROut])
def list_crs(model_id: int, user: CurrentUser, db: DB, status_filter: CRStatus | None = None):
    get_model_checked(db, model_id, user, Role.viewer)
    q = db.query(ChangeRequest).filter_by(model_id=model_id)
    if status_filter is not None:
        q = q.filter_by(status=status_filter)
    return [_cr_out(cr) for cr in q.order_by(ChangeRequest.id.desc()).all()]


@router.post("/models/{model_id}/change-requests", response_model=CROut, status_code=201)
def create_cr(model_id: int, body: CRCreate, user: CurrentUser, db: DB):
    model = get_model_checked(db, model_id, user, Role.engineer)
    version = db.get(Version, body.version_id)
    if version is None or version.model_id != model.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Versiya shu modelga tegishli emas")
    if version.state != VersionState.wip:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Versiya holati '{version.state.value}', faqat wip yuboriladi",
        )
    version.state = VersionState.shared
    cr = ChangeRequest(
        model_id=model.id,
        version_id=version.id,
        author_id=user.id,
        title=body.title,
        description=body.description,
    )
    db.add(cr)
    db.flush()
    audit.log(
        db,
        user_id=user.id,
        action="cr.create",
        target_type="change_request",
        target_id=cr.id,
        project_id=model.project_id,
        detail={"version_id": version.id},
    )
    notifications.push(
        db,
        notifications.member_ids(db, model.project_id, Role.approver, user.id, with_admins=True),
        "review",
        f"Tasdiqlash so'rovi #{cr.id}: {cr.title}",
        f"{user.username} «{model.name}» v{version.number} ni tasdiqqa yubordi",
        _path(model.id, version.id),
    )
    db.commit()
    notify.send_async(
        _emails(db, model.project_id, Role.approver, exclude=user.id),
        f"Tasdiqlash so'rovi #{cr.id}: {cr.title}",
        f"{user.username} «{model.name}» v{version.number} ni tasdiqqa yubordi.\n{body.description}\n\n{_link(model.id, version.id)}",
    )
    return _cr_out(cr)


@router.get("/change-requests/{cr_id}", response_model=CROut)
def get_cr(cr_id: int, user: CurrentUser, db: DB):
    return _cr_out(_get_cr(db, cr_id, user, Role.viewer))


@router.post("/change-requests/{cr_id}/reviews", response_model=CROut, status_code=201)
def review_cr(cr_id: int, body: ReviewIn, user: CurrentUser, db: DB):
    cr = _get_cr(db, cr_id, user, Role.viewer)
    project_id = cr.version.model.project_id
    if cr.status not in (CRStatus.open, CRStatus.changes_requested):
        raise HTTPException(status.HTTP_409_CONFLICT, "CR yopilgan")
    if body.decision != "comment":
        if not has_role(get_project_role(db, project_id, user), Role.approver):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Faqat tasdiqlovchi qaror bera oladi")
        if cr.author_id == user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "O'z CR ingizni tasdiqlay olmaysiz")
    db.add(
        Review(
            change_request_id=cr.id,
            reviewer_id=user.id,
            decision=body.decision,
            comment=body.comment,
        )
    )
    if body.decision == "approve":
        cr.status = CRStatus.approved
    elif body.decision == "request_changes":
        cr.status = CRStatus.changes_requested
    audit.log(
        db,
        user_id=user.id,
        action=f"cr.{body.decision}",
        target_type="change_request",
        target_id=cr.id,
        project_id=project_id,
    )
    labels = {
        "approve": "ma'qulladi",
        "request_changes": "o'zgartirish so'radi",
        "comment": "izoh qoldirdi",
    }
    if cr.author_id != user.id:
        notifications.push(
            db,
            [cr.author_id],
            "review",
            f"#{cr.id} {cr.title}: {user.username} {labels[body.decision]}",
            body.comment or "",
            _path(cr.model_id, cr.version_id),
        )
    db.commit()
    db.refresh(cr)
    if cr.author.email and cr.author_id != user.id:
        notify.send_async(
            [cr.author.email],
            f"#{cr.id} {cr.title}: {user.username} {labels[body.decision]}",
            f"{body.comment}\n\n{_link(cr.model_id, cr.version_id)}",
        )
    return _cr_out(cr)


@router.post("/change-requests/{cr_id}/version", response_model=CROut)
def set_cr_version(cr_id: int, body: CRSetVersion, user: CurrentUser, db: DB):
    """O'zgartirish so'ralganda muallif yangi versiyani CR ga bog'laydi → qayta open."""
    cr = _get_cr(db, cr_id, user, Role.engineer)
    if cr.author_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Faqat CR muallifi")
    if cr.status not in (CRStatus.open, CRStatus.changes_requested):
        raise HTTPException(status.HTTP_409_CONFLICT, "CR yopilgan")
    new_version = db.get(Version, body.version_id)
    if new_version is None or new_version.model_id != cr.model_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Versiya shu modelga tegishli emas")
    if new_version.state != VersionState.wip:
        raise HTTPException(status.HTTP_409_CONFLICT, "Yangi versiya wip holatida bo'lishi kerak")
    cr.version.state = VersionState.wip
    new_version.state = VersionState.shared
    cr.version_id = new_version.id
    cr.status = CRStatus.open
    audit.log(
        db,
        user_id=user.id,
        action="cr.set_version",
        target_type="change_request",
        target_id=cr.id,
        project_id=cr.version.model.project_id,
        detail={"version_id": new_version.id},
    )
    db.commit()
    db.refresh(cr)
    return _cr_out(cr)


@router.post("/change-requests/{cr_id}/merge", response_model=CROut)
def merge_cr(cr_id: int, user: CurrentUser, db: DB):
    """Tasdiqlangan CR ni published qilish; avvalgi published → archived."""
    cr = _get_cr(db, cr_id, user, Role.approver)
    if cr.status != CRStatus.approved:
        raise HTTPException(status.HTTP_409_CONFLICT, "Avval tasdiqlanishi kerak")
    for v in cr.version.model.versions:
        if v.state == VersionState.published:
            v.state = VersionState.archived
    cr.version.state = VersionState.published
    cr.status = CRStatus.merged
    cr.closed_at = utcnow()
    audit.log(
        db,
        user_id=user.id,
        action="cr.merge",
        target_type="change_request",
        target_id=cr.id,
        project_id=cr.version.model.project_id,
        detail={"version_id": cr.version_id},
    )
    notifications.push(
        db,
        notifications.member_ids(db, cr.version.model.project_id, exclude=user.id),
        "review",
        f"Tasdiqlandi: «{cr.version.model.name}» v{cr.version.number}",
        f"{user.username} #{cr.id} «{cr.title}» ni tasdiqladi — joriy versiya",
        _path(cr.model_id, cr.version_id),
    )
    db.commit()
    db.refresh(cr)
    notify.send_async(
        _emails(db, cr.version.model.project_id, exclude=user.id),
        f"Tasdiqlandi: «{cr.version.model.name}» v{cr.version.number}",
        f"{user.username} #{cr.id} «{cr.title}» ni tasdiqladi — endi bu joriy (published) versiya.\n\n{_link(cr.model_id, cr.version_id)}",
    )
    return _cr_out(cr)


@router.post("/change-requests/{cr_id}/reject", response_model=CROut)
def reject_cr(cr_id: int, user: CurrentUser, db: DB):
    """Rad etish/yopish — muallif yoki tasdiqlovchi. Versiya wip ga qaytadi."""
    cr = _get_cr(db, cr_id, user, Role.viewer)
    _require_approver_or_author(db, cr, user)
    if cr.status in (CRStatus.merged, CRStatus.rejected):
        raise HTTPException(status.HTTP_409_CONFLICT, "CR allaqachon yopilgan")
    cr.version.state = VersionState.wip
    cr.status = CRStatus.rejected
    cr.closed_at = utcnow()
    audit.log(
        db,
        user_id=user.id,
        action="cr.reject",
        target_type="change_request",
        target_id=cr.id,
        project_id=cr.version.model.project_id,
    )
    if cr.author_id != user.id:
        notifications.push(
            db,
            [cr.author_id],
            "review",
            f"Rad etildi: #{cr.id} {cr.title}",
            f"{user.username} so'rovni yopdi",
            _path(cr.model_id, cr.version_id),
        )
    db.commit()
    db.refresh(cr)
    return _cr_out(cr)


@router.get("/models/{model_id}/published", response_model=VersionOut)
def published_version(model_id: int, user: CurrentUser, db: DB):
    model = get_model_checked(db, model_id, user, Role.viewer)
    v = next((v for v in model.versions if v.state == VersionState.published), None)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tasdiqlangan versiya yo'q")
    return version_out(v)


# ---------- Issues (BCF) ----------


@router.get("/models/{model_id}/issues", response_model=list[IssueOut])
def list_issues(
    model_id: int,
    user: CurrentUser,
    db: DB,
    status_filter: IssueStatus | None = None,
    change_request_id: int | None = None,
):
    get_model_checked(db, model_id, user, Role.viewer)
    q = db.query(Issue).filter_by(model_id=model_id)
    if status_filter is not None:
        q = q.filter_by(status=status_filter)
    if change_request_id is not None:
        q = q.filter_by(change_request_id=change_request_id)
    return [_issue_out(i) for i in q.order_by(Issue.id.desc()).all()]


@router.post("/models/{model_id}/issues", response_model=IssueOut, status_code=201)
def create_issue(model_id: int, body: IssueCreate, user: CurrentUser, db: DB):
    model = get_model_checked(db, model_id, user, Role.viewer)
    if body.version_id is not None:
        v = db.get(Version, body.version_id)
        if v is None or v.model_id != model.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Versiya shu modelga tegishli emas")
    if body.change_request_id is not None:
        cr = db.get(ChangeRequest, body.change_request_id)
        if cr is None or cr.model_id != model.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "CR shu modelga tegishli emas")
    if body.assignee_id is not None and db.get(User, body.assignee_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ijrochi topilmadi")
    issue = Issue(
        model_id=model.id, author_id=user.id, bcf_guid=str(uuid.uuid4()), **body.model_dump()
    )
    db.add(issue)
    db.flush()
    audit.log(
        db,
        user_id=user.id,
        action="issue.create",
        target_type="issue",
        target_id=issue.id,
        project_id=model.project_id,
        detail={"title": issue.title},
    )
    if issue.assignee_id and issue.assignee_id != user.id:
        notifications.push(
            db,
            [issue.assignee_id],
            "issue",
            f"Sizga issue tayinlandi: {issue.title}",
            f"{user.username}, «{model.name}»",
            _path(model.id, issue.version_id),
        )
    db.commit()
    db.refresh(issue)
    return _issue_out(issue, with_comments=True)


@router.get("/models/{model_id}/issues/bcf")
def export_bcf(model_id: int, user: CurrentUser, db: DB, status_filter: IssueStatus | None = None):
    """Model issue larini BCF 2.1 zip qilib beradi (BIMcollab, Revit, ArchiCAD, Solibri o'qiydi)."""
    model = get_model_checked(db, model_id, user, Role.viewer)
    q = db.query(Issue).filter_by(model_id=model.id)
    if status_filter is not None:
        q = q.filter_by(status=status_filter)
    data = bcf.export_zip(q.order_by(Issue.id).all(), model.project.name)
    return Response(
        data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{model.name}_issues.bcfzip"'},
    )


@router.post("/models/{model_id}/issues/bcf")
async def import_bcf(model_id: int, file: UploadFile, user: CurrentUser, db: DB):
    """BCF zip dan issue larni yuklash; bcf_guid bo'yicha mavjudlari yangilanadi."""
    model = get_model_checked(db, model_id, user, Role.engineer)
    data = await file.read()
    try:
        topics = bcf.import_zip(data)
    except Exception as e:  # noqa: BLE001 — yaroqsiz zip/xml
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"BCF o'qilmadi: {e}") from e
    if not topics:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "BCF ichida topic topilmadi")
    result = bcf.apply_import(db, model, topics, user)
    audit.log(
        db,
        user_id=user.id,
        action="issue.bcf_import",
        target_type="model",
        target_id=model.id,
        project_id=model.project_id,
        detail=result,
    )
    db.commit()
    return result


def _get_issue(db, issue_id: int, user: User) -> Issue:
    issue = db.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Issue topilmadi")
    get_model_checked(db, issue.model_id, user, Role.viewer)
    return issue


@router.get("/issues/{issue_id}", response_model=IssueOut)
def get_issue(issue_id: int, user: CurrentUser, db: DB):
    return _issue_out(_get_issue(db, issue_id, user), with_comments=True)


@router.patch("/issues/{issue_id}", response_model=IssueOut)
def update_issue(issue_id: int, body: IssueUpdate, user: CurrentUser, db: DB):
    """Muallif, ijrochi yoki tasdiqlovchi o'zgartira oladi."""
    issue = _get_issue(db, issue_id, user)
    project_id = get_model_checked(db, issue.model_id, user, Role.viewer).project_id
    allowed = (
        issue.author_id == user.id
        or issue.assignee_id == user.id
        or has_role(get_project_role(db, project_id, user), Role.approver)
    )
    if not allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ruxsat yo'q")
    changes = body.model_dump(exclude_none=True)
    if "assignee_id" in changes and db.get(User, changes["assignee_id"]) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ijrochi topilmadi")
    for k, v in changes.items():
        setattr(issue, k, v)
    audit.log(
        db,
        user_id=user.id,
        action="issue.update",
        target_type="issue",
        target_id=issue.id,
        project_id=project_id,
        detail={
            k: (v.value if hasattr(v, "value") else v)
            for k, v in changes.items()
            if k != "viewpoint"
        },
    )
    if changes.get("assignee_id") and changes["assignee_id"] != user.id:
        notifications.push(
            db,
            [changes["assignee_id"]],
            "issue",
            f"Sizga issue tayinlandi: {issue.title}",
            f"{user.username}",
            _path(issue.model_id, issue.version_id),
        )
    elif "status" in changes and issue.author_id != user.id:
        notifications.push(
            db,
            [issue.author_id],
            "issue",
            f"Issue «{issue.title}»: {changes['status'].value}",
            f"{user.username} holatni o'zgartirdi",
            _path(issue.model_id, issue.version_id),
        )
    db.commit()
    db.refresh(issue)
    return _issue_out(issue, with_comments=True)


@router.post("/issues/{issue_id}/comments", response_model=IssueOut, status_code=201)
def comment_issue(issue_id: int, body: CommentIn, user: CurrentUser, db: DB):
    issue = _get_issue(db, issue_id, user)
    db.add(
        IssueComment(issue_id=issue.id, author_id=user.id, body=body.body, viewpoint=body.viewpoint)
    )
    issue.updated_at = utcnow()
    db.commit()
    db.refresh(issue)
    return _issue_out(issue, with_comments=True)


# ---------- Saqlangan ko'rinishlar ----------


class ViewIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    viewpoint: dict


class ViewOut(BaseModel):
    id: int
    name: str
    author_username: str
    viewpoint: dict
    created_at: datetime


@router.get("/models/{model_id}/views", response_model=list[ViewOut])
def list_views(model_id: int, user: CurrentUser, db: DB):
    get_model_checked(db, model_id, user, Role.viewer)
    return [
        ViewOut(
            id=v.id,
            name=v.name,
            author_username=v.author.username,
            viewpoint=v.viewpoint,
            created_at=v.created_at,
        )
        for v in db.query(SavedView).filter_by(model_id=model_id).order_by(SavedView.name).all()
    ]


@router.put("/models/{model_id}/views", response_model=ViewOut)
def save_view(model_id: int, body: ViewIn, user: CurrentUser, db: DB):
    """Nomi bo'yicha yaratadi yoki yangilaydi (ko'ruvchi ham saqlay oladi)."""
    model = get_model_checked(db, model_id, user, Role.viewer)
    v = db.query(SavedView).filter_by(model_id=model_id, name=body.name).one_or_none()
    if v is None:
        v = SavedView(model_id=model_id, author_id=user.id, name=body.name)
        db.add(v)
    elif v.author_id != user.id and not has_role(
        get_project_role(db, model.project_id, user), Role.approver
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Bu nomdagi ko'rinish boshqa foydalanuvchiniki"
        )
    v.viewpoint = body.viewpoint
    db.commit()
    db.refresh(v)
    return ViewOut(
        id=v.id,
        name=v.name,
        author_username=v.author.username,
        viewpoint=v.viewpoint,
        created_at=v.created_at,
    )


@router.delete("/views/{view_id}", status_code=204)
def delete_view(view_id: int, user: CurrentUser, db: DB):
    v = db.get(SavedView, view_id)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ko'rinish topilmadi")
    model = get_model_checked(db, v.model_id, user, Role.viewer)
    if v.author_id != user.id and not has_role(
        get_project_role(db, model.project_id, user), Role.approver
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Faqat muallif yoki tasdiqlovchi")
    db.delete(v)
    db.commit()
