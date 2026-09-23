"""B3: ingest/command kalitlari ajratilgan, muddat, oxirgi ishlatilgan vaqt, gateway konfiguratsiyasi."""

import importlib.util
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from ges_server.db import SessionLocal
from ges_server.monitoring import keys
from ges_server.orm import Project, utcnow


def test_keys_are_separate_with_expiry_and_audit(client, users, admin):
    pid = users["project_id"]
    ik = client.get(f"/api/projects/{pid}/keys/ingest", headers=users["approver"]).json()
    ck = client.get(f"/api/projects/{pid}/keys/command", headers=users["approver"]).json()
    assert ik["key"] != ck["key"] and ik["header"] == "X-Ingest-Key" and ck["header"] == "X-Command-Key"
    assert 360 <= ik["days_left"] <= 365 and ik["last_used_at"] is None
    assert ik["ingest_key"] == ik["key"] and ik["shown_once"] is True  # eski nom
    # SCADA-04: kalit faqat yaratilganda ko'rsatiladi; keyin — prefiks (eski manzil ham)
    again = client.get(f"/api/projects/{pid}/ingest-key", headers=users["approver"]).json()
    assert again["ingest_key"] is None and again["key"] is None and again["key_prefix"] == ik["key"][:6]
    # muhandis kalitni ko'ra olmaydi
    assert client.get(f"/api/projects/{pid}/keys/command", headers=users["engineer"]).status_code == 403
    # rotatsiya alohida: command o'zgaradi, ingest o'zgarmaydi; muddatsiz kalit
    r = client.post(f"/api/projects/{pid}/keys/command", headers=users["approver"], params={"ttl_days": 0}).json()
    assert r["key"] != ck["key"] and r["expires_at"] is None and r["shown_once"] is True
    assert client.get(f"/api/projects/{pid}/keys/ingest", headers=users["approver"]).json()["key_prefix"] == ik["key"][:6]
    acts = [a["action"] for a in client.get("/api/audit", headers=admin, params={"project_id": pid}).json()]
    assert "project.command_key.rotate" in acts and "project.command_key.read" in acts
    assert "project.ingest_key.create" in acts


def test_ingest_key_cannot_use_command_channel_and_vice_versa(client, users, admin):
    pid = users["project_id"]
    ik = client.get(f"/api/projects/{pid}/keys/ingest", headers=users["approver"]).json()["key"]
    ck = client.get(f"/api/projects/{pid}/keys/command", headers=users["approver"]).json()["key"]
    assert client.post(f"/api/projects/{pid}/commands/claim", headers={"X-Command-Key": ik}).status_code == 403
    assert client.post(f"/api/projects/{pid}/readings", json=[], headers={"X-Ingest-Key": ck}).status_code == 403
    assert client.post(f"/api/projects/{pid}/commands/claim", headers={"X-Command-Key": "yoq"}).status_code == 401
    assert client.post(f"/api/projects/{pid}/commands/claim", headers={"X-Command-Key": ck}).status_code == 200
    acts = [a["action"] for a in client.get("/api/audit", headers=admin, params={"project_id": pid}).json()]
    assert acts.count("gateway.key_misuse") == 2


def test_expired_key_rejected_and_last_used_tracked(client, users):
    pid = users["project_id"]
    ck = client.get(f"/api/projects/{pid}/keys/command", headers=users["approver"]).json()["key"]
    assert client.post(f"/api/projects/{pid}/commands/claim", headers={"X-Command-Key": ck}).status_code == 200
    info = client.get(f"/api/projects/{pid}/keys/command", headers=users["approver"]).json()
    assert info["last_used_at"] is not None
    with SessionLocal() as db:
        p = db.get(Project, pid)
        p.command_key_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    r = client.post(f"/api/projects/{pid}/commands/claim", headers={"X-Command-Key": ck})
    assert r.status_code == 401 and "muddati" in r.json()["detail"]


def test_expiry_warning_notifications(client, users, admin):
    pid = users["project_id"]
    client.get(f"/api/projects/{pid}/keys/ingest", headers=users["approver"])
    with SessionLocal() as db:
        p = db.get(Project, pid)
        p.ingest_key_expires_at = utcnow() + timedelta(days=7, hours=1)
        db.commit()
        n = keys.warn_expiring(db)
        assert n >= 1
        assert keys.warn_expiring(db) >= 1  # kuniga bir marta chaqiriladi — idempotent emas, shu kun ichida takrorlanmaydi (background)
    notes = client.get("/api/notifications", headers=users["approver"]).json()
    assert any("7 kunda tugaydi" in x["title"] for x in notes)
    notes_admin = client.get("/api/notifications", headers=admin).json()
    assert any("kaliti" in x["title"] for x in notes_admin)


