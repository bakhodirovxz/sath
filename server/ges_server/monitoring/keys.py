"""Loyiha gateway kalitlari (B3): ingest (faqat o'lchov) va command (buyruq kanali) — alohida.

Kalit sizib chiqsa zarar chegaralanadi: ingest kaliti buyruqlarni o'qiy/soxta ack qila olmaydi.
Har kalitda muddat (`*_expires_at`, default 365 kun) va oxirgi ishlatilgan vaqt; muddati yaqinlashsa
adminlar/tasdiqlovchilarga bildirishnoma (background.tick_keys).
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .. import audit, notifications
from ..orm import Project, Role, utcnow

KeyKind = Literal["ingest", "command"]
DEFAULT_TTL_DAYS = 365
LAST_USED_WRITE_INTERVAL_S = 60  # har so'rovda yozmaslik uchun
EXPIRY_WARN_DAYS = (14, 7, 3, 1)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def get(project: Project, kind: KeyKind) -> str | None:
    return project.ingest_key if kind == "ingest" else project.command_key


def expires_at(project: Project, kind: KeyKind) -> datetime | None:
    return _aware(project.ingest_key_expires_at if kind == "ingest" else project.command_key_expires_at)


def last_used_at(project: Project, kind: KeyKind) -> datetime | None:
    return _aware(
        project.ingest_key_last_used_at if kind == "ingest" else project.command_key_last_used_at
    )


def ensure(
    db: Session, project: Project, kind: KeyKind, user_id: int | None, ttl_days: int | None = None
) -> str:
    """Kalit bo'lmasa yaratadi (audit bilan). Commit chaqiruvchi zimmasida."""
    if get(project, kind):
        return get(project, kind)
    return rotate(db, project, kind, user_id, ttl_days, action_suffix="create")


def rotate(
    db: Session,
    project: Project,
    kind: KeyKind,
    user_id: int | None,
    ttl_days: int | None = None,
    action_suffix: str = "rotate",
) -> str:
    """Yangi kalit; ttl_days=0 — muddatsiz, None — DEFAULT_TTL_DAYS. Commit chaqiruvchi zimmasida."""
    key = secrets.token_urlsafe(24)
    days = DEFAULT_TTL_DAYS if ttl_days is None else ttl_days
    exp = utcnow() + timedelta(days=days) if days > 0 else None
    if kind == "ingest":
        project.ingest_key, project.ingest_key_expires_at = key, exp
        project.ingest_key_last_used_at = None
    else:
        project.command_key, project.command_key_expires_at = key, exp
        project.command_key_last_used_at = None
    audit.log(
        db,
        user_id=user_id,
        action=f"project.{kind}_key.{action_suffix}",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
        detail={"expires_at": exp.isoformat() if exp else None},
    )
    return key


def verify(db: Session, project: Project, kind: KeyKind, presented: str | None) -> None:
    """Sarlavhadagi kalitni tekshiradi: yo'q/noto'g'ri → 401, boshqa turdagi kalit → 403,
    muddati o'tgan → 401. `*_last_used_at` ni (60 s dan oshsa) yangilaydi — commit chaqiruvchida."""
    if not presented:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"{kind} kaliti kerak")
    expected = get(project, kind)
    if expected and secrets.compare_digest(presented, expected):
        exp = expires_at(project, kind)
        if exp is not None and exp <= utcnow():
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, f"{kind} kalitining muddati o'tgan — almashtiring"
            )
        last = last_used_at(project, kind)
        now = utcnow()
        if last is None or (now - last).total_seconds() > LAST_USED_WRITE_INTERVAL_S:
            if kind == "ingest":
                project.ingest_key_last_used_at = now
            else:
                project.command_key_last_used_at = now
        return
    other = get(project, "command" if kind == "ingest" else "ingest")
    if other and secrets.compare_digest(presented, other):
        # to'g'ri loyiha, noto'g'ri kanal: ingest kaliti buyruq kanaliga kira olmaydi (va aksincha)
        audit.log_now(
            user_id=None,
            action="gateway.key_misuse",
            target_type="project",
            target_id=project.id,
            project_id=project.id,
            detail={"presented": "command" if kind == "ingest" else "ingest", "wanted": kind},
        )
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"bu kalit {('buyruq' if kind == 'ingest' else 'ingest')} kanali uchun — {kind} kaliti kerak",
        )
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"{kind} kaliti noto'g'ri")


def info(project: Project, kind: KeyKind) -> dict:
    exp = expires_at(project, kind)
    return {
        "kind": kind,
        "key": get(project, kind),
        "expires_at": exp.isoformat() if exp else None,
        "days_left": (exp - utcnow()).days if exp else None,
        "last_used_at": (last_used_at(project, kind) or None) and last_used_at(project, kind).isoformat(),
    }


def warn_expiring(db: Session) -> int:
    """Muddati EXPIRY_WARN_DAYS ichida bo'lgan kalitlar — loyiha tasdiqlovchilari + adminlarga
    bildirishnoma (kuniga bir marta chaqiriladi). Qaytaradi: yuborilgan bildirishnomalar soni."""
    n = 0
    now = utcnow()
    for p in db.query(Project).all():
        for kind in ("ingest", "command"):
            exp = expires_at(p, kind)
            if exp is None or not get(p, kind):
                continue
            days = (exp - now).days
            if days in EXPIRY_WARN_DAYS or exp <= now:
                ids = notifications.member_ids(db, p.id, Role.approver, with_admins=True)
                title = (
                    f"{p.name}: {kind} kaliti muddati o'tdi"
                    if exp <= now
                    else f"{p.name}: {kind} kalitining muddati {days} kunda tugaydi"
                )
                notifications.push(
                    db, ids, "system", title, "Monitoring → Ulanish kalitlari → almashtirish",
                    f"/projects/{p.id}/models",
                )
                n += len(ids)
    if n:
        db.commit()
    return n
