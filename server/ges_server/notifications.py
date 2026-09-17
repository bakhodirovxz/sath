"""Ilova ichidagi bildirishnomalar (qo'ng'iroq belgisi): yozish yordamchilari + API.

Email (notify.py) ixtiyoriy; bu jadval har doim ishlaydi — web/desktop /api/notifications dan o'qiydi.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from .auth.deps import DB, CurrentUser
from .orm import Notification, ProjectMember, Role, User, utcnow

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def member_ids(
    db: Session,
    project_id: int,
    role: Role | None = None,
    exclude: int | None = None,
    with_admins: bool = False,
) -> list[int]:
    """Loyiha a'zolari (ixtiyoriy: faqat shu rol); with_admins — tizim adminlari ham."""
    q = db.query(ProjectMember).filter_by(project_id=project_id)
    if role is not None:
        q = q.filter_by(role=role)
    ids = {m.user_id for m in q.all() if m.user.is_active and m.user_id != exclude}
    if with_admins:
        ids |= {
            u.id
            for u in db.query(User).filter_by(is_admin=True, is_active=True).all()
            if u.id != exclude
        }
    return sorted(ids)


def push(
    db: Session, user_ids: list[int], kind: str, title: str, body: str = "", link: str = ""
) -> None:
    """Bildirishnoma qo'shadi (commit chaqiruvchi zimmasida)."""
    for uid in dict.fromkeys(user_ids):
        db.add(Notification(user_id=uid, kind=kind, title=title[:200], body=body, link=link[:200]))


class NotificationOut(BaseModel):
    id: int
    kind: str
    title: str
    body: str
    link: str
    created_at: datetime
    read_at: datetime | None

    model_config = {"from_attributes": True}

    @field_validator("created_at", "read_at")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        # SQLite naive qaytaradi — UTC deb belgilaymiz (brauzer to'g'ri mahalliy vaqtga o'giradi)
        return v.replace(tzinfo=timezone.utc) if v and v.tzinfo is None else v


class ReadIn(BaseModel):
    ids: list[int] | None = None  # None — hammasi


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    user: CurrentUser, db: DB, unread: bool = False, limit: int = Query(50, gt=0, le=500)
):
    q = db.query(Notification).filter_by(user_id=user.id)
    if unread:
        q = q.filter(Notification.read_at.is_(None))
    return q.order_by(Notification.id.desc()).limit(limit).all()


@router.get("/count")
def unread_count(user: CurrentUser, db: DB):
    n = db.query(Notification).filter_by(user_id=user.id, read_at=None).count()
    return {"unread": n}


@router.post("/read")
def mark_read(body: ReadIn, user: CurrentUser, db: DB):
    q = db.query(Notification).filter_by(user_id=user.id, read_at=None)
    if body.ids is not None:
        q = q.filter(Notification.id.in_(body.ids))
    n = 0
    for item in q.all():
        item.read_at = utcnow()
        n += 1
    db.commit()
    return {"read": n}
