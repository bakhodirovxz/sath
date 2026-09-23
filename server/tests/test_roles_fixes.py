"""AUTH-04: rol berish chegaralari, issue ijrochisi — loyiha a'zosi, ijrochi faqat holatni o'zgartiradi."""

import pytest
from conftest import login, make_user


@pytest.fixture
def model_id(client, users):
    r = client.post(f"/api/projects/{users['project_id']}/models", json={"name": "R"}, headers=users["engineer"])
    return r.json()["id"]


def _put(client, pid, uid, role, headers):
    return client.put(f"/api/projects/{pid}/members", json={"user_id": uid, "role": role}, headers=headers)


def test_only_admin_grants_or_revokes_approver(client, users, admin):
    pid = users["project_id"]
    out = users["ids"]["outsider"]
    ap = users["approver"]
    assert _put(client, pid, out, "approver", ap).status_code == 403  # approver approver bera olmaydi
    assert _put(client, pid, out, "engineer", ap).status_code == 200  # o'zidan past — mumkin
    assert _put(client, pid, out, "viewer", ap).status_code == 200
    # boshqa tasdiqlovchini pasaytirish / chiqarish — faqat admin
    uid = make_user(client, admin, "ap2")
    assert _put(client, pid, uid, "approver", admin).status_code == 200
    assert _put(client, pid, uid, "viewer", ap).status_code == 403
    assert client.delete(f"/api/projects/{pid}/members/{uid}", headers=ap).status_code == 403
    assert _put(client, pid, uid, "engineer", admin).status_code == 200
    assert client.delete(f"/api/projects/{pid}/members/{uid}", headers=ap).status_code == 204


def test_issue_assignee_must_be_member(client, users, model_id, admin):
    r = client.post(
        f"/api/models/{model_id}/issues", json={"title": "X", "assignee_id": users["ids"]["outsider"]}, headers=users["viewer"]
    )
    assert r.status_code == 400 and "a'zosi" in r.json()["detail"]
    r = client.post(f"/api/models/{model_id}/issues", json={"title": "X", "assignee_id": users["ids"]["engineer"]}, headers=users["viewer"])
    assert r.status_code == 201
    iid = r.json()["id"]
    r = client.patch(f"/api/issues/{iid}", json={"assignee_id": users["ids"]["outsider"]}, headers=users["viewer"])
    assert r.status_code == 400
    # admin — har loyihada (a'zo bo'lmasa ham) ijrochi bo'la oladi
    me = client.get("/api/auth/me", headers=admin).json()
    assert client.patch(f"/api/issues/{iid}", json={"assignee_id": me["id"]}, headers=users["viewer"]).status_code == 200


def test_assignee_can_only_change_status(client, users, model_id, admin):
    r = client.post(
        f"/api/models/{model_id}/issues",
        json={"title": "Asl", "assignee_id": users["ids"]["engineer"], "priority": "low"},
        headers=users["viewer"],
    )
    iid = r.json()["id"]
    eng = users["engineer"]
    for body in ({"assignee_id": users["ids"]["approver"]}, {"title": "boshqa"}, {"priority": "critical"}, {"viewpoint": {}}):
        assert client.patch(f"/api/issues/{iid}", json=body, headers=eng).status_code == 403, body
    assert client.patch(f"/api/issues/{iid}", json={"status": "in_progress"}, headers=eng).status_code == 200
    assert client.post(f"/api/issues/{iid}/comments", json={"body": "boshladim"}, headers=eng).status_code == 201
    # muallif va tasdiqlovchi — hamma maydon
    assert client.patch(f"/api/issues/{iid}", json={"title": "Yangi"}, headers=users["viewer"]).status_code == 200
    r = client.patch(f"/api/issues/{iid}", json={"priority": "high", "assignee_id": users["ids"]["approver"]}, headers=users["approver"])
    assert r.status_code == 200 and r.json()["assignee_username"] == "approver"
    # boshqa muhandis (muallif ham, ijrochi ham emas) — 403
    uid = make_user(client, admin, "eng3")
    _put(client, users["project_id"], uid, "engineer", admin)
    assert client.patch(f"/api/issues/{iid}", json={"status": "closed"}, headers=login(client, "eng3", "pass1234")).status_code == 403
