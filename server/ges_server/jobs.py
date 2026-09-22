"""Ish navbati (L3): DB asosidagi navbat — atomik claim (UPDATE ... WHERE status='queued'), ijara (lease)
va uzaytirish, restartda yarashtirish, idempotentlik kalitlari.

Ikki jadval bitta protokolda: `SimJob` (simulyatsiyalar) va `Job` (hosilaviy artefaktlar — fragments,
geometriya). Ishchi: shu jarayondagi `runner()` (asyncio vazifasi, thread hovuzi) yoki tashqi CFD ishchisi
(`sim/worker.py`). Ijara muddati tugagan `running` ish egasiz hisoblanadi: urinishlar qolsa navbatga
qaytadi, aks holda `failed`. Redis siz — bitta DB, ko'p ishchi (Postgres da `SELECT ... FOR UPDATE SKIP
LOCKED` shart emas: claim UPDATE ning o'zi atomik).
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import threading
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from .config import get_settings
from .db import SessionLocal
from .orm import Job, JobStatus, SimJob, SimStatus, utcnow

log = logging.getLogger("ges_server.jobs")

WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
LEASE_S = 90  # ijara; ishchi har LEASE_S/3 da uzaytiradi


def _aware(dt: datetime | None) -> datetime | None:
    return None if dt is None else (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))


# --------------------------------------------------------------------------- claim / lease (ikkala jadval)


def claim(db: Session, table, job_id: int, worker_id: str = WORKER_ID, lease_s: int = LEASE_S) -> bool:
    """Atomik claim: faqat `queued` holatdagi qator `running` ga o'tadi (bitta UPDATE — ikki ishchi bir ishni
    ololmaydi). True — bu ishchi oldi."""
    queued = SimStatus.queued if table is SimJob else JobStatus.queued
    running = SimStatus.running if table is SimJob else JobStatus.running
    now = datetime.now(timezone.utc)
    r = db.execute(
        update(table)
        .where(table.id == job_id, table.status == queued)
        .values(
            status=running,
            worker_id=worker_id,
            lease_until=now + timedelta(seconds=lease_s),
            started_at=now,
            attempts=table.attempts + 1,
        )
    )
    db.commit()
    return r.rowcount == 1


def renew(db: Session, table, job_id: int, worker_id: str = WORKER_ID, lease_s: int = LEASE_S) -> bool:
    """Ijarani uzaytirish; False — ish endi bu ishchiniki emas (yarashtirish olib qo'ygan)."""
    r = db.execute(
        update(table)
        .where(table.id == job_id, table.worker_id == worker_id)
        .values(lease_until=datetime.now(timezone.utc) + timedelta(seconds=lease_s))
    )
    db.commit()
    return r.rowcount == 1


def next_queued(db: Session, table, *, kind: str | None = None, exclude_kind: str | None = None) -> int | None:
    q = db.query(table.id).filter(table.status == (SimStatus.queued if table is SimJob else JobStatus.queued))
    if kind is not None:
        q = q.filter(table.kind == kind)
    if exclude_kind is not None:
        q = q.filter(table.kind != exclude_kind)
    row = q.order_by(table.id).first()
    return row[0] if row else None


def reconcile(db: Session, *, now: datetime | None = None, own_host: bool = True) -> dict[str, int]:
    """Egasiz `running` ishlar: ijarasi tugagan (ishchi o'lgan) yoki shu hostdagi oldingi jarayonniki
    (`own_host`, restart). Urinishlar qolsa `queued`, aks holda `failed`. Startda va davriy chaqiriladi."""
    now = now or datetime.now(timezone.utc)
    host = socket.gethostname() + ":"
    out = {"requeued": 0, "failed": 0}
    for table, running, queued, failed in (
        (SimJob, SimStatus.running, SimStatus.queued, SimStatus.failed),
        (Job, JobStatus.running, JobStatus.queued, JobStatus.failed),
    ):
        for j in db.query(table).filter(table.status == running).all():
            lease = _aware(j.lease_until)
            orphan = lease is None or lease <= now
            if not orphan and own_host and j.worker_id and j.worker_id.startswith(host) and j.worker_id != WORKER_ID:
                orphan = True  # shu hostdagi oldingi jarayon (restart) — bir hostda bitta Sath jarayoni
            if not orphan:
                continue
            if j.attempts < j.max_attempts:
                j.status = queued
                j.worker_id = None
                j.lease_until = None
                j.error = f"ishchi javob bermadi ({j.worker_id or '?'}), qayta navbatda ({j.attempts}/{j.max_attempts})"
                out["requeued"] += 1
            else:
                j.status = failed
                j.error = "Ishchi javob bermadi (server qayta ishga tushgan yoki ish qotgan) — qayta urinishlar tugadi"
                j.finished_at = utcnow()
                out["failed"] += 1
    db.commit()
    return out


# --------------------------------------------------------------------------- hosilaviy artefakt navbati (Job)


def enqueue(db: Session, kind: str, payload: dict, *, idempotency_key: str | None = None, project_id: int | None = None, user_id: int | None = None, max_attempts: int = 2) -> Job:
    """Navbatga qo'yish; `idempotency_key` mavjud bo'lsa (queued/running/done) shu qator qaytadi
    (takror yuklash ikki marta konvertatsiya qilmaydi); `failed` bo'lsa qayta navbatga."""
    if idempotency_key:
        row = db.query(Job).filter_by(idempotency_key=idempotency_key).one_or_none()
        if row is not None:
            if row.status == JobStatus.failed:
                row.status = JobStatus.queued
                row.attempts = 0
                row.error = ""
                row.finished_at = None
                db.flush()
            return row
    row = Job(kind=kind, payload=payload, idempotency_key=idempotency_key, project_id=project_id, user_id=user_id, max_attempts=max_attempts)
    db.add(row)
    db.flush()
    return row


def finish(db: Session, table, job_id: int, *, ok: bool, error: str = "") -> None:
    j = db.get(table, job_id)
    if j is None:
        return
    j.status = (SimStatus.done if table is SimJob else JobStatus.done) if ok else (SimStatus.failed if table is SimJob else JobStatus.failed)
    j.error = error[:4000]
    j.finished_at = utcnow()
    j.lease_until = None
    db.commit()


# Hosilaviy ish bajaruvchilari: kind → (payload) -> None. Ro'yxatga olish: jobs.HANDLERS["fragments"] = fn
HANDLERS: dict[str, Callable[[dict], None]] = {}


def run_derived(job_id: int) -> None:
    with SessionLocal() as db:
        j = db.get(Job, job_id)
        if j is None:
            return
        kind, payload = j.kind, dict(j.payload)
    fn = HANDLERS.get(kind)
    if fn is None:
        with SessionLocal() as db:
            finish(db, Job, job_id, ok=False, error=f"noma'lum ish turi: {kind}")
        return
    stop = threading.Event()
    t = threading.Thread(target=_renew_loop, args=(Job, job_id, stop), daemon=True)
    t.start()
    try:
        fn(payload)
        ok, err = True, ""
    except Exception as e:  # noqa: BLE001 — xato ish qatoriga yoziladi, ishchi to'xtamaydi
        log.exception("hosilaviy ish %s (%s) xato", job_id, kind)
        ok, err = False, str(e)
    finally:
        stop.set()
    with SessionLocal() as db:
        finish(db, Job, job_id, ok=ok, error=err)


def _renew_loop(table, job_id: int, stop: threading.Event) -> None:
    while not stop.wait(LEASE_S / 3):
        with SessionLocal() as db:
            if not renew(db, table, job_id):
                log.warning("ish %s ijarasi yo'qoldi (yarashtirish olib qo'ydi)", job_id)
                return


def renew_forever(table, job_id: int) -> threading.Event:
    """Uzun ish uchun (sim): ijarani fon threadida uzaytirib turadi; qaytgan Event ni set() qilib to'xtatiladi."""
    stop = threading.Event()
    threading.Thread(target=_renew_loop, args=(table, job_id, stop), daemon=True).start()
    return stop


# --------------------------------------------------------------------------- jarayon ichidagi ishchi


class Runner:
    """Asyncio vazifasi: navbatni tekshiradi, ishlarni chegaralangan thread hovuzida bajaradi.
    `kick()` — yangi ish qo'shilganda darhol uyg'otish (boshqa threaddan xavfsiz)."""

    def __init__(self, run_sim: Callable[[int], None]):
        self._run_sim = run_sim
        self._wake: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.active = 0

    def kick(self) -> None:
        if self._loop is not None and self._wake is not None:
            self._loop.call_soon_threadsafe(self._wake.set)

    async def run(self, stop: asyncio.Event) -> None:
        s = get_settings()
        self._loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        sem = asyncio.Semaphore(max(1, s.jobs_concurrency))
        last_reconcile = 0.0
        await asyncio.to_thread(self._startup)
        while not stop.is_set():
            try:
                now = self._loop.time()
                if now - last_reconcile >= 60:
                    last_reconcile = now
                    r = await asyncio.to_thread(self._reconcile_periodic)
                    if r["requeued"] or r["failed"]:
                        log.warning("ish navbati yarashtirildi: %s", r)
                started = False
                if not sem.locked():
                    job = await asyncio.to_thread(self._claim_one)
                    if job is not None:
                        started = True
                        asyncio.create_task(self._execute(sem, *job))
                if not started:
                    self._wake.clear()
                    try:
                        await asyncio.wait_for(self._wake.wait(), timeout=s.jobs_poll_s)
                    except (TimeoutError, asyncio.TimeoutError):
                        pass
            except Exception:  # noqa: BLE001 — ishchi sikli to'xtamasin
                log.exception("ish navbati sikli xatosi")
                await asyncio.sleep(1)

    def _startup(self) -> None:
        with SessionLocal() as db:
            r = reconcile(db, own_host=True)
        if r["requeued"] or r["failed"]:
            log.warning("startda egasiz ishlar yarashtirildi: %s", r)

    def _reconcile_periodic(self) -> dict[str, int]:
        with SessionLocal() as db:
            return reconcile(db, own_host=False)

    def _claim_one(self):
        """Navbatdan bitta ish: avval hosilaviy (tez), keyin sim (CFD — faqat worker rejimi bo'lmasa)."""
        s = get_settings()
        with SessionLocal() as db:
            jid = next_queued(db, Job)
            if jid is not None and claim(db, Job, jid):
                return (Job, jid)
            sid = next_queued(db, SimJob, exclude_kind="cfd" if s.cfd_mode == "worker" else None)
            if sid is not None and claim(db, SimJob, sid):
                return (SimJob, sid)
        return None

    async def _execute(self, sem: asyncio.Semaphore, table, job_id: int) -> None:
        async with sem:
            self.active += 1
            try:
                if table is Job:
                    await asyncio.to_thread(run_derived, job_id)
                else:
                    await asyncio.to_thread(self._run_sim, job_id)
            except Exception:  # noqa: BLE001
                log.exception("ish %s bajarilmadi", job_id)
            finally:
                self.active -= 1
        if self._wake is not None:
            self._wake.set()  # bo'sh o'rin — keyingi ish


runner: Runner | None = None


def kick() -> None:
    if runner is not None:
        runner.kick()
