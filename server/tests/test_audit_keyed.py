"""AUTH-05: kalitli (HMAC) versiyalangan audit zanjiri, eski v1 qatorlar tekshiriladi, sxemani pasaytirish
aniqlanadi, yozish xatosi baland ovozda (log, metrika, bildirishnoma); Postgres: advisory lock va trigger."""

import importlib.util
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest
from ges_server import audit
from ges_server.db import SessionLocal, engine
from ges_server.orm import AuditLog, Notification
from sqlalchemy import insert, text

PG = engine.dialect.name == "postgresql"


def _entry(action="t.x", **kw):
    return {
        "created_at": datetime.now(timezone.utc),
        "user_id": None,
        "action": action,
        "target_type": "t",
        "target_id": None,
        "project_id": None,
        "detail": kw,
    }


def _wipe():
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM audit_log"))


def test_new_rows_are_hmac_v2_and_verify(client, admin):
    r = client.get("/api/audit/verify", headers=admin).json()
    assert r["ok"] and r["keyed"] and r["schemes"]["v1"] == 0 and r["schemes"]["v2"] == r["checked"] > 0
    with SessionLocal() as db:
        row = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        assert row.hash_alg == "v2"
        # kalitsiz sha256 bilan mos kelmaydi
        assert row.row_hash != audit.row_hash(
            created_at=row.created_at, user_id=row.user_id, action=row.action, target_type=row.target_type,
            target_id=row.target_id, project_id=row.project_id, detail=row.detail, prev_hash=row.prev_hash, alg="v1",
        )


def test_legacy_v1_prefix_then_v2_verifies():
    _wipe()
    prev = ""
    with engine.begin() as conn:
        for i in range(3):
            e = _entry("legacy", i=i)
            h = audit.row_hash(prev_hash=prev, **e)  # v1 (eski qatorlar, hash_alg NULL)
            conn.execute(insert(AuditLog.__table__).values(**e, prev_hash=prev, row_hash=h))
            prev = h
    assert audit.write_now([_entry("new", i=1), _entry("new", i=2)])
    with SessionLocal() as db:
        r = audit.verify_chain(db)
    assert r["ok"] and r["schemes"] == {"v1": 3, "v2": 2} and r["keyed"]


def test_forged_rows_without_key_detected():
    """Kalitsiz hujumchi: v2 qatorni o'zgartirib, sha256 (v1) bilan zanjirni qayta hisoblaydi — aniqlanadi."""
    _wipe()
    assert audit.write_now([_entry("a", n=1), _entry("b", n=2), _entry("c", n=3)])
    with SessionLocal() as db:
        rows = db.query(AuditLog).order_by(AuditLog.id).all()
        victim = rows[1]
        prev = rows[0].row_hash
        for r in rows[1:]:
            d = {"n": 999} if r.id == victim.id else r.detail
            h = audit.row_hash(created_at=r.created_at, user_id=r.user_id, action=r.action, target_type=r.target_type,
                               target_id=r.target_id, project_id=r.project_id, detail=d, prev_hash=prev, alg="v1")
            db.execute(text("UPDATE audit_log SET detail = :d, prev_hash = :p, row_hash = :h, hash_alg = NULL WHERE id = :i"),
                       {"d": '{"n": 999}' if r.id == victim.id else __import__("json").dumps(r.detail), "p": prev, "h": h, "i": r.id})
            prev = h
        db.commit()
        rep = audit.verify_chain(db)
    assert rep["ok"] is False and rep["first_bad_id"] == victim.id


def test_wrong_key_detected(monkeypatch):
    _wipe()
    assert audit.write_now([_entry("a"), _entry("b")])
    monkeypatch.setattr(audit, "_KEY", b"boshqa-kalit")
    with SessionLocal() as db:
        rep = audit.verify_chain(db)
    assert rep["ok"] is False


def test_write_failure_is_loud(client, admin, monkeypatch, caplog):
    before = audit.STATS["write_failures"]
    monkeypatch.setattr(audit, "_last_alarm", 0.0)

    class Boom:
        dialect = engine.dialect

        def begin(self):
            raise RuntimeError("disk to'la")

    monkeypatch.setattr(audit, "engine", Boom())
    with caplog.at_level(logging.CRITICAL, logger="ges_server.audit"):
        assert audit.write_now([_entry("lost", secret_marker="XYZ")]) is False
    assert audit.STATS["write_failures"] == before + 1 and "disk to'la" in audit.STATS["last_error"]
    assert any("AUDIT YOZILMADI" in r.message and "XYZ" in r.message for r in caplog.records)
    with SessionLocal() as db:
        assert db.query(Notification).filter_by(kind="system", title="Audit jurnaliga yozib bo'lmadi").count() >= 1
    monkeypatch.undo()
    st = client.get("/api/audit/status", headers=admin).json()
    assert st["write_failures"] >= before + 1 and st["hash_alg"] == "v2"


def test_concurrent_writers_single_chain():
    """Bir jarayondagi parallel yozuvchilar (va Postgres da advisory lock bilan jarayonlar) zanjirni tarmoqlamaydi."""
    _wipe()
    ts = [threading.Thread(target=audit.write_now, args=([_entry("p", i=i)],)) for i in range(20)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    with SessionLocal() as db:
        rep = audit.verify_chain(db)
    assert rep["ok"] and rep["checked"] == 20


@pytest.mark.skipif(not PG, reason="Postgres kerak (GES_TEST_DATABASE_URL)")
def test_pg_advisory_lock_and_trigger():
    spec = importlib.util.spec_from_file_location(
        "m0039", Path(audit.__file__).parent / "migrations" / "versions" / "0039_audit_keyed_immutable.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert audit.write_now([_entry("x")])
    with engine.begin() as conn:
        mod.create_pg_trigger(conn)
    try:
        with pytest.raises(Exception, match="faqat qo"):
            with engine.begin() as conn:
                conn.execute(text("UPDATE audit_log SET action = 'buzildi'"))
        with pytest.raises(Exception, match="faqat qo"):
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM audit_log"))
        assert audit.write_now([_entry("y")])  # INSERT ruxsat
        # advisory lock: boshqa ulanish ushlab tursa yozuvchi kutadi
        held = engine.connect()
        tx = held.begin()
        held.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": audit.AUDIT_LOCK_KEY})
        done = threading.Event()
        t = threading.Thread(target=lambda: (audit.write_now([_entry("z")]), done.set()))
        t.start()
        assert not done.wait(1.0)
        tx.rollback()
        held.close()
        assert done.wait(10)
    finally:
        with engine.begin() as conn:
            mod.drop_pg_trigger(conn)
