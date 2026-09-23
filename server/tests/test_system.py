import pytest
from conftest import upload
from ges_server import notify


@pytest.fixture
def mail(monkeypatch):
    """SMTP o'rniga xabarlarni ro'yxatga yig'amiz."""
    sent: list[tuple[list[str], str, str]] = []
    monkeypatch.setattr(
        notify, "send_async", lambda to, subject, body: sent.append((to, subject, body))
    )
    return sent


def test_notifications_on_review_flow(client, users, ifc_file, mail):
    pid = users["project_id"]
    # email lar
    for name in ("engineer", "approver"):
        client.patch(
            f"/api/users/{users['ids'][name]}",
            json={"email": f"{name}@x.uz"},
            headers=users["admin"],
        )
    r = client.post(f"/api/projects/{pid}/models", json={"name": "M"}, headers=users["engineer"])
    mid = r.json()["id"]
    v = upload(client, users["engineer"], mid, ifc_file, "v1").json()
    cr = client.post(
        f"/api/models/{mid}/change-requests",
        json={"version_id": v["id"], "title": "Tasdiqlang", "description": "Iltimos"},
        headers=users["engineer"],
    ).json()
    # tasdiqlovchiga xabar (muallif emas)
    assert (
        mail[-1][0] == ["approver@x.uz"]
        and "Tasdiqlash so'rovi" in mail[-1][1]
        and "Iltimos" in mail[-1][2]
    )
    client.post(
        f"/api/change-requests/{cr['id']}/reviews",
        json={"decision": "approve", "comment": "OK"},
        headers=users["approver"],
    )
    assert mail[-1][0] == ["engineer@x.uz"] and "ma'qulladi" in mail[-1][1]
    client.post(f"/api/change-requests/{cr['id']}/merge", headers=users["approver"])
    assert "Tasdiqlandi" in mail[-1][1] and "engineer@x.uz" in mail[-1][0]


def test_notify_silent_without_smtp(monkeypatch):
    from ges_server import config

    monkeypatch.setattr(config.get_settings(), "smtp_url", None)
    notify.send_async(["a@b"], "x", "y")  # xato bermaydi, hech narsa yubormaydi


def test_user_email_field(client, admin):
    r = client.post(
        "/api/users",
        json={"username": "mailer", "password": "pass1234", "email": "m@x.uz"},
        headers=admin,
    )
    assert r.status_code == 201 and r.json()["email"] == "m@x.uz"


def test_desktop_package_flow(client, users, admin, tmp_path):
    assert client.get("/api/desktop/latest", headers=users["viewer"]).status_code == 404
    # noto'g'ri nom
    r = client.post(
        "/api/desktop/upload", files={"file": ("x.zip", b"zip", "application/zip")}, headers=admin
    )
    assert r.status_code == 400
    # admin emas
    r = client.post(
        "/api/desktop/upload",
        files={"file": ("Sath-Desktop-0.1.0.zip", b"zip", "application/zip")},
        headers=users["approver"],
    )
    assert r.status_code == 403
    for ver in ("0.1.0", "0.2.3", "0.2.10"):
        r = client.post(
            "/api/desktop/upload",
            files={
                "file": (f"Sath-Desktop-{ver}.zip", b"zipdata" + ver.encode(), "application/zip")
            },
            headers=admin,
        )
        assert r.status_code == 201, r.text
    latest = client.get("/api/desktop/latest", headers=users["viewer"]).json()
    assert latest["version"] == "0.2.10"  # semantik taqqoslash (0.2.10 > 0.2.3)
    assert latest["kind"] == "zip" and len(latest["files"]) == 1
    r = client.get(latest["url"], headers=users["viewer"])
    assert r.status_code == 200 and r.content == b"zipdata0.2.10"
    # Fork build nomlari: installer afzal, zip qo'shimcha; installer + zip bir versiyada
    for name, body in (
        ("Sath-0.3.0-Windows-x86_64.zip", b"z3"),
        ("Sath-0.3.0-Windows-x86_64-installer.exe", b"exe3"),
    ):
        r = client.post(
            "/api/desktop/upload",
            files={"file": (name, body, "application/octet-stream")},
            headers=admin,
        )
        assert r.status_code == 201, r.text
    latest = client.get("/api/desktop/latest", headers=users["viewer"]).json()
    assert latest["version"] == "0.3.0" and latest["kind"] == "installer"
    assert [f["kind"] for f in latest["files"]] == ["installer", "zip"]
    r = client.get(latest["url"], headers=users["viewer"])
    assert r.status_code == 200 and r.content == b"exe3"
    assert r.headers["content-type"].startswith("application/vnd.microsoft.portable-executable")
    # nom regex bilan tekshiriladi
    r = client.get("/api/desktop/download/Sath-Desktop-9.9.9.zip", headers=users["viewer"])
    assert r.status_code == 404
    r = client.get("/api/desktop/download/boshqa.zip", headers=users["viewer"])
    assert r.status_code == 400


