"""SCADA darajasi: alarm jurnali + kvitlash, bildirishnomalar, historian, dispetcher paneli,
hisobot, audit ko'rish."""

from datetime import datetime, timedelta, timezone

import pytest
from ges_server.db import SessionLocal
from ges_server.monitoring import background, historian
from ges_server.orm import Reading, ReadingHourly, Sensor


@pytest.fixture
def power(client, users):
    pid = users["project_id"]
    r = client.post(
        f"/api/projects/{pid}/sensors",
        json={
            "key": "AGG1.P",
            "name": "Agregat 1",
            "kind": "power",
            "unit": "MW",
            "high_alarm": 30,
            "low_alarm": 5,
        },
        headers=users["engineer"],
    )
    assert r.status_code == 201, r.text
    return r.json()


def _push(client, users, items):
    r = client.post(
        f"/api/projects/{users['project_id']}/readings", json=items, headers=users["engineer"]
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_alarm_journal_ack_and_notifications(client, users, power):
    pid = users["project_id"]
    # normal → jurnalda hech narsa
    _push(client, users, [{"key": "AGG1.P", "value": 20}])
    assert (
        client.get(f"/api/projects/{pid}/alarm-events?active=true", headers=users["viewer"]).json()
        == []
    )
    # yuqori → hodisa ochiladi, hamma a'zoga bildirishnoma
    _push(client, users, [{"key": "AGG1.P", "value": 35}])
    ev = client.get(f"/api/projects/{pid}/alarm-events?active=true", headers=users["viewer"]).json()
    assert (
        len(ev) == 1
        and ev[0]["state"] == "high"
        and ev[0]["value"] == 35
        and ev[0]["ended_at"] is None
    )
    n = client.get("/api/notifications?unread=true", headers=users["viewer"]).json()
    assert (
        n
        and n[0]["kind"] == "alarm"
        and "Agregat 1" in n[0]["title"]
        and n[0]["link"].endswith("/dashboard")
    )
    assert client.get("/api/notifications/count", headers=users["viewer"]).json()["unread"] == 1
    # bir xil holatda qolsa yangi hodisa ochilmaydi
    _push(client, users, [{"key": "AGG1.P", "value": 36}])
    assert (
        len(
            client.get(
                f"/api/projects/{pid}/alarm-events?active=true", headers=users["viewer"]
            ).json()
        )
        == 1
    )
    # normalga qaytdi → yopildi, lekin kvitlanmagani uchun hali "faol" ro'yxatda
    _push(client, users, [{"key": "AGG1.P", "value": 20}])
    ev = client.get(f"/api/projects/{pid}/alarm-events?active=true", headers=users["viewer"]).json()
    assert len(ev) == 1 and ev[0]["ended_at"] is not None and ev[0]["acked_at"] is None
    # viewer kvitlay olmaydi, muhandis kvitlaydi
    assert (
        client.post(
            f"/api/alarm-events/{ev[0]['id']}/ack",
            json={"comment": "ko'rdim"},
            headers=users["viewer"],
        ).status_code
        == 403
    )
    r = client.post(
        f"/api/alarm-events/{ev[0]['id']}/ack",
        json={"comment": "ko'rdim"},
        headers=users["engineer"],
    )
    assert (
        r.status_code == 200
        and r.json()["acked_by"] == users["ids"]["engineer"]
        and r.json()["comment"] == "ko'rdim"
    )
    assert (
        client.get(f"/api/projects/{pid}/alarm-events?active=true", headers=users["viewer"]).json()
        == []
    )
    hist = client.get(f"/api/projects/{pid}/alarm-events", headers=users["viewer"]).json()
    assert len(hist) == 1
    # past → yangi hodisa; ack-all
    _push(client, users, [{"key": "AGG1.P", "value": 1}])
    assert (
        client.post(f"/api/projects/{pid}/alarm-events/ack-all", headers=users["engineer"]).json()[
            "acked"
        ]
        == 1
    )
    # bildirishnomalarni o'qilgan qilish
    assert (
        client.post("/api/notifications/read", json={"ids": None}, headers=users["viewer"]).json()[
            "read"
        ]
        == 2
    )
    assert client.get("/api/notifications/count", headers=users["viewer"]).json()["unread"] == 0


def test_stale_event_from_background_tick(client, users, power):
    pid = users["project_id"]
    client.patch(
        f"/api/sensors/{power['id']}", json={"stale_after_s": 1}, headers=users["engineer"]
    )
    old = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    _push(client, users, [{"key": "AGG1.P", "value": 20, "ts": old}])
    assert background.tick_stale() >= 1
    ev = client.get(f"/api/projects/{pid}/alarm-events?active=true", headers=users["viewer"]).json()
    assert ev and ev[0]["state"] == "stale"


def test_historian_rollup_purge_and_long_range(client, users, power):
    now = datetime.now(timezone.utc)
    # 5 kunlik, 10 daqiqalik xom ma'lumot
    items = [
        {
            "key": "AGG1.P",
            "value": 10 + (i % 6),
            "ts": (now - timedelta(days=5) + timedelta(minutes=10 * i)).isoformat(),
        }
        for i in range(5 * 24 * 6)
    ]
    _push(client, users, items[:5000])
    _push(client, users, items[5000:])
    with SessionLocal() as db:
        written = historian.rollup(db)
        assert written >= 5 * 24 - 2
        hourly = db.query(ReadingHourly).filter_by(sensor_id=power["id"]).all()
        assert all(h.n == 6 for h in hourly[1:-1]) and abs(hourly[5].avg - 12.5) < 1e-6
        # retention 2 kun: eski xomlar o'chadi, soatlik qoladi
        purged = historian.purge(db, retention_days=2)
        assert purged > 0
        assert db.query(Reading).filter(Reading.sensor_id == power["id"]).count() < len(items)
        # kun statistikasi: energiya ≈ o'rtacha quvvat × 24 soat
        s = db.get(Sensor, power["id"])
        st = historian.sensor_stats(db, s, now - timedelta(days=4), now - timedelta(days=3))
        assert st["n"] > 0 and 12 * 24 * 0.95 < st["energy_mwh"] < 13 * 24 * 1.05
    # 7 kunlik so'rov — soatlik agregatdan (hourly=True), oxirgi soat xomdan
    r = client.get(f"/api/sensors/{power['id']}/readings?hours=168", headers=users["viewer"]).json()
    assert r["hourly"] is True and r["total"] >= 5 * 24 - 2
    # CSV eksport
    r = client.get(f"/api/sensors/{power['id']}/export.csv?hours=24", headers=users["viewer"])
    assert r.status_code == 200 and r.text.startswith("ts,value_MW")


def test_dashboard_and_report(client, users, power):
    pid = users["project_id"]
    r = client.post(
        f"/api/projects/{pid}/sensors",
        json={"key": "RES.H", "name": "Yuqori byef", "kind": "level", "unit": "m"},
        headers=users["engineer"],
    )
    level_id = r.json()["id"]
    now = datetime.now(timezone.utc)
    _push(
        client,
        users,
        [
            {"key": "AGG1.P", "value": 24, "ts": (now - timedelta(hours=h)).isoformat()}
            for h in range(0, 13)
        ]
        + [{"key": "RES.H", "value": 890.5}],
    )
    d = client.get(f"/api/projects/{pid}/dashboard", headers=users["viewer"]).json()
    assert {s["key"] for s in d["sensors"]} == {"AGG1.P", "RES.H"}
    # "Yuqori byef" → yuqori byef sloti; AGG1 → agregat 1 (nom/kalit belgilari), umumiy quvvat bo'sh
    assert d["mimic"]["upstream_level"] == level_id and d["mimic"]["unit1_power"] == power["id"]
    assert "total_power" not in d["mimic"]
    assert d["energy_24h_mwh"] is not None and d["energy_24h_mwh"] > 0
    assert d["active_alarms"] == 0 and any(s["slot"] == "unit1_power" for s in d["slots"])
    # sozlash: muhandis; noto'g'ri sensor rad
    assert (
        client.put(
            f"/api/projects/{pid}/dashboard",
            json={"mimic": {"unit1_power": 999}},
            headers=users["engineer"],
        ).status_code
        == 400
    )
    assert (
        client.put(
            f"/api/projects/{pid}/dashboard",
            json={"mimic": {"unit1_power": power["id"]}, "tiles": [level_id]},
            headers=users["viewer"],
        ).status_code
        == 403
    )
    r = client.put(
        f"/api/projects/{pid}/dashboard",
        json={"mimic": {"unit1_power": power["id"]}, "tiles": [level_id]},
        headers=users["engineer"],
    )
    assert r.status_code == 200
    d = client.get(f"/api/projects/{pid}/dashboard", headers=users["viewer"]).json()
    assert d["mimic"]["unit1_power"] == power["id"] and d["tiles"] == [level_id]
    # hisobot: kun (JSON) va CSV
    rep = client.get(f"/api/projects/{pid}/report?period=day", headers=users["viewer"]).json()
    p = next(s for s in rep["sensors"] if s["key"] == "AGG1.P")
    assert p["avg"] == 24 and rep["energy_mwh"] > 0 and rep["alarms"]["count"] == 0
    csv = client.get(f"/api/projects/{pid}/report?period=month&format=csv", headers=users["viewer"])
    assert (
        csv.status_code == 200
        and "AGG1.P" in csv.text
        and csv.headers["content-type"].startswith("text/csv")
    )
    assert (
        client.get(f"/api/projects/{pid}/report?date=xx", headers=users["viewer"]).status_code
        == 400
    )


def test_review_notifications(client, users, ifc_file):
    from conftest import upload

    pid = users["project_id"]
    mid = client.post(
        f"/api/projects/{pid}/models", json={"name": "M"}, headers=users["engineer"]
    ).json()["id"]
    v = upload(client, users["engineer"], mid, ifc_file, "v1").json()
    cr = client.post(
        f"/api/models/{mid}/change-requests",
        json={"version_id": v["id"], "title": "T"},
        headers=users["engineer"],
    ).json()
    n = client.get("/api/notifications?unread=true", headers=users["approver"]).json()
    assert (
        n
        and n[0]["kind"] == "review"
        and f"#{cr['id']}" in n[0]["title"]
        and n[0]["link"] == f"/models/{mid}?v={v['id']}"
    )
    assert client.get("/api/notifications/count", headers=users["engineer"]).json()["unread"] == 0
    client.post(
        f"/api/change-requests/{cr['id']}/reviews",
        json={"decision": "approve", "comment": "OK"},
        headers=users["approver"],
    )
    n = client.get("/api/notifications?unread=true", headers=users["engineer"]).json()
    assert n and "ma'qulladi" in n[0]["title"]
    client.post(f"/api/change-requests/{cr['id']}/merge", headers=users["approver"])
    n = client.get("/api/notifications?unread=true", headers=users["viewer"]).json()
    assert n and n[0]["title"].startswith("Tasdiqlandi")
    # issue tayinlash
    client.post(
        f"/api/models/{mid}/issues",
        json={"title": "I", "assignee_id": users["ids"]["viewer"]},
        headers=users["engineer"],
    )
    n = client.get("/api/notifications?unread=true", headers=users["viewer"]).json()
    assert any(x["kind"] == "issue" for x in n)


def test_audit_view_permissions(client, users, admin, power):
    pid = users["project_id"]
    rows = client.get("/api/audit", headers=admin).json()
    assert any(r["action"] == "sensor.create" for r in rows) and rows[0]["username"]
    assert client.get("/api/audit", headers=users["approver"]).status_code == 403
    rows = client.get(
        f"/api/audit?project_id={pid}&action=sensor.", headers=users["approver"]
    ).json()
    assert rows and all(r["action"].startswith("sensor.") for r in rows)
    assert client.get(f"/api/audit?project_id={pid}", headers=users["engineer"]).status_code == 403


def test_dashboard_scheme_saved_and_validated(client, users, power):
    """F3: mimika sxemasi (JSON) saqlanadi, sensor id lari va agregat soni tekshiriladi."""
    pid = users["project_id"]
    scheme = {
        "version": 1,
        "units": 2,
        "elements": [
            {"id": "unit1", "type": "unit", "x": 500, "y": 272, "unit": 1, "sensor_id": power["id"], "extra": {"run": None}},
            {"id": "unit2", "type": "unit", "x": 580, "y": 272, "unit": 2},
            {"id": "upstream_level", "type": "value", "x": 130, "y": 128, "label": "Sath"},
        ],
    }
    r = client.put(f"/api/projects/{pid}/dashboard", json={"mimic": {}, "tiles": [], "scheme": scheme}, headers=users["engineer"])
    assert r.status_code == 200, r.text
    d = client.get(f"/api/projects/{pid}/dashboard", headers=users["viewer"]).json()
    assert d["scheme"]["units"] == 2 and [e["id"] for e in d["scheme"]["elements"]] == ["unit1", "unit2", "upstream_level"]
    assert d["scheme"]["elements"][0]["sensor_id"] == power["id"]
    # sxemasiz PUT eski sxemani saqlab qoladi
    client.put(f"/api/projects/{pid}/dashboard", json={"mimic": {}, "tiles": []}, headers=users["engineer"])
    assert client.get(f"/api/projects/{pid}/dashboard", headers=users["viewer"]).json()["scheme"]["units"] == 2
    # yo'q sensor → 400; agregat soni mos emas → 400; takror id → 422; noma'lum tur → 422
    bad = {**scheme, "elements": [{**scheme["elements"][0], "sensor_id": 99999}] + scheme["elements"][1:]}
    assert client.put(f"/api/projects/{pid}/dashboard", json={"mimic": {}, "tiles": [], "scheme": bad}, headers=users["engineer"]).status_code == 400
    assert client.put(f"/api/projects/{pid}/dashboard", json={"mimic": {}, "tiles": [], "scheme": {**scheme, "units": 3}}, headers=users["engineer"]).status_code == 400
    dup = {**scheme, "elements": scheme["elements"] + [scheme["elements"][2]]}
    assert client.put(f"/api/projects/{pid}/dashboard", json={"mimic": {}, "tiles": [], "scheme": dup}, headers=users["engineer"]).status_code == 422
    odd = {**scheme, "elements": scheme["elements"] + [{"id": "x", "type": "rocket", "x": 1, "y": 1}]}
    assert client.put(f"/api/projects/{pid}/dashboard", json={"mimic": {}, "tiles": [], "scheme": odd}, headers=users["engineer"]).status_code == 422
    # viewer saqlay olmaydi
    assert client.put(f"/api/projects/{pid}/dashboard", json={"mimic": {}, "tiles": [], "scheme": scheme}, headers=users["viewer"]).status_code == 403


def test_dashboard_pen_groups(client, users, power):
    """F7: trend qalam guruhlari (nom → sensorlar) dashboard konfiguratsiyasida; sensor id tekshiriladi."""
    pid = users["project_id"]
    r = client.put(f"/api/projects/{pid}/dashboard", json={"mimic": {}, "tiles": [], "pen_groups": [{"name": "Agregat 1", "sensor_ids": [power["id"]]}]}, headers=users["engineer"])
    assert r.status_code == 200, r.text
    d = client.get(f"/api/projects/{pid}/dashboard", headers=users["viewer"]).json()
    assert d["pen_groups"] == [{"name": "Agregat 1", "sensor_ids": [power["id"]]}]
    client.put(f"/api/projects/{pid}/dashboard", json={"mimic": {}, "tiles": []}, headers=users["engineer"])  # None — saqlanadi
    assert client.get(f"/api/projects/{pid}/dashboard", headers=users["viewer"]).json()["pen_groups"][0]["name"] == "Agregat 1"
    assert client.put(f"/api/projects/{pid}/dashboard", json={"mimic": {}, "tiles": [], "pen_groups": [{"name": "x", "sensor_ids": [99999]}]}, headers=users["engineer"]).status_code == 400
    assert client.put(f"/api/projects/{pid}/dashboard", json={"mimic": {}, "tiles": [], "pen_groups": [{"name": "x", "sensor_ids": list(range(1, 9))}]}, headers=users["engineer"]).status_code == 422
