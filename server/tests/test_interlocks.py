"""B4: blokirovkalar — shart bajarilmasa 409 (sabab bilan), bad/stale sensor → taqiq, chetlab o'tish."""

import pytest
from conftest import ingest_headers, login, make_user, send_command
from ges_server.monitoring import interlock


@pytest.fixture
def operator(client, admin, users):
    uid = make_user(client, admin, "operator")
    client.put(f"/api/projects/{users['project_id']}/members", json={"user_id": uid, "role": "operator"}, headers=admin)
    return login(client, "operator", "pass1234")


@pytest.fixture
def plant(client, users):
    pid = users["project_id"]
    mk = lambda **kw: client.post(f"/api/projects/{pid}/sensors", json=kw, headers=users["engineer"]).json()  # noqa: E731
    gate = mk(key="GATE1.SP", name="Zatvor 1", kind="position", unit="%", writable=True, min_setpoint=0, max_setpoint=100)
    run = mk(key="AGG1.RUN", name="Agregat 1 holati", kind="status", unit="")
    level = mk(key="RES.H", name="Sath", kind="level", unit="m")
    r = client.post(
        f"/api/projects/{pid}/interlocks",
        json={
            "sensor_id": gate["id"],
            "name": "Agregat to'xtagan va sath yetarli",
            "condition": "AGG1_RUN == 0 and RES_H > 890",
            "message": "agregat ishlayapti yoki sath 890 m dan past",
        },
        headers=users["engineer"],
    )
    assert r.status_code == 201, r.text
    return {"gate": gate, "run": run, "level": level, "il": r.json()}


def _push(client, users, items):
    r = client.post(f"/api/projects/{users['project_id']}/readings", json=items, headers=ingest_headers(client, users))
    assert r.status_code == 200, r.text


def test_var_name_and_validation():
    assert interlock.var_name("AGG1.P") == "AGG1_P" and interlock.var_name("1x") == "_1x"
    with pytest.raises(ValueError):
        interlock.validate("__import__('os')")
    interlock.validate("AGG1_RUN == 0 and value < 50")


def test_blocked_when_condition_false_and_allowed_when_true(client, users, operator, plant):
    pid = users["project_id"]
    _push(client, users, [{"key": "AGG1.RUN", "value": 1}, {"key": "RES.H", "value": 900}])
    r = send_command(client, operator, pid, plant["gate"]["id"], 30)
    assert r.status_code == 409 and "agregat ishlayapti" in r.json()["detail"]
    lst = client.get(f"/api/projects/{pid}/interlocks", headers=users["viewer"]).json()
    assert lst[0]["current_ok"] is False and lst[0]["sensor_key"] == "GATE1.SP"
    _push(client, users, [{"key": "AGG1.RUN", "value": 0}])
    sel = client.post(f"/api/projects/{pid}/commands/select", json={"sensor_id": plant["gate"]["id"], "value": 30}, headers=operator)
    assert sel.status_code == 200 and sel.json()["interlocks"][0]["ok"] is True
    r = send_command(client, operator, pid, plant["gate"]["id"], 30)
    assert r.status_code == 201


def test_bad_or_stale_sensor_blocks(client, users, operator, plant):
    pid = users["project_id"]
    _push(client, users, [{"key": "AGG1.RUN", "value": 0}, {"key": "RES.H", "value": 900, "quality": "bad"}])
    # RES.H faqat bad → last_value yo'q → baholab bo'lmaydi → taqiq
    r = send_command(client, operator, pid, plant["gate"]["id"], 30)
    assert r.status_code == 409 and "baholab bo'lmadi" in r.json()["detail"] and "RES_H" in r.json()["detail"]
    lst = client.get(f"/api/projects/{pid}/interlocks", headers=users["viewer"]).json()
    assert lst[0]["current_ok"] is None