def test_desktop_download_with_query_token(client, users, admin):
    client.post(
        "/api/desktop/upload",
        files={"file": ("Sath-Desktop-1.0.0.zip", b"zip1", "application/zip")},
        headers=admin,
    )
    # sessiya tokeni URL da ishlamaydi — faqat maxsus yuklab olish tokeni
    session_token = users["viewer"]["Authorization"].split(" ", 1)[1]
    assert (
        client.get(
            f"/api/desktop/download/Sath-Desktop-1.0.0.zip?token={session_token}"
        ).status_code
        == 401
    )
    token = client.post("/api/desktop/download-token", headers=users["viewer"]).json()["token"]
    r = client.get(f"/api/desktop/download/Sath-Desktop-1.0.0.zip?token={token}")
    assert r.status_code == 200 and r.content == b"zip1"
    # yuklab olish tokeni oddiy API ga yaramaydi
    assert (
        client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    )
    assert (
        client.get("/api/desktop/download/Sath-Desktop-1.0.0.zip?token=bad").status_code == 401
    )
    assert client.get("/api/desktop/download/Sath-Desktop-1.0.0.zip").status_code == 401


def test_spa_fallback_does_not_shadow_api(tmp_path, monkeypatch):
    """Web build bo'lganda: noma'lum sahifa → index.html (keshsiz), /api/... noma'lum → 404 JSON,
    dist dan tashqariga chiqib bo'lmaydi."""
    from fastapi.testclient import TestClient
    from ges_server import config
    from ges_server.main import create_app

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>GES</title>", encoding="utf-8")
    (dist / "assets" / "a.js").write_text("1", encoding="utf-8")
    monkeypatch.setattr(config.get_settings(), "web_dist", dist)
    with TestClient(create_app()) as c:
        r = c.get("/projects/1/dashboard")
        assert r.status_code == 200 and "GES" in r.text and r.headers["cache-control"] == "no-cache"
        assert c.get("/assets/a.js").text == "1"
        r = c.get("/api/versions/1/nomalum")
        assert r.status_code == 404 and r.headers["content-type"].startswith("application/json")
        assert c.get("/api").status_code == 404
        assert "GES" in c.get("/..%2f..%2fetc/passwd").text  # traversal → index.html


@pytest.fixture
def clean_desktop():
    """data_dir test sessiyasi bo'yicha umumiy — oldingi testlarning paketlari aralashmasin."""
    import shutil

    from ges_server import config

    shutil.rmtree(config.get_settings().data_dir / "desktop", ignore_errors=True)
    yield


def _keypair():
    import base64

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    sk = Ed25519PrivateKey.generate()
    raw = sk.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    pub = sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return raw, pub, base64.b64encode(pub).decode()


