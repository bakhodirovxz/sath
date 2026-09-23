"""Audit jurnalini ko'rish: admin — hammasi; tasdiqlovchi — o'z loyihasi."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel

from .. import audit
from ..auth.deps import DB, AdminUser, CurrentUser, get_project_role, has_role
from ..config import get_settings
from ..downloads import content_disposition
from ..orm import AuditLog, Role, User

router = APIRouter(prefix="/api/audit", tags=["system"])


@router.get("/verify")
def verify(_: AdminUser, db: DB):
    """Hash zanjirini boshidan tekshiradi: {ok, checked, first_bad_id, head, schemes, keyed, write_failures}
    — v1 (sha256, eski) va v2 (HMAC, audit kaliti) qatorlar birga tekshiriladi."""
    return audit.verify_chain(db)


@router.get("/status")
def status_(_: AdminUser):
    """AUTH-05: audit yozish xatolari metrikasi (jarayon bo'yicha) — monitoring/alarm uchun."""
    return {**audit.STATS, "hash_alg": audit.HASH_ALG}


@router.get("/export")
def export_day(_: AdminUser, db: DB, day: str = Query(..., description="YYYY-MM-DD (UTC)")):
    """Bir kunlik yozuvlar JSONL + HMAC-SHA256 imzosi (X-Audit-Signature sarlavhasi, server kaliti
    bilan). Saqlab qo'yilgan fayl keyin `hmac(secret, body)` bilan tekshiriladi."""
    try:
        d = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "day: YYYY-MM-DD") from e
    body, sig = audit.export_day(db, d, get_settings().ensure_secret_key())
    audit.log(
        db, user_id=_.id, action="export.audit", target_type="audit", detail={"day": day}
    )
    db.commit()
    return Response(
        body,
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": content_disposition(f"audit-{day}.jsonl"),
            "X-Audit-Signature": sig,
        },
    )


class AuditOut(BaseModel):
    id: int
    user_id: int | None
    username: str | None
    action: str
    target_type: str
    target_id: int | None
    project_id: int | None
    detail: dict
    created_at: datetime


@router.get("", response_model=list[AuditOut])
def list_audit(
    user: CurrentUser,
    db: DB,
    project_id: int | None = None,
    action: str | None = Query(None, description="prefiks: cr., issue., alarm., version. ..."),
    user_id: int | None = None,
    limit: int = Query(200, gt=0, le=2000),
    before_id: int | None = None,
):
    if not user.is_admin:
        if project_id is None or not has_role(
            get_project_role(db, project_id, user), Role.approver
        ):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Faqat admin yoki loyiha tasdiqlovchisi (project_id bilan)",
            )
    q = db.query(AuditLog)
    if project_id is not None:
        q = q.filter(AuditLog.project_id == project_id)
    if action:
        q = q.filter(AuditLog.action.like(action + "%"))
    if user_id is not None:
        q = q.filter(AuditLog.user_id == user_id)
    if before_id is not None:
        q = q.filter(AuditLog.id < before_id)
    rows = q.order_by(AuditLog.id.desc()).limit(limit).all()
    ids = {r.user_id for r in rows if r.user_id}
    names = {u.id: u.username for u in db.query(User).filter(User.id.in_(ids)).all()} if ids else {}
    return [
        AuditOut(
            id=r.id,
            user_id=r.user_id,
            username=names.get(r.user_id),
            action=r.action,
            target_type=r.target_type,
            target_id=r.target_id,
            project_id=r.project_id,
            detail=r.detail or {},
            created_at=r.created_at.replace(tzinfo=timezone.utc)
            if r.created_at.tzinfo is None
            else r.created_at,
        )
        for r in rows
    ]
