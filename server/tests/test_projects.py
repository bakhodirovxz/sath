def test_only_admin_creates_project(client, users):
    r = client.post("/api/projects", json={"name": "New"}, headers=users["approver"])
    assert r.status_code == 403
    r = client.post("/api/projects", json={"name": "New"}, headers=users["admin"])
    assert r.status_code == 201


def test_duplicate_project_name(client, users):
    r = client.post("/api/projects", json={"name": "Test GES"}, headers=users["admin"])
    assert r.status_code == 409


def test_list_projects_by_membership(client, users):
    pid = users["project_id"]
    for role in ("viewer", "engineer", "approver"):
        r = client.get("/api/projects", headers=users[role])
        assert [p["id"] for p in r.json()] == [pid]
        assert r.json()[0]["my_role"] == role
    assert client.get("/api/projects", headers=users["outsider"]).json() == []
    # admin hammasini ko'radi, roli approver
    r = client.get("/api/projects", headers=users["admin"])
    assert r.json()[0]["my_role"] == "approver"


def test_outsider_cannot_see_project(client, users):
    pid = users["project_id"]
    assert client.get(f"/api/projects/{pid}", headers=users["outsider"]).status_code == 403
    assert client.get(f"/api/projects/{pid}/members", headers=users["outsider"]).status_code == 403


def test_update_project_requires_approver(client, users):
    pid = users["project_id"]
    r = client.patch(f"/api/projects/{pid}", json={"location": "X"}, headers=users["engineer"])
    assert r.status_code == 403
    r = client.patch(f"/api/projects/{pid}", json={"location": "X"}, headers=users["approver"])
    assert r.status_code == 200
    assert r.json()["location"] == "X"


def test_member_management(client, users):
    pid = users["project_id"]
    outsider = users["ids"]["outsider"]
    # muhandis a'zo qo'sha olmaydi
    r = client.put(
        f"/api/projects/{pid}/members",
        json={"user_id": outsider, "role": "viewer"},
        headers=users["engineer"],
    )
    assert r.status_code == 403
    # approver qo'shadi
    r = client.put(
        f"/api/projects/{pid}/members",
        json={"user_id": outsider, "role": "viewer"},
        headers=users["approver"],
    )
    assert r.status_code == 200
    assert client.get(f"/api/projects/{pid}", headers=users["outsider"]).status_code == 200
    # rolni o'zgartirish
    r = client.put(
        f"/api/projects/{pid}/members",
        json={"user_id": outsider, "role": "engineer"},
        headers=users["approver"],
    )
    assert r.json()["role"] == "engineer"
    members = client.get(f"/api/projects/{pid}/members", headers=users["viewer"]).json()
    assert {m["username"]: m["role"] for m in members}["outsider"] == "engineer"
    # o'chirish
    r = client.delete(f"/api/projects/{pid}/members/{outsider}", headers=users["approver"])
    assert r.status_code == 204
    assert client.get(f"/api/projects/{pid}", headers=users["outsider"]).status_code == 403


def test_delete_project_admin_only(client, users):
    pid = users["project_id"]
    assert client.delete(f"/api/projects/{pid}", headers=users["approver"]).status_code == 403
    assert client.delete(f"/api/projects/{pid}", headers=users["admin"]).status_code == 204
    assert client.get(f"/api/projects/{pid}", headers=users["admin"]).status_code == 404
