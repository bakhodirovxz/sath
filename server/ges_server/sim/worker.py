"""CFD worker: navbatdagi `kind="cfd"` ishlarni atomik claim qilib (L3, ijara bilan) shu muhitdagi
OpenFOAM bilan bajaradi. Ikki worker bir ishni ololmaydi; worker o'lsa ijara tugagach ish yarashtiriladi.

Ishga tushirish (OpenFOAM konteynerida): ges-worker
Server GES_CFD_MODE=worker bo'lganda CFD ishlarini o'zi bajarmaydi — worker oladi.
"""

from __future__ import annotations

import logging
import time

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


def main(poll_s: float = 3.0) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
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
