"""F4: aloqa holati (stale) alarm holatidan ajratilgan — yuqori alarmdagi sensor aloqani yo'qotsa alarm yashirinmaydi;
aloqa qaytsa stale hodisasi yopiladi; WebSocket xabarida stale/age_s; heartbeat ping."""

from datetime import datetime, timedelta, timezone

from ges_server.db import SessionLocal
from ges_server.monitoring import background, live
from ges_server.orm import AlarmEvent, Sensor


def test_high_alarm_survives_comm_loss_and_stale_event_closes_on_return(client, users):
    pid = users["project_id"]
    r = client.post(f"/api/projects/{pid}/sensors", json={"key": "RES.H", "name": "Sath", "kind": "level", "unit": "m", "high_alarm": 900, "stale_after_s": 60, "priority": "critical"}, headers=users["engineer"])
    sid = r.json()["id"]
    assert r.json()["stale"] is True and r.json()["alarm"] == "ok"
    client.post(f"/api/projects/{pid}/readings", json=[{"key": "RES.H", "value": 905}], headers=users["engineer"])
    s = next(x for x in client.get(f"/api/projects/{pid}/sensors", headers=users["viewer"]).json() if x["id"] == sid)
    assert s["alarm"] == "high" and s["stale"] is False
    with SessionLocal() as db:  # aloqa uziladi
        x = db.get(Sensor, sid)
        x.last_ts = datetime.now(timezone.utc) - timedelta(minutes=5)
        db.commit()
    assert background.tick_stale() >= 1
    s = next(x for x in client.get(f"/api/projects/{pid}/sensors", headers=users["viewer"]).json() if x["id"] == sid)
    assert s["alarm"] == "high" and s["stale"] is True  # faol alarm YASHIRINMAYDI
    alarms = client.get(f"/api/projects/{pid}/alarms", headers=users["viewer"]).json()
    assert [(a["id"], a["alarm"], a["stale"]) for a in alarms] == [(sid, "high", True)]
    with SessionLocal() as db:
        evs = db.query(AlarmEvent).filter_by(sensor_id=sid).order_by(AlarmEvent.id).all()
        assert [(e.state.value, e.ended_at is None) for e in evs] == [("high", True), ("stale", True)]  # ikkalasi ochiq
    # aloqa qaytdi: stale hodisasi yopiladi, high davom etadi; qiymat past bo'lsa high ham yopiladi
    client.post(f"/api/projects/{pid}/readings", json=[{"key": "RES.H", "value": 906}], headers=users["engineer"])
    with SessionLocal() as db:
        evs = db.query(AlarmEvent).filter_by(sensor_id=sid).order_by(AlarmEvent.id).all()
        assert [(e.state.value, e.ended_at is None) for e in evs] == [("high", True), ("stale", False)]
        assert db.get(Sensor, sid).stale is False
    client.post(f"/api/projects/{pid}/readings", json=[{"key": "RES.H", "value": 890}], headers=users["engineer"])
    with SessionLocal() as db:
        assert db.get(Sensor, sid).alarm.value == "ok"
        msg = live.sensor_message(db.get(Sensor, sid))
        assert msg["stale"] is False and msg["age_s"] is not None and msg["age_s"] < 5 and msg["alarm"] == "ok"


def test_ws_snapshot_has_stale_and_ping(client, users, monkeypatch):
    from ges_server.monitoring import router as mon

    pid = users["project_id"]
    client.post(f"/api/projects/{pid}/sensors", json={"key": "AGG1.P", "name": "P", "kind": "power", "unit": "MW"}, headers=users["engineer"])
    monkeypatch.setattr(mon, "WS_PING_S", 0.2)
    token = users["viewer"]["Authorization"].split()[1]
    with client.websocket_connect(f"/api/projects/{pid}/live?token={token}") as ws:
        snap = ws.receive_json()
        assert snap["type"] == "snapshot" and snap["sensors"][0]["stale"] is True and "age_s" in snap["sensors"][0]
        ping = ws.receive_json()  # 0.2 s ichida heartbeat
        assert ping["type"] == "ping" and ping["ts"].endswith("+00:00")
