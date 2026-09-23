"""A5: parallel commit (versiya raqami poygasi) va bitta sensorga bitta ochiq buyruq (DB indeksi)."""

import threading

import pytest
from conftest import make_ifc, upload
from ges_server.db import SessionLocal
from ges_server.models import router as models_router
from ges_server.orm import Command, CommandStatus
from sqlalchemy.exc import IntegrityError


def _model(client, users):
    r = client.post(
        f"/api/projects/{users['project_id']}/models",
        json={"name": "M"},
        headers=users["engineer"],
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_parallel_commits_get_distinct_numbers(client, users, tmp_path, monkeypatch):
    mid = _model(client, users)
    files = [make_ifc(tmp_path / f"m{i}.ifc", wall_names=(f"W{i}",)) for i in range(2)]
    barrier = threading.Barrier(2, timeout=10)
    orig = models_router._next_number

    def racy(db, model_id):
        n = orig(db, model_id)
        try:
            barrier.wait()  # ikkalasi ham bir xil raqamni "ko'rdi"
        except threading.BrokenBarrierError:
            pass
        return n

    monkeypatch.setattr(models_router, "_next_number", racy)
    results = {}

    def run(i):
        results[i] = upload(client, users["engineer"], mid, files[i], message=f"c{i}")

    ts = [threading.Thread(target=run, args=(i,)) for i in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=60)
    codes = sorted(r.status_code for r in results.values())
    assert codes == [201, 201], [r.text for r in results.values()]
    numbers = sorted(r.json()["number"] for r in results.values())
    assert numbers == [1, 2]


def test_retry_exhausted_gives_409(client, users, tmp_path, monkeypatch):
    mid = _model(client, users)
    f = make_ifc(tmp_path / "m.ifc")
    assert upload(client, users["engineer"], mid, f).status_code == 201
    monkeypatch.setattr(models_router, "_next_number", lambda db, model_id: 1)  # doim band raqam
    r = upload(client, users["engineer"], mid, make_ifc(tmp_path / "m2.ifc", wall_names=("B",)))
    assert r.status_code == 409


def test_one_open_command_per_sensor_enforced_by_db(client, users):
    pid = users["project_id"]
    r = client.post(
        f"/api/projects/{pid}/sensors",
        json={"key": "G.SP", "name": "Zatvor", "kind": "position", "unit": "%", "writable": True, "min_setpoint": 0, "max_setpoint": 100},
        headers=users["engineer"],
    )
    sid = r.json()["id"]
    with SessionLocal() as db:
        db.add(Command(project_id=pid, sensor_id=sid, value=1, created_by=users["ids"]["engineer"]))
        db.commit()
        db.add(Command(project_id=pid, sensor_id=sid, value=2, created_by=users["ids"]["engineer"]))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
        # yopilgan buyruqdan keyin yangisi mumkin
        c = db.query(Command).filter_by(sensor_id=sid).one()
        c.status = CommandStatus.acked
        db.commit()
        db.add(Command(project_id=pid, sensor_id=sid, value=3, created_by=users["ids"]["engineer"]))
        db.commit()
        assert db.query(Command).filter_by(sensor_id=sid).count() == 2