def test_execute_reevaluates_after_select(client, users, operator, plant):
    pid = users["project_id"]
    _push(client, users, [{"key": "AGG1.RUN", "value": 0}, {"key": "RES.H", "value": 900}])
    sel = client.post(f"/api/projects/{pid}/commands/select", json={"sensor_id": plant["gate"]["id"], "value": 30}, headers=operator).json()
    _push(client, users, [{"key": "AGG1.RUN", "value": 1}])  # select va execute orasida holat o'zgardi
    r = client.post(f"/api/projects/{pid}/commands/execute", json={"select_token": sel["select_token"]}, headers=operator)
    assert r.status_code == 409 and "Blokirovka" in r.json()["detail"]


def test_override_only_shift_supervisor_with_reason_audit_and_alarm(client, users, operator, plant, admin):
    from conftest import add_member

    pid = users["project_id"]
    sup = add_member(client, admin, pid, "sup", "shift_supervisor")
    _push(client, users, [{"key": "AGG1.RUN", "value": 1}, {"key": "RES.H", "value": 900}])
    q = {"override": "true", "override_reason": "avariya: qo'lda boshqaruv"}
    body = {"sensor_id": plant["gate"]["id"], "value": 30}
    assert client.post(f"/api/projects/{pid}/commands/select", json=body, headers=operator, params=q).status_code == 403
    assert client.post(f"/api/projects/{pid}/commands/select", json=body, headers=users["approver"], params=q).status_code == 403
    assert client.post(f"/api/projects/{pid}/commands/select", json=body, headers=sup, params={"override": "true", "override_reason": "x"}).status_code == 400
    sel = client.post(f"/api/projects/{pid}/commands/select", json=body, headers=sup, params=q)
    assert sel.status_code == 200 and sel.json()["override"] is True and sel.json()["interlocks"][0]["ok"] is False
    r = client.post(f"/api/projects/{pid}/commands/execute", json={"select_token": sel.json()["select_token"]}, headers=sup)
    assert r.status_code == 201
    acts = [a for a in client.get("/api/audit", headers=admin, params={"project_id": pid}).json()]
    ov = [a for a in acts if a["action"] == "command.interlock_override"]
    assert ov and ov[0]["detail"]["reason"] == "avariya: qo'lda boshqaruv" and ov[0]["detail"]["blocked"]
    cr = next(a for a in acts if a["action"] == "command.create")
    assert cr["detail"]["interlock_override"] is True
    n = client.get("/api/notifications", headers=operator).json()
    assert any(x["kind"] == "alarm" and "chetlab o'tildi" in x["title"] for x in n)


def test_interlock_crud_and_validation(client, users, plant):
    pid = users["project_id"]
    bad = client.post(
        f"/api/projects/{pid}/interlocks",
        json={"sensor_id": plant["gate"]["id"], "name": "x", "condition": "__import__('os')"},
        headers=users["engineer"],
    )
    assert bad.status_code == 400
    nonwritable = client.post(
        f"/api/projects/{pid}/interlocks",
        json={"sensor_id": plant["level"]["id"], "name": "x", "condition": "1 == 1"},
        headers=users["engineer"],
    )
    assert nonwritable.status_code == 400
    assert client.post(f"/api/projects/{pid}/interlocks", json={"sensor_id": plant["gate"]["id"], "name": "x", "condition": "1"}, headers=users["viewer"]).status_code == 403
    vars_ = client.get(f"/api/projects/{pid}/interlocks/variables", headers=users["viewer"]).json()
    assert any(v["var"] == "AGG1_RUN" for v in vars_) and vars_[-1]["var"] == "value"
    il = plant["il"]["id"]
    r = client.patch(f"/api/interlocks/{il}", json={"enabled": False}, headers=users["engineer"])
    assert r.status_code == 200 and r.json()["enabled"] is False
    assert client.patch(f"/api/interlocks/{il}", json={"condition": "AGG1_RUN ==="}, headers=users["engineer"]).status_code == 400
    assert client.delete(f"/api/interlocks/{il}", headers=users["viewer"]).status_code == 403
    assert client.delete(f"/api/interlocks/{il}", headers=users["engineer"]).status_code == 204
    assert client.get(f"/api/projects/{pid}/interlocks", headers=users["viewer"]).json() == []
