"""C2: ISA-18.2 shelving (muddatli, avtomatik qaytish), out-of-service, suppression-by-design; audit."""

from datetime import datetime, timedelta, timezone

import pytest
from conftest import ingest_headers, login
from ges_server.db import SessionLocal
from ges_server.monitoring import live
from ges_server.orm import AlarmEvent, AuditLog, Notification, Sensor


@pytest.fixture
def sensor(client, users):
    def make(**kw):
        body = {"key": kw.pop("key", "RES.H"), "name": "Sath", "kind": "level", "unit": "m", **kw}
        r = client.post(f"/api/projects/{users['project_id']}/sensors", json=body, headers=users["engineer"])
        assert r.status_code == 201, r.text
        return r.json()

    return make


def _push(client, users, items):
    r = client.post(f"/api/projects/{users['project_id']}/readings", json=items, headers=ingest_headers(client, users))
    assert r.status_code == 200, r.text


def _active(client, users, include_suppressed=False):
    r = client.get(
        f"/api/projects/{users['project_id']}/alarm-events?active=true&include_suppressed={str(include_suppressed).lower()}",
        headers=users["viewer"],
    )
    assert r.status_code == 200
    return r.json()


def _audit_actions():
    with SessionLocal() as db:
        return [a.action for a in db.query(AuditLog).order_by(AuditLog.id).all()]


def _notif_count(users):
    with SessionLocal() as db:
        return db.query(Notification).filter_by(kind="alarm", user_id=users["ids"]["engineer"]).count()


def test_shelve_hides_alarm_and_auto_returns(client, users, sensor):
    pid = users["project_id"]
    s = sensor(high_alarm=900.0)
    _push(client, users, [{"key": "RES.H", "value": 901.0}])
    assert [e["alarm_state"] for e in _active(client, users)] == ["unack"]
    n0 = _notif_count(users)
    # sabab majburiy
    r = client.post(f"/api/sensors/{s['id']}/shelve", json={"reason": ""}, headers=users["engineer"])
    assert r.status_code == 422
    # viewer mumkin emas
    r = client.post(f"/api/sensors/{s['id']}/shelve", json={"reason": "ta'mir"}, headers=users["viewer"])
    assert r.status_code == 403
    # maksimal muddatdan oshiq
    r = client.post(f"/api/sensors/{s['id']}/shelve", json={"reason": "ta'mir", "hours": 100}, headers=users["engineer"])
    assert r.status_code == 400
    r = client.post(f"/api/sensors/{s['id']}/shelve", json={"reason": "datchik ta'miri", "hours": 2}, headers=users["engineer"])
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["alarm_mode"] == "shelved" and j["alarm_mode_reason"] == "datchik ta'miri" and j["alarm_mode_until"]
    # faol ro'yxatda ko'rinmaydi, include_suppressed bilan ko'rinadi
    assert _active(client, users) == []
    assert [e["alarm_state"] for e in _active(client, users, True)] == ["shelved"]
    # shelved paytida yangi hodisa ham bostirilgan, bildirishnoma yo'q
    _push(client, users, [{"key": "RES.H", "value": 895.0}])
    _push(client, users, [{"key": "RES.H", "value": 902.0}])
    assert _active(client, users) == [] and _notif_count(users) == n0
    with SessionLocal() as db:
        evs = db.query(AlarmEvent).filter_by(sensor_id=s["id"]).order_by(AlarmEvent.id).all()
        assert [e.suppressed for e in evs] == ["shelved", "shelved"] and evs[1].ended_at is None
    # muddat tugadi → fon vazifasi normal ga qaytaradi, davom etayotgan alarm faollashadi + bildirishnoma
    with SessionLocal() as db:
        x = db.get(Sensor, s["id"])
        x.alarm_mode_until = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
        assert [c.id for c in live.unshelve_expired(db, pid)] == [s["id"]]
    r = client.get(f"/api/projects/{pid}/sensors", headers=users["viewer"]).json()
    me = next(x for x in r if x["id"] == s["id"])
    assert me["alarm_mode"] == "normal" and me["alarm"] == "high"
    act = _active(client, users)
    assert len(act) == 1 and act[0]["alarm_state"] == "unack" and act[0]["suppressed"] is None
    assert _notif_count(users) == n0 + 1
    acts = _audit_actions()
    assert "alarm.shelve" in acts and "alarm.unshelve_auto" in acts


