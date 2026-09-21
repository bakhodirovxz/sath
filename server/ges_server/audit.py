"""Audit jurnali: hash zanjiri bilan, asosiy tranzaksiyadan ajratilgan yozuv.

Nima uchun ajratilgan: SQLite (WAL) da bitta yozuvchi — so'rov o'z tranzaksiyasini ushlab turganda
alohida sessiyada yozish qulf kutadi. Shuning uchun `log()` faqat sessiya buferiga qo'shadi; sessiya
`commit` bo'lgach (`after_commit`) yozuvlar alohida qisqa tranzaksiyada, jarayon qulfi ostida zanjirga
ulanadi. `rollback` bo'lsa bufer tashlanadi (bo'lmagan o'zgarish haqida yozuv qolmasin). Asosiy
tranzaksiyaga bog'liq bo'lmagan hodisalar (`auth.login_failed`, `ws.*`) — `log_now()`.

Zanjir: `row_hash = sha256(canonical_json(created_at, user_id, action, target_type, target_id,
project_id, detail, prev_hash))`; `prev_hash` — oldingi qatorning `row_hash` i, birinchisi uchun "".
`id` hashga kirmaydi (insert dan oldin noma'lum). `verify_chain()` butun jadvalni qayta hisoblaydi.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
from datetime import datetime, timezone

from sqlalchemy import event, insert, select
from sqlalchemy.orm import Session

from .db import SessionLocal, engine
from .orm import AuditLog, utcnow

log_ = logging.getLogger("ges_server.audit")

_chain_lock = threading.Lock()
_BUF = "audit"


# ---------- hash ----------


def _canon_ts(dt: datetime) -> str:
    """UTC, tz siz, mikrosekund — SQLite (naive) va Postgres (timestamptz) da bir xil."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.isoformat(timespec="microseconds")


def _canon_detail(detail) -> dict:
    """JSON ustuniga yozilgandan keyin qanday o'qilsa shunday (tuple → list, boshqa turlar → str)."""
    return json.loads(json.dumps(detail or {}, default=str))


def row_hash(
    *,
    created_at: datetime,
    user_id: int | None,
    action: str,
    target_type: str,
    target_id: int | None,
    project_id: int | None,
    detail,
    prev_hash: str,
) -> str:
    payload = {
        "created_at": _canon_ts(created_at),
        "user_id": user_id,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "project_id": project_id,
        "detail": _canon_detail(detail),
        "prev_hash": prev_hash or "",
    }
    s = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ---------- yozish ----------


def _entry(
    *,
    user_id: int | None,
    action: str,
    target_type: str,
    target_id: int | None,
    project_id: int | None,
    detail: dict | None,
) -> dict:
    return {
        "created_at": utcnow(),
        "user_id": user_id,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "project_id": project_id,
        "detail": _canon_detail(detail),
    }


def log(
    db: Session,
    *,
    user_id: int | None,
    action: str,
    target_type: str,
    target_id: int | None = None,
    project_id: int | None = None,
    detail: dict | None = None,
) -> None:
    """Audit yozuvini sessiya buferiga qo'shadi; sessiya commit bo'lganda zanjirga yoziladi.
    Rollback bo'lsa tashlanadi. Commit chaqiruvchi zimmasida (o'qish endpointlarida ham)."""
    db.info.setdefault(_BUF, []).append(
        _entry(
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            project_id=project_id,
            detail=detail,
        )
    )


def log_now(
    *,
    user_id: int | None,
    action: str,
    target_type: str,
    target_id: int | None = None,
    project_id: int | None = None,
    detail: dict | None = None,
) -> None:
    """Darhol, o'z tranzaksiyasida yozadi — asosiy tranzaksiya yo'q yoki u yiqilsa ham qolishi kerak
    bo'lgan hodisalar uchun (kirish xatosi, WebSocket ulanishi)."""
    write_now(
        [
            _entry(
                user_id=user_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                project_id=project_id,
                detail=detail,
            )
        ]
    )


