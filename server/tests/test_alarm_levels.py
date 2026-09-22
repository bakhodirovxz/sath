"""C1: ko'p bosqichli chegaralar (LL/L/H/HH), o'lik zona, on/off kechikish, ROC, og'ish alarmi."""

from datetime import datetime, timedelta, timezone

import pytest
from ges_server.db import SessionLocal
from ges_server.monitoring import live
from ges_server.orm import AlarmEvent, AlarmState, Sensor


@pytest.fixture
def sensor(client, users):
    def make(**kw):
        body = {"key": kw.pop("key", "RES.H"), "name": "Sath", "kind": "level", "unit": "m", **kw}
        r = client.post(f"/api/projects/{users['project_id']}/sensors", json=body, headers=users["engineer"])
        assert r.status_code == 201, r.text
        return r.json()

    return make


def _push(client, users, items):
    r = client.post(f"/api/projects/{users['project_id']}/readings", json=items, headers=users["engineer"])
    assert r.status_code == 200, r.text
    return r.json()


def _events(sid):
    with SessionLocal() as db:
        return [(e.state.value, e.ended_at is not None) for e in db.query(AlarmEvent).filter_by(sensor_id=sid).order_by(AlarmEvent.id)]


def _alarm(sid):
    with SessionLocal() as db:
        return db.get(Sensor, sid).alarm.value


def test_chatter_around_threshold_creates_one_event(client, users, sensor):
    s = sensor(high_alarm=900.0, deadband=0.5)
    key = "RES.H"
    # chegara atrofida tebranish: 900.2, 899.9, 900.3, 899.8 … — o'lik zona 0.5 → bitta hodisa
    for v in (900.2, 899.9, 900.3, 899.8, 900.1, 899.7):
        _push(client, users, [{"key": key, "value": v}])
    assert _events(s["id"]) == [("high", False)]
    assert _alarm(s["id"]) == "high"
    # o'lik zonadan chiqdi → yopiladi
    _push(client, users, [{"key": key, "value": 899.4}])
    assert _events(s["id"]) == [("high", True)] and _alarm(s["id"]) == "ok"
    # o'lik zonasiz (deadband=0) — har kesishish yangi hodisa (eski xatti-harakat, taqqoslash uchun)
    s2 = sensor(key="RES.H2", high_alarm=900.0)
    for v in (900.2, 899.9, 900.3, 899.8):
        _push(client, users, [{"key": "RES.H2", "value": v}])
    assert [st for st, _ in _events(s2["id"])] == ["high", "high"]


def test_ll_hh_escalation_and_return_through_levels(client, users, sensor):
    s = sensor(ll_alarm=880.0, low_alarm=890.0, high_alarm=900.0, hh_alarm=905.0, deadband=1.0)
    _push(client, users, [{"key": "RES.H", "value": 895.0}])
    assert _alarm(s["id"]) == "ok"
    _push(client, users, [{"key": "RES.H", "value": 901.0}])
    assert _alarm(s["id"]) == "high"
    _push(client, users, [{"key": "RES.H", "value": 906.0}])
    assert _alarm(s["id"]) == "highhigh"
    assert _events(s["id"]) == [("high", True), ("highhigh", False)]
    _push(client, users, [{"key": "RES.H", "value": 904.5}])  # HH − deadband ichida → hali HH
    assert _alarm(s["id"]) == "highhigh"
    _push(client, users, [{"key": "RES.H", "value": 903.0}])  # HH dan chiqdi, H da
    assert _alarm(s["id"]) == "high"
    _push(client, users, [{"key": "RES.H", "value": 879.0}])
    assert _alarm(s["id"]) == "lowlow"
    _push(client, users, [{"key": "RES.H", "value": 895.0}])
    assert _alarm(s["id"]) == "ok"
    assert [st for st, _ in _events(s["id"])] == ["high", "highhigh", "high", "lowlow"]
    assert all(done for _, done in _events(s["id"]))


def test_on_delay_ignores_short_excursion_and_background_settles(client, users, sensor):
    s = sensor(high_alarm=900.0, on_delay_s=5, off_delay_s=3)
    _push(client, users, [{"key": "RES.H", "value": 895.0}])
    _push(client, users, [{"key": "RES.H", "value": 901.0}])  # chegaradan chiqdi — kutish boshlanadi
    assert _alarm(s["id"]) == "ok" and _events(s["id"]) == []
    with SessionLocal() as db:
        x = db.get(Sensor, s["id"])
        assert x.alarm_pending == "high" and x.alarm_pending_since is not None
    _push(client, users, [{"key": "RES.H", "value": 895.0}])  # qisqa sakrash — kutish bekor
    with SessionLocal() as db:
        assert db.get(Sensor, s["id"]).alarm_pending is None
    assert _events(s["id"]) == []
    # 5 s dan uzoq tursa — alarm (kutish vaqtini orqaga suramiz)
    _push(client, users, [{"key": "RES.H", "value": 901.0}])
    with SessionLocal() as db:
        x = db.get(Sensor, s["id"])
        x.alarm_pending_since = datetime.now(timezone.utc) - timedelta(seconds=6)
        db.commit()
    _push(client, users, [{"key": "RES.H", "value": 901.5}])
    assert _alarm(s["id"]) == "high" and _events(s["id"]) == [("high", False)]
    # qaytish: off_delay 3 s — darhol yopilmaydi
    _push(client, users, [{"key": "RES.H", "value": 895.0}])
    assert _alarm(s["id"]) == "high"
    # yangi o'lchov kelmasa ham fon vazifasi yakunlaydi
    with SessionLocal() as db:
        x = db.get(Sensor, s["id"])
        assert x.alarm_pending == "ok"
        x.alarm_pending_since = datetime.now(timezone.utc) - timedelta(seconds=4)
        db.commit()
        assert [c.id for c in live.settle_pending(db, users["project_id"])] == [s["id"]]
    assert _alarm(s["id"]) == "ok" and _events(s["id"]) == [("high", True)]


