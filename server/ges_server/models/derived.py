"""Hosilaviy artefaktlar navbati (L3): IFC → fragments (.frag) va QTO/to'qnashuv oldindan hisoblash.
Ilgari `BackgroundTasks` (restartda yo'qolar edi); endi `jobs` navbati — idempotent (`<tur>:<sha>`)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from .. import jobs
from ..config import get_settings
from . import storage


def _fragments(payload: dict) -> None:
    from . import fragments

    fragments.convert(storage.resolve(payload["sha"]), payload["sha"])


def _geometry(payload: dict) -> None:
    from . import geometry

    geometry.precompute(storage.resolve(payload["sha"]), payload["sha"])


jobs.HANDLERS.setdefault("fragments", _fragments)
jobs.HANDLERS.setdefault("geometry", _geometry)


def enqueue_for(db: Session, sha: str) -> None:
    """Yangi versiya fayli uchun hosilaviy ishlar (sozlamalarga qarab), commit + ishchini uyg'otish."""
    s = get_settings()
    if s.fragments_enabled:
        jobs.enqueue(db, "fragments", {"sha": sha}, idempotency_key=f"fragments:{sha}")
    if s.precompute_geometry:
        jobs.enqueue(db, "geometry", {"sha": sha}, idempotency_key=f"geometry:{sha}")
    db.commit()
    jobs.kick()
