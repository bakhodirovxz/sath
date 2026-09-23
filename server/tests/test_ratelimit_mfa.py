"""L1: tezlik cheklovi, hisobni bloklash (lockout), TOTP MFA."""

import pytest
from conftest import login, make_user
from ges_server import ratelimit
from ges_server.auth import totp
from ges_server.config import get_settings


@pytest.fixture
def settings():
    s = get_settings()
    saved = {k: getattr(s, k) for k in ("rate_login_per_min", "rate_ingest_per_min", "rate_commands_per_min", "rate_sim_per_min", "login_max_failures", "login_lockout_minutes", "mfa_required_for_admins")}
    yield s
    for k, v in saved.items():
        setattr(s, k, v)


def test_limiter_sliding_window():
    lim = ratelimit.RateLimiter()
    t = 1000.0
    for _ in range(3):
        assert lim.hit("k", 3, 60, now=t) is None
    ra = lim.hit("k", 3, 60, now=t + 10)
    assert ra == pytest.approx(50.0)
    # oyna o'tgach yana ruxsat
    assert lim.hit("k", 3, 60, now=t + 61) is None
    assert lim.hit("other", 3, 60, now=t + 10) is None
    assert lim.hit("k", 0, 60, now=t + 10) is None  # 0 — o'chirilgan


def test_account_lockout_after_failures(client, admin, settings):
    """Qabul mezoni: 20 ta noto'g'ri urinish → hisob bloklanadi; to'g'ri parol ham kirmaydi. Yangi xato (b):
    bloklangan hisob javobi noma'lum login bilan bir xil (401, bir xil matn) — login sanab bo'lmaydi."""
    settings.rate_login_per_min = 0  # IP cheklovi aralashmasin — hisob bloklashning o'zi sinaladi
    settings.login_max_failures = 10
    make_user(client, admin, "victim", "correct-pw-1")
    codes = [client.post("/api/auth/login", data={"username": "victim", "password": "wrong"}).status_code for _ in range(20)]
    assert codes == [401] * 20
    r = client.post("/api/auth/login", data={"username": "victim", "password": "correct-pw-1"})
    unknown = client.post("/api/auth/login", data={"username": "yoq-odam", "password": "correct-pw-1"})
    assert r.status_code == unknown.status_code == 401, r.text
    assert r.json() == unknown.json() and "Retry-After" not in r.headers
    # audit: bloklash hodisasi yozilgan
    r = client.get("/api/audit", params={"action": "auth.account_locked"}, headers=admin)
    assert r.status_code == 200 and any(e["action"] == "auth.account_locked" for e in r.json())
    # admin blokni ochadi
    uid = next(u["id"] for u in client.get("/api/users", headers=admin).json() if u["username"] == "victim")
    r = client.patch(f"/api/users/{uid}", json={"unlock": True}, headers=admin)
    assert r.status_code == 200 and r.json()["locked_until"] is None
    assert client.post("/api/auth/login", data={"username": "victim", "password": "correct-pw-1"}).status_code == 200


def test_successful_login_resets_counter(client, admin, settings):
    settings.rate_login_per_min = 0
    settings.login_max_failures = 3
    make_user(client, admin, "user1", "pw-u1-ok")
    for _ in range(2):
        client.post("/api/auth/login", data={"username": "user1", "password": "x"})
    assert client.post("/api/auth/login", data={"username": "user1", "password": "pw-u1-ok"}).status_code == 200
    for _ in range(2):
        client.post("/api/auth/login", data={"username": "user1", "password": "x"})
    # hisoblagich tiklangani uchun hali bloklanmagan
    assert client.post("/api/auth/login", data={"username": "user1", "password": "pw-u1-ok"}).status_code == 200