def test_unshelve_manual_and_oos_roles(client, users, sensor):
    s = sensor(high_alarm=900.0)
    _push(client, users, [{"key": "RES.H", "value": 901.0}])
    r = client.post(f"/api/sensors/{s['id']}/unshelve", headers=users["engineer"])
    assert r.status_code == 409  # shelved emas
    client.post(f"/api/sensors/{s['id']}/shelve", json={"reason": "sinov"}, headers=users["engineer"])
    r = client.post(f"/api/sensors/{s['id']}/unshelve", headers=users["engineer"])
    assert r.status_code == 200 and r.json()["alarm_mode"] == "normal"
    assert [e["alarm_state"] for e in _active(client, users)] == ["unack"]
    # out-of-service: faqat muhandis+; operator (viewer roli emas) rad etiladi
    r = client.post("/api/users", json={"username": "op1", "password": "pass1234"}, headers=users["admin"])
    uid = r.json()["id"]
    client.put(f"/api/projects/{users['project_id']}/members", json={"user_id": uid, "role": "operator"}, headers=users["admin"])
    op = login(client, "op1", "pass1234")
    r = client.post(f"/api/sensors/{s['id']}/out-of-service", json={"reason": "kalibrlash"}, headers=op)
    assert r.status_code == 403
    r = client.post(f"/api/sensors/{s['id']}/out-of-service", json={"reason": "kalibrlash"}, headers=users["engineer"])
    assert r.status_code == 200 and r.json()["alarm_mode"] == "out_of_service"
    assert _active(client, users) == []
    assert [e["alarm_state"] for e in _active(client, users, True)] == ["out_of_service"]
    # OOS paytida shelve mumkin emas
    r = client.post(f"/api/sensors/{s['id']}/shelve", json={"reason": "sinov"}, headers=users["engineer"])
    assert r.status_code == 409
    # ack-all bostirilganlarni kvitlamaydi
    assert client.post(f"/api/projects/{users['project_id']}/alarm-events/ack-all", headers=users["engineer"]).json() == {"acked": 0}
    r = client.post(f"/api/sensors/{s['id']}/in-service", headers=users["engineer"])
    assert r.status_code == 200 and r.json()["alarm_mode"] == "normal"
    assert [e["alarm_state"] for e in _active(client, users)] == ["unack"]
    acts = _audit_actions()
    for a in ("alarm.shelve", "alarm.unshelve", "alarm.out_of_service", "alarm.in_service"):
        assert a in acts