def test_desktop_manifest_sha256_and_signature(client, users, admin, monkeypatch, clean_desktop):
    """SEC-03: latest da sha256/hajm/imzo; imzo server ochiq kaliti bilan tekshiriladi; sha256 mos kelmasa rad."""
    import hashlib

    from ges_server import config
    from ges_server.system import release

    raw, pub, pub_b64 = _keypair()
    s = config.get_settings()
    monkeypatch.setattr(s, "desktop_signing_public_key", pub_b64)
    body = b"blender-bundle-0.4.0"
    man = {"product": "blender", "version": "0.4.0", "kind": "zip", "name": "Sath-0.4.0-Windows-x86_64.zip",
           "size": len(body), "sha256": hashlib.sha256(body).hexdigest()}
    sig = release.sign(raw, man)
    # sha256 mos emas — rad, fayl qolmaydi
    r = client.post("/api/desktop/upload", data={"product": "blender", "sha256": "0" * 64},
                    files={"file": (man["name"], body)}, headers=admin)
    assert r.status_code == 400 and "sha256" in r.json()["detail"]
    # soxta imzo — rad
    bad = release.sign(raw, {**man, "sha256": "f" * 64})
    r = client.post("/api/desktop/upload", data={"product": "blender", "signature": bad},
                    files={"file": (man["name"], body)}, headers=admin)
    assert r.status_code == 400 and "Imzo" in r.json()["detail"]
    assert client.get("/api/desktop/latest", headers=users["viewer"]).status_code == 404
    # to'g'ri imzo
    r = client.post("/api/desktop/upload", data={"product": "blender", "sha256": man["sha256"], "signature": sig},
                    files={"file": (man["name"], body)}, headers=admin)
    assert r.status_code == 201 and r.json()["verified"] is True, r.text
    latest = client.get("/api/desktop/latest", headers=users["viewer"]).json()
    assert latest["product"] == "blender" and latest["sha256"] == man["sha256"] and latest["size"] == len(body)
    assert latest["signature"] == sig and latest["key_id"] == release.key_id(pub)
    f = latest["files"][0]
    assert release.verify(pub, f, f["signature"])  # klient xuddi shu maydonlardan kanonik xabar tuzadi
    assert client.get(latest["url"], headers=users["viewer"]).content == body
    # imzo majburiy — imzosiz rad
    monkeypatch.setattr(s, "desktop_require_signature", True)
    r = client.post("/api/desktop/upload", files={"file": ("Sath-0.5.0-Windows-x86_64.zip", b"x")}, headers=admin)
    assert r.status_code == 400 and "Imzo talab" in r.json()["detail"]
    assert client.get("/api/desktop/latest", headers=users["viewer"]).json()["version"] == "0.4.0"


def test_desktop_partial_upload_never_latest(client, users, admin, monkeypatch, clean_desktop):
    """SEC-03: yuklash .part ga, faqat oxirida os.replace — uzilgan/katta yuklash «latest» bo'lmaydi."""
    from ges_server import config

    s = config.get_settings()
    r = client.post("/api/desktop/upload", files={"file": ("Sath-1.0.0-Windows-x86_64.zip", b"ok")}, headers=admin)
    assert r.status_code == 201
    monkeypatch.setattr(s, "max_upload_mb", 1)
    big = b"x" * (2 * 1024 * 1024)
    r = client.post("/api/desktop/upload", files={"file": ("Sath-2.0.0-Windows-x86_64.zip", big)}, headers=admin)
    assert r.status_code == 413
    d = s.data_dir / "desktop" / "blender"
    assert not (d / "Sath-2.0.0-Windows-x86_64.zip").exists()
    assert not list(d.glob("*.part"))  # vaqtinchalik fayl o'chirilgan
    # parallel yuklanayotgan (.part) fayl ro'yxatga tushmaydi
    (d / ".Sath-3.0.0-Windows-x86_64.zip.abc.part").write_bytes(b"yarim")
    latest = client.get("/api/desktop/latest", headers=users["viewer"]).json()
    assert latest["version"] == "1.0.0" and latest["sha256"]


def test_desktop_products_do_not_collide(client, users, admin, clean_desktop):
    """CODE-03/SEC-03: FreeCAD va Blender paketlari bir xil nomda — alohida mahsulot papkalarida."""
    name = "Sath-0.9.0-Windows-x86_64.zip"
    for prod, body in (("blender", b"B"), ("freecad", b"F")):
        r = client.post("/api/desktop/upload", data={"product": prod}, files={"file": (name, body)}, headers=admin)
        assert r.status_code == 201 and r.json()["product"] == prod
    b = client.get("/api/desktop/latest", headers=users["viewer"]).json()  # default — blender
    f = client.get("/api/desktop/latest?product=freecad", headers=users["viewer"]).json()
    assert b["product"] == "blender" and f["product"] == "freecad" and b["sha256"] != f["sha256"]
    assert client.get(b["url"], headers=users["viewer"]).content == b"B"
    assert client.get(f["url"], headers=users["viewer"]).content == b"F"
    assert client.get("/api/desktop/latest?product=boshqa", headers=users["viewer"]).status_code == 400
    r = client.post("/api/desktop/upload", data={"product": "freecad"},
                    files={"file": ("Sath-Blender-1.0.0-Windows-x86_64.zip", b"x")}, headers=admin)
    assert r.status_code == 400  # nomdagi mahsulot bilan mos emas
