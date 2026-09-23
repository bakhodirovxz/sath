"""SCADA-01: ruxsatlarga asoslangan RBAC — loyihalash rollari buyruq bermaydi, sensor.configure alohida."""

import pytest
from conftest import add_member, send_command
from ges_server.auth import deps
from ges_server.orm import Role


@pytest.fixture
def gate(client, users):
    r = client.post(
        f"/api/projects/{users['project_id']}/sensors",
        json={"key": "GATE1.SP", "name": "Zatvor 1", "kind": "position", "unit": "%", "writable": True,
              "min_setpoint": 0, "max_setpoint": 100},
        headers=users["engineer"],
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_permission_sets_do_not_overlap():
    cmd = {deps.P_SCADA_COMMAND, deps.P_SCADA_COMMAND_APPROVE, deps.P_SCADA_INTERLOCK_OVERRIDE}
    for role in (Role.viewer, Role.engineer, Role.approver):
        assert not (deps.role_permissions(role) & cmd), role
    for role in (Role.operator, Role.shift_supervisor, Role.viewer):
        assert deps.P_SENSOR_CONFIGURE not in deps.role_permissions(role)
        assert deps.P_MODEL_WRITE not in deps.role_permissions(role)
    assert deps.P_SCADA_COMMAND_APPROVE in deps.role_permissions(Role.shift_supervisor)
    assert deps.P_SCADA_COMMAND_APPROVE not in deps.role_permissions(Role.operator)
    # eski ierarxiya: smena boshlig'i dispetcherni qoplaydi, muhandisni emas
    assert deps.has_role(Role.shift_supervisor, Role.operator)
    assert not deps.has_role(Role.shift_supervisor, Role.engineer)
    assert not deps.has_role(Role.engineer, Role.shift_supervisor)
    assert deps.has_role(Role.approver, Role.engineer)


def test_engineer_and_approver_cannot_command(client, users, admin, gate):
    pid = users["project_id"]
    for who in ("engineer", "approver", "viewer", "admin"):
        hdr = users[who]
        r = client.post(f"/api/projects/{pid}/commands/select", json={"sensor_id": gate["id"], "value": 10}, headers=hdr)
        assert r.status_code == 403, (who, r.text)
        r = client.post(f"/api/projects/{pid}/commands/execute", json={"select_token": "x.y"}, headers=hdr)
        assert r.status_code == 403, (who, r.text)
    op = add_member(client, admin, pid, "op1", "operator")
    sup = add_member(client, admin, pid, "sup1", "shift_supervisor")
    assert send_command(client, op, pid, gate["id"], 10).status_code == 201
    cid = client.get(f"/api/projects/{pid}/commands", headers=op).json()[0]["id"]
    # cancel — faqat buyruq huquqi bilan
    assert client.post(f"/api/commands/{cid}/cancel", headers=users["engineer"]).status_code == 403
    assert client.post(f"/api/commands/{cid}/cancel", headers=sup).status_code == 200
    assert send_command(client, sup, pid, gate["id"], 12).status_code == 201


def test_dual_approval_only_shift_supervisor(client, users, admin, gate):
    pid = users["project_id"]
    client.patch(f"/api/sensors/{gate['id']}", json={"requires_dual_approval": True}, headers=users["engineer"])
    op = add_member(client, admin, pid, "op1", "operator")
    op2 = add_member(client, admin, pid, "op2", "operator")
    sup = add_member(client, admin, pid, "sup1", "shift_supervisor")
    r = send_command(client, op, pid, gate["id"], 20)
    assert r.status_code == 201 and r.json()["status"] == "pending_approval"
    cid = r.json()["id"]
    for hdr in (op2, users["engineer"], users["approver"], users["admin"]):
        assert client.post(f"/api/commands/{cid}/approve", headers=hdr).status_code == 403
    # tasdiq so'rovi bildirishnomasi faqat smena boshlig'iga
    assert any("Tasdiq kutilmoqda" in n["title"] for n in client.get("/api/notifications", headers=sup).json())
    assert not any("Tasdiq kutilmoqda" in n["title"] for n in client.get("/api/notifications", headers=op2).json())
    r = client.post(f"/api/commands/{cid}/approve", headers=sup)
    assert r.status_code == 200 and r.json()["status"] == "pending"


def test_interlock_override_only_shift_supervisor(client, users, admin, gate):
    pid = users["project_id"]
    r = client.post(
        f"/api/projects/{pid}/interlocks",
        json={"sensor_id": gate["id"], "name": "Doim yopiq", "condition": "value < 0"},
        headers=users["engineer"],
    )
    assert r.status_code == 201, r.text
    op = add_member(client, admin, pid, "op1", "operator")
    sup = add_member(client, admin, pid, "sup1", "shift_supervisor")
    q = {"override": "true", "override_reason": "sinov sababi"}
    body = {"sensor_id": gate["id"], "value": 10}
    assert client.post(f"/api/projects/{pid}/commands/select", json=body, params=q, headers=op).status_code == 403
    r = client.post(f"/api/projects/{pid}/commands/select", json=body, params=q, headers=sup)
    assert r.status_code == 200 and r.json()["override"] is True


def test_sensor_configure_is_separate_and_audited(client, users, admin, gate):
    pid = users["project_id"]
    sup = add_member(client, admin, pid, "sup1", "shift_supervisor")
    # dispetcher/smena boshlig'i nuqtani sozlay olmaydi
    assert client.patch(f"/api/sensors/{gate['id']}", json={"address": {"register": 99}}, headers=sup).status_code == 403
    assert client.post(
        f"/api/projects/{pid}/interlocks", json={"sensor_id": gate["id"], "name": "x", "condition": "value > 0"}, headers=sup
    ).status_code == 403
    r = client.patch(f"/api/sensors/{gate['id']}", json={"address": {"register": 11}, "max_setpoint": 90}, headers=users["engineer"])
    assert r.status_code == 200, r.text
    logs = client.get("/api/audit", headers=users["approver"], params={"project_id": pid}).json()
    conf = [a for a in logs if a["action"] == "sensor.configure"]
    assert conf, [a["action"] for a in logs]
    changes = conf[0]["detail"]["changes"]
    assert changes["address"]["new"] == {"register": 11} and changes["max_setpoint"] == {"old": 100, "new": 90}


def test_sensor_import_keeps_control_config(client, users, gate):
    pid = users["project_id"]
    csv = "key;name;protocol;address\nGATE1.SP;Zatvor 1;modbus;12\n"
    r = client.post(f"/api/projects/{pid}/sensors/import", json={"csv": csv}, headers=users["engineer"])
    assert r.status_code == 200 and r.json()["updated"] == 1, r.text
    s = next(x for x in client.get(f"/api/projects/{pid}/sensors", headers=users["viewer"]).json() if x["key"] == "GATE1.SP")
    assert s["writable"] is True and s["max_setpoint"] == 100 and s["address"] == {"register": "12"}
