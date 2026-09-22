from conftest import ws_ticket

"""A4: audit zanjiri — yaxlitlik tekshiruvi, rollback dan omon qolish, yetishmagan hodisalar, eksport."""

import hashlib
import hmac
import time
from datetime import datetime, timezone

from ges_server import audit
from ges_server.config import get_settings
from ges_server.db import SessionLocal
from ges_server.orm import AuditLog
from sqlalchemy import text


def _actions(client, admin, **params):
    r = client.get("/api/audit", headers=admin, params={"limit": 2000, **params})
    assert r.status_code == 200
    return [a["action"] for a in r.json()]


def test_chain_verifies_and_detects_tampering(client, admin, users):
    r = client.get("/api/audit/verify", headers=admin).json()
    assert r["ok"] and r["checked"] > 3 and r["first_bad_id"] is None
    with SessionLocal() as db:
        rows = db.query(AuditLog).order_by(AuditLog.id).all()
        assert rows[0].prev_hash == "" and all(x.row_hash for x in rows)
        for a, b in zip(rows, rows[1:], strict=False):
            assert b.prev_hash == a.row_hash
        victim = rows[2].id
        db.execute(text("UPDATE audit_log SET detail = '{\"x\": 1}' WHERE id = :i"), {"i": victim})
        db.commit()
    r = client.get("/api/audit/verify", headers=admin).json()
    assert r["ok"] is False and r["first_bad_id"] == victim
    # oddiy foydalanuvchi tekshira olmaydi
    assert client.get("/api/audit/verify", headers=users["approver"]).status_code == 403


def test_login_failed_is_logged_despite_401(client, admin, users):
    r = client.post("/api/auth/login", data={"username": "viewer", "password": "notoGri"})
    assert r.status_code == 401
    r = client.post("/api/auth/login", data={"username": "yoq_odam", "password": "x"})
    assert r.status_code == 401
    rows = [a for a in client.get("/api/audit", headers=admin).json() if a["action"] == "auth.login_failed"]
    assert len(rows) == 2
    assert rows[0]["detail"]["username"] == "yoq_odam" and rows[0]["user_id"] is None
    assert rows[1]["detail"]["username"] == "viewer" and rows[1]["user_id"] == users["ids"]["viewer"]
    assert client.get("/api/audit/verify", headers=admin).json()["ok"]


def test_rollback_drops_buffered_entries():
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))  # haqiqiy so'rovda bufer doim ochiq tranzaksiya ichida
        audit.log(db, user_id=None, action="test.rolled_back", target_type="x")
        assert audit.pending(db) == 1
        db.rollback()
        assert audit.pending(db) == 0
        audit.log(db, user_id=None, action="test.committed", target_type="x")
        db.commit()
    with SessionLocal() as db:
        acts = [a for (a,) in db.query(AuditLog.action).all()]
        assert "test.committed" in acts and "test.rolled_back" not in acts


def test_missing_events_are_logged(client, admin, users):
    pid = users["project_id"]
    client.post(
        f"/api/projects/{pid}/sensors",
        json={"key": "AGG1.P", "name": "A", "kind": "power", "unit": "MW"},
        headers=users["engineer"],
    )
    # ingest kalitini o'qish
    key = client.get(f"/api/projects/{pid}/ingest-key", headers=users["approver"]).json()["ingest_key"]
    # ingest: kalit bilan va token bilan — partiya bo'yicha bitta yozuv
    client.post(f"/api/projects/{pid}/readings", json=[{"key": "AGG1.P", "value": 1}], headers={"X-Ingest-Key": key})
    client.post(f"/api/projects/{pid}/readings", json=[{"key": "AGG1.P", "value": 2}, {"key": "YOQ", "value": 3}], headers=users["engineer"])
    sid = client.get(f"/api/projects/{pid}/sensors", headers=users["viewer"]).json()[0]["id"]
    client.get(f"/api/sensors/{sid}/export.csv", headers=users["viewer"])
    client.get(f"/api/projects/{pid}/report", headers=users["viewer"])
    r = client.post("/api/auth/change-password", json={"old_password": "pass1234", "new_password": "Kuzatuv-pw-9999"}, headers=users["viewer"])
    assert r.status_code == 200, r.text
    viewer = {"Authorization": f"Bearer {r.json()['access_token']}"}  # L2: parol o'zgargach eski token yaroqsiz
    token = ws_ticket(client, viewer)
    with client.websocket_connect(f"/api/projects/{pid}/live?ticket={token}") as ws:
        ws.receive_json()
    for _ in range(50):  # ws.disconnect audit yozuvi alohida oqimda (to_thread) — biroz kutish mumkin
        rows = client.get("/api/audit", headers=admin, params={"limit": 2000}).json()
        if any(a["action"] == "ws.disconnect" for a in rows):
            break
        time.sleep(0.05)
    by = {}
    for a in rows:
        by.setdefault(a["action"], []).append(a)
    assert "project.ingest_key.read" in by
    ing = sorted(by["readings.ingest"], key=lambda a: a["id"])
    assert len(ing) == 2
    assert ing[0]["detail"]["auth"] == "key" and ing[0]["detail"]["key_prefix"] == key[:6]
    assert ing[1]["detail"] == {"count": 2, "accepted": 1, "bad": 0, "unknown": 1, "rejected": 0, "auth": "token", "key_prefix": None}
    assert ing[1]["user_id"] == users["ids"]["engineer"]
    assert by["export.csv"][0]["detail"] == {"hours": 24.0}
    assert by["export.report"][0]["detail"]["period"] == "day"
    assert by["auth.password_changed"][0]["user_id"] == users["ids"]["viewer"]
    assert "ws.connect" in by and "duration_s" in by["ws.disconnect"][0]["detail"]
    assert client.get("/api/audit/verify", headers=admin).json()["ok"]


def test_daily_signed_export(client, admin, users):
    day = datetime.now(timezone.utc).date().isoformat()
    r = client.get("/api/audit/export", headers=admin, params={"day": day})
    assert r.status_code == 200, r.text
    sig = r.headers["X-Audit-Signature"]
    body = r.text
    assert body.count("\n") >= 3 and '"action"' in body
    expected = hmac.new(
        get_settings().ensure_secret_key().encode(), body.encode(), hashlib.sha256
    ).hexdigest()
    assert sig == expected
    assert client.get("/api/audit/export", headers=admin, params={"day": "kecha"}).status_code == 400
    assert client.get("/api/audit/export", headers=users["approver"], params={"day": day}).status_code == 403


def test_row_hash_is_stable_for_equivalent_inputs():
    ts = datetime(2026, 1, 1, 12, 0, 0, 123456, tzinfo=timezone.utc)
    a = audit.row_hash(created_at=ts, user_id=1, action="x", target_type="t", target_id=None,
                       project_id=None, detail={"b": 1, "a": (1, 2)}, prev_hash="")
    b = audit.row_hash(created_at=ts.replace(tzinfo=None), user_id=1, action="x", target_type="t",
                       target_id=None, project_id=None, detail={"a": [1, 2], "b": 1}, prev_hash="")
    assert a == b and len(a) == 64
