"""L8: rol, yetakchi qulfi, tayyorlik (readiness), ko'p replika — bitta replika o'chsa xizmat davom etadi."""

import os

import pytest
from fastapi.testclient import TestClient
from ges_server import ha, jobs
from ges_server.config import get_settings
from ges_server.main import app
from ges_server.monitoring import backplane, live


def test_ready_ok_and_role(client):
    r = client.get("/api/ready")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "ready" and j["db"] == "ok" and j["schema"] == "head" and j["role"] == "all" and j["jobs"] == "ok"
    assert client.get("/api/health").json()["role"] == "all"


def test_ready_503_when_db_or_schema_bad(client, monkeypatch):
    def broken():
        raise RuntimeError("DB sxemasi eskirgan")

    monkeypatch.setattr("ges_server.db.assert_at_head", broken)
    r = client.get("/api/ready")
    assert r.status_code == 503 and "eskirgan" in r.json()["detail"]["schema"]


def test_ready_503_when_backplane_not_listening(client):
    bp = backplane.PgBackplane("host=yoq")  # start qilinmagan — listening bayrog'i tushirilgan
    old = live.hub.backplane
    live.hub.backplane = bp
    try:
        r = client.get("/api/ready")
        assert r.status_code == 503 and r.json()["detail"]["backplane"] == "ulanmagan"
    finally:
        live.hub.backplane = old


def test_leader_lock_single_holder(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    a, b = ha.Leader(), ha.Leader()
    if a.is_pg:
        pytest.skip("Postgres advisory lock — bitta jarayonda ikki sessiya bilan alohida sinaladi")
    assert a.acquire() is True and a.held() is True
    assert b.acquire() is False  # ikkinchi nusxa yetakchi emas
    a.release()
    assert a.held() is False
    assert b.acquire() is True  # qulf bo'shagach ikkinchisi oladi
    b.release()
    assert (tmp_path / "leader.lock").exists()


@pytest.mark.skipif(not os.environ.get("GES_TEST_DATABASE_URL", "").startswith("postgresql"), reason="Postgres kerak")
def test_leader_lock_pg_two_sessions():
    a, b = ha.Leader(), ha.Leader()
    assert a.acquire() is True and b.acquire() is False
    a.release()
    assert b.acquire() is True
    b.release()


def test_api_role_starts_no_background(monkeypatch):
    """GES_ROLE=api: fon sikli va ish navbati ishchisi ishga tushmaydi, HTTP ishlaydi; ready da jobs yo'q."""
    monkeypatch.setattr(get_settings(), "role", "api")
    with TestClient(app) as c:
        assert jobs.runner is None
        r = c.get("/api/ready")
        assert r.status_code == 200 and r.json()["role"] == "api" and "jobs" not in r.json()
        assert c.get("/api/health").json()["role"] == "api"


def test_two_replicas_one_dies_service_continues(users, monkeypatch):
    """Qabul mezoni: ikki replika (ikki TestClient, umumiy DB va MemoryBackplane) — birinchisi o'chirilganda
    ikkinchisi so'rovlarga va jonli oqimga xizmat qiladi; jonli xabar replikalar orasida yetadi."""
    monkeypatch.setattr(get_settings(), "role", "api")
    monkeypatch.setattr(backplane, "from_settings", lambda: backplane.MemoryBackplane("ha", node_id=f"n{id(object())}"))
    pid = users["project_id"]
    a = TestClient(app)
    a.__enter__()
    hub_a_bp = live.hub.backplane
    assert isinstance(hub_a_bp, backplane.MemoryBackplane)
    assert a.get("/api/ready").status_code == 200
    # birinchi replika o'chadi
    a.__exit__(None, None, None)
    assert live.hub.backplane is None
    with TestClient(app) as b:
        assert b.get("/api/ready").status_code == 200
        assert b.get(f"/api/projects/{pid}", headers=users["viewer"]).status_code == 200
        # ikkinchi replikada jonli oqim ishlaydi; boshqa replikadan (peer) kelgan xabar yetadi
        t = b.post("/api/auth/ws-ticket", headers=users["viewer"]).json()["ticket"]
        peer = backplane.MemoryBackplane("ha", node_id="peer")
        import asyncio

        asyncio.run(peer.start(lambda p, m: None))
        try:
            with b.websocket_connect(f"/api/projects/{pid}/live?ticket={t}") as ws:
                assert ws.receive_json()["type"] == "snapshot"
                peer.publish(pid, {"type": "reading", "sensor_id": 0, "key": "X", "value": 1.0, "ts": None, "alarm": "ok", "element_guid": None, "unit": ""})
                m = ws.receive_json()
                assert m["type"] == "reading" and m["key"] == "X"
        finally:
            asyncio.run(peer.stop())
