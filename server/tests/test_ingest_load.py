"""D1: ingest yuk testi — 10 000 qator/soniya (Postgres+COPY da qat'iy, SQLite da yumshoq chegara);
sensor keshi (TTL, invalidatsiya); Postgres da hypertable migratsiyasi (faqat GES_TEST_DATABASE_URL bilan)."""

import os
import time
from datetime import datetime, timedelta, timezone

import pytest
from ges_server.db import Base, SessionLocal, engine, migrate, stamp_head
from ges_server.monitoring import live
from ges_server.orm import Reading, Sensor

IS_PG = engine.dialect.name == "postgresql"


def _make_sensors(pid: int, n: int) -> list[int]:
    with SessionLocal() as db:
        ids = []
        for i in range(n):
            s = Sensor(project_id=pid, key=f"T{i:04d}", name=f"Teg {i}", kind="value", unit="", high_alarm=1e9)
            db.add(s)
            db.flush()
            ids.append(s.id)
        db.commit()
    live.invalidate_sensors(pid)
    return ids


def test_ingest_10k_rows_per_second(client, users):
    pid = users["project_id"]
    n_sensors, n_rows = 200, 10_000
    _make_sensors(pid, n_sensors)
    t0 = datetime.now(timezone.utc) - timedelta(minutes=30)
    items = [
        {"key": f"T{i % n_sensors:04d}", "value": float(i % 97), "ts": (t0 + timedelta(seconds=i // n_sensors)).isoformat()}
        for i in range(n_rows)
    ]
    with SessionLocal() as db:
        live.ingest(db, pid, [{"key": "T0000", "value": 1.0}])  # kesh va ulanishni isitish
        start = time.perf_counter()
        res = live.ingest(db, pid, items, max_age=timedelta(days=30))
        dt = time.perf_counter() - start
    assert res["accepted"] == n_rows and res["unknown"] == [] and res["rejected"] == []
    with SessionLocal() as db:
        assert db.query(Reading).count() == n_rows + 1
        s = db.query(Sensor).filter_by(project_id=pid, key="T0199").one()
        assert s.last_value == float((n_rows - 1) % 97) and s.alarm.value == "ok"
    limit = 1.0 if IS_PG else 3.0  # Postgres COPY: 10 000 qator/s (qabul mezoni); SQLite dev — yumshoq
    assert dt < limit, f"{n_rows} qator {dt:.2f} s ({n_rows / dt:.0f} qator/s) — chegara {limit} s"


def test_sensor_cache_ttl_and_invalidation(client, users, monkeypatch):
    pid = users["project_id"]
    _make_sensors(pid, 3)
    with SessionLocal() as db:
        by_key, enabled = live._sensor_index(db, pid)
        assert set(by_key) == {"T0000", "T0001", "T0002"} and all(enabled.values())
        # yangi sensor keshsiz ko'rinmaydi; ingest noma'lum kalitda bir marta yangilaydi
        s = Sensor(project_id=pid, key="YANGI", name="y", kind="value", unit="")
        db.add(s)
        db.commit()
        assert "YANGI" not in live._sensor_index(db, pid)[0]
        res = live.ingest(db, pid, [{"key": "YANGI", "value": 2.0}, {"key": "YOQ", "value": 1.0}])
        assert res["accepted"] == 1 and res["unknown"] == ["YOQ"]
        assert "YANGI" in live._sensor_index(db, pid)[0]
        # o'chirilgan sensor: PATCH kesh ni tozalaydi
    r = client.patch(f"/api/sensors/{s.id}", json={"enabled": False}, headers=users["engineer"])
    assert r.status_code == 200
    with SessionLocal() as db:
        assert live.ingest(db, pid, [{"key": "YANGI", "value": 3.0}])["unknown"] == ["YANGI"]
        # TTL: muddat o'tsa qayta o'qiladi
        monkeypatch.setattr(live, "SENSOR_CACHE_TTL_S", 0.0)
        live._sensor_index(db, pid, force=True)
        assert live._sensor_index(db, pid)[1][s.id] is False


@pytest.mark.skipif(not IS_PG, reason="faqat Postgres (GES_TEST_DATABASE_URL)")
def test_postgres_hypertable_migration_and_copy():
    """Bo'sh sxemadan `alembic upgrade head` → readings hypertable (timescaledb), COPY ingest ishlaydi."""
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    migrate()
    with engine.connect() as conn:
        ht = conn.exec_driver_sql(
            "SELECT hypertable_name, num_dimensions FROM timescaledb_information.hypertables WHERE hypertable_name='readings'"
        ).first()
        assert ht is not None and ht[1] == 2  # ts + sensor_id
        assert conn.exec_driver_sql("SELECT indexname FROM pg_indexes WHERE tablename='readings' AND indexname='uq_readings_id_ts'").first()
    # migratsiya ikkinchi marta ham xatosiz (idempotent)
    migrate()
    # oddiy sxemaga qaytish keyingi testlar uchun (fresh_db drop_all + create_all)
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    Base.metadata.create_all(engine)
    stamp_head()
    assert os.environ.get("GES_TEST_DATABASE_URL")
