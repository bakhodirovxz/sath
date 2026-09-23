"""L2: sessiya boshqaruvi — qisqa access token + refresh aylanishi, bekor qilish, token versiyasi,
parol siyosati, majburiy parol almashtirish, WS chipta va qayta avtorizatsiya, iss/aud."""

import jwt
import pytest
from conftest import make_user
from ges_server.auth import security
from ges_server.auth.router import REFRESH_COOKIE
from ges_server.config import get_settings


def _login(c, username, password, **extra):
    r = c.post("/api/auth/login", data={"username": username, "password": password, **extra})
    assert r.status_code == 200, r.text
    return r


def _auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def _fresh_user(client, admin, name="sess", pw="Kirish-2026-a"):
    """Yaratilgan foydalanuvchi must_change_password=True — avval parolni almashtirib, oddiy holatga keltiramiz."""
    make_user(client, admin, name, pw, must_change_password=True)
    r = _login(client, name, pw)
    r2 = client.post("/api/auth/change-password", json={"old_password": pw, "new_password": pw + "x"}, headers=_auth(r.json()["access_token"]))
    assert r2.status_code == 200, r2.text
    return name, pw + "x", r2.json()


def test_login_returns_pair_and_cookie(client):
    r = _login(client, "admin", "admin123")
    j = r.json()
    assert j["access_token"] and j["refresh_token"] and j["expires_in"] == get_settings().access_token_minutes * 60
    assert REFRESH_COOKIE in r.cookies
    p = jwt.decode(j["access_token"], options={"verify_signature": False})
    assert p["iss"] == security.ISSUER and p["aud"] == security.AUDIENCE and p["scope"] == "session" and "jti" in p and "sid" in p


def test_token_without_iss_aud_rejected(client):
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    bad = jwt.encode({"sub": "1", "iat": now, "exp": now + timedelta(minutes=5), "scope": "session", "ver": 0}, get_settings().secret_key, algorithm="HS256")
    assert client.get("/api/auth/me", headers=_auth(bad)).status_code == 401
    other = jwt.encode({"sub": "1", "iss": "boshqa", "aud": security.AUDIENCE, "iat": now, "exp": now + timedelta(minutes=5), "scope": "session", "ver": 0}, get_settings().secret_key, algorithm="HS256")
    assert client.get("/api/auth/me", headers=_auth(other)).status_code == 401


def test_old_token_invalid_after_password_change(client, admin):
    """Qabul mezoni: parol o'zgargandan keyin eski token ishlamaydi."""
    name, pw, _ = _fresh_user(client, admin)
    a = _login(client, name, pw).json()
    b = _login(client, name, pw).json()  # ikkinchi qurilma
    assert client.get("/api/auth/me", headers=_auth(a["access_token"])).status_code == 200
    r = client.post("/api/auth/change-password", json={"old_password": pw, "new_password": "Yangi-parol-77"}, headers=_auth(a["access_token"]))
    assert r.status_code == 200
    new = r.json()
    assert client.get("/api/auth/me", headers=_auth(a["access_token"])).status_code == 401
    assert client.get("/api/auth/me", headers=_auth(b["access_token"])).status_code == 401
    assert client.post("/api/auth/refresh", json={"refresh_token": b["refresh_token"]}).status_code == 401
    assert client.get("/api/auth/me", headers=_auth(new["access_token"])).status_code == 200


def test_refresh_rotation_and_reuse_detection(client, admin):
    name, pw, _ = _fresh_user(client, admin, "rot")
    first = _login(client, name, pw).json()
    r = client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert r.status_code == 200
    second = r.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert client.get("/api/auth/me", headers=_auth(second["access_token"])).status_code == 200
    # eski (aylantirilgan) refresh token takrori → o'g'irlangan belgisi: hamma sessiya bekor
    assert client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]}).status_code == 401
    assert client.post("/api/auth/refresh", json={"refresh_token": second["refresh_token"]}).status_code == 401
    assert client.get("/api/auth/me", headers=_auth(second["access_token"])).status_code == 401
    r = client.get("/api/audit", params={"action": "auth.session_reuse"}, headers=admin)
    assert any(e["action"] == "auth.session_reuse" for e in r.json())


