"""B2: select-before-operate, ikki kishi tasdig'i, readback."""

from datetime import timedelta

import pytest
from conftest import add_member, login, make_user, send_command
from ges_server.db import SessionLocal
from ges_server.monitoring import control
from ges_server.orm import Command, CommandStatus, utcnow


@pytest.fixture
def operator(client, admin, users):
    uid = make_user(client, admin, "operator")
    client.put(
        f"/api/projects/{users['project_id']}/members",
        json={"user_id": uid, "role": "operator"},
        headers=admin,
    )
    return login(client, "operator", "pass1234")


@pytest.fixture
def gate(client, users):
    r = client.post(
        f"/api/projects/{users['project_id']}/sensors",
        json={"key": "GATE1.SP", "name": "Zatvor 1", "kind": "position", "unit": "%", "writable": True, "min_setpoint": 0, "max_setpoint": 100},
        headers=users["engineer"],
    )
    return r.json()


def _key(client, users):
    return client.get(f"/api/projects/{users['project_id']}/keys/command", headers=users["approver"]).json()["key"]


def test_execute_requires_valid_token(client, users, operator, gate):
    pid = users["project_id"]
    # tokensiz / soxta token
    r = client.post(f"/api/projects/{pid}/commands/execute", json={"select_token": "abc.def"}, headers=operator)
    assert r.status_code == 400
    sel = client.post(
        f"/api/projects/{pid}/commands/select", json={"sensor_id": gate["id"], "value": 40}, headers=operator
    )
    assert sel.status_code == 200, sel.text
    tok = sel.json()["select_token"]
    assert sel.json()["requires_approval"] is False
    # imzo buzilgan
    bad = tok[:-4] + ("aaaa" if not tok.endswith("aaaa") else "bbbb")
    assert client.post(f"/api/projects/{pid}/commands/execute", json={"select_token": bad}, headers=operator).status_code == 400
    # boshqa foydalanuvchi tokeni — 403
    assert client.post(f"/api/projects/{pid}/commands/execute", json={"select_token": tok}, headers=users["engineer"]).status_code == 403
    # muddati o'tgan — 409
    b64, sig = tok.split(".", 1)
    import base64
    import json

    body = json.loads(base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4)))
    body["e"] -= 100
    raw = json.dumps(body, separators=(",", ":")).encode()
    expired = base64.urlsafe_b64encode(raw).decode().rstrip("=") + "." + control._sign(raw)
    r = client.post(f"/api/projects/{pid}/commands/execute", json={"select_token": expired}, headers=operator)
    assert r.status_code == 409 and "muddati" in r.json()["detail"]
    # to'g'ri token → 201, qiymat tokendagi (so'rov tanasida qiymat yo'q)
    r = client.post(f"/api/projects/{pid}/commands/execute", json={"select_token": tok, "note": "ok"}, headers=operator)
    assert r.status_code == 201 and r.json()["value"] == 40 and r.json()["status"] == "pending"
    acts = [a["action"] for a in client.get("/api/audit", headers=users["approver"], params={"project_id": pid}).json()]
    assert "command.select" in acts and "command.create" in acts


def test_dual_approval_author_cannot_approve(client, users, operator, gate):
    pid = users["project_id"]
    client.patch(f"/api/sensors/{gate['id']}", json={"requires_dual_approval": True}, headers=users["engineer"])
    sup = add_member(client, users["admin"], pid, "sup", "shift_supervisor")
    r = send_command(client, operator, pid, gate["id"], 55, "ikki kishi")
    assert r.status_code == 201 and r.json()["status"] == "pending_approval" and r.json()["expires_at"] is None
    cid = r.json()["id"]
    key = _key(client, users)
    # gateway ga berilmaydi
    assert client.post(f"/api/projects/{pid}/commands/claim", headers={"X-Command-Key": key}).json() == []
    # muallif o'zini tasdiqlay olmaydi
    assert client.post(f"/api/commands/{cid}/approve", headers=operator).status_code == 403
    # ko'ruvchi — 403
    assert client.post(f"/api/commands/{cid}/approve", headers=users["viewer"]).status_code == 403
    # muhandis tasdiqlay olmaydi (SCADA-01); smena boshlig'i tasdiqlaydi → pending, TTL boshlanadi
    assert client.post(f"/api/commands/{cid}/approve", headers=users["engineer"]).status_code == 403
    r = client.post(f"/api/commands/{cid}/approve", headers=sup)
    assert r.status_code == 200 and r.json()["status"] == "pending"
    assert r.json()["approved_by_username"] == "sup" and r.json()["expires_at"] is not None
    assert client.post(f"/api/commands/{cid}/approve", headers=sup).status_code == 409
    got = client.post(f"/api/projects/{pid}/commands/claim", headers={"X-Command-Key": key}).json()
    assert [g["id"] for g in got] == [cid]
    # tasdiq kutayotganda ikkinchi buyruq — 409; bekor qilish mumkin
    r2 = send_command(client, operator, pid, gate["id"], 56)
    assert r2.status_code == 409
    n = client.get("/api/notifications", headers=sup).json()
    assert any("Tasdiq kutilmoqda" in x["title"] for x in n)


def test_readback_match_and_mismatch(client, users, operator, gate):
    pid = users["project_id"]
    client.patch(f"/api/sensors/{gate['id']}", json={"readback_tolerance": 0.02}, headers=users["engineer"])
    key = _key(client, users)
    cid = send_command(client, operator, pid, gate["id"], 50).json()["id"]
    client.post(f"/api/projects/{pid}/commands/claim", headers={"X-Command-Key": key})
    # readback sent holatida ham qabul qilinadi
    r = client.post(f"/api/commands/{cid}/readback", json={"value": 50.5}, headers={"X-Command-Key": key})
    assert r.status_code == 200 and r.json()["status"] == "acked" and r.json()["readback_value"] == 50.5
    # mismatch
    cid2 = send_command(client, operator, pid, gate["id"], 60).json()["id"]
    client.post(f"/api/projects/{pid}/commands/claim", headers={"X-Command-Key": key})
    client.post(f"/api/commands/{cid2}/ack", json={"status": "acked", "result": "yozildi"}, headers={"X-Command-Key": key})
    r = client.post(f"/api/commands/{cid2}/readback", json={"value": 30}, headers={"X-Command-Key": key})
    assert r.status_code == 200 and r.json()["status"] == "mismatch" and "≠" in r.json()["result"]
    n = client.get("/api/notifications", headers=operator).json()
    assert any("mos kelmadi" in x["title"] for x in n)
    acts = [a["action"] for a in client.get("/api/audit", headers=users["approver"], params={"project_id": pid}).json()]
    assert "command.mismatch" in acts and "command.readback" in acts
    # mismatch dan keyin sensor bo'sh (ochiq buyruq emas)
    assert send_command(client, operator, pid, gate["id"], 61).status_code == 201
    # NaN readback — 422; pending buyruqqa readback — 409
    assert client.post(f"/api/commands/{cid2}/readback", json={"value": "nan"}, headers={"X-Command-Key": key}).status_code == 422
    with SessionLocal() as db:
        c = db.query(Command).filter_by(value=61).one()
        assert c.status == CommandStatus.pending
        assert control._aware(c.expires_at) > utcnow() - timedelta(seconds=1)
    assert client.post(f"/api/commands/{c.id}/readback", json={"value": 61}, headers={"X-Command-Key": key}).status_code == 409
