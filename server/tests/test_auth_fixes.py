"""AUTH-01: logout dan keyin access token darhol yaroqsiz, change-password brute force hisoblagichi,
admin/tasdiqlovchi uchun parol ≥ 12; yangi xato (b): login sanash va vaqt farqi."""

import jwt
import pytest
from conftest import login, make_user
from ges_server.auth import router as auth_router
from ges_server.auth import sessions
from ges_server.config import get_settings


def _auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def settings():
    s = get_settings()
    saved = {k: getattr(s, k) for k in ("rate_login_per_min", "login_max_failures")}
    s.rate_login_per_min = 0
    yield s
    for k, v in saved.items():
        setattr(s, k, v)


def test_access_token_dies_with_session_on_logout(client, admin):
    make_user(client, admin, "lo1", "Kirish-2026-a")
    t = client.post("/api/auth/login", data={"username": "lo1", "password": "Kirish-2026-a"}).json()
    p = jwt.decode(t["access_token"], options={"verify_signature": False})
    assert isinstance(p["sn"], int)
    h = _auth(t["access_token"])
    assert client.get("/api/auth/me", headers=h).status_code == 200  # kesh to'ldi
    assert client.post("/api/auth/logout", headers=h).status_code == 204
    assert client.get("/api/auth/me", headers=h).status_code == 401  # ≤ 15 daqiqa emas — darhol


def test_revoking_other_session_kills_its_access_token(client, admin):
    make_user(client, admin, "two", "Kirish-2026-a")
    a = client.post("/api/auth/login", data={"username": "two", "password": "Kirish-2026-a"}).json()
    b = client.post("/api/auth/login", data={"username": "two", "password": "Kirish-2026-a"}).json()
    assert client.get("/api/auth/me", headers=_auth(a["access_token"])).status_code == 200
    rows = client.get("/api/auth/sessions", headers=_auth(b["access_token"])).json()
    other = next(x for x in rows if not x["current"])
    assert client.delete(f"/api/auth/sessions/{other['id']}", headers=_auth(b["access_token"])).status_code == 204
    assert client.get("/api/auth/me", headers=_auth(a["access_token"])).status_code == 401
    assert client.get("/api/auth/me", headers=_auth(b["access_token"])).status_code == 200


def test_session_revoked_elsewhere_seen_after_cache_ttl(client, admin, monkeypatch):
    """Boshqa API jarayoni bekor qilgan sessiya (kesh bu jarayonda tozalanmagan) — kesh muddatidan keyin 401."""
    from datetime import datetime, timezone

    from ges_server.db import SessionLocal
    from ges_server.orm import UserSession

    make_user(client, admin, "ha1", "Kirish-2026-a")
    t = client.post("/api/auth/login", data={"username": "ha1", "password": "Kirish-2026-a"}).json()
    h = _auth(t["access_token"])
    assert client.get("/api/auth/me", headers=h).status_code == 200
    sn = jwt.decode(t["access_token"], options={"verify_signature": False})["sn"]
    with SessionLocal() as db:  # "boshqa jarayon": to'g'ridan-to'g'ri DB, kesh tozalanmaydi
        db.get(UserSession, sn).revoked_at = datetime.now(timezone.utc)
        db.info.pop("sessions.forget", None)
        db.commit()
    monkeypatch.setattr(sessions, "SESSION_CACHE_S", 0.0)
    sessions._ALIVE.clear()
    assert client.get("/api/auth/me", headers=h).status_code == 401


def test_change_password_bruteforce_locks_and_revokes(client, admin, settings):
    settings.login_max_failures = 5
    make_user(client, admin, "cp1", "Kirish-2026-a")
    h = login(client, "cp1", "Kirish-2026-a")
    codes = [
        client.post("/api/auth/change-password", json={"old_password": f"xato-{i}", "new_password": "Yangi-parol-2026"}, headers=h).status_code
        for i in range(5)
    ]
    assert codes == [400] * 5
    # chegara — sessiyalar bekor (o'g'irlangan token bilan terib topish to'xtaydi), hisob bloklangan
    assert client.get("/api/auth/me", headers=h).status_code == 401
    r = client.post("/api/auth/login", data={"username": "cp1", "password": "Kirish-2026-a"})
    assert r.status_code == 401
    acts = [a["action"] for a in client.get("/api/audit", params={"action": "auth."}, headers=admin).json()]
    assert "auth.account_locked" in acts and "auth.sessions_revoked" in acts


def test_privileged_password_min_12(client, admin, users):
    # admin hisob yaratishda
    r = client.post("/api/users", json={"username": "adm2", "password": "Qisqa-pw1", "is_admin": True}, headers=admin)
    assert r.status_code == 422 and "12" in r.json()["detail"]
    r = client.post("/api/users", json={"username": "adm2", "password": "Uzun-parol-2026", "is_admin": True, "must_change_password": False}, headers=admin)
    assert r.status_code == 201
    # tasdiqlovchi o'z parolini almashtirishda
    r = client.post("/api/auth/change-password", json={"old_password": "pass1234", "new_password": "Qisqa-pw1"}, headers=users["approver"])
    assert r.status_code == 422
    r = client.post("/api/auth/change-password", json={"old_password": "pass1234", "new_password": "Uzun-parol-2026"}, headers=users["approver"])
    assert r.status_code == 200
    # muhandis — umumiy siyosat (8)
    r = client.post("/api/auth/change-password", json={"old_password": "pass1234", "new_password": "Qisqa-pw1"}, headers=users["engineer"])
    assert r.status_code == 200
    # admin tasdiqlovchi parolini qayta o'rnatganda ham
    r = client.patch(f"/api/users/{users['ids']['approver']}", json={"password": "Qisqa-pw2"}, headers=admin)
    assert r.status_code == 422


def test_unknown_user_same_response_and_hash_verified(client, admin, settings, monkeypatch):
    make_user(client, admin, "real", "Kirish-2026-a")
    calls = []
    orig = auth_router.verify_password

    def spy(pw, h):
        calls.append(h)
        return orig(pw, h)

    monkeypatch.setattr(auth_router, "verify_password", spy)
    a = client.post("/api/auth/login", data={"username": "real", "password": "xato"})
    b = client.post("/api/auth/login", data={"username": "yoq_odam", "password": "xato"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()
    assert len(calls) == 2 and calls[1] == auth_router._dummy_hash()  # noma'lum loginda ham Argon2
