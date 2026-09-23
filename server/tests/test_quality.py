"""A1: o'lchov sifati (quality) va manbadagi vaqt tamg'asi (src_ts)."""

from datetime import datetime, timedelta, timezone

import pytest
from conftest import ingest_headers, ws_ticket
from ges_server.db import SessionLocal
from ges_server.monitoring import historian, twin
from ges_server.orm import Reading, ReadingHourly, Sensor


@pytest.fixture
def power(client, users):
    r = client.post(
        f"/api/projects/{users['project_id']}/sensors",
        json={"key": "AGG1.P", "name": "Agregat 1", "kind": "power", "unit": "MW", "high_alarm": 30},
        headers=users["engineer"],
    )
    assert r.status_code == 201, r.text
    return r.json()


def _sensor(client, users, key):
    rows = client.get(f"/api/projects/{users['project_id']}/sensors", headers=users["viewer"]).json()
    return next(s for s in rows if s["key"] == key)


def _push(client, users, items):
    r = client.post(
        f"/api/projects/{users['project_id']}/readings", json=items, headers=ingest_headers(client, users)
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_bad_quality_is_stored_but_does_not_change_state_or_alarm(client, users, power):
    pid = users["project_id"]
    assert _push(client, users, [{"key": "AGG1.P", "value": 20}]) == {
        "accepted": 1,
        "unknown": [],
        "bad": 0,
        "rejected": [],
    }
    # bad sifatli, alarm chegarasidan yuqori qiymat: tarixga yoziladi, holat o'zgarmaydi
    r = _push(client, users, [{"key": "AGG1.P", "value": 99, "quality": "bad"}])
    assert r == {"accepted": 1, "unknown": [], "bad": 1, "rejected": []}
    s = _sensor(client, users, "AGG1.P")
    assert s["last_value"] == 20 and s["alarm"] == "ok" and s["last_quality"] == "good"
    assert client.get(f"/api/projects/{pid}/alarms", headers=users["viewer"]).json() == []
    with SessionLocal() as db:
        rows = db.query(Reading).filter_by(sensor_id=power["id"]).order_by(Reading.id).all()
        assert [r.quality for r in rows] == ["good", "bad"] and rows[1].value == 99
    # uncertain: holat yangilanadi, sifat ko'rinadi, alarm baholanadi
    _push(client, users, [{"key": "AGG1.P", "value": 35, "quality": "uncertain"}])
    s = _sensor(client, users, "AGG1.P")
    assert s["last_value"] == 35 and s["alarm"] == "high" and s["last_quality"] == "uncertain"
    # noma'lum sifat → good
    _push(client, users, [{"key": "AGG1.P", "value": 21, "quality": "whatever"}])
    s = _sensor(client, users, "AGG1.P")
    assert s["last_quality"] == "good" and s["alarm"] == "ok"


def test_src_ts_stored_and_exported(client, users, power):
    src = "2026-03-01T10:00:00+00:00"
    _push(client, users, [{"key": "AGG1.P", "value": 5, "src_ts": src}])
    with SessionLocal() as db:
        r = db.query(Reading).filter_by(sensor_id=power["id"]).one()
        assert r.src_ts is not None and r.src_ts.replace(tzinfo=timezone.utc).isoformat() == src
    csv = client.get(f"/api/sensors/{power['id']}/export.csv", headers=users["viewer"]).text
    assert csv.splitlines()[0] == "ts,value_MW,quality,src_ts"
    assert csv.splitlines()[1].endswith(f",5.0,good,{src}")


def test_rollup_excludes_bad_and_reports_pct_good(client, users, power):
    now = datetime.now(timezone.utc)
    hour = (now - timedelta(hours=3)).replace(minute=0, second=0, microsecond=0)
    items = []
    for i in range(6):
        q = "bad" if i == 5 else ("uncertain" if i == 4 else "good")
        items.append(
            {
                "key": "AGG1.P",
                "value": 1000 if q == "bad" else 10 + i,
                "ts": (hour + timedelta(minutes=10 * i)).isoformat(),
                "quality": q,
            }
        )
    _push(client, users, items)
    with SessionLocal() as db:
        assert historian.rollup(db) == 1
        h = db.query(ReadingHourly).filter_by(sensor_id=power["id"]).one()
        assert h.n == 5 and h.n_bad == 1 and h.max == 14 and abs(h.pct_good - 4 / 6) < 1e-9
        s = db.get(Sensor, power["id"])
        st = historian.sensor_stats(db, s, hour, hour + timedelta(hours=1))
        assert st["max"] == 14  # bad (1000) hisobga olinmaydi
        snap = {x["key"]: x for x in twin.snapshot(db, users["project_id"], hour + timedelta(hours=1))}
        assert snap["AGG1.P"]["value"] == 14 and snap["AGG1.P"]["quality"] == "uncertain"
    pts = client.get(
        f"/api/sensors/{power['id']}/readings?hours=168", headers=users["viewer"]
    ).json()["points"]
    assert pts and pts[0]["pct_good"] < 1 and pts[0]["max"] == 14


def test_only_bad_hour_writes_no_aggregate(client, users, power):
    hour = (datetime.now(timezone.utc) - timedelta(hours=3)).replace(
        minute=0, second=0, microsecond=0
    )
    _push(
        client,
        users,
        [{"key": "AGG1.P", "value": 1, "ts": hour.isoformat(), "quality": "bad"}],
    )
    with SessionLocal() as db:
        assert historian.rollup(db) == 0
        assert db.query(ReadingHourly).count() == 0


def test_websocket_snapshot_carries_quality(client, users, power):
    _push(client, users, [{"key": "AGG1.P", "value": 7, "quality": "manual"}])
    token = ws_ticket(client, users["viewer"])
    with client.websocket_connect(f"/api/projects/{users['project_id']}/live?ticket={token}") as ws:
        snap = ws.receive_json()
        assert snap["type"] == "snapshot"
        assert [s["quality"] for s in snap["sensors"] if s["key"] == "AGG1.P"] == ["manual"]
