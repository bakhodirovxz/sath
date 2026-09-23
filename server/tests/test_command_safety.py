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


@pytest.fixture(autouse=True)
def _op(client, admin, users):
    """SCADA-01: buyruqlar dispetcher nomidan (muhandis buyruq bera olmaydi)."""
    from conftest import add_member

    users["op"] = add_member(client, admin, users["project_id"], "opr", "operator")


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
    return send_command(client, hdr or users["op"], users["project_id"], sid, value, "t")


def _key(client, users):
    return client.get(f"/api/projects/{users['project_id']}/keys/command", headers=users["approver"]).json()["key"]


def test_out_of_range_and_non_finite_rejected(client, users, gate):
    assert gate["min_setpoint"] == 0 and gate["max_setpoint"] == 100 and gate["command_ttl_s"] == 60
    r = _cmd(client, users, gate["id"], 150)
    assert r.status_code == 422 and "maksimum" in r.json()["detail"]
    r = _cmd(client, users, gate["id"], -5)
    assert r.status_code == 422 and "minimum" in r.json()["detail"]
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
    assert r.status_code == 422 and "tezligi" in r.json()["detail"]
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
    got = client.post(f"/api/projects/{users['project_id']}/commands/claim", headers={"X-Command-Key": key}).json()
    assert got == []
    cmds = client.get(f"/api/projects/{users['project_id']}/commands", headers=users["viewer"]).json()
    assert cmds[0]["id"] == cid and cmds[0]["status"] == "expired"
    # sensor bo'sh — yangi buyruq mumkin
    assert _cmd(client, users, gate["id"], 31).status_code == 201
    # eskirgan buyruqqa ack — 409
    r = client.post(f"/api/commands/{cid}/ack", json={"status": "acked"}, headers={"X-Command-Key": key})
    assert r.status_code == 409


def test_watchdog_frees_sensor_stuck_in_sent(client, users, gate, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "command_sent_timeout_s", 30)
    cid = _cmd(client, users, gate["id"], 40).json()["id"]
    key = _key(client, users)
    got = client.post(f"/api/projects/{users['project_id']}/commands/claim", headers={"X-Command-Key": key}).json()
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
    # SCADA-03: failed emas — bajarilgani noma'lum (unknown) + dispetcherlarga alarm
    assert me["status"] == "unknown" and "watchdog" in me["result"]
    assert _cmd(client, users, gate["id"], 41).status_code == 201  # blok ochildi
    n = client.get("/api/notifications", headers=users["op"]).json()
    assert any(x["kind"] == "alarm" and "noma'lum" in x["title"] for x in n)
    acts = [a["action"] for a in client.get("/api/audit", headers=users["approver"], params={"project_id": users["project_id"]}).json()]
    assert "command.unknown" in acts and "command.expired" not in acts
    # kechikkan gateway natijasi noma'lum holatni aniqlaydi
    r = client.post(f"/api/commands/{cid}/ack", json={"status": "acked", "result": "kech"}, headers={"X-Command-Key": key})
    assert r.status_code == 200 and r.json()["status"] == "acked"


def test_writable_sensor_requires_finite_ordered_range(client, users):
    """SCADA-02: writable nuqta — min/max_setpoint majburiy, chekli, min <= max (create va update)."""
    pid = users["project_id"]
    url = f"/api/projects/{pid}/sensors"
    base = {"name": "Zatvor 2", "kind": "position", "unit": "%", "writable": True}
    assert client.post(url, json={**base, "key": "G2.SP"}, headers=users["engineer"]).status_code == 422
    assert client.post(url, json={**base, "key": "G2.SP", "min_setpoint": 0}, headers=users["engineer"]).status_code == 422
    r = client.post(url, json={**base, "key": "G2.SP", "min_setpoint": 10, "max_setpoint": 5}, headers=users["engineer"])
    assert r.status_code == 422 and "katta" in r.text
    for bad in ("Infinity", "NaN"):
        r = client.post(
            url, content=f'{{"key": "G2.SP", "name": "x", "writable": true, "min_setpoint": 0, "max_setpoint": {bad}}}',
            headers={**users["engineer"], "Content-Type": "application/json"},
        )
        assert r.status_code == 422, (bad, r.text)
    r = client.post(url, json={**base, "key": "G2.SP", "min_setpoint": 0, "max_setpoint": 100}, headers=users["engineer"])
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    # update: diapazonni olib tashlash yoki teskari qilish — 422, sensor o'zgarmaydi
    assert client.patch(f"/api/sensors/{sid}", json={"clear_setpoint_range": True}, headers=users["engineer"]).status_code == 422
    assert client.patch(f"/api/sensors/{sid}", json={"min_setpoint": 200}, headers=users["engineer"]).status_code == 422
    s = next(x for x in client.get(url, headers=users["viewer"]).json() if x["id"] == sid)
    assert s["min_setpoint"] == 0 and s["max_setpoint"] == 100
    # read-only nuqta: diapazonsiz ham mumkin; writable ga o'tkazish — diapazon bilan
    r = client.post(url, json={"key": "G3.SP", "name": "x"}, headers=users["engineer"])
    assert client.patch(f"/api/sensors/{r.json()['id']}", json={"writable": True}, headers=users["engineer"]).status_code == 422