def test_suppression_by_design_condition(client, users, sensor):
    run = sensor(key="AGG1.RUN", kind="status", unit="")
    vib = sensor(key="AGG1.VIB", kind="vibration", unit="mm/s", high_alarm=5.0, suppress_condition="AGG1_RUN == 0")
    # agregat to'xtagan → vibratsiya alarmi bostiriladi
    _push(client, users, [{"key": "AGG1.RUN", "value": 0}, {"key": "AGG1.VIB", "value": 7.0}])
    assert _active(client, users) == []
    with SessionLocal() as db:
        v = db.get(Sensor, vib["id"])
        assert v.suppressed is True and v.alarm.value == "high"
        assert db.query(AlarmEvent).filter_by(sensor_id=vib["id"]).one().suppressed == "suppressed_by_design"
    # agregat ishga tushdi → shart yolg'on; alarm ko'rinadi (yangi hodisa)
    _push(client, users, [{"key": "AGG1.RUN", "value": 1}])
    _push(client, users, [{"key": "AGG1.VIB", "value": 4.0}])
    _push(client, users, [{"key": "AGG1.VIB", "value": 7.5}])
    act = _active(client, users)
    assert len(act) == 1 and act[0]["sensor_id"] == vib["id"] and act[0]["suppressed"] is None
    # yaroqsiz ifoda → 422; shart baholanmasa (sensor yo'q) → bostirilMAYDI
    r = client.patch(f"/api/sensors/{vib['id']}", json={"suppress_condition": "import os"}, headers=users["engineer"])
    assert r.status_code == 422
    r = client.patch(f"/api/sensors/{vib['id']}", json={"suppress_condition": "YOQ_SENSOR == 0"}, headers=users["engineer"])
    assert r.status_code == 200 and r.json()["suppressed"] is False
    _push(client, users, [{"key": "AGG1.VIB", "value": 8.0}])
    with SessionLocal() as db:
        assert db.get(Sensor, vib["id"]).suppressed is False
    assert run["id"] != vib["id"]


def test_ack_batch_only_listed_and_not_suppressed(client, users, sensor):
    """F5: tanlangan (filtrlangan) hodisalarni kvitlash — ro'yxatdagi, kvitlanmagan, bostirilmaganlar."""
    pid = users["project_id"]
    a = sensor(key="A", high_alarm=1.0)
    b = sensor(key="B", high_alarm=1.0)
    c = sensor(key="C", high_alarm=1.0)
    client.post(f"/api/sensors/{c['id']}/shelve", json={"reason": "sinov"}, headers=users["engineer"])
    _push(client, users, [{"key": "A", "value": 5}, {"key": "B", "value": 5}, {"key": "C", "value": 5}])
    allev = client.get(f"/api/projects/{pid}/alarm-events?active=true&include_suppressed=true", headers=users["viewer"]).json()
    ids = {e["sensor_key"]: e["id"] for e in allev}
    assert set(ids) == {"A", "B", "C"}
    r = client.post(f"/api/projects/{pid}/alarm-events/ack-batch", json={"ids": [ids["A"], ids["C"], 99999], "comment": "smena"}, headers=users["engineer"])
    assert r.status_code == 200 and r.json() == {"acked": 1}  # C bostirilgan, 99999 yo'q
    ev = {e["sensor_key"]: e for e in client.get(f"/api/projects/{pid}/alarm-events?active=true", headers=users["viewer"]).json()}
    assert ev["A"]["alarm_state"] == "acked" and ev["A"]["comment"] == "smena" and ev["B"]["alarm_state"] == "unack"
    assert client.post(f"/api/projects/{pid}/alarm-events/ack-batch", json={"ids": [ids["B"]]}, headers=users["viewer"]).status_code == 403
    assert client.post(f"/api/projects/{pid}/alarm-events/ack-batch", json={"ids": []}, headers=users["engineer"]).status_code == 422
    assert "alarm.ack_batch" in _audit_actions()
    assert a["id"] != b["id"]


def test_annunciator_silence_audited(client, users):
    """F6: ovozli signalni vaqtincha o'chirish auditga yoziladi (operator+)."""
    pid = users["project_id"]
    assert client.post(f"/api/projects/{pid}/annunciator/silence", json={"minutes": 15, "reason": "ta'mir"}, headers=users["viewer"]).status_code == 403
    r = client.post(f"/api/projects/{pid}/annunciator/silence", json={"minutes": 15, "reason": "ta'mir"}, headers=users["engineer"])
    assert r.status_code == 200 and r.json()["minutes"] == 15
    client.post(f"/api/projects/{pid}/annunciator/silence", json={"minutes": 0}, headers=users["engineer"])
    acts = _audit_actions()
    assert "annunciator.silence" in acts and "annunciator.unsilence" in acts
    assert client.post(f"/api/projects/{pid}/annunciator/silence", json={"minutes": 99999}, headers=users["engineer"]).status_code == 422
