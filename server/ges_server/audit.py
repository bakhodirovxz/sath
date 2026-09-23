"""Audit jurnali: hash zanjiri bilan, asosiy tranzaksiyadan ajratilgan yozuv.

Nima uchun ajratilgan: SQLite (WAL) da bitta yozuvchi — so'rov o'z tranzaksiyasini ushlab turganda
alohida sessiyada yozish qulf kutadi. Shuning uchun `log()` faqat sessiya buferiga qo'shadi; sessiya
`commit` bo'lgach (`after_commit`) yozuvlar alohida qisqa tranzaksiyada, jarayon qulfi ostida zanjirga
ulanadi. `rollback` bo'lsa bufer tashlanadi (bo'lmagan o'zgarish haqida yozuv qolmasin). Asosiy
tranzaksiyaga bog'liq bo'lmagan hodisalar (`auth.login_failed`, `ws.*`) — `log_now()`.

Zanjir: `row_hash = H(canonical_json(created_at, user_id, action, target_type, target_id, project_id,
detail, prev_hash))`; `prev_hash` — oldingi qatorning `row_hash` i, birinchisi uchun "". `id` hashga
kirmaydi (insert dan oldin noma'lum). `verify_chain()` butun jadvalni qayta hisoblaydi.

Versiyalangan sxema (AUTH-05, `hash_alg` ustuni):
- `v1` (NULL — eski qatorlar): H = sha256 — kalitsiz; DB ga yozish huquqi bor odam qatorni o'zgartirib, keyingi
  barcha hashlarni qayta hisoblab zanjirni "tuzatishi" mumkin edi;
- `v2` (yangi qatorlar): H = HMAC-SHA256(audit kaliti, payload + "alg") — kalit DB da emas (`GES_AUDIT_KEY` yoki
  `data_dir/audit.key`, 0600; server `secret_key` dan alohida, JWT kaliti almashtirilsa zanjir buzilmaydi).
  Birinchi v2 qatordan keyin v1 ga "qaytish" taqiqlangan (verify xato beradi) — shuning uchun butun oldingi
  v1 qismini ham kalitsiz qayta yozib bo'lmaydi (birinchi v2 qatorning prev_hash i mos kelmay qoladi).

Bir nechta jarayon (L8 HA): Postgres da zanjir boshi `pg_advisory_xact_lock` ostida o'qiladi va yoziladi
(jarayon qulfi bitta jarayon uchun; aks holda ikki replika bir prev_hash dan tarmoqlanardi). Postgres da
migratsiya 0039 audit_log ga UPDATE/DELETE/TRUNCATE ni trigger bilan taqiqlaydi (SQLite da yo'q).
Yozish xatosi so'rovni yiqitmaydi, lekin baland ovozda: CRITICAL log (yozuvlar mazmuni bilan), `STATS`
hisoblagichi (`GET /api/audit/status`) va administratorlarga tizim bildirishnomasi.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import event, insert, select, text
from sqlalchemy.orm import Session

from .config import get_settings, write_private
from .db import SessionLocal, engine
from .orm import AuditLog, utcnow

log_ = logging.getLogger("ges_server.audit")

_chain_lock = threading.Lock()
_BUF = "audit"
HASH_ALG = "v2"  # yangi qatorlar: HMAC-SHA256 (audit kaliti bilan)
AUDIT_LOCK_KEY = 0x53415544  # 'SAUD' — pg_advisory_xact_lock kaliti (ha.LEADER_KEY dan farqli)

# Yozish xatolari (metrika): GET /api/audit/status, /api/audit/verify
STATS: dict = {"write_failures": 0, "lost_entries": 0, "last_failure_at": None, "last_error": ""}
_ALARM_EVERY_S = 300.0
_last_alarm = 0.0


# ---------- audit kaliti ----------

_KEY: bytes | None = None
_KEY_LOCK = threading.Lock()


def audit_key() -> bytes:
    """HMAC kaliti: `GES_AUDIT_KEY` muhit o'zgaruvchisi yoki `data_dir/audit.key` (birinchi ishga tushishda
    yaratiladi, 0600). Bir necha replikada — umumiy muhit o'zgaruvchisi yoki umumiy data papka shart."""
    global _KEY
    if _KEY is not None:
        return _KEY
    with _KEY_LOCK:
        if _KEY is None:
            env = os.environ.get("GES_AUDIT_KEY", "").strip()
            if env:
                _KEY = env.encode("utf-8")
            else:
                f = get_settings().data_dir / "audit.key"
                if not f.exists():
                    write_private(f, secrets.token_urlsafe(48))
                _KEY = f.read_text().strip().encode("utf-8")
    return _KEY


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
    alg: str | None = None,
) -> str:
    """alg None/"v1" — sha256 (eski qatorlar); "v2" — HMAC-SHA256(audit_key) va payload da "alg"."""
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
    if alg in (None, "", "v1"):
        s = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(s.encode("utf-8")).hexdigest()
    if alg != "v2":
        raise ValueError(f"noma'lum audit hash sxemasi: {alg}")
    payload["alg"] = alg
    s = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hmac.new(audit_key(), s.encode("utf-8"), hashlib.sha256).hexdigest()


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


