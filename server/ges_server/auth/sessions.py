"""Sessiyalar (L2): refresh token aylanishi, bekor qilish, foydalanuvchi bo'yicha ro'yxat.

Access token qisqa umrli (`access_token_minutes`), refresh token `refresh_token_hours` — har ishlatilganda
aylantiriladi (yangi `jti`, eskisi `prev_jti` da qoladi). Eski `jti` qayta ko'rsatilsa — o'g'irlangan token
belgisi: foydalanuvchining barcha sessiyalari bekor qilinadi (OAuth 2.0 Security BCP §4.14.2).
"""

from __future__ import annotations

import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import event
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import SessionLocal
from ..orm import User, UserSession
from .security import create_access_token, create_refresh_token, decode_token


class TokenPair:
    __slots__ = ("access_token", "refresh_token", "expires_in", "session_id")

    def __init__(self, access_token: str, refresh_token: str, expires_in: int, session_id: int):
        self.access_token, self.refresh_token, self.expires_in, self.session_id = access_token, refresh_token, expires_in, session_id


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def open_session(db: Session, user: User, *, ip: str = "", user_agent: str = "", client: str = "web") -> TokenPair:
    """Login: yangi sessiya qatori + token juftligi (chaqiruvchi commit qiladi)."""
    s = get_settings()
    jti = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    row = UserSession(
        user_id=user.id,
        jti=jti,
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(hours=s.refresh_token_hours),
        ip=ip[:64],
        user_agent=user_agent[:256],
        client=client[:16],
    )
    db.add(row)
    db.flush()
    return TokenPair(
        create_access_token(user.id, ver=user.token_version, sid=jti, sn=row.id),
        create_refresh_token(user.id, jti, s.refresh_token_hours, ver=user.token_version),
        s.access_token_minutes * 60,
        row.id,
    )


def refresh(db: Session, refresh_token: str) -> tuple[TokenPair, User] | None:
    """Refresh tokenni aylantiradi. None — yaroqsiz (chaqiruvchi 401 beradi). Takror ishlatilgan eski
    token → foydalanuvchining barcha sessiyalari bekor (auditda `auth.session_reuse`)."""
    p = decode_token(refresh_token, scope="refresh")
    if p is None:
        return None
    jti = p.get("jti", "")
    row = db.query(UserSession).filter_by(jti=jti).one_or_none()
    if row is None:
        reused = db.query(UserSession).filter_by(prev_jti=jti).one_or_none()
        if reused is not None:
            revoke_all(db, reused.user_id, reason="refresh_reuse")
            audit.log(
                db, user_id=reused.user_id, action="auth.session_reuse", target_type="user", target_id=reused.user_id,
                detail={"session_id": reused.id},
            )
            db.commit()
        return None
    user = db.get(User, row.user_id)
    now = datetime.now(timezone.utc)
    if (
        user is None
        or not user.is_active
        or row.revoked_at is not None
        or _aware(row.expires_at) <= now
        or p.get("ver", 0) != user.token_version
    ):
        return None
    s = get_settings()
    row.prev_jti = row.jti
    row.jti = secrets.token_urlsafe(24)
    row.last_used_at = now
    return (
        TokenPair(
            create_access_token(user.id, ver=user.token_version, sid=row.jti, sn=row.id),
            create_refresh_token(user.id, row.jti, max(0.0, (_aware(row.expires_at) - now).total_seconds() / 3600), ver=user.token_version),
            s.access_token_minutes * 60,
            row.id,
        ),
        user,
    )


def revoke(db: Session, user_id: int, *, jti: str | None = None, session_id: int | None = None) -> bool:
    q = db.query(UserSession).filter_by(user_id=user_id, revoked_at=None)
    row = q.filter_by(jti=jti).one_or_none() if jti else q.filter_by(id=session_id).one_or_none()
    if row is None:
        return False
    row.revoked_at = datetime.now(timezone.utc)
    _forget_later(db, [row.id])
    return True


def revoke_all(db: Session, user_id: int, *, reason: str = "") -> int:
    """Foydalanuvchining barcha sessiyalari bekor va token versiyasi oshadi → mavjud access tokenlar
    ham yaroqsiz (parol/rol o'zgarishi, o'chirish, refresh takrori)."""
    now = datetime.now(timezone.utc)
    n = 0
    ids = []
    for row in db.query(UserSession).filter_by(user_id=user_id, revoked_at=None).all():
        row.revoked_at = now
        row.revoke_reason = reason[:32]
        ids.append(row.id)
        n += 1
    _forget_later(db, ids)
    user = db.get(User, user_id)
    if user is not None:
        user.token_version = (user.token_version or 0) + 1
    return n


def purge_expired(db: Session, keep_days: int = 30) -> int:
    """Muddati o'tgan/bekor qilingan eski qatorlarni tozalash (fon vazifasi)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    return (
        db.query(UserSession)
        .filter((UserSession.expires_at < cutoff) | (UserSession.revoked_at < cutoff))
        .delete(synchronize_session=False)
    )


# --------------------------------------------------------------------------- AUTH-01: access token ↔ sessiya

# Faol sessiyalar keshi: sn → (user_id, amal qilish muddati, monotonic). Faqat ijobiy natija keshlanadi —
# bekor qilingan sessiya har safar DB dan tekshiriladi (faqat eski/o'g'irlangan token egasi uchun narx).
# Shu jarayonda bekor qilish keshni darhol tozalaydi; boshqa API jarayonlarida ≤ SESSION_CACHE_S kechikish.
SESSION_CACHE_S = 5.0
_ALIVE: dict[int, tuple[int, float]] = {}
_ALIVE_MAX = 20_000
_alive_lock = threading.Lock()
_FORGET = "sessions.forget"


def _forget(ids) -> None:
    with _alive_lock:
        for i in ids:
            _ALIVE.pop(i, None)


def _forget_later(db: Session, ids: list[int]) -> None:
    """Keshdan hozir va tranzaksiya commit bo'lgach yana olib tashlash (oraliqda qayta keshlanmasin)."""
    _forget(ids)
    db.info.setdefault(_FORGET, set()).update(ids)


@event.listens_for(SessionLocal, "after_commit")
def _forget_on_commit(session: Session) -> None:
    ids = session.info.pop(_FORGET, None)
    if ids:
        _forget(ids)


@event.listens_for(SessionLocal, "after_rollback")
def _forget_drop(session: Session) -> None:
    session.info.pop(_FORGET, None)


def session_alive(sn: int, user_id: int) -> bool:
    """Access token sessiyasi hali faolmi (bekor qilinmagan, muddati o'tmagan, shu foydalanuvchiniki)."""
    now = time.monotonic()
    with _alive_lock:
        hit = _ALIVE.get(sn)
        if hit is not None and hit[0] == user_id and hit[1] > now:
            return True
    with SessionLocal() as db:
        row = db.get(UserSession, sn)
        ok = (
            row is not None
            and row.user_id == user_id
            and row.revoked_at is None
            and _aware(row.expires_at) > datetime.now(timezone.utc)
        )
    with _alive_lock:
        if ok:
            if len(_ALIVE) >= _ALIVE_MAX:
                _ALIVE.clear()
            _ALIVE[sn] = (user_id, now + SESSION_CACHE_S)
        else:
            _ALIVE.pop(sn, None)
    return ok