def test_refresh_via_cookie(client):
    r = _login(client, "admin", "admin123")
    r2 = client.post("/api/auth/refresh", json={})  # TestClient cookie ni saqlaydi
    assert r2.status_code == 200 and r2.json()["access_token"] != r.json()["access_token"]


def test_logout_revokes_session(client, admin):
    name, pw, _ = _fresh_user(client, admin, "logout1")
    t = _login(client, name, pw).json()
    assert client.post("/api/auth/logout", headers=_auth(t["access_token"])).status_code == 204
    assert client.post("/api/auth/refresh", json={"refresh_token": t["refresh_token"]}).status_code == 401


def test_sessions_list_and_revoke_and_logout_all(client, admin):
    name, pw, _ = _fresh_user(client, admin, "multi")
    a = _login(client, name, pw, client="desktop").json()
    b = _login(client, name, pw).json()
    r = client.get("/api/auth/sessions", headers=_auth(b["access_token"]))
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 3 and sum(x["current"] for x in rows) == 1  # _fresh_user parol almashtirganda ham sessiya ochilgan
    other = next(x for x in rows if not x["current"])
    assert other["client"] == "desktop"
    assert client.delete(f"/api/auth/sessions/{other['id']}", headers=_auth(b["access_token"])).status_code == 204
    assert client.post("/api/auth/refresh", json={"refresh_token": a["refresh_token"]}).status_code == 401
    # AUTH-01: sessiya bekor qilinsa uning access tokeni ham darhol yaroqsiz (ilgari ≤ 15 daqiqa ishlardi)
    assert client.get("/api/auth/me", headers=_auth(a["access_token"])).status_code == 401
    assert client.post("/api/auth/logout-all", headers=_auth(b["access_token"])).status_code == 204
    assert client.get("/api/auth/me", headers=_auth(a["access_token"])).status_code == 401
    assert client.get("/api/auth/me", headers=_auth(b["access_token"])).status_code == 401


def test_role_change_and_deactivation_invalidate_tokens(client, users, admin):
    pid = users["project_id"]
    vid = users["ids"]["viewer"]
    # rol ko'tarilishi sessiyani buzmaydi; pasaytirilishi — barcha tokenlar bekor
    r = client.put(f"/api/projects/{pid}/members", json={"user_id": vid, "role": "operator"}, headers=admin)
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=users["viewer"]).status_code == 200
    eng = users["ids"]["engineer"]
    r = client.put(f"/api/projects/{pid}/members", json={"user_id": eng, "role": "viewer"}, headers=admin)
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=users["engineer"]).status_code == 401
    # o'chirish (is_active=false)
    r = client.put(f"/api/projects/{pid}/members", json={"user_id": vid, "role": "viewer"}, headers=admin)  # pasaytirish
    assert client.get("/api/auth/me", headers=users["viewer"]).status_code == 401
    vh = {"Authorization": f"Bearer {_login(client, 'viewer', 'pass1234').json()['access_token']}"}
    assert client.patch(f"/api/users/{vid}", json={"is_active": False}, headers=admin).status_code == 200
    assert client.get("/api/auth/me", headers=vh).status_code == 401
    # a'zolikdan chiqarish
    assert client.get("/api/auth/me", headers=users["approver"]).status_code == 200
    assert client.delete(f"/api/projects/{pid}/members/{users['ids']['approver']}", headers=admin).status_code == 204
    assert client.get("/api/auth/me", headers=users["approver"]).status_code == 401


