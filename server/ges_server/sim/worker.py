"""CFD worker: navbatdagi `kind="cfd"` ishlarni oladi va shu muhitdagi OpenFOAM bilan bajaradi.

Ishga tushirish (OpenFOAM konteynerida): ges-worker
Server GES_CFD_MODE=worker bo'lganda CFD ishlarini o'zi bajarmaydi — worker oladi.
"""

from __future__ import annotations

import logging
import time

from ..db import SessionLocal
from ..orm import SimJob, SimStatus
from .router import run_job

log = logging.getLogger("ges_worker")


def next_job() -> int | None:
    with SessionLocal() as db:
        job = (
            db.query(SimJob)
            .filter_by(kind="cfd", status=SimStatus.queued)
            .order_by(SimJob.id)
            .first()
        )
        return job.id if job else None


def main(poll_s: float = 3.0) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log.info("CFD worker ishga tushdi (har %ss navbat tekshiriladi)", poll_s)
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