def test_rate_of_change_alarm(client, users, sensor):
    s = sensor(roc_limit_per_min=2.0)
    t0 = (datetime.now(timezone.utc) - timedelta(minutes=10)).replace(microsecond=0)  # fon tick_stale eskirtirmasin
    _push(client, users, [{"key": "RES.H", "value": 895.0, "ts": t0.isoformat()}])
    _push(client, users, [{"key": "RES.H", "value": 895.5, "ts": (t0 + timedelta(minutes=1)).isoformat()}])
    assert _alarm(s["id"]) == "ok"  # 0.5 m/min
    _push(client, users, [{"key": "RES.H", "value": 900.5, "ts": (t0 + timedelta(minutes=2)).isoformat()}])
    assert _alarm(s["id"]) == "roc" and _events(s["id"]) == [("roc", False)]  # 5 m/min
    _push(client, users, [{"key": "RES.H", "value": 900.6, "ts": (t0 + timedelta(minutes=3)).isoformat()}])
    assert _alarm(s["id"]) == "ok" and _events(s["id"]) == [("roc", True)]
    # daraja alarmi ROC dan ustun
    s2 = sensor(key="RES.H3", high_alarm=900.0, roc_limit_per_min=1.0)
    _push(client, users, [{"key": "RES.H3", "value": 890.0, "ts": t0.isoformat()}])
    _push(client, users, [{"key": "RES.H3", "value": 905.0, "ts": (t0 + timedelta(minutes=1)).isoformat()}])
    assert _alarm(s2["id"]) == "high"


def test_deviation_kind_gives_deviation_state(client, users, sensor):
    s = sensor(key="TWIN.1.DEV", kind="deviation", unit="%", low_alarm=-10, high_alarm=10)
    _push(client, users, [{"key": "TWIN.1.DEV", "value": 12.0}])
    assert _alarm(s["id"]) == "deviation" and _events(s["id"]) == [("deviation", False)]
    _push(client, users, [{"key": "TWIN.1.DEV", "value": -12.0}])
    assert _alarm(s["id"]) == "deviation" and len(_events(s["id"])) == 1  # bir xil holat — yangi hodisa yo'q
    _push(client, users, [{"key": "TWIN.1.DEV", "value": 3.0}])
    assert _alarm(s["id"]) == "ok"


def test_patch_levels_and_clear(client, users, sensor):
    s = sensor(high_alarm=900.0)
    r = client.patch(f"/api/sensors/{s['id']}", json={"hh_alarm": 905, "deadband": 0.5, "on_delay_s": 10, "roc_limit_per_min": 3}, headers=users["engineer"])
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["hh_alarm"] == 905 and j["deadband"] == 0.5 and j["on_delay_s"] == 10 and j["roc_limit_per_min"] == 3
    r = client.patch(f"/api/sensors/{s['id']}", json={"clear_alarms": True, "clear_roc": True}, headers=users["engineer"])
    j = r.json()
    assert j["high_alarm"] is None and j["hh_alarm"] is None and j["roc_limit_per_min"] is None
    r = client.patch(f"/api/sensors/{s['id']}", json={"deadband": -1}, headers=users["engineer"])
    assert r.status_code == 422


def test_evaluate_alarm_pure():
    s = Sensor(key="x", name="x", low_alarm=10, high_alarm=20, ll_alarm=5, hh_alarm=25, deadband=1, alarm=AlarmState.ok)
    ev = live.evaluate_alarm
    assert ev(s, 15) == AlarmState.ok and ev(s, 20.5) == AlarmState.high and ev(s, 26) == AlarmState.highhigh
    assert ev(s, 9) == AlarmState.low and ev(s, 4) == AlarmState.lowlow
    s.alarm = AlarmState.high
    assert ev(s, 19.5) == AlarmState.high and ev(s, 18.9) == AlarmState.ok  # gisterezis
    s.alarm = AlarmState.lowlow
    assert ev(s, 5.5) == AlarmState.lowlow and ev(s, 6.5) == AlarmState.low and ev(s, 11.5) == AlarmState.ok
