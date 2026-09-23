"""CFD worker: navbatdagi `kind="cfd"` ishlarni atomik claim qilib (L3, ijara bilan) shu muhitdagi
OpenFOAM bilan bajaradi. Ikki worker bir ishni ololmaydi; worker o'lsa ijara tugagach ish yarashtiriladi.

Ishga tushirish (OpenFOAM konteynerida): ges-worker
Server GES_CFD_MODE=worker bo'lganda CFD ishlarini o'zi bajarmaydi — worker oladi.

Izolyatsiya (SEC-01): worker server bilan bir DB ga ulanadi (GES_DATABASE_URL — Postgres), lekin faqat
`/data/cfd` (case papkalari + natija) ni ko'radi — `secret.key`, IFC fayllar, `.env` sirlari yo'q
(GES_SECRET_KEY_REQUIRED=false). Solver tozalangan muhitda ishlaydi (runner.solver_env), worker jarayoni
esa "dumpable" emas — bir xil uid dagi solver /proc/<pid>/environ|mem orqali DB parolini o'qiy olmaydi.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from .. import jobs
from ..db import SessionLocal
from ..orm import SimJob
from .router import run_job

log = logging.getLogger("ges_worker")


def next_job() -> int | None:
    """Navbatdagi birinchi CFD ishini claim qiladi (UPDATE ... WHERE status='queued'); yo'q — None."""
    with SessionLocal() as db:
        while True:
            jid = jobs.next_queued(db, SimJob, kind="cfd")
            if jid is None:
                return None
            if jobs.claim(db, SimJob, jid):
                return jid
            # boshqa worker olib ulgurdi — keyingisi


def _harden_process() -> None:
    """Linux: PR_SET_DUMPABLE=0 — /proc/<pid>/environ va mem boshqa (shu uid dagi) jarayonlarga yopiq."""
    if not sys.platform.startswith("linux"):
        return
    try:
        import ctypes

        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(4, 0, 0, 0, 0) != 0:  # PR_SET_DUMPABLE = 4
            log.warning("prctl(PR_SET_DUMPABLE) muvaffaqiyatsiz: errno %s", ctypes.get_errno())
    except OSError as e:  # pragma: no cover — libc topilmadi
        log.warning("prctl mavjud emas: %s", e)


def check_database_url(url: str) -> str | None:
    """Worker server DB siga ulanishi shart. SQLite fayli yo'q bo'lsa (konteynerda server bazasi ko'rinmaydi)
    worker yangi bo'sh baza yaratib, navbatni hech qachon ko'rmas edi — xato matni qaytadi."""
    if url.startswith("sqlite"):
        path = url.split(":///", 1)[-1]
        if not path or path == ":memory:" or not Path(path).exists():
            return (
                f"CFD worker server bazasini topmadi ({url.split('://', 1)[0]}): konteyner deployda Postgres "
                "ishlating — GES_DATABASE_URL server bilan bir xil bo'lsin (deploy/.env.example)"
            )
    return None


def main(poll_s: float = 3.0) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from ..config import get_settings

    problem = check_database_url(get_settings().database_url)
    if problem:
        log.error(problem)
        raise SystemExit(2)
    _harden_process()
    log.info("CFD worker %s ishga tushdi (har %ss navbat tekshiriladi)", jobs.WORKER_ID, poll_s)
    while True:
        job_id = next_job()
        if job_id is None:
            time.sleep(poll_s)
            continue
        log.info("ish #%s boshlandi", job_id)
        run_job(job_id, cfd_mode="local")
        log.info("ish #%s tugadi", job_id)


if __name__ == "__main__":
    main()
