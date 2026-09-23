"""D2: qatlamlar (1m/10m/1h) SQL GROUP BY bilan, 1 mln qatorli sensorda rollup xotirasi, kech kelgan
ma'lumot, partiyali purge (alarm atrofi saqlanadi), qatlam muddati, arxiv siqishi (deadband), grafik qatlami."""

import tracemalloc
from datetime import datetime, timedelta, timezone

from conftest import ingest_headers
from ges_server.db import SessionLocal, engine
from ges_server.monitoring import historian, live
from ges_server.orm import AlarmEvent, AlarmState, Reading, ReadingAgg, ReadingHourly, Sensor


def _sensor(client, users, key="AGG1.P", **kw):
    r = client.post(
        f"/api/projects/{users['project_id']}/sensors",
        json={"key": key, "name": key, "kind": "power", "unit": "MW", **kw},
        headers=users["engineer"],
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _bulk_raw(sid: int, start: datetime, n: int, step_s: int, value=lambda i: 10.0 + (i % 6)):
    """Xom qatorlarni to'g'ridan-to'g'ri (ingest siz) partiyalab yozadi."""
    with SessionLocal() as db:
        for off in range(0, n, 50_000):
            rows = [
                {"sensor_id": sid, "ts": start + timedelta(seconds=step_s * i), "value": value(i), "quality": "good", "src_ts": None}
                for i in range(off, min(n, off + 50_000))
            ]
            live._bulk_insert_readings(db, rows)
            db.commit()


def test_rollup_one_million_rows_bounded_memory(client, users):
    sid = _sensor(client, users)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    n = 1_000_000
    start = now - timedelta(seconds=n)  # 1 s qadam → ~11.6 kun
    _bulk_raw(sid, start, n, 1)
    tracemalloc.start()
    with SessionLocal() as db:
        base = tracemalloc.get_traced_memory()[0]
        written = historian.rollup(db, now)
        peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert written >= 11 * 24
    assert peak - base < 120 * 1024 * 1024, f"rollup xotirasi {(peak - base) / 1e6:.0f} MB — xom qatorlar RAM ga yuklanmasligi kerak"
    with SessionLocal() as db:
        h = db.query(ReadingHourly).filter_by(sensor_id=sid).order_by(ReadingHourly.hour).all()
        assert all(x.n == 3600 for x in h[1:-1]) and abs(h[5].avg - 12.5) < 1e-6
        # 1m qatlam: bitta tickda 4 kun (4 × 1 kun oyna), qolgani keyingi ticklarda
        m1 = db.query(ReadingAgg).filter_by(sensor_id=sid, tier="1m").count()
        assert 4 * 1440 - 2 <= m1 <= 4 * 1440 + 2
        assert db.query(ReadingAgg).filter_by(sensor_id=sid, tier="10m").count() >= 11 * 144 - 2
        wm = historian.watermark(db, "1m")
        assert wm is not None and wm < now
        historian.rollup(db, now)  # davom etadi
        assert db.query(ReadingAgg).filter_by(sensor_id=sid, tier="1m").count() > m1


def test_late_data_recomputed_and_only_bad_bucket_skipped(client, users):
    sid = _sensor(client, users)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    hour = now - timedelta(hours=2)
    _bulk_raw(sid, hour, 6, 600, value=lambda i: 10.0)
    with SessionLocal() as db:
        assert historian.rollup(db, now) == 1
        assert db.query(ReadingHourly).filter_by(sensor_id=sid).one().avg == 10.0
        # kech kelgan ma'lumot (lookback ichida) → soat qayta hisoblanadi
        live._bulk_insert_readings(db, [{"sensor_id": sid, "ts": hour + timedelta(minutes=5), "value": 40.0, "quality": "good", "src_ts": None}])
        db.commit()
        assert historian.rollup(db, now + timedelta(hours=1)) == 0  # yangi soat yo'q, lekin qayta hisob
        h = db.query(ReadingHourly).filter_by(sensor_id=sid).one()
        assert h.n == 7 and abs(h.avg - (60 + 40) / 7) < 1e-6
        # faqat bad bo'lak yozilmaydi
        live._bulk_insert_readings(db, [{"sensor_id": sid, "ts": hour + timedelta(hours=1, minutes=1), "value": 1.0, "quality": "bad", "src_ts": None}])
        db.commit()
        historian.rollup(db, now + timedelta(hours=1))
        assert db.query(ReadingHourly).filter_by(sensor_id=sid).count() == 1
        assert db.query(ReadingAgg).filter_by(sensor_id=sid, tier="1m").count() == 7  # 0,10,…,50 daq + kech kelgan 5 daq


def test_purge_batches_and_keeps_raw_around_alarms(client, users):
    sid = _sensor(client, users)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(days=10)
    _bulk_raw(sid, start, 10 * 24 * 60, 60)  # 10 kun, daqiqalik
    alarm_at = start + timedelta(days=3)
    with SessionLocal() as db:
        db.add(AlarmEvent(project_id=users["project_id"], sensor_id=sid, state=AlarmState.high, value=99, started_at=alarm_at, ended_at=alarm_at + timedelta(minutes=30)))
        db.commit()
        historian.rollup(db, now)
        purged = historian.purge(db, retention_days=5, now=now, batch=1000, max_batches=3)
        assert purged <= 3000  # partiyalab — bitta tickda ko'pi bilan 3 × 1000
        total = purged
        for _ in range(20):
            p = historian.purge(db, retention_days=5, now=now, batch=1000, max_batches=3)
            total += p
            if p == 0:
                break
        left = db.query(Reading).filter(Reading.sensor_id == sid, Reading.ts < now - timedelta(days=5)).order_by(Reading.ts).all()
        # faqat alarm atrofi (±1 soat + 30 daq hodisa = 150 daqiqa ≈ 151 qator) qoladi
        assert 149 <= len(left) <= 152
        assert all(alarm_at - timedelta(hours=1) <= live._aware(r.ts) <= alarm_at + timedelta(minutes=90) for r in left)
        assert total + len(left) == 5 * 24 * 60
        # takroriy purge himoyalanganlarni qayta o'chirmaydi va sekin emas (kursor)
        assert historian.purge(db, retention_days=5, now=now) == 0
        # qatlam muddati
        assert db.query(ReadingAgg).filter_by(tier="1m").count() > 0
        n_old = historian.purge_agg(db, "1m", retention_days=7, now=now)
        assert n_old > 0 and db.query(ReadingAgg).filter(ReadingAgg.tier == "1m", ReadingAgg.bucket < now - timedelta(days=7)).count() == 0


def test_archive_deadband_compression(client, users):
    pid = users["project_id"]
    sid = _sensor(client, users, archive_deadband=0.5, archive_max_interval_s=60)
    t0 = datetime.now(timezone.utc) - timedelta(minutes=10)
    items = [{"key": "AGG1.P", "value": v, "ts": (t0 + timedelta(seconds=10 * i)).isoformat()} for i, v in enumerate([10.0, 10.1, 10.2, 10.4, 10.6, 10.7, 10.65])]
    r = client.post(f"/api/projects/{pid}/readings", json=items, headers=ingest_headers(client, users))
    assert r.status_code == 200 and r.json()["accepted"] == 7
    with SessionLocal() as db:
        vals = [x.value for x in db.query(Reading).filter_by(sensor_id=sid).order_by(Reading.ts)]
        assert vals == [10.0, 10.6]  # 10.1..10.4 o'lik zonada; 10.6 ≥ 0.5 farq; keyingilar yana zonada
        s = db.get(Sensor, sid)
        assert s.last_value == 10.65 and s.last_archived_value == 10.6  # holat baribir yangilanadi
    # majburiy yozuv: max_interval (60 s) o'tgach o'zgarish kichik bo'lsa ham yoziladi; bad har doim
    later = t0 + timedelta(seconds=130)
    client.post(f"/api/projects/{pid}/readings", json=[{"key": "AGG1.P", "value": 10.66, "ts": later.isoformat()}, {"key": "AGG1.P", "value": 10.66, "ts": (later + timedelta(seconds=5)).isoformat(), "quality": "bad"}], headers=ingest_headers(client, users))
    with SessionLocal() as db:
        rows = db.query(Reading).filter_by(sensor_id=sid).order_by(Reading.ts).all()
        assert [x.value for x in rows] == [10.0, 10.6, 10.66, 10.66] and rows[-1].quality == "bad"
    r = client.patch(f"/api/sensors/{sid}", json={"clear_archive_deadband": True}, headers=users["engineer"])
    assert r.json()["archive_deadband"] is None


def test_readings_endpoint_uses_tiers(client, users):
    sid = _sensor(client, users)
    now = datetime.now(timezone.utc)
    _bulk_raw(sid, now - timedelta(hours=30), 30 * 60, 60)
    with SessionLocal() as db:
        historian.rollup(db, now)
    r = client.get(f"/api/sensors/{sid}/readings?hours=24", headers=users["viewer"]).json()
    assert r["tier"] == "1m" and r["hourly"] is False and 24 * 60 - 3 <= r["total"] <= 24 * 60 + 1
    r = client.get(f"/api/sensors/{sid}/readings?hours=72", headers=users["viewer"]).json()
    assert r["tier"] == "10m" and r["total"] >= 30 * 6 - 2
    r = client.get(f"/api/sensors/{sid}/readings?hours=168", headers=users["viewer"]).json()
    assert r["tier"] == "1h" and r["hourly"] is True and r["total"] >= 29
    r = client.get(f"/api/sensors/{sid}/readings?hours=2", headers=users["viewer"]).json()
    assert r["tier"] == "raw" and 118 <= r["total"] <= 121
    assert historian.tier_for_span(6) == "raw" and historian.tier_for_span(48) == "1m" and historian.tier_for_span(96) == "10m"
    assert engine.dialect.name in ("sqlite", "postgresql")


def _import_csv(client, users, sid, start: datetime, n: int, step_s: int, value: float):
    body = "ts,value\n" + "".join(
        f"{(start + timedelta(seconds=step_s * i)).isoformat()},{value}\n" for i in range(n)
    )
    r = client.post(
        f"/api/sensors/{sid}/import",
        files={"file": ("old.csv", body.encode(), "text/csv")},
        headers=users["engineer"],
    )
    assert r.status_code == 200 and r.json()["accepted"] == n, r.text


def test_old_import_aggregated_before_purge_no_data_loss(client, users):
    """SCADA-10: suv belgisidan (lookback dan) eski tarixiy import → rollup qayta yig'adi, purge
    xomni faqat agregat yozilgandan keyin o'chiradi."""
    from ges_server.orm import HistorianDirty

    sid = _sensor(client, users, key="OLD.IMPORT")
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    _bulk_raw(sid, now - timedelta(hours=2), 6, 600, value=lambda i: 1.0)
    with SessionLocal() as db:
        historian.rollup(db, now)  # suv belgilari `now` ga yetadi, skaner kursori o'rnatiladi
        assert historian.watermark(db, "1h") == now
    old_hour = now - timedelta(days=10)
    _import_csv(client, users, sid, old_hour, 6, 600, 7.0)
    with SessionLocal() as db:
        # rollup dan OLDIN purge: hali skanerlanmagan qatorlar o'chirilmaydi
        historian.purge(db, retention_days=1, now=now)
        assert db.query(Reading).filter(Reading.sensor_id == sid, Reading.ts < now - timedelta(days=5)).count() == 6
        historian.rollup(db, now)
        h = db.query(ReadingHourly).filter_by(sensor_id=sid, hour=old_hour).one()
        assert h.n == 6 and h.avg == 7.0
        assert db.query(ReadingAgg).filter_by(sensor_id=sid, tier="10m").filter(ReadingAgg.bucket < now - timedelta(days=5)).count() == 6
        assert db.query(HistorianDirty).filter_by(sensor_id=sid).count() == 0
        purged = historian.purge(db, retention_days=1, now=now)
        assert purged >= 6
        assert db.query(Reading).filter(Reading.sensor_id == sid, Reading.ts < now - timedelta(days=5)).count() == 0
        # agregat saqlanib qoldi — ma'lumot yo'qolmadi
        assert db.query(ReadingHourly).filter_by(sensor_id=sid, hour=old_hour).one().avg == 7.0


def test_dirty_range_protected_from_purge_until_processed(client, users):
    from ges_server.orm import HistorianDirty

    sid = _sensor(client, users, key="OLD.DIRTY")
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    _bulk_raw(sid, now - timedelta(hours=2), 2, 600, value=lambda i: 1.0)
    with SessionLocal() as db:
        historian.rollup(db, now)
    old = now - timedelta(days=20)
    _bulk_raw(sid, old, 4, 900, value=lambda i: 3.0)
    with SessionLocal() as db:
        historian.scan_late(db)  # aniqlaydi, lekin hali qayta yig'maydi
        assert db.query(HistorianDirty).filter_by(sensor_id=sid, tier="1h").count() == 1
        historian.purge(db, retention_days=1, now=now)
        assert db.query(Reading).filter(Reading.sensor_id == sid, Reading.ts < now - timedelta(days=5)).count() == 4
        historian.process_dirty(db)
        assert db.query(ReadingHourly).filter_by(sensor_id=sid, hour=old).one().n == 4
        historian.purge(db, retention_days=1, now=now)
        assert db.query(Reading).filter(Reading.sensor_id == sid, Reading.ts < now - timedelta(days=5)).count() == 0
    # mark_dirty — lookback ichidagi ma'lumot uchun belgilanmaydi (oddiy rollup yetarli)
    with SessionLocal() as db:
        assert historian.mark_dirty(db, sid, now - timedelta(minutes=30), now - timedelta(minutes=10)) == 0
        assert historian.mark_dirty(db, sid, now - timedelta(days=3), now - timedelta(days=3)) == 3
        db.rollback()