@pytest.mark.parametrize(
    "pw,ok",
    [("pass1234", True), ("Kirish-2026-a", True), ("short1", False), ("12345678", False), ("abcdefgh", False), ("password1", False), ("aaaaaaa1", False), ("bob12345", False)],
)
def test_password_policy(pw, ok):
    problems = security.password_problems(pw, "bob")
    assert (not problems) == ok, problems


def test_password_policy_enforced_on_change_and_create(client, admin):
    r = client.post("/api/users", json={"username": "weak", "password": "12345678"}, headers=admin)
    assert r.status_code == 422 and "Parol talabga" in r.json()["detail"]
    name, pw, tok = _fresh_user(client, admin, "pol")
    r = client.post("/api/auth/change-password", json={"old_password": pw, "new_password": "password1"}, headers=_auth(tok["access_token"]))
    assert r.status_code == 422
    r = client.post("/api/auth/change-password", json={"old_password": pw, "new_password": pw}, headers=_auth(tok["access_token"]))
    assert r.status_code == 422  # eskisi bilan bir xil


def test_must_change_password_gate(client, admin):
    make_user(client, admin, "newbie", "Fresh-pw-1", must_change_password=True)
    t = _login(client, "newbie", "Fresh-pw-1").json()
    assert t["must_change_password"] is True
    h = _auth(t["access_token"])
    assert client.get("/api/auth/me", headers=h).json()["must_change_password"] is True
    r = client.get("/api/projects", headers=h)
    assert r.status_code == 403 and r.headers.get("X-Password-Change-Required") == "1"
    r = client.post("/api/auth/change-password", json={"old_password": "Fresh-pw-1", "new_password": "Fresh-pw-2"}, headers=h)
    assert r.status_code == 200 and r.json()["must_change_password"] is False
    assert client.get("/api/projects", headers=_auth(r.json()["access_token"])).status_code == 200
    # admin parolni qayta o'rnatsa — yana majburiy
    uid = next(u["id"] for u in client.get("/api/users", headers=admin).json() if u["username"] == "newbie")
    assert client.patch(f"/api/users/{uid}", json={"password": "Reset-pw-99"}, headers=admin).status_code == 200
    assert client.get("/api/projects", headers=_auth(r.json()["access_token"])).status_code == 401  # sessiyalar bekor
    t2 = _login(client, "newbie", "Reset-pw-99").json()
    assert t2["must_change_password"] is True


def test_ws_ticket_and_reauth(client, users, admin):
    pid = users["project_id"]
    # sessiya tokeni bilan WS ochilmaydi — faqat chipta
    with pytest.raises(Exception):  # noqa: B017 — WebSocketDisconnect yoki ulanish rad
        with client.websocket_connect(f"/api/projects/{pid}/live?ticket={users['viewer']['Authorization'][7:]}"):
            pass
    with pytest.raises(Exception):  # noqa: B017 — WebSocketDisconnect yoki ulanish rad
        with client.websocket_connect(f"/api/projects/{pid}/live?token={users['viewer']['Authorization'][7:]}"):
            pass
    ticket = client.post("/api/auth/ws-ticket", headers=users["viewer"]).json()["ticket"]
    p = jwt.decode(ticket, options={"verify_signature": False})
    assert p["scope"] == "ws" and p["exp"] - p["iat"] <= 60
    settings = get_settings()
    old = settings.ws_reauth_s
    settings.ws_reauth_s = 0  # har siklda qayta tekshiruv
    try:
        with client.websocket_connect(f"/api/projects/{pid}/live?ticket={ticket}") as ws:
            snap = ws.receive_json()
            assert snap["type"] == "snapshot"
            # a'zolikdan chiqarilgach keyingi xabarda 4401 bilan yopiladi
            assert client.delete(f"/api/projects/{pid}/members/{users['ids']['viewer']}", headers=admin).status_code == 204
            ws.send_text("x")
            with pytest.raises(Exception):  # noqa: B017 — WebSocketDisconnect yoki ulanish rad
                for _ in range(3):
                    ws.receive_json()
    finally:
        settings.ws_reauth_s = old
