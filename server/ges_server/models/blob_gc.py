"""Fayl ombori tozalash (SRV-05): hech bir yozuv murojaat qilmaydigan content-addressed fayllar va eskirgan
vaqtinchalik fayllar.

Nima to'planadi:
- `files/ab/cd/<sha><ext>` — `sha` hech bir `Version` / `ProjectDocument` / `ImageUnderlay` / `AssetDocument`
  da yo'q (rad etilgan yuklash, 409 bilan tugagan commit, tozalangan model versiyalari);
- `derived/<sha>.*` — yuqoridagidek murojaatsiz sha uchun hosilaviy kesh (frag, QTO, clash, heightmap);
- `files/tmp*` (storage.store vaqtinchalik fayli) va `derived/*.part`, `derived/tmp*` — uzilgan so'rov qoldig'i.

Xavfsizlik: faqat `grace_s` dan eski fayllar (mtime) o'chiriladi. Yangi saqlangan, lekin hali versiya yozuvi
commit bo'lmagan fayl shu oyna ichida; mavjud faylga dedup bo'lganda `storage.store` mtime ni yangilaydi — shu
bilan parallel yuklash va GC poygasi yopiladi. `dry_run` — faqat hisobot.
Ishga tushirish: admin endpoint (`POST /api/admin/storage/gc`), kunlik navbat ishi (`blob_gc`, yuklash
faolligida bir kunda bir marta) va model tozalanganda (`purge`) — faqat o'sha sha lar uchun.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from sqlalchemy.orm import Session

from .. import jobs
from ..config import get_settings
from ..db import SessionLocal
from ..orm import AssetDocument, ImageUnderlay, ProjectDocument, Version

log = logging.getLogger("ges_server.blob_gc")

DEFAULT_GRACE_S = 24 * 3600
_SHA = re.compile(r"^([0-9a-f]{64})\.")  # <sha>.<ext...>
_SHA_ONLY = re.compile(r"^([0-9a-f]{64})$")
_KEEP_DERIVED = (".fedclash.",)  # federatsiya keshi — kaliti a'zolar xeshi, fayl sha si emas
_REPORT_LIMIT = 200


def referenced_shas(db: Session) -> set[str]:
    out: set[str] = set()
    for col in (Version.file_sha256, ProjectDocument.file_sha256, ImageUnderlay.file_sha256, AssetDocument.file_sha256):
        out |= {s for (s,) in db.query(col).distinct().all() if s}
    return out


def _sha_of(name: str) -> str | None:
    m = _SHA.match(name) or _SHA_ONLY.match(name)
    return m.group(1) if m else None


def collect(
    db: Session,
    *,
    dry_run: bool = True,
    grace_s: float = DEFAULT_GRACE_S,
    only_shas: set[str] | None = None,
    now: float | None = None,
) -> dict:
    """Murojaatsiz blob/hosilaviy va eskirgan vaqtinchalik fayllarni topadi (dry_run=False — o'chiradi).
    `only_shas` — faqat shu sha lar (model tozalanganda); vaqtinchalik fayllarga tegilmaydi."""
    s = get_settings()
    cutoff = (now if now is not None else time.time()) - max(0.0, grace_s)
    refs = referenced_shas(db)
    rep: dict = {"dry_run": dry_run, "grace_s": grace_s, "blobs": 0, "derived": 0, "temp": 0, "bytes": 0, "kept_recent": 0, "errors": 0, "paths": []}

    def _drop(p: Path, kind: str) -> None:
        try:
            size = p.stat().st_size
            if not dry_run:
                p.unlink()
        except FileNotFoundError:
            return
        except OSError as e:
            rep["errors"] += 1
            log.warning("GC: %s o'chirilmadi: %s", p, e)
            return
        rep[kind] += 1
        rep["bytes"] += size
        if len(rep["paths"]) < _REPORT_LIMIT:
            rep["paths"].append(str(p))

    def _old(p: Path) -> bool:
        try:
            return p.stat().st_mtime <= cutoff
        except OSError:
            return False

    files_dir = s.files_dir
    if files_dir.exists():
        for p in files_dir.rglob("*"):
            if not p.is_file():
                continue
            sha = _sha_of(p.name)
            in_store = p.parent.parent.parent == files_dir  # files/ab/cd/<sha>.ext
            if sha and in_store:
                if (only_shas is not None and sha not in only_shas) or sha in refs:
                    continue
                if not _old(p):
                    rep["kept_recent"] += 1
                    continue
                _drop(p, "blobs")
            elif only_shas is None and p.parent == files_dir and p.name.startswith("tmp") and _old(p):
                _drop(p, "temp")  # storage.store NamedTemporaryFile qoldig'i (uzilgan yuklash)
        if not dry_run and only_shas is None:
            for d in sorted((x for x in files_dir.rglob("*") if x.is_dir()), key=lambda x: len(x.parts), reverse=True):
                try:
                    d.rmdir()  # faqat bo'sh papkalar
                except OSError:
                    pass

    derived = s.data_dir / "derived"
    if derived.exists():
        for p in derived.iterdir():
            if not p.is_file():
                continue
            sha = _sha_of(p.name)
            if p.name.endswith(".part") or p.name.startswith("tmp"):
                if only_shas is None and _old(p):
                    _drop(p, "temp")
                continue
            if not sha or any(k in p.name for k in _KEEP_DERIVED):
                continue
            if (only_shas is not None and sha not in only_shas) or sha in refs:
                continue
            if not _old(p):
                rep["kept_recent"] += 1
                continue
            _drop(p, "derived")
    if not dry_run and (rep["blobs"] or rep["derived"] or rep["temp"]):
        log.info("GC: %d blob, %d hosilaviy, %d vaqtinchalik fayl, %d bayt", rep["blobs"], rep["derived"], rep["temp"], rep["bytes"])
    return rep


# --------------------------------------------------------------------------- davriy ish (jobs navbati)


def _job(payload: dict) -> None:
    with SessionLocal() as db:
        collect(db, dry_run=False, grace_s=float(payload.get("grace_s", DEFAULT_GRACE_S)))


jobs.HANDLERS.setdefault("blob_gc", _job)


def enqueue_daily(db: Session) -> None:
    """Kunlik GC ishi (idempotent kalit — bir kunda bitta); chaqiruvchi commit qiladi."""
    day = time.strftime("%Y-%m-%d", time.gmtime())
    jobs.enqueue(db, "blob_gc", {"grace_s": DEFAULT_GRACE_S}, idempotency_key=f"blob_gc:{day}", max_attempts=1)
