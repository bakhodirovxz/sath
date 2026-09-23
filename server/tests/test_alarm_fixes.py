from conftest import ingest_headers, ws_ticket

"""C5: WebSocket ulanishi alarm/email bermaydi; email navbati (cheklangan, jamlangan); fon holati DB da."""

import queue
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from ges_server import notify
from ges_server.db import SessionLocal
from ges_server.monitoring import background, live
from ges_server.orm import AlarmEvent, Sensor


def test_50_ws_connections_send_no_email_and_no_stale_events(client, users, monkeypatch):
    pid = users["project_id"]
    r = client.post(
        f"/api/projects/{pid}/sensors",
        json={"key": "RES.H", "name": "Sath", "kind": "level", "unit": "m", "stale_after_s": 1},
        headers=users["engineer"],
    )
    sid = r.json()["id"]
    client.post(f"/api/projects/{pid}/readings", json=[{"key": "RES.H", "value": 900}], headers=ingest_headers(client, users))
    with SessionLocal() as db:  # o'lchov eskirgan — stale bo'lishi kerak, lekin faqat fon vazifasi buni aniqlaydi
        s = db.get(Sensor, sid)
        s.last_ts = datetime.now(timezone.utc) - timedelta(minutes=10)
        db.commit()
    calls = []
    monkeypatch.setattr(notify, "send_async", lambda *a, **k: calls.append(a))
    token = ws_ticket(client, users["viewer"])
    for _ in range(50):
        with client.websocket_connect(f"/api/projects/{pid}/live?ticket={token}") as ws:
            snap = ws.receive_json()
            assert snap["type"] == "snapshot"
    assert calls == []
    with SessionLocal() as db:
        assert db.query(AlarmEvent).filter_by(sensor_id=sid).count() == 0
        assert db.get(Sensor, sid).alarm.value == "ok"
    # fon vazifasi — bitta stale hodisa, bitta bildirishnoma
    assert background.tick_stale() >= 1
    with SessionLocal() as db:
        assert [e.state.value for e in db.query(AlarmEvent).filter_by(sensor_id=sid)] == ["stale"]
    for _ in range(10):
        client.get(f"/api/projects/{pid}/alarms", headers=users["viewer"])
        client.get(f"/api/projects/{pid}/dashboard", headers=users["viewer"])
    assert len(calls) <= 1


def test_email_queue_bounded_and_coalesced(monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "_send", lambda to, subject, body: sent.append((to, subject, body)))
    monkeypatch.setattr(notify, "get_settings", lambda: SimpleNamespace(smtp_url="smtp://x@localhost:25"))
    q: queue.Queue = queue.Queue(maxsize=5)
    monkeypatch.setattr(notify, "_ensure_worker", lambda: q)  # ishchi oqimsiz — qo'lda process_once
    monkeypatch.setattr(notify, "dropped", 0)
    to = ["a@x.uz", "b@x.uz"]
    for i in range(4):
        notify.send_async(to, f"Alarm {i}", f"tafsilot {i}", group="alarm:1")
    notify.send_async(["c@x.uz"], "Kunlik hisobot", "…", group="report:1")
    notify.send_async(to, "Ortiqcha", "…", group="alarm:1")  # navbat to'la (5) → tashlanadi
    assert notify.dropped == 1 and q.qsize() == 5
    # birinchi olish: 4 ta alarm bitta jamlangan emailga, hisobot navbatga qaytadi
    assert notify.process_once(q, timeout=None) == 4
    assert len(sent) == 1 and sent[0][0] == to and "4 ta xabar" in sent[0][1]
    assert all(f"Alarm {i}" in sent[0][2] for i in range(4))
    assert notify.process_once(q, timeout=None) == 1 and sent[1][1] == "[Sath] Kunlik hisobot"
    assert notify.process_once(q, timeout=None) == 0
    # SMTP sozlanmagan — navbatga tushmaydi
    monkeypatch.setattr(notify, "get_settings", lambda: SimpleNamespace(smtp_url=None))
    notify.send_async(to, "x", "y")
    assert q.qsize() == 0


def test_last_hour_persisted_in_db(client):
    assert background.load_last_hour() is None
    h = datetime(2026, 9, 22, 6, 0, tzinfo=timezone.utc)
    background.state_set(background.LAST_HOUR_KEY, h.isoformat())
    assert background.load_last_hour() == h
    background.state_set(background.LAST_HOUR_KEY, "buzuq")
    assert background.load_last_hour() is None
    assert live.hub.count(1) == 0