def write_now(entries: list[dict]) -> None:
    """Yozuvlarni zanjirga ulab yozadi (jarayon qulfi ostida, alohida ulanish/tranzaksiya).

    Bir jarayon: qulf yetarli. Postgres + bir necha ishchi: `pg_advisory_xact_lock` bilan
    kuchaytiriladi (L8). Xato so'rovni yiqitmaydi — loglanadi.
    """
    if not entries:
        return
    tbl = AuditLog.__table__
    try:
        with _chain_lock, engine.begin() as conn:
            head = conn.execute(
                select(tbl.c.row_hash).order_by(tbl.c.id.desc()).limit(1)
            ).scalar()
            prev = head or ""
            for e in entries:
                h = row_hash(prev_hash=prev, **e)
                conn.execute(insert(tbl).values(**e, prev_hash=prev, row_hash=h))
                prev = h
    except Exception:  # noqa: BLE001 — audit xatosi asosiy ishni to'xtatmasin, lekin ko'rinsin
        log_.exception("audit yozib bo'lmadi (%d yozuv)", len(entries))


@event.listens_for(SessionLocal, "after_commit")
def _flush_on_commit(session: Session) -> None:
    entries = session.info.pop(_BUF, None)
    if entries:
        write_now(entries)


@event.listens_for(SessionLocal, "after_rollback")
def _drop_on_rollback(session: Session) -> None:
    dropped = session.info.pop(_BUF, None)
    if dropped:
        log_.debug("audit: rollback — %d yozuv tashlandi", len(dropped))


def pending(db: Session) -> int:
    """Hali commit bo'lmagan bufer hajmi (diagnostika/test)."""
    return len(db.info.get(_BUF, []))


# ---------- tekshirish / eksport ----------


def verify_chain(db: Session, batch: int = 1000) -> dict:
    """Butun jadvalni id tartibida qayta hisoblaydi. Qaytaradi:
    {ok, checked, first_bad_id, head} — first_bad_id: hash mos kelmagan birinchi qator."""
    tbl = AuditLog.__table__
    prev = ""
    checked, first_bad, head = 0, None, ""
    last_id = 0
    while True:
        rows = db.execute(
            select(
                tbl.c.id,
                tbl.c.created_at,
                tbl.c.user_id,
                tbl.c.action,
                tbl.c.target_type,
                tbl.c.target_id,
                tbl.c.project_id,
                tbl.c.detail,
                tbl.c.prev_hash,
                tbl.c.row_hash,
            )
            .where(tbl.c.id > last_id)
            .order_by(tbl.c.id)
            .limit(batch)
        ).all()
        if not rows:
            break
        for r in rows:
            last_id = r.id
            checked += 1
            expected = row_hash(
                created_at=r.created_at,
                user_id=r.user_id,
                action=r.action,
                target_type=r.target_type,
                target_id=r.target_id,
                project_id=r.project_id,
                detail=r.detail,
                prev_hash=prev,
            )
            if (r.prev_hash or "") != prev or r.row_hash != expected:
                first_bad = r.id
                break
            prev = r.row_hash
            head = r.row_hash
        if first_bad is not None:
            break
    return {"ok": first_bad is None, "checked": checked, "first_bad_id": first_bad, "head": head}


def export_day(db: Session, day: datetime, secret: str) -> tuple[str, str]:
    """Bir kunlik yozuvlar JSONL sifatida + HMAC-SHA256 imzosi (secret = server kaliti).
    Qaytaradi: (jsonl_matn, imzo_hex). Tekshirish: hmac(secret, jsonl) == imzo."""
    start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(hour=23, minute=59, second=59, microsecond=999999)
    tbl = AuditLog.__table__
    rows = db.execute(
        select(tbl).where(tbl.c.created_at >= start, tbl.c.created_at <= end).order_by(tbl.c.id)
    ).all()
    lines = []
    for r in rows:
        d = dict(r._mapping)
        d["created_at"] = _canon_ts(d["created_at"])
        lines.append(json.dumps(d, sort_keys=True, ensure_ascii=False, default=str))
    body = "\n".join(lines) + ("\n" if lines else "")
    sig = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
    return body, sig
