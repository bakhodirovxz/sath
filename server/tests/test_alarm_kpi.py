"""C4: EEMUA-191 alarm KPI — yuk, cho'qqi/toshqin, turg'un, chattering, ustuvorlik, eng yomon 10, kvitlash."""

from datetime import datetime, timedelta, timezone

from ges_server.db import SessionLocal
from ges_server.monitoring import alarm_kpi
from ges_server.orm import AlarmEvent, AlarmState, Sensor


def _seed(pid: int, now: datetime):
    """Sun'iy jurnal: 5 sensor; S1 chattering (soatda 6), S2 turg'un (30 soat), 12 ta toshqin bir daqiqada."""
    with SessionLocal() as db:
        sids = []
        for i, prio in enumerate(("low", "low", "medium", "high", "critical")):
            s = Sensor(project_id=pid, key=f"S{i + 1}", name=f"S{i + 1}", kind="value", unit="", priority=prio, high_alarm=1.0)
            db.add(s)
            db.flush()
            sids.append(s.id)
        add = lambda sid, t, **kw: db.add(AlarmEvent(project_id=pid, sensor_id=sid, state=AlarmState.high, value=2.0, started_at=t, **kw))  # noqa: E731
        base = now - timedelta(hours=5)
        for k in range(6):  # S1: 6 ta 40 daqiqa ichida — chattering
            add(sids[0], base + timedelta(minutes=8 * k), ended_at=base + timedelta(minutes=8 * k + 2), acked_at=base + timedelta(minutes=8 * k + 1))
        add(sids[1], now - timedelta(hours=30))  # turg'un, ochiq (oynadan tashqarida boshlangan)
        for k in range(12):  # toshqin: 12 ta bir daqiqada (S3/S4 navbatma-navbat)
            add(sids[2 + k % 2], now - timedelta(hours=2, seconds=5 * k), ended_at=now - timedelta(hours=1))
        add(sids[4], now - timedelta(minutes=30), acked_at=now - timedelta(minutes=20))  # kritik, 10 daqiqada kvitlangan
        add(sids[4], now - timedelta(minutes=15), suppressed="shelved")  # bostirilgan — hisobga kirmaydi
        db.commit()
    return sids


def test_kpi_metrics_and_eemua_rating(client, users):
    pid = users["project_id"]
    now = datetime.now(timezone.utc).replace(microsecond=0)
    sids = _seed(pid, now)
    r = client.get(f"/api/projects/{pid}/alarms/kpi?hours=24", headers=users["viewer"])
    assert r.status_code == 200, r.text
    k = r.json()
    assert k["total"] == 19 and k["suppressed"] == {"shelved": 1}
    assert abs(k["per_hour"] - 19 / 24) < 0.01 and k["rating"] == "acceptable"
    assert k["peak_10min"] == 12 and k["flood_time_pct"] > 0 and k["flood_now"] is False
    assert [s["key"] for s in k["standing"]] == ["S2"] and k["standing"][0]["hours"] >= 29
    assert k["chattering"] and k["chattering"][0]["key"] == "S1" and k["chattering"][0]["peak_per_hour"] == 6
    assert k["priority_pct"]["low"] == round(100 * 6 / 19, 1) and k["priority_pct"]["critical"] == round(100 / 19, 1)
    assert k["top10"][0]["key"] in ("S1", "S3", "S4") and k["top10"][0]["count"] == 6
    assert k["top10_share_pct"] == 100.0
    assert k["ack_mean_s"] and 60 <= k["ack_median_s"] <= 600
    assert k["unacked_active"] == 1  # S2
    assert any("Toshqin" in v for v in k["verdicts"]) and any("turg'un" in v for v in k["verdicts"]) and any("chattering" in v for v in k["verdicts"])
    assert sids[1] == k["standing"][0]["sensor_id"]
    # tor oyna: toshqin ichida — yuk qabul qilib bo'lmaydigan darajada
    with SessionLocal() as db:
        kk = alarm_kpi.kpi(db, pid, now - timedelta(hours=2, minutes=5), now - timedelta(hours=1, minutes=55), now)
    assert kk["total"] == 12 and kk["rating"] == "unacceptable" and kk["per_10min"] == 12.0


def test_flood_now_flag_on_dashboard(client, users):
    pid = users["project_id"]
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        s = Sensor(project_id=pid, key="X", name="X", kind="value", unit="", high_alarm=1.0)
        db.add(s)
        db.flush()
        for k in range(11):
            db.add(AlarmEvent(project_id=pid, sensor_id=s.id, state=AlarmState.high, value=2.0, started_at=now - timedelta(seconds=10 * k)))
        db.commit()
        assert alarm_kpi.flood_now(db, pid, now) == (True, 11)
    d = client.get(f"/api/projects/{pid}/dashboard", headers=users["viewer"]).json()
    assert d["alarm_flood"] is True
    assert alarm_kpi.rate_rating(0.5)[0] == "acceptable" and alarm_kpi.rate_rating(1.5)[0] == "manageable"
    assert alarm_kpi.rate_rating(3)[0] == "over_demanding" and alarm_kpi.rate_rating(11)[0] == "unacceptable"
