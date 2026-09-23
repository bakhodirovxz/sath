"""Hosilaviy artefaktlar navbati (L3): IFC → fragments (.frag) va QTO/to'qnashuv oldindan hisoblash.
Ilgari `BackgroundTasks` (restartda yo'qolar edi); endi `jobs` navbati — idempotent (`<tur>:<sha>`).

OPS-03: GET /fragments, /qto, /clashes keshda natija bo'lmasa so'rov ichida hisoblamaydi — shu navbatga
`fragments`, `qto`, `clash` ishini qo'yib 202 qaytaradi; katta IFC metadata si (`meta`) ham shu yerda."""

from __future__ import annotations

from sqlalchemy.orm import Session

from .. import jobs
from ..config import get_settings
from . import blob_gc, storage


def _fragments(payload: dict) -> None:
    from . import fragments

    if not fragments.available():
        return  # Node/vosita yo'q — brauzer IFC ni o'zi ochadi (xato emas)
    if fragments.convert(storage.resolve(payload["sha"]), payload["sha"]) is None:
        raise RuntimeError("fragments konvertatsiyasi bajarilmadi (log ga qarang)")


def _qto(payload: dict) -> None:
    from . import geometry

    path = storage.resolve(payload["sha"])
    geometry.cached(payload["sha"], "qto", lambda: geometry.compute_qto(path))


def _clash(payload: dict) -> None:
    from . import geometry

    path = storage.resolve(payload["sha"])
    ta, tb = payload.get("types_a") or None, payload.get("types_b") or None
    geometry.cached(payload["sha"], geometry.clash_kind(ta, tb), lambda: geometry.compute_clashes(path, 0.0, ta, tb))


def _meta(payload: dict) -> None:
    """Katta IFC ning to'liq metadata si (yuklashda faqat sarlavha o'qilgan) — shu fayldagi versiyalarga."""
    from ..db import SessionLocal
    from ..orm import Version
    from . import ifc_meta

    full = ifc_meta.extract(storage.resolve(payload["sha"]))
    with SessionLocal() as db:
        for v in db.query(Version).filter_by(file_sha256=payload["sha"]).all():
            if (v.meta or {}).get("pending"):
                keep = [w for w in v.meta.get("warnings", []) if not w.startswith(ifc_meta.PENDING_WARNING)]
                v.meta = {**full, "warnings": keep + full.get("warnings", [])}
        db.commit()


def _geometry(payload: dict) -> None:
    from . import geometry

    geometry.precompute(storage.resolve(payload["sha"]), payload["sha"])


def _ids(payload: dict) -> None:
    from . import ids_check

    ids_check.check_and_store(payload["sha"])


jobs.HANDLERS.setdefault("fragments", _fragments)
jobs.HANDLERS.setdefault("geometry", _geometry)
jobs.HANDLERS.setdefault("ids", _ids)
jobs.HANDLERS.setdefault("qto", _qto)
jobs.HANDLERS.setdefault("clash", _clash)
jobs.HANDLERS.setdefault("meta", _meta)


def enqueue_for(db: Session, sha: str, *, meta_pending: bool = False) -> None:
    """Yangi versiya fayli uchun hosilaviy ishlar (sozlamalarga qarab), commit + ishchini uyg'otish."""
    s = get_settings()
    if meta_pending:
        jobs.enqueue(db, "meta", {"sha": sha}, idempotency_key=f"meta:{sha}")
    if s.fragments_enabled:
        jobs.enqueue(db, "fragments", {"sha": sha}, idempotency_key=f"fragments:{sha}")
    if s.precompute_geometry:
        jobs.enqueue(db, "geometry", {"sha": sha}, idempotency_key=f"geometry:{sha}")
    jobs.enqueue(db, "ids", {"sha": sha}, idempotency_key=f"ids:{sha}")  # G2: IDS tekshiruvi har yuklashda
    blob_gc.enqueue_daily(db)  # SRV-05: fayl ombori tozalash — faollik bo'lgan kuni bir marta
    db.commit()
    jobs.kick()