def test_legacy_writable_without_range_cannot_be_commanded(client, users, gate):
    with SessionLocal() as db:
        from ges_server.orm import Sensor

        s = db.get(Sensor, gate["id"])
        s.min_setpoint = s.max_setpoint = None
        db.commit()
    r = _cmd(client, users, gate["id"], 10)
    assert r.status_code == 422 and "diapazon" in r.json()["detail"]


def _status(cid):
    with SessionLocal() as db:
        return db.get(Command, cid).status


def test_state_machine_rejects_invalid_transitions(client, users, gate):
    """SCADA-03: ack faqat sent/unknown dan; yakuniy holatdan o'tish yo'q — 409."""
    assert not control.can_transition(CommandStatus.pending, CommandStatus.acked)
    assert not control.can_transition(CommandStatus.failed, CommandStatus.acked)
    assert not control.can_transition(CommandStatus.mismatch, CommandStatus.acked)
    assert control.can_transition(CommandStatus.unknown, CommandStatus.acked)
    key = _key(client, users)
    hk = {"X-Command-Key": key}
    cid = _cmd(client, users, gate["id"], 30).json()["id"]
    # pending → acked/failed (gateway olmagan) — 409
    for st in ("acked", "failed", "sent"):
        assert client.post(f"/api/commands/{cid}/ack", json={"status": st}, headers=hk).status_code == 409
    assert _status(cid) == CommandStatus.pending
    client.post(f"/api/projects/{users['project_id']}/commands/claim", headers=hk)
    assert client.post(f"/api/commands/{cid}/ack", json={"status": "failed", "result": "x"}, headers=hk).status_code == 200
    # failed yakuniy: acked/readback — 409
    assert client.post(f"/api/commands/{cid}/ack", json={"status": "acked"}, headers=hk).status_code == 409
    assert client.post(f"/api/commands/{cid}/readback", json={"value": 30}, headers=hk).status_code == 409
    assert client.post(f"/api/commands/{cid}/cancel", headers=users["op"]).status_code == 409
    assert _status(cid) == CommandStatus.failed
    # mismatch yakuniy
    cid2 = _cmd(client, users, gate["id"], 31).json()["id"]
    client.post(f"/api/projects/{users['project_id']}/commands/claim", headers=hk)
    assert client.post(f"/api/commands/{cid2}/readback", json={"value": 99}, headers=hk).json()["status"] == "mismatch"
    assert client.post(f"/api/commands/{cid2}/ack", json={"status": "acked"}, headers=hk).status_code == 409
    assert _status(cid2) == CommandStatus.mismatch


def test_default_ttl_60s_and_two_minute_old_pending_not_dispatched(client, users):
    """SCADA-03 qabul: default TTL 60 s; 2 daqiqa eski pending gateway ga berilmaydi."""
    pid = users["project_id"]
    r = client.post(
        f"/api/projects/{pid}/sensors",
        json={"key": "G9.SP", "name": "Zatvor 9", "writable": True, "min_setpoint": 0, "max_setpoint": 100},
        headers=users["engineer"],
    )
    assert r.json()["command_ttl_s"] == 60
    cid = _cmd(client, users, r.json()["id"], 10).json()["id"]
    with SessionLocal() as db:
        c = db.get(Command, cid)
        assert 50 <= (control._aware(c.expires_at) - utcnow()).total_seconds() <= 61
        c.created_at = utcnow() - timedelta(minutes=2)
        c.expires_at = c.created_at + timedelta(seconds=60)
        db.commit()
    assert client.post(f"/api/projects/{pid}/commands/claim", headers={"X-Command-Key": _key(client, users)}).json() == []
    assert _status(cid) == CommandStatus.expired


def test_pending_approval_expires(client, users, gate, monkeypatch):
    """SCADA-03: tasdiq kutish muddati — sensorni abadiy band qilmaydi; muddati o'tgach approve — 409."""
    from conftest import add_member

    monkeypatch.setattr(config.get_settings(), "command_approval_ttl_s", 120)
    client.patch(f"/api/sensors/{gate['id']}", json={"requires_dual_approval": True}, headers=users["engineer"])
    sup = add_member(client, users["admin"], users["project_id"], "sup", "shift_supervisor")
    r = _cmd(client, users, gate["id"], 20)
    assert r.json()["status"] == "pending_approval" and r.json()["expires_at"] is not None
    cid = r.json()["id"]
    with SessionLocal() as db:
        c = db.get(Command, cid)
        assert 100 <= (control._aware(c.expires_at) - utcnow()).total_seconds() <= 121
        c.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert client.post(f"/api/commands/{cid}/approve", headers=sup).status_code == 409
    assert _status(cid) == CommandStatus.expired
    assert _cmd(client, users, gate["id"], 21).status_code == 201  # sensor bo'sh