def write_now(entries: list[dict]) -> bool:
    """Yozuvlarni zanjirga ulab yozadi (alohida ulanish/tranzaksiya). True — yozildi.

    Bir jarayon: `threading.Lock`. Postgres (bir necha API/ishchi jarayoni, L8): tranzaksiya ichida
    `pg_advisory_xact_lock` — zanjir boshini o'qish va yozish butun klaster bo'yicha ketma-ket (tarmoqlanmaydi).
    Xato so'rovni yiqitmaydi, lekin yashirilmaydi: CRITICAL log + STATS + administratorlarga bildirishnoma.
    """
    if not entries:
        return True
    tbl = AuditLog.__table__
    try:
        with _chain_lock, engine.begin() as conn:
            if conn.dialect.name == "postgresql":
                conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": AUDIT_LOCK_KEY})
            head = conn.execute(
                select(tbl.c.row_hash).order_by(tbl.c.id.desc()).limit(1)
            ).scalar()
            prev = head or ""
            for e in entries:
                h = row_hash(prev_hash=prev, alg=HASH_ALG, **e)
                conn.execute(insert(tbl).values(**e, prev_hash=prev, row_hash=h, hash_alg=HASH_ALG))
                prev = h
        return True
    except Exception as exc:  # noqa: BLE001 — audit xatosi asosiy ishni to'xtatmasin, lekin baland ovozda
        _write_failed(entries, exc)
        return False


def _write_failed(entries: list[dict], exc: Exception) -> None:
    STATS["write_failures"] += 1
    STATS["lost_entries"] += len(entries)
    STATS["last_failure_at"] = datetime.now(timezone.utc).isoformat()
    STATS["last_error"] = f"{type(exc).__name__}: {exc}"[:500]
    # Yozuvlar mazmuni logga — keyin qo'lda tiklash mumkin bo'lsin (log markazlashtirilgan SIEM ga ketadi)
    log_.critical(
        "AUDIT YOZILMADI (%d yozuv, jami xato %d): %s | %s",
        len(entries),
        STATS["write_failures"],
        STATS["last_error"],
        json.dumps(entries, default=str, ensure_ascii=False)[:20000],
        exc_info=exc,
    )
    _alarm_admins()


def _alarm_admins() -> None:
    """Administratorlarga tizim bildirishnomasi (5 daqiqada ko'pi bilan bir marta; DB ishlamasa — jim)."""
    global _last_alarm
    now = time.monotonic()
    if now - _last_alarm < _ALARM_EVERY_S:
        return
    _last_alarm = now
    try:
        from .orm import Notification, User

        with SessionLocal() as db:
            for (uid,) in db.query(User.id).filter_by(is_admin=True, is_active=True).all():
                db.add(
                    Notification(
                        user_id=uid,
                        kind="system",
                        title="Audit jurnaliga yozib bo'lmadi",
                        body=f"{STATS['write_failures']} ta xato, oxirgisi: {STATS['last_error'][:150]}",
                        link="/admin/audit",
                    )
                )
            db.commit()
    except Exception:  # noqa: BLE001 — signal berishning o'zi yiqilsa ham asosiy ish davom etadi
        log_.exception("audit xatosi haqida bildirishnoma yuborilmadi")


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
    {ok, checked, first_bad_id, head, schemes, keyed, write_failures} — first_bad_id: hash mos kelmagan
    birinchi qator; v2 (HMAC) qatordan keyin v1 qator — ham buzilish (sxemani pasaytirish)."""
    tbl = AuditLog.__table__
    prev = ""
    checked, first_bad, head = 0, None, ""
    last_id = 0
    schemes = {"v1": 0, "v2": 0}
    seen_v2 = False
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
                tbl.c.hash_alg,
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
            alg = r.hash_alg or "v1"
            if alg not in schemes or (seen_v2 and alg != "v2"):
                first_bad = r.id  # noma'lum sxema yoki HMAC dan kalitsiz sxemaga qaytish
                break
            seen_v2 = seen_v2 or alg == "v2"
            schemes[alg] += 1
            expected = row_hash(
                created_at=r.created_at,
                user_id=r.user_id,
                action=r.action,
                target_type=r.target_type,
                target_id=r.target_id,
                project_id=r.project_id,
                detail=r.detail,
                prev_hash=prev,
                alg=alg,
            )
            if (r.prev_hash or "") != prev or not hmac.compare_digest(r.row_hash or "", expected):
                first_bad = r.id
                break
            prev = r.row_hash
            head = r.row_hash
        if first_bad is not None:
            break
    return {
        "ok": first_bad is None,
        "checked": checked,
        "first_bad_id": first_bad,
        "head": head,
        "schemes": schemes,
        "keyed": seen_v2,
        "write_failures": STATS["write_failures"],
    }


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
