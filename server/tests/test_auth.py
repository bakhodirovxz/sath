from conftest import login, make_user


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_admin_seeded_and_login(client, admin):
    r = client.get("/api/auth/me", headers=admin)
    assert r.status_code == 200
    assert r.json()["username"] == "admin"
    assert r.json()["is_admin"] is True


def test_wrong_password(client):
    r = client.post("/api/auth/login", data={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_no_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_non_admin_cannot_manage_users(client, admin):
    make_user(client, admin, "bob")
    bob = login(client, "bob", "pass1234")
    assert client.get("/api/users", headers=bob).status_code == 403
    r = client.post("/api/users", json={"username": "x", "password": "yyyy"}, headers=bob)
    assert r.status_code == 403


def test_duplicate_username(client, admin):
    make_user(client, admin, "bob")
    r = client.post("/api/users", json={"username": "bob", "password": "yyyy"}, headers=admin)
    assert r.status_code == 409


def test_deactivated_user_cannot_login(client, admin):
    uid = make_user(client, admin, "bob")
    bob = login(client, "bob", "pass1234")
    r = client.patch(f"/api/users/{uid}", json={"is_active": False}, headers=admin)
    assert r.status_code == 200
    # eski token ham ishlamaydi
    assert client.get("/api/auth/me", headers=bob).status_code == 401
    r = client.post("/api/auth/login", data={"username": "bob", "password": "pass1234"})
    assert r.status_code == 401


def test_change_password(client, admin):
    make_user(client, admin, "bob")
    bob = login(client, "bob", "pass1234")
    r = client.post(
        "/api/auth/change-password",
        json={"old_password": "wrong", "new_password": "newpass"},
        headers=bob,
    )
    assert r.status_code == 400
    r = client.post(
        "/api/auth/change-password",
        json={"old_password": "pass1234", "new_password": "newpass"},
        headers=bob,
    )
    assert r.status_code == 204
    login(client, "bob", "newpass")


def test_admin_cannot_demote_self(client, admin):
    me = client.get("/api/auth/me", headers=admin).json()
    r = client.patch(f"/api/users/{me['id']}", json={"is_admin": False}, headers=admin)
    assert r.status_code == 400
