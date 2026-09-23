"""UX-12: "Mening vazifalarim" va loyiha vaqt chizig'i."""

import pytest
from conftest import send_command, upload


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
def model_id(client, users):
    r = client.post(f"/api/projects/{users['project_id']}/models", json={"name": "To'g'on"}, headers=users["engineer"])
    assert r.status_code == 201, r.text
    return r.json()["id"]


def tasks(client, headers):
    r = client.get("/api/me/tasks", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_review_and_issue_tasks(client, users, model_id, ifc_file):
    v1 = upload(client, users["engineer"], model_id, ifc_file, "v1").json()
    cr = client.post(
        f"/api/models/{model_id}/change-requests", json={"version_id": v1["id"], "title": "Tasdiqqa"}, headers=users["engineer"]
    ).json()
    # tasdiqlovchini kutadi; muallifning o'zida — yo'q; ko'ruvchida — yo'q
    t = tasks(client, users["approver"])
    assert [c["id"] for c in t["reviews"]] == [cr["id"]]
    assert t["reviews"][0]["model_name"] == "To'g'on" and t["reviews"][0]["version_number"] == 1
    assert tasks(client, users["engineer"])["reviews"] == []
    assert tasks(client, users["viewer"])["reviews"] == []
    # o'zgartirish so'raldi → tasdiqlovchidan ketadi, muallifda "o'z CR larim" ga tushadi
    r = client.post(f"/api/change-requests/{cr['id']}/reviews", json={"decision": "request_changes", "comment": "x"}, headers=users["approver"])
    assert r.status_code == 201, r.text
    assert tasks(client, users["approver"])["reviews"] == []
    assert [c["id"] for c in tasks(client, users["engineer"])["my_change_requests"]] == [cr["id"]]
    # menga biriktirilgan muammo
    iss = client.post(
        f"/api/models/{model_id}/issues",
        json={"title": "Devor", "assignee_id": users["ids"]["engineer"], "priority": "high"},
        headers=users["viewer"],
    ).json()
    t = tasks(client, users["engineer"])
    assert [i["id"] for i in t["issues"]] == [iss["id"]] and t["issues"][0]["priority"] == "high"
    assert t["total"] == 2
    client.patch(f"/api/issues/{iss['id']}", json={"status": "resolved"}, headers=users["engineer"])
    assert tasks(client, users["engineer"])["issues"] == []
    # begona foydalanuvchi — hech narsa
    assert tasks(client, users["outsider"])["total"] == 0


def test_work_order_and_command_approval_tasks(client, users, operator):
    pid = users["project_id"]
    wo = client.post(
        f"/api/projects/{pid}/work-orders",
        json={"title": "Podshipnik", "assignee_id": users["ids"]["engineer"], "priority": "high"},
        headers=operator,
    )
    assert wo.status_code == 201, wo.text
    assert [w["id"] for w in tasks(client, users["engineer"])["work_orders"]] == [wo.json()["id"]]
    gate = client.post(
        f"/api/projects/{pid}/sensors",
        json={"key": "GATE1.SP", "name": "Zatvor 1", "kind": "position", "unit": "%", "writable": True,
              "protocol": "modbus", "address": {"register": 10}, "min_setpoint": 0, "max_setpoint": 100},
        headers=users["engineer"],
    ).json()
    client.patch(f"/api/sensors/{gate['id']}", json={"requires_dual_approval": True}, headers=users["engineer"])
    r = send_command(client, operator, pid, gate["id"], 55, "ikki kishi")
    assert r.status_code == 201 and r.json()["status"] == "pending_approval", r.text
    cid = r.json()["id"]
    # muallif o'z buyrug'ini ko'rmaydi (tasdiqlay olmaydi)
    assert tasks(client, operator)["command_approvals"] == []
    assert tasks(client, users["viewer"])["command_approvals"] == []
    # ro'yxatdagi foydalanuvchi haqiqatan tasdiqlay oladi (ruxsatlar serverdagi qoidaga mos)
    who = [h for h in (users["engineer"], users["approver"], users["admin"]) if any(c["id"] == cid for c in tasks(client, h)["command_approvals"])]
    assert who, "tasdiqlay oladigan hech kim ro'yxatda yo'q"
    item = next(c for c in tasks(client, who[0])["command_approvals"] if c["id"] == cid)
    assert item["sensor_key"] == "GATE1.SP" and item["value"] == 55 and item["unit"] == "%"
    assert client.post(f"/api/commands/{cid}/approve", headers=who[0]).status_code == 200
    assert tasks(client, who[0])["command_approvals"] == []


def test_timeline(client, users, model_id, ifc_file, operator):
    pid = users["project_id"]
    v1 = upload(client, users["engineer"], model_id, ifc_file, "birinchi").json()
    cr = client.post(
        f"/api/models/{model_id}/change-requests", json={"version_id": v1["id"], "title": "Nashr"}, headers=users["engineer"]
    ).json()
    client.post(f"/api/change-requests/{cr['id']}/reviews", json={"decision": "approve"}, headers=users["approver"])
    r = client.post(f"/api/change-requests/{cr['id']}/merge", headers=users["approver"])
    assert r.status_code == 200, r.text
    client.post(f"/api/projects/{pid}/work-orders", json={"title": "Ko'rik"}, headers=operator)
    r = client.get(f"/api/projects/{pid}/history", headers=users["viewer"])
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    kinds = [i["kind"] for i in items]
    assert {"version", "cr", "publish", "work_order"} <= set(kinds)
    ts = [i["ts"] for i in items]
    assert ts == sorted(ts, reverse=True)  # eng yangisi birinchi
    pub = next(i for i in items if i["kind"] == "publish")
    assert pub["version_id"] == v1["id"] and "nashr" in pub["title"]
    ver = next(i for i in items if i["kind"] == "version")
    assert ver["detail"] == "birinchi" and ver["model_id"] == model_id
    # limit va ruxsat
    assert len(client.get(f"/api/projects/{pid}/history", params={"limit": 2}, headers=users["viewer"]).json()["items"]) == 2
    assert client.get(f"/api/projects/{pid}/history", headers=users["outsider"]).status_code == 403
    assert client.get("/api/projects/9999/history", headers=users["viewer"]).status_code == 404
