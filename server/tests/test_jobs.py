"""L3: ish navbati — atomik claim, ijara, restartda yarashtirish, idempotentlik, kvota, hosilaviy navbat."""

import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from ges_server import jobs
from ges_server.config import get_settings
from ges_server.db import SessionLocal
from ges_server.orm import Job, JobStatus, SimJob, SimStatus
from ges_server.sim import worker


@pytest.fixture
def model_id(client, users):
    r = client.post(f"/api/projects/{users['project_id']}/models", json={"name": "Sim"}, headers=users["engineer"])
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _hydro_params(client, users) -> dict:
    p = client.get("/api/sim/example", headers=users["viewer"]).json()
    p["inflow_m3s"] = {"constant": 120, "steps": 10}
    return p


def _sim_row(**kw) -> int:
    with SessionLocal() as db:
        j = SimJob(model_id=kw.pop("model_id"), author_id=kw.pop("author_id"), kind=kw.pop("kind", "hydro"), params={}, **kw)
        db.add(j)
        db.commit()
        return j.id


def test_claim_is_atomic_between_threads(client, users, model_id):
    jid = _sim_row(model_id=model_id, author_id=users["ids"]["engineer"], kind="cfd")
    barrier = threading.Barrier(2)
    won: list[str] = []

    def go(name: str):
        with SessionLocal() as db:
            barrier.wait()
            if jobs.claim(db, SimJob, jid, worker_id=name):
                won.append(name)

    ts = [threading.Thread(target=go, args=(f"w{i}",)) for i in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(won) == 1, won
    with SessionLocal() as db:
        j = db.get(SimJob, jid)
        assert j.status == SimStatus.running and j.worker_id == won[0] and j.attempts == 1 and j.lease_until is not None
        # ijara faqat egasi tomonidan uzaytiriladi
        assert jobs.renew(db, SimJob, jid, worker_id="boshqa") is False
        assert jobs.renew(db, SimJob, jid, worker_id=won[0]) is True


def test_cfd_worker_next_job_claims_once(client, users, model_id):
    jid = _sim_row(model_id=model_id, author_id=users["ids"]["engineer"], kind="cfd")
    assert worker.next_job() == jid
    assert worker.next_job() is None  # allaqachon running


def test_reconcile_requeues_then_fails(client, users, model_id):
    """Ijarasi tugagan `running` ish: urinish qolsa navbatga, tugasa failed. Restart (shu host) ham egasiz."""
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    a = _sim_row(model_id=model_id, author_id=users["ids"]["engineer"], kind="cfd", status=SimStatus.running, worker_id="olik:1", lease_until=past, attempts=1, max_attempts=2)
    b = _sim_row(model_id=model_id, author_id=users["ids"]["engineer"], kind="cfd", status=SimStatus.running, worker_id="olik:1", lease_until=past, attempts=2, max_attempts=2)
    fresh = _sim_row(model_id=model_id, author_id=users["ids"]["engineer"], kind="cfd", status=SimStatus.running, worker_id="boshqa-host:7", lease_until=datetime.now(timezone.utc) + timedelta(minutes=1), attempts=1)
    with SessionLocal() as db:
        d = Job(kind="fragments", payload={}, status=JobStatus.running, worker_id="olik:1", lease_until=past, attempts=1, max_attempts=2)
        db.add(d)
        db.commit()
        did = d.id
        r = jobs.reconcile(db)
    assert r == {"requeued": 2, "failed": 1}
    with SessionLocal() as db:
        assert db.get(SimJob, a).status == SimStatus.queued and db.get(SimJob, a).worker_id is None
        assert db.get(SimJob, b).status == SimStatus.failed and "Ishchi javob bermadi" in db.get(SimJob, b).error
        assert db.get(SimJob, fresh).status == SimStatus.running  # ijara amalda, boshqa host
        assert db.get(Job, did).status == JobStatus.queued
        # shu hostdagi oldingi jarayon (restart): ijara amalda bo'lsa ham egasiz
        j = db.get(SimJob, fresh)
        j.worker_id = jobs.WORKER_ID.split(":")[0] + ":999999"
        db.commit()
        r = jobs.reconcile(db, own_host=True)
        assert r["requeued"] == 1 and db.get(SimJob, fresh).status == SimStatus.queued


def test_sim_idempotency_key_returns_same_job(client, users, model_id):
    body = {"kind": "hydro", "params": _hydro_params(client, users), "idempotency_key": "abc-1"}
    r1 = client.post(f"/api/models/{model_id}/sim", json=body, headers=users["engineer"])
    assert r1.status_code == 202, r1.text
    r2 = client.post(f"/api/models/{model_id}/sim", json=body, headers=users["engineer"])
    assert r2.status_code == 202 and r2.json()["id"] == r1.json()["id"]
    # boshqa foydalanuvchi uchun shu kalit — alohida ish
    r3 = client.post(f"/api/models/{model_id}/sim", json=body, headers=users["approver"])
    assert r3.status_code == 202 and r3.json()["id"] != r1.json()["id"]


def test_project_quota(client, users, model_id):
    s = get_settings()
    old_u, old_p = s.sim_max_active_per_user, s.sim_max_active_per_project
    s.sim_max_active_per_user, s.sim_max_active_per_project = 100, 2
    try:
        for _ in range(2):
            _sim_row(model_id=model_id, author_id=users["ids"]["viewer"], kind="cfd")  # navbatda qoladi (worker yo'q)
        r = client.post(f"/api/models/{model_id}/sim", json={"kind": "hydro", "params": _hydro_params(client, users)}, headers=users["engineer"])
        assert r.status_code == 429 and "Loyihada" in r.json()["detail"]
    finally:
        s.sim_max_active_per_user, s.sim_max_active_per_project = old_u, old_p


def test_queued_sim_runs_via_runner_and_survives_without_background_tasks(client, users, model_id):
    """Ish navbatdan jarayon ichidagi ishchi tomonidan olinadi va bajariladi (BackgroundTasks emas)."""
    r = client.post(f"/api/models/{model_id}/sim", json={"kind": "hydro", "params": _hydro_params(client, users)}, headers=users["engineer"])
    assert r.status_code == 202, r.text
    jid = r.json()["id"]
    for _ in range(200):
        j = client.get(f"/api/sim/{jid}", headers=users["engineer"]).json()
        if j["status"] in ("done", "failed"):
            break
        time.sleep(0.1)
    assert j["status"] == "done", j["error"]
    assert j["attempts"] == 1
    with SessionLocal() as db:
        row = db.get(SimJob, jid)
        assert row.worker_id == jobs.WORKER_ID and row.lease_until is None and row.started_at is not None


def test_derived_jobs_enqueued_idempotent_on_upload(client, users, ifc_file):
    from conftest import upload

    pid = users["project_id"]
    mid = client.post(f"/api/projects/{pid}/models", json={"name": "M"}, headers=users["engineer"]).json()["id"]
    v = upload(client, users["engineer"], mid, ifc_file, "v1").json()
    sha = v["file_sha256"]
    with SessionLocal() as db:
        rows = db.query(Job).filter(Job.idempotency_key.in_([f"fragments:{sha}", f"geometry:{sha}"])).all()
        assert {r.kind for r in rows} == {"fragments", "geometry"}
        # takror enqueue — yangi qator emas
        again = jobs.enqueue(db, "geometry", {"sha": sha}, idempotency_key=f"geometry:{sha}")
        assert again.id in {r.id for r in rows}
        db.rollback()
    for _ in range(300):
        with SessionLocal() as db:
            st = {r.kind: r.status for r in db.query(Job).filter(Job.idempotency_key.in_([f"geometry:{sha}"])).all()}
        if st.get("geometry") in (JobStatus.done, JobStatus.failed):
            break
        time.sleep(0.1)
    assert st.get("geometry") == JobStatus.done


def test_unknown_derived_kind_fails_cleanly():  # `client` yo'q — jarayon ichidagi ishchi ishni olib qo'ymasin
    with SessionLocal() as db:
        j = jobs.enqueue(db, "nomalum", {})
        db.commit()
        jid = j.id
        assert jobs.claim(db, Job, jid)
    jobs.run_derived(jid)
    with SessionLocal() as db:
        row = db.get(Job, jid)
        assert row.status == JobStatus.failed and "noma'lum" in row.error