def test_login_ip_rate_limit(client, settings):
    """IP bo'yicha login cheklovi — noma'lum login uchun ham (Argon2 CPU sarfi)."""
    settings.rate_login_per_min = 5
    codes = [client.post("/api/auth/login", data={"username": "nobody", "password": "x"}).status_code for _ in range(7)]
    assert codes[:5] == [401] * 5 and codes[5:] == [429, 429]
    r = client.post("/api/auth/login", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1


def test_ingest_rate_limit(client, users, settings):
    pid = users["project_id"]
    settings.rate_ingest_per_min = 3
    r = client.post(f"/api/projects/{pid}/sensors", json={"key": "T1", "name": "T", "kind": "value"}, headers=users["engineer"])
    assert r.status_code == 201
    codes = [client.post(f"/api/projects/{pid}/readings", json=[{"key": "T1", "value": 1.0}], headers=users["engineer"]).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    # boshqa loyiha — alohida hisob
    r = client.post("/api/projects", json={"name": "Ikkinchi"}, headers=users["admin"])
    p2 = r.json()["id"]
    assert client.post(f"/api/projects/{p2}/readings", json=[], headers=users["admin"]).status_code == 200


def test_commands_and_sim_rate_limit(client, users, settings):
    pid = users["project_id"]
    settings.rate_commands_per_min = 2
    settings.rate_sim_per_min = 1
    r = client.post(
        f"/api/projects/{pid}/sensors",
        json={"key": "SP1", "name": "Setpoint", "kind": "value", "writable": True, "min_setpoint": 0, "max_setpoint": 100},
        headers=users["engineer"],
    )
    assert r.status_code == 201
    sid = r.json()["id"]
    body = {"sensor_id": sid, "value": 10}
    codes = [client.post(f"/api/projects/{pid}/commands/select", json=body, headers=users["engineer"]).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_totp_rfc6238_vector():
    # RFC 6238 Annex B (SHA1, kalit "12345678901234567890"), T=59 → 94287082 (8 raqam); 6 raqamli — oxirgi 6
    import base64

    secret = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
    assert totp.totp(secret, t=59) == "287082"
    assert totp.totp(secret, t=1111111109) == "081804"
    assert totp.verify(secret, "287082", t=59) == 1
    assert totp.verify(secret, "287082", t=59, last_counter=1) is None  # takror
    assert totp.verify(secret, "000000", t=59) is None
    assert totp.verify(secret, "28708", t=59) is None


def test_mfa_flow(client, admin, settings, monkeypatch):
    settings.rate_login_per_min = 0
    # Soxta soat: har qadamda 30 s oldinga — TOTP hisoblagichi o'sadi (takror himoyasi bilan to'qnashmaydi)
    clock = {"t": 1_800_000_000.0}
    monkeypatch.setattr(totp.time, "time", lambda: clock["t"])
    step = lambda: clock.__setitem__("t", clock["t"] + totp.STEP_S)  # noqa: E731
    make_user(client, admin, "mfa", "pw-secret-ok1")
    h = login(client, "mfa", "pw-secret-ok1")
    assert client.post("/api/auth/mfa/enable", json={"code": "123456"}, headers=h).status_code == 400
    r = client.post("/api/auth/mfa/setup", headers=h)
    assert r.status_code == 200
    secret = r.json()["secret"]
    assert r.json()["otpauth_url"].startswith("otpauth://totp/Sath:mfa?secret=")
    assert client.post("/api/auth/mfa/enable", json={"code": "000000"}, headers=h).status_code == 400
    code = totp.totp(secret)
    assert client.post("/api/auth/mfa/enable", json={"code": code}, headers=h).status_code == 204
    assert client.get("/api/auth/me", headers=h).json()["mfa_enabled"] is True
    # kodsiz login — 401 + X-MFA-Required; noto'g'ri kod — 401; ishlatilgan kod — 401 (takror); yangi kod — 200
    r = client.post("/api/auth/login", data={"username": "mfa", "password": "pw-secret-ok1"})
    assert r.status_code == 401 and r.headers.get("X-MFA-Required") == "1"
    r = client.post("/api/auth/login", data={"username": "mfa", "password": "pw-secret-ok1", "otp": "000000"})
    assert r.status_code == 401
    r = client.post("/api/auth/login", data={"username": "mfa", "password": "pw-secret-ok1", "otp": code})
    assert r.status_code == 401
    step()
    r = client.post("/api/auth/login", data={"username": "mfa", "password": "pw-secret-ok1", "otp": totp.totp(secret)})
    assert r.status_code == 200, r.text
    h2 = {"Authorization": f"Bearer {r.json()['access_token']}"}
    # o'chirish — parol + kod
    step()
    code3 = totp.totp(secret)
    r = client.post("/api/auth/mfa/disable", json={"password": "wrong", "code": code3}, headers=h2)
    assert r.status_code == 400
    r = client.post("/api/auth/mfa/disable", json={"password": "pw-secret-ok1", "code": code3}, headers=h2)
    assert r.status_code == 204
    assert client.post("/api/auth/login", data={"username": "mfa", "password": "pw-secret-ok1"}).status_code == 200


def test_admin_mfa_required(client, admin, settings):
    settings.mfa_required_for_admins = True
    me = client.get("/api/auth/me", headers=admin).json()
    assert me["mfa_required"] is True
    r = client.get("/api/users", headers=admin)
    assert r.status_code == 403 and "MFA" in r.json()["detail"]
    r = client.post("/api/auth/mfa/setup", headers=admin)
    assert r.status_code == 200
    assert client.post("/api/auth/mfa/enable", json={"code": totp.totp(r.json()["secret"])}, headers=admin).status_code == 204
    assert client.get("/api/users", headers=admin).status_code == 200
    assert client.get("/api/auth/me", headers=admin).json()["mfa_required"] is False


def test_admin_mfa_reset(client, admin, settings):
    settings.rate_login_per_min = 0
    uid = make_user(client, admin, "lost", "pw-secret-ok2")
    h = login(client, "lost", "pw-secret-ok2")
    secret = client.post("/api/auth/mfa/setup", headers=h).json()["secret"]
    assert client.post("/api/auth/mfa/enable", json={"code": totp.totp(secret)}, headers=h).status_code == 204
    assert client.post("/api/auth/login", data={"username": "lost", "password": "pw-secret-ok2"}).status_code == 401
    r = client.patch(f"/api/users/{uid}", json={"mfa_reset": True}, headers=admin)
    assert r.status_code == 200 and r.json()["mfa_enabled"] is False
    assert client.post("/api/auth/login", data={"username": "lost", "password": "pw-secret-ok2"}).status_code == 200