def test_address_change_while_pending_blocks_dispatch(client, users, gate):
    """SCADA-03: manzil snapshoti — pending paytida sensor manzili o'zgarsa buyruq gateway ga berilmaydi."""
    key = _key(client, users)
    cid = _cmd(client, users, gate["id"], 30).json()["id"]
    r = client.patch(f"/api/sensors/{gate['id']}", json={"address": {"register": 99}}, headers=users["engineer"])
    assert r.status_code == 200
    got = client.post(f"/api/projects/{users['project_id']}/commands/claim", headers={"X-Command-Key": key}).json()
    assert got == [] and _status(cid) == CommandStatus.cancelled
    # o'zgarmagan manzil — snapshot beriladi
    cid2 = _cmd(client, users, gate["id"], 31).json()["id"]
    got = client.post(f"/api/projects/{users['project_id']}/commands/claim", headers={"X-Command-Key": key}).json()
    assert [(g["id"], g["address"], g["protocol"]) for g in got] == [(cid2, {"register": 99}, "modbus")]


def _dual(client, users, gate):
    from conftest import add_member

    client.patch(f"/api/sensors/{gate['id']}", json={"requires_dual_approval": True}, headers=users["engineer"])
    sup = add_member(client, users["admin"], users["project_id"], "sup", "shift_supervisor")
    r = _cmd(client, users, gate["id"], 20)
    assert r.json()["status"] == "pending_approval"
    return sup, r.json()["id"]


def test_approve_rechecks_interlocks(client, users, gate):
    """Yangi xato: approve blokirovkani qayta tekshirmas edi — endi execute dan keyin paydo bo'lgan
    blokirovka tasdiqni 409 bilan rad etadi, buyruq tasdiq kutishda qoladi."""
    sup, cid = _dual(client, users, gate)
    r = client.post(
        f"/api/projects/{users['project_id']}/interlocks",
        json={"sensor_id": gate["id"], "name": "Taqiq", "condition": "value < 0", "message": "sinov taqiqi"},
        headers=users["engineer"],
    )
    assert r.status_code == 201
    il = r.json()["id"]
    r = client.post(f"/api/commands/{cid}/approve", headers=sup)
    assert r.status_code == 409 and "sinov taqiqi" in r.json()["detail"]
    assert _status(cid) == CommandStatus.pending_approval
    client.patch(f"/api/interlocks/{il}", json={"enabled": False}, headers=users["engineer"])
    assert client.post(f"/api/commands/{cid}/approve", headers=sup).status_code == 200


def test_approve_rechecks_range_and_loto(client, users, gate):
    sup, cid = _dual(client, users, gate)
    # diapazon toraytirildi — 20 endi ruxsat etilmagan
    assert client.patch(f"/api/sensors/{gate['id']}", json={"max_setpoint": 10}, headers=users["engineer"]).status_code == 200
    r = client.post(f"/api/commands/{cid}/approve", headers=sup)
    assert r.status_code == 409 and "maksimum" in r.json()["detail"]
    client.patch(f"/api/sensors/{gate['id']}", json={"max_setpoint": 100}, headers=users["engineer"])
    # LOTO — chetlab o'tilmaydi
    from ges_server.monitoring import cmms

    orig = cmms.loto_blocks
    cmms.loto_blocks = lambda db, s: ["LOTO faol: sinov"]
    try:
        r = client.post(f"/api/commands/{cid}/approve", headers=sup)
        assert r.status_code == 409 and "LOTO" in r.json()["detail"]
    finally:
        cmms.loto_blocks = orig
    assert client.post(f"/api/commands/{cid}/approve", headers=sup).status_code == 200


def test_claim_rechecks_interlocks(client, users, gate):
    """Tasdiq/execute dan keyin paydo bo'lgan blokirovka — gateway ga berilmaydi (cancelled + alarm)."""
    key = _key(client, users)
    cid = _cmd(client, users, gate["id"], 30).json()["id"]
    client.post(
        f"/api/projects/{users['project_id']}/interlocks",
        json={"sensor_id": gate["id"], "name": "Taqiq", "condition": "value < 0", "message": "sinov taqiqi"},
        headers=users["engineer"],
    )
    got = client.post(f"/api/projects/{users['project_id']}/commands/claim", headers={"X-Command-Key": key}).json()
    assert got == [] and _status(cid) == CommandStatus.cancelled
    n = client.get("/api/notifications", headers=users["op"]).json()
    assert any(x["kind"] == "alarm" and "bekor qilindi" in x["title"] for x in n)