def _load_gateway():
    path = Path(__file__).resolve().parents[2] / "deploy" / "gateway" / "ges_gateway.py"
    sys.modules.setdefault("requests", type(sys)("requests"))  # gateway importi uchun stub
    spec = importlib.util.spec_from_file_location("ges_gateway", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_gateway_commands_default_off_and_env_override(tmp_path, monkeypatch):
    gw = _load_gateway()
    cfg_path = tmp_path / "c.json"
    cfg_path.write_text('{"server": "http://s", "project_id": 1, "ingest_key": "ik", "sources": []}', encoding="utf-8")
    for name in ("GES_GATEWAY_COMMANDS", "GES_GATEWAY_COMMAND_KEY", "GES_GATEWAY_SERVER"):
        monkeypatch.delenv(name, raising=False)
    cfg = gw.load_config(str(cfg_path))
    assert cfg["commands"] is False and gw.build_commander(cfg, []) is None
    # commands=true, lekin command_key yo'q → xato (ingest kaliti bilan ishlamaydi)
    monkeypatch.setenv("GES_GATEWAY_COMMANDS", "true")
    cfg = gw.load_config(str(cfg_path))
    with pytest.raises(ValueError, match="command_key"):
        gw.build_commander(cfg, [])
    monkeypatch.setenv("GES_GATEWAY_COMMAND_KEY", "ck")
    cfg = gw.load_config(str(cfg_path))
    cmd = gw.build_commander(cfg, [])
    assert cmd is not None and cmd.headers == {"X-Command-Key": "ck"}
    # fayl majburiy emas — muhitdan
    monkeypatch.setenv("GES_GATEWAY_SERVER", "http://env")
    monkeypatch.setenv("GES_GATEWAY_PROJECT_ID", "7")
    monkeypatch.setenv("GES_GATEWAY_INGEST_KEY", "envik")
    cfg = gw.load_config(None)
    assert cfg["server"] == "http://env" and cfg["project_id"] == 7 and cfg["ingest_key"] == "envik"
    monkeypatch.delenv("GES_GATEWAY_SERVER")
    with pytest.raises(ValueError, match="server"):
        gw.load_config(None)


def test_keys_stored_hashed_not_plaintext(client, users):
    """SCADA-04: bazada kalit ochiq holda yo'q — faqat SHA-256 xesh va prefiks; kalit bilan kirish ishlaydi."""
    import hashlib

    pid = users["project_id"]
    ik = client.get(f"/api/projects/{pid}/keys/ingest", headers=users["approver"]).json()["key"]
    ck = client.get(f"/api/projects/{pid}/keys/command", headers=users["approver"]).json()["key"]
    with SessionLocal() as db:
        p = db.get(Project, pid)
        assert p.ingest_key_hash == hashlib.sha256(ik.encode()).hexdigest() and p.ingest_key_prefix == ik[:6]
        assert p.command_key_hash == hashlib.sha256(ck.encode()).hexdigest()
        assert p.command_sign_key == keys.derive_sign_key(ck) and p.command_sign_key != ck
        cols = {c.name for c in Project.__table__.columns}
        assert "ingest_key" not in cols and "command_key" not in cols
        row = db.execute(__import__("sqlalchemy").text("SELECT * FROM projects WHERE id = :i"), {"i": pid}).mappings().one()
        assert ik not in [str(v) for v in row.values()] and ck not in [str(v) for v in row.values()]
    assert client.post(f"/api/projects/{pid}/readings", json=[], headers={"X-Ingest-Key": ik}).status_code == 200
    assert client.post(f"/api/projects/{pid}/commands/claim", headers={"X-Command-Key": ck}).status_code == 200


def test_migration_hashes_existing_plaintext_keys(tmp_path):
    """0034: mavjud ochiq kalitlar xeshlanadi va ochiq ustunlar olib tashlanadi."""
    import hashlib

    from alembic import command
    from ges_server import db as gdb
    from sqlalchemy import create_engine, inspect, text

    eng = create_engine(f"sqlite:///{(tmp_path / 'k.db').as_posix()}")
    with eng.begin() as conn:
        cfg = gdb._alembic_config()
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0033")
        conn.execute(text(
            "INSERT INTO users (id, username, full_name, email, password_hash, is_admin, is_active, created_at) "
            "VALUES (1, 'a', 'A', '', 'x', 1, 1, '2026-01-01 00:00:00')"
        ))
        conn.execute(text(
            "INSERT INTO projects (id, name, description, location, dashboard, site, created_by, created_at, "
            "calibration, ingest_key, command_key) VALUES (1, 'P', '', '', '{}', '{}', 1, '2026-01-01 00:00:00', '{}', 'ikey123456', 'ckey654321')"
        ))
        command.upgrade(cfg, "0034")
        row = conn.execute(text(
            "SELECT ingest_key_hash, ingest_key_prefix, command_key_hash, command_sign_key FROM projects"
        )).one()
        assert row[0] == hashlib.sha256(b"ikey123456").hexdigest() and row[1] == "ikey12"
        assert row[2] == hashlib.sha256(b"ckey654321").hexdigest() and row[3] == keys.derive_sign_key("ckey654321")
        cols = {c["name"] for c in inspect(conn).get_columns("projects")}
        assert "ingest_key" not in cols and "command_key" not in cols
