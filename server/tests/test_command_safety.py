"""B1: buyruq xavfsizlik konverti — diapazon, tezlik, NaN, parallel 409, TTL, watchdog."""

import threading
from datetime import timedelta

import pytest
from conftest import send_command
from ges_server import config
from ges_server.db import SessionLocal
from ges_server.monitoring import control
from ges_server.orm import Command, CommandStatus, utcnow


@pytest.fixture
def operator(client, admin, users):
    from conftest import login, make_user

    uid = make_user(client, admin, "operator")
    client.put(
        f"/api/projects/{users['project_id']}/members",
        json={"user_id": uid, "role": "operator"},
        headers=users["approver"],
    )
    return login(client, "operator", "pass1234")


@pytest.fixture
def gate(client, users):
    r = client.post(
        f"/api/projects/{users['project_id']}/sensors",
        json={
            "key": "GATE1.SP",
            "name": "Zatvor 1",
            "kind": "position",
            "unit": "%",
            "writable": True,
            "protocol": "modbus",
            "address": {"register": 10},
            "min_setpoint": 0,
            "max_setpoint": 100,
            "max_rate_per_min": 20,
            "command_ttl_s": 60,
        },
        headers=users["engineer"],
    )
    assert r.status_code == 201, r.text
    return r.json()


def _cmd(client, users, sid, value, hdr=None):
    return send_command(client, hdr or users["engineer"], users["project_id"], sid, value, "t")


def _key(client, users):
    return client.get(f"/api/projects/{users['project_id']}/ingest-key", headers=users["approver"]).json()["ingest_key"]


def test_out_of_range_and_non_finite_rejected(client, users, gate):
    assert gate["min_setpoint"] == 0 and gate["max_setpoint"] == 100 and gate["command_ttl_s"] == 60
    r = _cmd(client, users, gate["id"], 150)
    assert r.status_code == 400 and "maksimum" in r.json()["detail"]
    r = _cmd(client, users, gate["id"], -5)
    assert r.status_code == 400 and "minimum" in r.json()["detail"]
    for bad in ("nan", "inf", "1e400"):
        assert _cmd(client, users, gate["id"], bad).status_code == 422
    r = _cmd(client, users, gate["id"], 50)
    assert r.status_code == 201 and r.json()["expires_at"] is not None


def test_rate_limit_against_last_command(client, users, gate):
    assert _cmd(client, users, gate["id"], 10).status_code == 201
    with SessionLocal() as db:
        c = db.query(Command).one()
        c.status = CommandStatus.acked
        db.commit()
    # 1 daqiqada 20 %/min → 10 → 50 (40 birlik) rad, 10 → 25 ruxsat
    r = _cmd(client, users, gate["id"], 50)
    assert r.status_code == 400 and "tezligi" in r.json()["detail"]
    assert _cmd(client, users, gate["id"], 25).status_code == 201


def test_parallel_commands_one_gets_409(client, users, gate, monkeypatch):
    barrier = threading.Barrier(2, timeout=10)
    orig = control.check_envelope

    def slow(db, s, value):
        orig(db, s, value)
        try:
            barrier.wait()  # ikkalasi ham "ochiq buyruq yo'q" tekshiruvidan oldin to'xtaydi
        except threading.BrokenBarrierError:
            pass

    monkeypatch.setattr(control, "check_envelope", slow)
    codes = []

    def run(v):
        codes.append(_cmd(client, users, gate["id"], v).status_code)

    ts = [threading.Thread(target=run, args=(v,)) for v in (10, 12)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=60)
    assert sorted(codes) == [201, 409], codes


def test_expired_pending_not_given_to_gateway(client, users, gate):
    r = _cmd(client, users, gate["id"], 30)
    cid = r.json()["id"]
    with SessionLocal() as db:
        c = db.get(Command, cid)
        c.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    key = _key(client, users)
    got = client.post(f"/api/projects/{users['project_id']}/commands/claim", headers={"X-Ingest-Key": key}).json()
    assert got == []
    cmds = client.get(f"/api/projects/{users['project_id']}/commands", headers=users["viewer"]).json()
    assert cmds[0]["id"] == cid and cmds[0]["status"] == "expired"
    # sensor bo'sh — yangi buyruq mumkin
    assert _cmd(client, users, gate["id"], 31).status_code == 201
    # eskirgan buyruqqa ack — 409
    r = client.post(f"/api/commands/{cid}/ack", json={"status": "acked"}, headers={"X-Ingest-Key": key})
    assert r.status_code == 409


def test_watchdog_frees_sensor_stuck_in_sent(client, users, gate, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "command_sent_timeout_s", 30)
    cid = _cmd(client, users, gate["id"], 40).json()["id"]
    key = _key(client, users)
    got = client.post(f"/api/projects/{users['project_id']}/commands/claim", headers={"X-Ingest-Key": key}).json()
    assert len(got) == 1
    # yangi buyruq — sensor band (sent)
    assert _cmd(client, users, gate["id"], 41).status_code == 409
    with SessionLocal() as db:
        c = db.get(Command, cid)
        assert c.status == CommandStatus.sent and c.sent_at is not None
        c.sent_at = utcnow() - timedelta(seconds=31)
        db.commit()
        assert control.tick(db) == 1
    cmds = client.get(f"/api/projects/{users['project_id']}/commands", headers=users["viewer"]).json()
    me = next(x for x in cmds if x["id"] == cid)
    assert me["status"] == "failed" and "watchdog" in me["result"]
    assert _cmd(client, users, gate["id"], 41).status_code == 201  # blok ochildi
    # muallif bildirishnoma oldi
    n = client.get("/api/notifications", headers=users["engineer"]).json()
    assert any("bajarilmadi" in x["title"] for x in n)
    # audit
    acts = [a["action"] for a in client.get("/api/audit", headers=users["approver"], params={"project_id": users["project_id"]}).json()]
    assert "command.failed" in acts and "command.expired" not in acts
